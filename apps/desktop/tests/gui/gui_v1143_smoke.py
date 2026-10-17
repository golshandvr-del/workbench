"""GUI smoke for the v1.14.3 repository browser and project binding flows."""
from __future__ import annotations
import json
import os
import subprocess
import tempfile
import time
import tkinter as tk
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

with tempfile.TemporaryDirectory(prefix="aiwb-repository-browser-gui-") as temp:
    appdata = Path(temp) / "AppData"
    os.environ["LOCALAPPDATA"] = str(appdata)
    import AI_Workbench as wb
    from aiwb.github import GitHubAccountService, GitHubApiClient, MemoryCredentialStore
    from aiwb.github.api_client import HttpResponse

    wb.messagebox.showinfo = lambda *args, **kwargs: None
    wb.messagebox.showwarning = lambda *args, **kwargs: None
    wb.messagebox.showerror = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError(f"Unexpected GUI error: {args}"))
    wb.messagebox.askyesno = lambda *args, **kwargs: True
    wb.webbrowser.open = lambda url: True

    token = "github_pat_" + "G" * 40
    repos = [
        {"id": 101, "name": "desktop", "full_name": "octocat/desktop", "owner": {"login": "octocat"},
         "private": True, "fork": False, "archived": False, "default_branch": "main", "updated_at": "2026-10-17T12:00:00Z",
         "description": "Workbench desktop app", "html_url": "https://github.com/octocat/desktop", "permissions": {"push": True}},
        {"id": 102, "name": "later-match", "full_name": "octocat/later-match", "owner": {"login": "octocat"},
         "private": False, "fork": True, "archived": True, "default_branch": "stable", "updated_at": "2026-10-16T12:00:00Z",
         "description": "Archived test repo", "html_url": "https://github.com/octocat/later-match", "permissions": {"push": False}},
    ]
    def transport(url, headers, timeout):
        assert headers["Authorization"] == "Bearer " + token
        if url == "https://api.github.com/user":
            return HttpResponse(200, {}, json.dumps({"id": 70421, "login": "smoke-account", "avatar_url": None, "html_url": "https://github.com/smoke-account"}).encode())
        if url.startswith("https://api.github.com/user/repos?"):
            query = parse_qs(urlsplit(url).query)
            assert query["per_page"] == ["100"]
            assert query["visibility"] == ["all"]
            assert query["affiliation"] == ["owner,collaborator,organization_member"]
            if query["page"] == ["1"]:
                return HttpResponse(200, {}, json.dumps(repos).encode())
            return HttpResponse(200, {}, b"[]")
        raise AssertionError(f"Unexpected GitHub API URL: {url}")

    root = tk.Tk()
    app = wb.WorkbenchApp(root)
    root.update()
    assert tuple(map(int, wb.APP_VERSION.split("."))) >= (1, 14, 3), f"v1.14.3 regression flow needs >= 1.14.3: {wb.APP_VERSION}"
    assert hasattr(app, "github_repositories_tree"), "Repository browser panel missing"
    assert hasattr(app, "github_repository_account_combo"), "Account selector missing"
    store = MemoryCredentialStore()
    app.github_account_service = GitHubAccountService(
        store, GitHubApiClient(transport=transport),
        load_accounts=lambda: app.settings_data.get("github_accounts", []),
        save_accounts=app._save_github_account_metadata,
    )
    account = app.github_account_service.add_pat(token)
    app._render_github_accounts()
    root.update()
    assert app.github_repository_account_choices, "repository account selector not populated"
    assert account.account_id in app.github_repository_account_choices.values()

    app._refresh_github_repositories()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        root.update()
        if not app.busy and app.github_repository_cache:
            break
        time.sleep(0.01)
    assert not app.busy, "repository refresh background work did not finish"
    assert [item.full_name for item in app.github_repository_cache] == ["octocat/desktop", "octocat/later-match"]
    assert len(app.github_repositories_tree.get_children("")) == 2
    app.github_repository_search_var.set("later-match")
    app._render_github_repository_tree()
    assert list(app.github_repositories_tree.get_children("")) == ["102"], "search did not filter loaded repository metadata"
    app.github_repository_search_var.set("")
    app.github_repository_filter_var.set("Archived")
    app._render_github_repository_tree()
    assert list(app.github_repositories_tree.get_children("")) == ["102"], "Archived filter failed"
    app.github_repository_filter_var.set("All")
    app._render_github_repository_tree()
    app.github_repositories_tree.selection_set("101")

    # A project below the repository root is bound as a subpath; adding origin is explicit.
    repo_root = Path(temp) / "local-monorepo"
    project = repo_root / "apps" / "desktop"
    project.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "main", str(repo_root)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo_root), "config", "user.name", "AIWB Smoke"], check=True)
    subprocess.run(["git", "-C", str(repo_root), "config", "user.email", "smoke@example.invalid"], check=True)
    (repo_root / "README.md").write_text("initial\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo_root), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(repo_root), "commit", "-m", "initial"], check=True, capture_output=True)
    app.set_workspace(project)
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        root.update()
        if not app.busy and app.project_version_baseline_state.get(str(project.resolve())) in {"ready", "failed", None}:
            # Allow completion callback to start any follow-up baseline/Git refresh.
            if app.status_var.get().startswith("Active project:") or "Git" in app.status_var.get():
                break
        time.sleep(0.01)
    assert app.github_repositories_tree.exists("101")
    app.github_repositories_tree.selection_set("101")
    app._link_selected_github_repository()
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        root.update()
        bindings = app.settings_data.get("github_repository_bindings", [])
        if not app.busy and bindings:
            break
        time.sleep(0.01)
    assert app.settings_data.get("github_repository_bindings"), "binding metadata was not saved"
    binding = app.settings_data["github_repository_bindings"][0]
    assert binding["repository_id"] == 101
    assert binding["project_subpath"] == "apps/desktop"
    assert Path(binding["local_git_root"]).resolve() == repo_root.resolve()
    remote = subprocess.run(["git", "-C", str(repo_root), "remote", "get-url", "origin"], capture_output=True, text=True, check=True).stdout.strip()
    assert remote == "https://github.com/octocat/desktop.git"
    settings_text = app.settings_path.read_text(encoding="utf-8")
    assert token not in settings_text, "PAT leaked into settings"
    assert app.github_repository_binding_var.get().find("octocat/desktop") >= 0

    app._unlink_active_github_repository()
    root.update()
    assert app.settings_data.get("github_repository_bindings", []) == []
    assert subprocess.run(["git", "-C", str(repo_root), "remote", "get-url", "origin"], capture_output=True, text=True, check=True).stdout.strip() == remote, "unlink unexpectedly changed local origin"
    assert "project subpath" not in app.github_repository_binding_var.get().lower() or "not linked" in app.github_repository_binding_var.get().lower()
    root.destroy()

print("v1.14.3 Repository Browser GUI, search/filter, binding persistence, monorepo subpath, explicit origin, unlink: PASS")
