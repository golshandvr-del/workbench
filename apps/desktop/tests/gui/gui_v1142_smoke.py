"""GUI smoke for the v1.14.2 GitHub Accounts panel and safe metadata wiring."""
from __future__ import annotations
import json
import os
import tempfile
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk


def descendants(widget):
    found = []
    for child in widget.winfo_children():
        found.append(child)
        found.extend(descendants(child))
    return found

with tempfile.TemporaryDirectory(prefix="aiwb-github-gui-") as temp:
    os.environ["LOCALAPPDATA"] = str(Path(temp) / "AppData")
    import AI_Workbench as wb
    from aiwb.github import GitHubAccountService, GitHubApiClient, MemoryCredentialStore
    from aiwb.github.api_client import HttpResponse

    wb.messagebox.showinfo = lambda *args, **kwargs: None
    wb.messagebox.showwarning = lambda *args, **kwargs: None
    wb.messagebox.showerror = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError(f"Unexpected GUI error: {args}"))

    root = tk.Tk()
    app = wb.WorkbenchApp(root)
    root.update()
    assert tuple(int(part) for part in wb.APP_VERSION.split(".")) >= (1, 14, 3), "app version was not updated"
    assert app.github_accounts_tree is not None, "GitHub accounts tree is missing"
    all_text = [str(w.cget("text")) for w in descendants(app.git_tab) if hasattr(w, "cget") and "text" in w.keys()]
    assert any("GitHub Accounts" in text for text in all_text), "GitHub Accounts panel not present"
    assert "github_accounts" not in app.settings_data or isinstance(app.settings_data["github_accounts"], list)

    token = "github_pat_" + "T" * 40
    payload = json.dumps({"id": 70421, "login": "smoke-account", "avatar_url": "https://avatars.githubusercontent.com/u/1?v=4", "html_url": "https://github.com/smoke-account"}).encode()
    def transport(url, headers, timeout):
        assert url == "https://api.github.com/user"
        assert headers["Authorization"] == "Bearer " + token
        return HttpResponse(200, {}, payload)

    app.github_account_service = GitHubAccountService(
        MemoryCredentialStore(), GitHubApiClient(transport=transport),
        load_accounts=lambda: app.settings_data.get("github_accounts", []),
        save_accounts=app._save_github_account_metadata,
    )
    # Account creation runs in a worker in the real UI. Its settings persistence must
    # not call Tk variables or touch the UI from that worker thread.
    outcome = {}
    def create_account_in_worker():
        try:
            outcome["account"] = app.github_account_service.add_pat(token)
        except Exception as exc:
            outcome["error"] = exc
    worker = threading.Thread(target=create_account_in_worker, name="GitHubAccountSmokeWorker")
    worker.start()
    deadline = time.monotonic() + 5
    while worker.is_alive() and time.monotonic() < deadline:
        root.update()
        time.sleep(0.01)
    worker.join(timeout=0.1)
    assert not worker.is_alive(), "GitHub account worker did not finish"
    assert "error" not in outcome, f"background account save failed: {outcome.get('error')}"
    account = outcome["account"]
    app._render_github_accounts()
    root.update()
    assert app.github_accounts_tree.exists(account.account_id), "connected account not rendered"
    row = app.github_accounts_tree.item(account.account_id)
    assert row["text"] == "@smoke-account"
    settings_text = app.settings_path.read_text(encoding="utf-8")
    assert token not in settings_text, "PAT leaked into settings.json"
    assert account.credential_ref in settings_text, "credential reference missing from settings"
    assert "repository_write" in account.capability_snapshot and account.capability_snapshot["repository_write"] == "not_checked"
    assert app.settings_data["github_accounts"][0]["login"] == "smoke-account"
    assert "token" not in app.settings_data["github_accounts"][0]
    assert app.github_accounts_tree.item(account.account_id, "values")[0] == "Connected"

    # Disconnect only affects account metadata/credential storage; there is no project root selected.
    assert app.github_account_service.disconnect(account.account_id) is True
    app._render_github_accounts()
    root.update()
    assert not app.github_accounts_tree.get_children(""), "disconnected account still appears in list"
    assert app.settings_data["github_accounts"] == []
    root.destroy()

print("GitHub Accounts GUI + safe settings metadata + disconnect regression: PASS")
