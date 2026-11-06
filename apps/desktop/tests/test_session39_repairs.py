"""Regression tests for the session-39 repairs: BF-096/097 (Git sync + Sync & Build), BF-101/103 (Build Center
dialogs), BF-107 (paste box ZIP warnings), BF-036/037/038/041 (guided loop), BF-058/059 (next action, attention),
BF-018/020/034/022 (publisher, archive, bundle), BF-025/029 (process runner), BF-087/088 (analysis)."""
from __future__ import annotations

import http.client
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import tkinter as tk
import unittest
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
sys.path.insert(0, str(HERE))

import AI_Workbench as wb  # noqa: E402
import test_closeout as tc  # noqa: E402
import test_orchestrator as to  # noqa: E402
import test_v2_guide as tg  # noqa: E402
from aiwb import dependency_analysis, semantic_diff  # noqa: E402
from aiwb.git import GitService  # noqa: E402
from aiwb.git import sync as gs  # noqa: E402
from aiwb.v2 import ModelError, V2Project, bundle, closeout  # noqa: E402
from aiwb.v2.controller import ProjectsController  # noqa: E402
from aiwb.v2.dashboard import attention_queue  # noqa: E402
from aiwb.v2.guide import Guide  # noqa: E402
from aiwb.v2.next_action import compute_next_actions  # noqa: E402
from aiwb.v2.publisher import ApiResult, GitHubStateClient, PublishError, StatePublisher  # noqa: E402
from aiwb.workspace.controller import WorkspaceController  # noqa: E402


def git(cwd: Path, *args: str) -> str:
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@e",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@e")
    r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, env=env, check=False)
    if r.returncode != 0:
        raise AssertionError(f"git {args}: {r.stderr}")
    return r.stdout.strip()


def tk_root():
    try:
        root = tk.Tk()
    except tk.TclError:
        return None
    root.withdraw()
    return root


def pump(root: tk.Misc, seconds: float, until=None) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        root.update()
        if until is not None and until():
            return True
        time.sleep(0.01)
    return until() if until is not None else True


# ---------------------------------------------------------------------------------------------- BF-096
class GitSyncBranchTargetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name).resolve()
        self.remote, self.a, self.b = base / "remote.git", base / "a", base / "b"
        git(base, "init", "-q", "--bare", "-b", "main", str(self.remote))
        git(base, "clone", "-q", str(self.remote), str(self.a))
        for repo in (self.a,):
            for k, v in (("user.name", "t"), ("user.email", "t@e"), ("commit.gpgsign", "false")):
                git(repo, "config", k, v)
        (self.a / "base.txt").write_text("base\n")
        git(self.a, "add", "base.txt")
        git(self.a, "commit", "-q", "-m", "base")
        git(self.a, "push", "-q", "origin", "HEAD:refs/heads/main")
        self.svc = gs.GitSyncService(GitService())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _commit(self, repo: Path, name: str) -> None:
        (repo / name).write_text(name + "\n")
        git(repo, "add", name)
        git(repo, "commit", "-q", "-m", name)

    def test_bf096_branch_pushed_without_upstream_can_be_pushed_again(self) -> None:
        git(self.a, "switch", "-q", "-c", "feat2")
        self._commit(self.a, "one.txt")
        git(self.a, "push", "-q", "origin", "feat2")          # no -u: the very common case
        self._commit(self.a, "two.txt")
        plan = self.svc.build_plan(self.a)
        self.assertEqual(plan.state, gs.NO_UPSTREAM)
        self.assertEqual(plan.remote_sha, git(self.a, "rev-parse", "origin/feat2"))
        res = self.svc.safe_push(self.a, plan)
        self.assertTrue(res.ok, res.message)
        self.assertEqual(git(self.a, "rev-parse", "HEAD"), git(self.a, "ls-remote", "origin", "refs/heads/feat2").split()[0])
        self.assertEqual(git(self.a, "rev-parse", "--abbrev-ref", "feat2@{upstream}"), "origin/feat2")

    def test_bf096_branch_tracking_main_is_pushed_to_its_own_ref_and_stops_being_ahead(self) -> None:
        git(self.a, "switch", "-q", "-c", "feat3", "origin/main")
        self._commit(self.a, "x.txt")
        plan = self.svc.build_plan(self.a)
        self.assertEqual(plan.upstream, "origin/main")
        self.assertEqual(plan.remote_sha, "", "the guard must watch origin/feat3, not main")
        res = self.svc.safe_push(self.a, plan)
        self.assertTrue(res.ok, res.message)
        after = self.svc.build_plan(self.a)
        self.assertEqual(after.upstream, "origin/feat3")
        self.assertEqual(after.state, gs.CLEAN)
        self.assertNotIn("push", after.allowed_actions)

    def test_bf096_existing_remote_branch_with_other_commits_is_refused_honestly(self) -> None:
        git(self.a, "switch", "-q", "-c", "feat4")
        self._commit(self.a, "a1.txt")
        base = Path(self.tmp.name).resolve()
        git(base, "clone", "-q", "-b", "main", str(self.remote), str(self.b))
        for k, v in (("user.name", "t"), ("user.email", "t@e"), ("commit.gpgsign", "false")):
            git(self.b, "config", k, v)
        git(self.b, "switch", "-q", "-c", "feat4")
        self._commit(self.b, "b1.txt")
        git(self.b, "push", "-q", "origin", "feat4")
        plan = self.svc.build_plan(self.a)
        res = self.svc.safe_push(self.a, plan)
        self.assertFalse(res.ok)
        self.assertIn("already exists and has different commits", res.message)


# ---------------------------------------------------------------------------------------------- BF-096 / BF-097 (orchestrator)
class OrchestratorBranchTests(unittest.TestCase):
    setUp = to.OrchestratorTests.setUp
    tearDown = to.OrchestratorTests.tearDown
    make = to.OrchestratorTests.make

    def test_bf096_bound_branch_that_exists_remotely_without_upstream_pushes(self) -> None:
        git(self.work, "switch", "-q", "-c", "w2")
        git(self.work, "push", "-q", "origin", "w2")          # no -u
        (self.work / "a.txt").write_text("2\n")
        o = self.make(branch="w2")
        self.assertTrue(o.check().ok)
        o.commit(["a.txt"], "x")
        o.push()
        self.assertTrue(o.git.pushed)

    def test_bf097_after_pull_rebase_the_new_head_is_used_instead_of_looping(self) -> None:
        (self.work / "a.txt").write_text("2\n")
        o = self.make()
        o.check()
        old = o.commit(["a.txt"], "x")
        other = Path(self.tmp.name) / "other"
        git(Path(self.tmp.name), "clone", "-q", "-b", "work", str(self.remote), str(other))
        (other / "r.txt").write_text("r\n")
        git(other, "add", "r.txt")
        git(other, "-c", "user.email=x@x", "-c", "user.name=x", "commit", "-q", "-m", "remote")
        git(other, "push", "-q", "origin", "work")
        with self.assertRaises(to.orc.OrchestratorError) as cm:
            o.push()
        self.assertIn("moved", str(cm.exception))
        git(self.work, "pull", "--rebase", "-q", "origin", "work")     # what the window tells the user to do
        new_head = git(self.work, "rev-parse", "HEAD")
        self.assertNotEqual(new_head, old)
        o.release()
        o2 = self.make(operation_id=o.operation_id)
        self.assertTrue(o2.resumed)
        self.assertTrue(o2.check().ok)
        self.assertEqual(o2.git.commit_sha, new_head)
        o2.push()
        self.assertTrue(o2.git.pushed)


# ---------------------------------------------------------------------------------------------- BF-101 / BF-103 / BF-107 (Tk)
class DispatchDialogRefTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tk_root()
        if self.root is None:
            self.skipTest("no display")

    def tearDown(self) -> None:
        self.root.destroy()

    def test_bf101_changing_the_ref_reloads_the_schema_and_submits_the_new_form(self) -> None:
        from aiwb.github import artifacts as ar
        from aiwb.github.actions import WorkflowInfo
        from aiwb.github.build_center_dialogs import DispatchDialog
        forms = {"main": ar.DispatchForm(True, (ar.DispatchInput("channel", "choice", True, "beta", "", ("beta", "stable")),)),
                 "release": ar.DispatchForm(True, (ar.DispatchInput("channel", "choice", True, "stable", "", ("beta", "stable")),
                                                   ar.DispatchInput("version", "string", True, "1.0", "", ())))}
        asked: list[str] = []
        sent: list[tuple] = []

        class Svc:
            def dispatch_form(self, token, owner, repo, workflow, *, ref):
                asked.append(ref)
                return forms[ref]

            def dispatch(self, token, owner, repo, workflow, *, ref, inputs, form):
                sent.append((ref, dict(inputs), form))
                return ar.DispatchResult("confirmed", 1, ref, 0.0, run_id=5)

        results: list = []
        wf = WorkflowInfo(1, "CI", ".github/workflows/ci.yml", "active", "")
        d = DispatchDialog(self.root, svc=Svc(), owner="o", repo="r", workflow=wf, ref="main", get_token=lambda: "T",
                           known_run_ids=lambda: set(), on_result=results.append)
        self.assertTrue(pump(self.root, 5, lambda: d.form is not None and d.form_ref == "main"))
        d.ref_var.set("release")
        self.assertIsNone(d.form, "a form of another ref must not stay submittable")
        self.assertEqual(str(d.btn_run.cget("state")), "disabled")
        self.assertTrue(pump(self.root, 6, lambda: d.form is not None and d.form_ref == "release"))
        self.assertEqual(asked[-1], "release")
        self.assertEqual(set(d.vars), {"channel", "version"})
        d.submit()
        self.assertTrue(pump(self.root, 5, lambda: bool(results)))
        self.assertEqual(sent[0][0], "release")
        self.assertEqual(sent[0][1]["channel"], "stable")
        self.assertEqual(sent[0][1]["version"], "1.0")
        d.close()


class BuildCenterJobsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tk_root()
        if self.root is None:
            self.skipTest("no display")

    def tearDown(self) -> None:
        self.root.destroy()

    def test_bf103_job_results_of_a_previous_run_are_discarded(self) -> None:
        from aiwb.github import actions as ga
        from aiwb.github.build_center import BuildCenterWindow
        ts = "2026-01-01T00:00:00Z"
        runs = tuple(ga.WorkflowRun(i, 7, "CI", "push", "completed", "success", "feat", "a" * 40, i, 1, ts, ts, ts,
                                    f"https://github.com/o/r/actions/runs/{i}") for i in (1, 2))

        class Svc:
            client = None

            def list_workflows(self, token, owner, repo, *, ref=None):
                return ()

            def list_runs(self, token, owner, repo, **kw):
                return runs

            def list_jobs(self, token, owner, repo, run_id):
                return ()

        win = BuildCenterWindow(self.root, owner="o", repo="r", branch="feat", get_token=lambda: "T", service=Svc(),
                                policy=ga.PollPolicy(min_interval=0.0), open_url=lambda u: None)
        try:
            self.assertTrue(pump(self.root, 5, lambda: len(win.run_tree.get_children()) == 2))
            calls: list[tuple] = []

            def recorder(label, work, done, *, poll=False):
                calls.append((label, done))
                win.busy = True

            win._run = recorder
            win.run_tree.selection_set("1:1")
            pump(self.root, 0.2)
            win.run_tree.selection_set("2:1")
            pump(self.root, 0.2)
            self.assertEqual(len(calls), 1, "the second selection waits for the running fetch")
            job_a = ga.WorkflowJob(11, "JOB FOR A", "completed", "failure", "", "", "https://github.com/o/r/actions/runs/1/job/11")
            win.busy = False
            calls[0][1]((job_a,))                                  # the slow answer for run 1 arrives now
            self.assertEqual(win.job_tree.get_children(), (), "run 1's jobs must not show under run 2")
            self.assertEqual(win.jobs, ())
            self.assertEqual(len(calls), 2, "the latest selection (run 2) is fetched next")
            self.assertIn("2", calls[1][0])
        finally:
            win.close()


class PasteBoxZipWarningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tk_root()
        if self.root is None:
            self.skipTest("no display")
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.root.destroy()
        self.tmp.cleanup()

    def test_bf107_pending_refresh_does_not_erase_zip_skipped_warnings(self) -> None:
        from aiwb.ui.paste_box import PastePanel
        z = Path(self.tmp.name) / "answer.zip"
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("src/a.py", "print(1)\n")
            zf.writestr("../secret.txt", "nope")
        panel = PastePanel(self.root)
        panel.pack()
        panel.box.insert("1.0", "previous answer")
        self.root.update()
        self.assertIsNotNone(panel._after, "a debounce is pending")
        pv = panel.load_zip(str(z))
        self.assertTrue(any("secret.txt" in p for p in pv.problems))
        immediate = panel.status_var.get()
        self.assertIn("skipped", immediate)
        pump(self.root, 0.7)
        self.assertIn("skipped", panel.status_var.get())
        self.assertTrue(any("secret.txt" in p for p in panel.preview.problems), panel.preview.problems)
        panel.set_text("now my own text")                            # editing the text drops the ZIP warnings
        self.assertFalse(any("secret.txt" in p for p in panel.preview.problems))


# ---------------------------------------------------------------------------------------------- guided loop
class GuidedLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.c = ProjectsController(Path(self.tmp.name), make_pipeline=wb.make_inbox_pipeline)
        self.g = Guide(self.c)
        self.p = self.c.project

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _task(self) -> str:
        return self.p.tasks.create({"title": "Calc", "objective": "calc", "owner_agent_id": "agent-implementer",
                                    "allowed_paths": ["src/x/"], "acceptance_criteria": ["works"]}, status="ready")["task_id"]

    def test_bf036_release_with_a_missing_run_id_changes_nothing_and_default_tag_has_one_v(self) -> None:
        tid = self._task()
        m = self.p.timeline.create_milestone({"title": "M", "task_ids": [tid]})
        self.p.timeline.accept_milestone(m["milestone_id"], force=True)
        v = self.p.timeline.propose_version({"label": "v1.0.0", "milestone_ids": [m["milestone_id"]], "task_ids": [tid]})
        key = f"version:{v['version_id']}"
        with self.assertRaises(ModelError):
            self.g.perform(key, "release", commit_sha="a" * 40, tag="", run_id="")
        self.assertEqual(self.p.timeline.versions()[0]["status"], "proposed", "no half-advanced version")
        self.g.perform(key, "release", commit_sha="a" * 40, tag="", run_id="run-9")
        done = self.p.timeline.versions()[0]
        self.assertEqual((done["status"], done["tag"]), ("released", "v1.0.0"))

    def test_bf037_accepting_a_failed_answer_does_not_promise_a_review_card(self) -> None:
        tid = self._task()
        h = self.c.start_task(tid)
        man = {"schema_version": "1.0", "handoff_id": h["handoff_id"], "task_id": tid, "task_revision": h["task_revision"],
               "attempt_id": h["attempt_id"], "outcome": "failed", "summary": "could not", "completed_items": [],
               "unresolved_items": ["everything"]}
        text = (f"AIWB_ATTEMPT_ID: {h['attempt_id']}\n"
                '<<<AIWB_FILE path="src/x/a.txt" action="write" body="raw">>>\nhalf\n<<<AIWB_END_FILE>>>\n'
                "<<<AIWB_HANDOFF>>>\n" + json.dumps(man) + "\n<<<AIWB_END_HANDOFF>>>\n")
        self.g.perform(f"handoff:{h['handoff_id']}", "paste", text=text)
        out = self.g.perform(f"handoff:{h['handoff_id']}", "accept_handoff", reason="keep the partial work")
        self.assertIn("failed attempt", out["message"])
        self.assertNotIn("review the task", out["message"])
        self.assertEqual(self.p.tasks.get(tid)["status"], "in_progress")

    def test_bf038_late_answer_for_a_dropped_prompt_is_not_reported_as_linked(self) -> None:
        tid = self._task()
        h1 = self.c.start_task(tid)
        self.c.resolve_handoff(h1["handoff_id"], False, "dropped")
        h2 = self.c.start_task(tid)
        r = self.c.route_answer(tg.answer_for(h1))
        self.assertEqual(r.kind, "rejected")
        self.assertIn("dropped", r.message)
        self.assertNotIn("Answer linked", r.message)
        self.assertIn("nothing was linked", r.message)
        self.assertIn(h2["handoff_id"], r.message)
        self.assertEqual(self.c.state()["handoffs"][h2["handoff_id"]]["status"], "prepared")

    def test_bf041_files_and_a_context_request_keep_the_request(self) -> None:
        from aiwb.intake.preview import preview
        tid = self._task()
        h = self.c.start_task(tid)
        req = {"schema_version": "1.0", "type": "AIWB_CONTEXT_REQUEST", "attempt_id": h["attempt_id"], "reason": "need it",
               "files": [{"path": "src/x/z.py"}]}
        text = tg.answer_for(h) + "<<<AIWB_CONTEXT_REQUEST>>>\n" + json.dumps(req) + "\n<<<AIWB_END_CONTEXT_REQUEST>>>\n"
        pv = preview(text)
        self.assertIn("context request", pv.line.lower())
        self.assertIn("Files", pv.line)
        r = self.c.route_answer(text)
        self.assertEqual(r.kind, "handoff")
        self.assertIn("also asked", r.message)
        rec = self.c.state()["handoffs"][h["handoff_id"]]
        self.assertTrue(rec.get("context_request"))
        self.assertTrue(any("also asked" in x for x in rec["unresolved_items"]))
        self.assertTrue(rec["staged_files"], "the delivery stays staged for review")


# ---------------------------------------------------------------------------------------------- next action / attention
class NextActionAttentionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ctl = ProjectsController(self.root, make_pipeline=wb.make_inbox_pipeline)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_bf058_no_second_planning_prompt_while_a_plan_or_decision_waits(self) -> None:
        st = self.ctl.state()
        self.assertIn("plan_project", [a["type"] for a in compute_next_actions(st)])
        st["proposals"]["PROP-0001"] = {"proposal_id": "PROP-0001", "status": "pending", "operations": [{}], "stale": False}
        types = [a["type"] for a in compute_next_actions(st)]
        self.assertNotIn("plan_project", types)
        self.assertIn("review_proposal", types)
        st["proposals"].clear()
        st["decisions"]["DEC-0001"] = {"decision_id": "DEC-0001", "status": "proposed", "title": "t", "affected_task_ids": []}
        self.assertNotIn("plan_project", [a["type"] for a in compute_next_actions(st)])

    def test_bf059_keys_name_the_event_and_trimming_keeps_the_newest(self) -> None:
        st = self.ctl.state()
        a = attention_queue(st, publish_paused="token expired")[0]["key"]
        b = attention_queue(st, publish_paused="repository not found")[0]["key"]
        self.assertNotEqual(a, b, "a new publish error must not stay muted by an old 'read' mark")
        wc = WorkspaceController(self.ctl)
        for i in range(599, -1, -1):                       # newest = smallest name: alphabetical trimming would drop it
            wc.mark_seen([f"k{i:03d}"])
        seen = wc.seen_keys()
        self.assertEqual(len(seen), 500)
        self.assertIn("k000", seen)
        self.assertNotIn("k599", seen)


# ---------------------------------------------------------------------------------------------- archive / publisher / bundle
class ArchiveOrderTests(unittest.TestCase):
    setUp = tc.CloseoutTests.setUp
    tearDown = tc.CloseoutTests.tearDown
    decide_complete = tc.CloseoutTests.decide_complete

    def test_bf020_bf034_failed_bundle_write_leaves_the_project_unarchived_and_retry_works(self) -> None:
        self.decide_complete()
        self.g.perform("closeout:announce", "announce")
        blocker = self.root / ".workbench" / "archive"
        blocker.parent.mkdir(parents=True, exist_ok=True)
        blocker.write_text("a file where the folder must go")
        with self.assertRaises(ModelError) as cm:
            self.g.perform("closeout:expand", "archive")
        self.assertIn("NOT archived", str(cm.exception))
        self.assertFalse(closeout.is_archived(self.c.state()))
        blocker.unlink()
        out = self.g.perform("closeout:expand", "archive")
        path = closeout.archive_path(self.root, self.c.state())
        self.assertTrue(path.is_file())
        self.assertIn(str(path), out["message"])
        self.assertTrue(closeout.is_archived(self.c.state()))
        with self.assertRaises(ModelError):
            closeout.archive(self.store, self.root)            # bundle present: really archived already
        path.unlink()                                            # lost afterwards (cleanup, antivirus ...)
        again = closeout.archive(self.store, self.root)
        self.assertEqual(again, path)
        self.assertTrue(path.is_file())


class PublisherRobustnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.p = V2Project(Path(self.tmp.name), "demo")
        self.p.open()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_bf018_odd_replies_are_publish_errors_not_bugs(self) -> None:
        def dropped(*_a):
            raise http.client.IncompleteRead(b"x")

        def html(*_a):
            raise json.JSONDecodeError("Expecting value", "<html>", 0)

        for tr in (dropped, html):
            with self.assertRaises(PublishError) as cm:
                GitHubStateClient("t", "o", "r", transport=tr).branch_head("aiwb-state")
            self.assertEqual(cm.exception.kind, "network")
        with self.assertRaises(PublishError):
            GitHubStateClient("t", "o", "r", transport=lambda *a: ApiResult(200, {}, {})).branch_head("aiwb-state")

    def test_bf018_tick_never_raises_and_records_the_error_with_backoff(self) -> None:
        class Broken(GitHubStateClient):
            def branch_head(self, branch):
                raise KeyError("boom")

        pub = StatePublisher(self.p.store, client_factory=lambda: Broken("t", "o", "r", transport=lambda *a: ApiResult(200, {}, {})))
        r = pub.tick(force=True)
        self.assertEqual(r["status"], "error")
        q = pub.queue()
        self.assertIn("KeyError", q["last_error"])
        self.assertEqual(q["attempts"], 1)
        self.assertGreater(q["next_try_at"], 0)


class BundleReadErrorTests(unittest.TestCase):
    def _bundle(self, **state_edits) -> dict:
        with tempfile.TemporaryDirectory() as d:
            p = V2Project(Path(d), "demo")
            p.open()
            st = p.store.load()
        st.update(state_edits)
        return bundle.export_bundle(st, name="demo")

    def test_bf022_plain_messages_for_damaged_bundles(self) -> None:
        with self.assertRaises(bundle.BundleError) as cm:
            bundle.read_bundle(b"\xe9\xff\xfe not utf8")
        self.assertIn("UTF-8", str(cm.exception))
        b = self._bundle()
        b["project"] = [1]
        with self.assertRaises(bundle.BundleError) as cm:
            bundle.read_bundle(b)
        self.assertIn("project", str(cm.exception))
        with self.assertRaises(bundle.BundleError) as cm:
            bundle.read_bundle(self._bundle(db_version="x"))
        self.assertIn("db_version", str(cm.exception))


# ---------------------------------------------------------------------------------------------- process runner
class ProcessRunnerTests(unittest.TestCase):
    def test_bf025_children_are_told_to_write_utf8(self) -> None:
        env = wb._utf8_child_env()
        self.assertEqual((env["PYTHONUTF8"], env["PYTHONIOENCODING"]), ("1", "utf-8"))
        with tempfile.TemporaryDirectory() as d:
            r = wb.run_argv_bounded([sys.executable, "-c", "print('سلام دنیا ✓')"], Path(d), timeout=30)
        self.assertEqual(r["exit_code"], 0, r)
        self.assertIn("سلام دنیا ✓", r["stdout"])

    def test_bf029_a_background_process_holding_the_pipe_does_not_hold_the_app(self) -> None:
        code = ("import subprocess, sys; subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(10)']); "
                "print('server started')")
        with tempfile.TemporaryDirectory() as d:
            t0 = time.monotonic()
            r = wb.run_argv_bounded([sys.executable, "-c", code], Path(d), timeout=30)
            took = time.monotonic() - t0
        self.assertLess(took, 8.0, f"returned after {took:.1f}s: still waiting for the grandchild")
        self.assertIn("server started", r["stdout"])
        self.assertTrue(r["background_process"])


# ---------------------------------------------------------------------------------------------- analysis
class AnalysisTests(unittest.TestCase):
    def test_bf087_large_file_is_not_reported_as_unchanged_or_as_a_syntax_error(self) -> None:
        before = "".join(f"def f{i}():\n    return {i}\n" for i in range(20000))
        after = before.replace("def f19999", "def g19999")
        self.assertGreater(len(before), semantic_diff.MAX_SEMANTIC_CHARS)
        rep = semantic_diff.analyze_semantic_diff("big.py", before, after)
        text = semantic_diff.format_semantic_report(rep)
        self.assertNotIn("SyntaxError", text)
        self.assertNotIn("no textual differences detected", text)
        self.assertIn("g19999", rep["unified_diff"])
        self.assertIn("too large", text)

    def test_bf088_relative_imports_resolve(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for rel, body in {"src/app/main.js": "import { x } from './util'\nimport y from '../lib/helper.js'\nimport z from './missing'\n",
                              "src/app/util.js": "export const x = 1\n", "src/lib/helper.js": "export default 2\n",
                              "src/app/a.c": '#include "b.h"\n#include "../../inc/c.h"\n', "src/app/b.h": "", "inc/c.h": ""}.items():
                f = root / rel
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(body)
            g = dependency_analysis.scan_dependency_graph(root)
            self.assertEqual(set(g["forward"]["src/app/main.js"]), {"src/app/util.js", "src/lib/helper.js"})
            self.assertEqual(set(g["forward"]["src/app/a.c"]), {"src/app/b.h", "inc/c.h"})
            self.assertEqual(g["unresolved"]["src/app/main.js"], ["./missing"])
            impact = dependency_analysis.analyze_project_impact(root, ["src/app/util.js"])
            self.assertIn("src/app/main.js", impact["direct_dependents"])


if __name__ == "__main__":
    unittest.main()
