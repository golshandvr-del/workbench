#!/usr/bin/env python3
"""Real end-to-end check of the GitHub chain against a SEPARATE test repository (roadmap 1.14.13).

Never targets the main repository. Drives the real desktop services (no fakes):

1. clone the sandbox repo, create a unique ``e2e/<id>`` work branch and push it;
2. change a file + add a sensitive file; run the Sync & Build orchestrator:
   preflight → review (sensitive blocked) → commit → push → wait for the run of
   exactly that commit → download + SHA-256 verify + safe-extract the artifact →
   check the artifact's ``commit.txt`` equals the pushed SHA;
3. idempotency: commit/push again return the recorded SHA without a new commit;
4. stale plan: a concurrent push to the remote makes the next commit refuse;
5. manual ``workflow_dispatch`` with a confirmed run ID;
6. no-leak: the token never appears in records, events, Git config or the clone URL;
7. cleanup: the work branch is deleted.

Usage::

    AIWB_E2E_TOKEN=... python tools/e2e_github_sandbox.py [--repo owner/name] [--timeout 900]

Prints a JSON summary; exit 0 only when every check passes.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPO = "golshandvr-del/aiwb-e2e-sandbox"
MAIN_REPO = "golshandvr-del/workbench"
WF = ".github/workflows/e2e.yml"


def git(cwd: Path, *args: str, env: dict | None = None) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True, env=env).stdout.strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=DEFAULT_REPO)
    ap.add_argument("--timeout", type=float, default=900)
    args = ap.parse_args()
    if args.repo.casefold() == MAIN_REPO.casefold():
        print("refusing to run E2E against the main repository")
        return 2
    token = os.environ.get("AIWB_E2E_TOKEN", "")
    if not token:
        print("AIWB_E2E_TOKEN is not set")
        return 2
    sys.path.insert(0, str(REPO_ROOT / "apps/desktop/src"))
    from aiwb.git import GitService, GitSyncService
    from aiwb.github import orchestrator as orc
    from aiwb.github.actions import GitHubActionsService, RepositoryOperationGuard
    from aiwb.github.api_client import GitHubApiClient
    from aiwb.github.artifacts import GitHubDispatchService, safe_extract_zip

    owner, repo = args.repo.split("/", 1)
    results: dict[str, str] = {}
    events: list[str] = []
    ok = True

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal ok
        results[name] = ("PASS " if cond else "FAIL ") + detail
        print(("PASS " if cond else "FAIL ") + name + (": " + detail if detail else ""), flush=True)
        ok = ok and cond

    client = GitHubApiClient()
    actions = GitHubActionsService(client)
    dispatch = GitHubDispatchService(actions)
    repo_info = json.loads(client._request_response(token, f"/repos/{owner}/{repo}", endpoint_label="repo").body)
    repo_id = int(repo_info["id"])
    branch = "e2e/" + uuid.uuid4().hex[:10]

    # Git authenticates through a one-shot credential helper reading an env var:
    # the token is never in the remote URL, .git/config or process arguments.
    env = dict(os.environ, AIWB_E2E_TOKEN=token, GIT_TERMINAL_PROMPT="0")
    helper = "!f() { echo username=x-access-token; echo \"password=$AIWB_E2E_TOKEN\"; }; f"
    os.environ["GIT_CONFIG_COUNT"] = "1"
    os.environ["GIT_CONFIG_KEY_0"] = "credential.helper"
    os.environ["GIT_CONFIG_VALUE_0"] = helper
    env.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="credential.helper", GIT_CONFIG_VALUE_0=helper)

    with tempfile.TemporaryDirectory(prefix="aiwb e2e ü ") as t:  # space + Unicode in the path
        base = Path(t)
        work = base / "work tree"
        url = f"https://github.com/{owner}/{repo}.git"
        git(base, "clone", "-q", url, str(work), env=env)
        git(work, "config", "user.email", "e2e@example.invalid")
        git(work, "config", "user.name", "AIWB E2E")
        git(work, "switch", "-q", "-c", branch)
        (work / "data").mkdir(exist_ok=True)
        (work / "data" / "seed.txt").write_text("seed\n", encoding="utf-8")
        git(work, "add", "data/seed.txt")
        git(work, "commit", "-q", "-m", "e2e: seed")
        git(work, "push", "-q", "-u", "origin", branch, env=env)
        # the seed push triggers a run too; we must NOT confuse it with ours.
        seed_sha = git(work, "rev-parse", "HEAD")
        try:
            (work / "data" / "seed.txt").write_text("changed " + branch + "\n", encoding="utf-8")
            (work / "secret.env").write_text("API_KEY=nope\n", encoding="utf-8")
            store = orc.RecordStore(base / "ops.json")
            o = orc.SyncBuildOrchestrator(
                sync=GitSyncService(GitService()), actions=actions, dispatch=dispatch, git_root=work,
                project_subpath="", owner=owner, repo=repo, repository_id=repo_id, branch=branch,
                workflow_file=WF, artifact_pattern="e2e-*", get_token=lambda: token, store=store,
                is_sensitive=lambda p: p.endswith(".env"), guard=RepositoryOperationGuard())
            o.subscribe(lambda s, m: events.append(f"{s}: {m}"))
            check("lock", o.acquire())
            res = o.check()
            check("preflight", res.ok, "; ".join(f"{c.name}={'ok' if c.ok else c.detail}" for c in res.checks))
            items = {i.path: i for i in res.items}
            check("review_sensitive_blocked", items.get("secret.env") is not None and items["secret.env"].blocked)
            try:
                o.commit(["secret.env"], "should fail")
                check("commit_refuses_sensitive", False)
            except orc.OrchestratorError:
                check("commit_refuses_sensitive", True)
            sha = o.commit(["data/seed.txt"], "e2e change")
            check("commit", len(sha) == 40, sha)
            check("idempotent_commit", o.commit(["data/seed.txt"], "again") == sha and git(work, "rev-parse", "HEAD") == sha)
            o.push()
            check("push", git(work, "ls-remote", "origin", "refs/heads/" + branch, env=env).split()[0] == sha)
            o.push()
            check("idempotent_push", o.git.pushed)
            run = o.wait_for_build(timeout=args.timeout, interval=10)
            check("exact_run", run is not None and run.head_sha == sha and run.head_sha != seed_sha,
                  f"run={getattr(run, 'run_id', None)}")
            check("build_passed", o.state == orc.BUILD_PASSED, o.state)
            dl = base / "downloads ü"
            arts = o.download_artifacts(dl)
            check("artifact_verified", bool(arts) and all(a["verification"] == "matched" for a in arts),
                  ",".join(f"{a['name']}:{a['verification']}" for a in arts))
            out = base / "extracted"
            safe_extract_zip(Path(arts[0]["path"]), out)
            commit_txt = next(out.rglob("commit.txt")).read_text().strip()
            check("artifact_content_is_this_commit", commit_txt == sha, commit_txt[:12])
            meta = orc.build_metadata(store.get(o.operation_id) or {}, repository_id=repo_id)
            check("build_metadata", bool(meta) and meta["commit_sha"] == sha and meta["run_id"] == run.run_id)
            o.release()

            # stale plan: someone else pushes to the branch after our review
            other = base / "other"
            git(base, "clone", "-q", "-b", branch, url, str(other), env=env)
            git(other, "config", "user.email", "o@example.invalid"); git(other, "config", "user.name", "Other")
            (other / "data" / "other.txt").write_text("x\n")
            git(other, "add", "."); git(other, "commit", "-q", "-m", "concurrent [skip ci]")
            (work / "data" / "seed.txt").write_text("third\n")
            o2 = orc.SyncBuildOrchestrator(
                sync=GitSyncService(GitService()), actions=actions, dispatch=dispatch, git_root=work,
                project_subpath="", owner=owner, repo=repo, repository_id=repo_id, branch=branch,
                workflow_file=WF, artifact_pattern="", get_token=lambda: token, store=store,
                is_sensitive=lambda p: p.endswith(".env"), guard=RepositoryOperationGuard())
            o2.acquire()
            r2 = o2.check()
            git(other, "push", "-q", "origin", branch, env=env)
            head_before = git(work, "rev-parse", "HEAD")
            try:
                o2.commit(["data/seed.txt"], "stale")
                check("stale_plan_refused", False, "committed on a stale plan")
            except orc.OrchestratorError:
                check("stale_plan_refused", git(work, "rev-parse", "HEAD") == head_before and r2.ok)
            o2.release()

            # manual dispatch with a confirmed run ID
            wf = next(w for w in actions.list_workflows(token, owner, repo, ref=branch) if w.path == WF)
            form = dispatch.dispatch_form(token, owner, repo, wf, ref=branch)
            known = {r.run_id for r in actions.list_runs(token, owner, repo, workflow_id=wf.workflow_id, branch=branch, per_page=20)}
            d = dispatch.dispatch(token, owner, repo, wf, ref=branch, inputs={"label": "e2e"}, form=form)
            for _ in range(20):
                if d.state == "confirmed":
                    break
                time.sleep(5)
                d = dispatch.find_dispatched_run(token, owner, repo, d, known_run_ids=known)
            check("dispatch_confirmed", d.state == "confirmed" and bool(d.run_id), str(d.run_id))
            if d.run_id:
                try:
                    run_obj = next(r for r in actions.list_runs(token, owner, repo, workflow_id=wf.workflow_id, branch=branch, per_page=20) if r.run_id == d.run_id)
                    if not run_obj.is_finished:
                        actions.cancel_run(token, owner, repo, run_obj, confirmed=True)
                except Exception:
                    pass

            # no token anywhere we persist or show
            blob = (base / "ops.json").read_text(encoding="utf-8") + "\n".join(events)
            blob += (work / ".git" / "config").read_text(encoding="utf-8")
            check("no_token_leak", token not in blob and "x-access-token:" not in blob)
        finally:
            try:
                git(work, "push", "-q", "origin", "--delete", branch, env=env)
                results["cleanup"] = "PASS branch deleted"
            except subprocess.CalledProcessError:
                results["cleanup"] = "WARN branch not deleted"
    print(json.dumps({"repo": args.repo, "branch": branch, "ok": ok, "results": results}, indent=2, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
