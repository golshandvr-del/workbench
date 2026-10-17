"""GUI smoke for v1.14.4 binding migration, scope-aware Git status and review UI."""
from __future__ import annotations
import json
import os
import subprocess
import tempfile
import time
import tkinter as tk
import uuid
from pathlib import Path

with tempfile.TemporaryDirectory(prefix="aiwb-v1144-gui-") as temp:
    os.environ["LOCALAPPDATA"] = str(Path(temp) / "AppData")
    base = Path(temp).resolve()
    appdata = Path(os.environ["LOCALAPPDATA"]) / "AIWorkbench"
    appdata.mkdir(parents=True)
    repo_root = base / "monorepo"
    project = repo_root / "apps" / "desktop"
    project.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "main", str(repo_root)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo_root), "config", "user.name", "AIWB GUI Smoke"], check=True)
    subprocess.run(["git", "-C", str(repo_root), "config", "user.email", "gui-smoke@example.invalid"], check=True)
    (repo_root / "README.md").write_text("root readme\n", encoding="utf-8")
    (project / "app.py").write_text("print('initial')\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo_root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo_root), "commit", "-m", "initial"], check=True, capture_output=True)

    import AI_Workbench as wb
    from aiwb.github.api_client import GitHubRepository
    from aiwb.github import repository_binding as repository_binding_service
    from aiwb.github.repository_binding import make_binding

    wb.messagebox.showinfo = lambda *args, **kwargs: None
    wb.messagebox.showwarning = lambda *args, **kwargs: None
    wb.messagebox.showerror = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError(f"Unexpected GUI error: {args}"))
    wb.messagebox.askyesno = lambda *args, **kwargs: True

    account_id = str(uuid.uuid4())
    fake_repo = GitHubRepository(9001, "octocat", "monorepo", "octocat/monorepo", True, False, False,
                                 "main", None, "smoke", "https://github.com/octocat/monorepo", True)
    context = type("Context", (), {
        "project_path": project.resolve(), "local_git_root": repo_root.resolve(),
        "project_subpath": "apps/desktop", "current_branch": "main",
    })()
    row = make_binding(context, account_id, fake_repo).to_dict()
    row["schema_version"] = 1
    for key in ("workflow_file", "artifact_pattern", "release_channel", "last_known_remote_sha", "last_synced_at", "metadata_refreshed_at"):
        row.pop(key)
    original_settings = {"github_repository_bindings": [row], "projects": []}
    settings_path = appdata / "settings.json"
    settings_path.write_text(json.dumps(original_settings), encoding="utf-8")

    root = tk.Tk()
    app = wb.WorkbenchApp(root)
    root.update()
    assert tuple(map(int, wb.APP_VERSION.split("."))) >= (1, 14, 4), wb.APP_VERSION
    migrated = app.settings_data["github_repository_bindings"][0]
    assert migrated["schema_version"] == 2 and migrated["release_channel"] == "dev"
    backups = list(appdata.glob("settings.pre-v1.14.4-binding-migration-*.json.bak"))
    assert backups, "legacy settings were migrated without a backup"
    assert json.loads(backups[0].read_text(encoding="utf-8")) == original_settings
    persisted = json.loads(settings_path.read_text(encoding="utf-8"))
    assert persisted["github_repository_binding_schema_version"] == 2
    assert persisted["github_repository_bindings"][0]["schema_version"] == 2

    # Add changes both inside and outside the subpath after binding migration.
    (project / "new-file.py").write_text("print('inside')\n", encoding="utf-8")
    (repo_root / "outside.txt").write_text("must never be staged from the active subproject\n", encoding="utf-8")
    app.set_workspace(project)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        root.update()
        if not app.busy and app.project_version_baseline_state.get(str(project.resolve())) in {"ready", "failed", None}:
            if "Branch:" in app.git_branch_var.get() and app.git_tree.get_children(""):
                break
        time.sleep(0.01)
    app.refresh_git(silent=False)
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        root.update()
        if not app.busy:
            break
        time.sleep(0.01)
    displayed = [str(app.git_tree.item(iid, "text")) for iid in app.git_tree.get_children("")]
    assert any("new-file.py" in path for path in displayed), f"in-scope status missing: {displayed}"
    assert any("OUTSIDE PROJECT SCOPE" in path and "outside.txt" in path for path in displayed), f"outside-scope warning missing: {displayed}"
    assert hasattr(app, "github_repository_clone_button")
    assert hasattr(app, "github_repository_initialize_button")
    assert hasattr(app, "github_repository_review_button")
    assert hasattr(app, "github_repository_binding_settings_button")
    assert app.github_repository_binding_var.get().find("repository ID 9001") >= 0

    app._review_initial_push_files()
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        root.update()
        if not app.busy and any("Initial Push Review" in item.title() for item in root.winfo_children() if isinstance(item, tk.Toplevel)):
            break
        time.sleep(0.01)
    dialogs = [item for item in root.winfo_children() if isinstance(item, tk.Toplevel) and "Initial Push Review" in item.title()]
    assert dialogs, "Initial Push Review dialog did not open"
    assert subprocess.run(["git", "-C", str(repo_root), "diff", "--cached", "--quiet"]).returncode == 0, "review staged changes"
    assert subprocess.run(["git", "-C", str(repo_root), "diff", "--cached", "--name-only"], capture_output=True, text=True, check=True).stdout == ""

    for dialog in dialogs:
        dialog.destroy()
    # Verify the high-risk behavior: committing from one Monorepo subproject may
    # stage/commit its own files only, never sibling/root changes.
    wb.simpledialog.askstring = lambda *args, **kwargs: "scoped subproject commit"
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        root.update()
        if not app.busy:
            break
        time.sleep(0.01)
    app.commit_changes()
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        root.update()
        latest_message = subprocess.run(["git", "-C", str(repo_root), "log", "-1", "--pretty=%s"], capture_output=True, text=True, check=True).stdout.strip()
        if latest_message == "scoped subproject commit" and not app.busy:
            break
        time.sleep(0.01)
    latest_message = subprocess.run(["git", "-C", str(repo_root), "log", "-1", "--pretty=%s"], capture_output=True, text=True, check=True).stdout.strip()
    assert latest_message == "scoped subproject commit", f"in-scope commit did not complete: {latest_message!r}"
    committed_paths = subprocess.run(["git", "-C", str(repo_root), "show", "--pretty=format:", "--name-only", "HEAD"], capture_output=True, text=True, check=True).stdout.splitlines()
    assert committed_paths == ["apps/desktop/new-file.py"], f"commit escaped active project scope: {committed_paths}"
    outside_status = subprocess.run(["git", "-C", str(repo_root), "status", "--porcelain=v1", "--", "outside.txt"], capture_output=True, text=True, check=True).stdout
    assert outside_status.strip().endswith("outside.txt"), "outside-scope file was unexpectedly staged or committed"
    assert subprocess.run(["git", "-C", str(repo_root), "diff", "--cached", "--quiet"]).returncode == 0

    # A pre-staged sibling must block Workbench Commit instead of being mixed in.
    subprocess.run(["git", "-C", str(repo_root), "add", "--", "outside.txt"], check=True)
    head_before_block = subprocess.run(["git", "-C", str(repo_root), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    app.commit_changes()
    head_after_block = subprocess.run(["git", "-C", str(repo_root), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    assert head_after_block == head_before_block, "Workbench committed an already-staged outside-scope file"
    staged_after_block = subprocess.run(["git", "-C", str(repo_root), "diff", "--cached", "--name-only", "-z"], capture_output=True, text=True, check=True).stdout.split("\0")
    assert staged_after_block == ["outside.txt", ""], f"staged outside path was unexpectedly changed: {staged_after_block}"
    subprocess.run(["git", "-C", str(repo_root), "reset", "--", "outside.txt"], check=True, capture_output=True)

    # Integration-test Initialize & Link on a truly unversioned folder. Workbench
    # metadata exists before git init, so the private exclude must be installed
    # after initialization and must not stage/create a commit/push.
    fresh_project = base / "fresh-project"
    fresh_project.mkdir()
    (fresh_project / "hello.py").write_text("print('hello')\n", encoding="utf-8")
    app.set_workspace(fresh_project)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        root.update()
        if not app.busy:
            break
        time.sleep(0.01)
    app.github_repository_cache_account_id = account_id
    app._initialize_and_link_active_project(fake_repo, account_id)
    deadline = time.monotonic() + 25
    init_dialogs = []
    while time.monotonic() < deadline:
        root.update()
        init_dialogs = [item for item in root.winfo_children() if isinstance(item, tk.Toplevel) and "Initial Push Review" in item.title()]
        git_dir = fresh_project / ".git"
        if git_dir.exists() and init_dialogs:
            if not app.busy:
                break
        time.sleep(0.01)
    assert (fresh_project / ".git").exists(), "Initialize & Link did not create local Git metadata"
    branch = subprocess.run(["git", "-C", str(fresh_project), "branch", "--show-current"], capture_output=True, text=True, check=True).stdout.strip()
    assert branch.startswith("workbench/initial-sync-"), f"initialization used unexpected branch: {branch!r}"
    origin = subprocess.run(["git", "-C", str(fresh_project), "remote", "get-url", "origin"], capture_output=True, text=True, check=True).stdout.strip()
    assert origin == "https://github.com/octocat/monorepo.git", f"unexpected or credential-bearing origin: {origin!r}"
    assert subprocess.run(["git", "-C", str(fresh_project), "diff", "--cached", "--quiet"]).returncode == 0, "Initialize & Link staged files"
    assert subprocess.run(["git", "-C", str(fresh_project), "rev-parse", "--verify", "HEAD"], capture_output=True).returncode != 0, "Initialize & Link created an initial commit"
    fresh_status = subprocess.run(["git", "-C", str(fresh_project), "status", "--porcelain=v1", "--untracked-files=all"], capture_output=True, text=True, check=True).stdout
    assert "hello.py" in fresh_status, "project source was unexpectedly altered or hidden"
    assert ".workbench" not in fresh_status, f"internal Workbench metadata was not excluded after init: {fresh_status!r}"
    assert repository_binding_service.find_binding(app.settings_data.get("github_repository_bindings", []), fresh_project) is not None
    for dialog in init_dialogs:
        dialog.destroy()
    root.destroy()

print("v1.14.4 GUI: migration backup, scope-limited commit, staged-outside blocking, and safe Initialize & Link: PASS")
