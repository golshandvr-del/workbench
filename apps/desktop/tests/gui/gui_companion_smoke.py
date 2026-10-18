"""GUI smoke for the Mobile Companion (Integration Spec §11.2): open from the main window, pair a simulated
phone over the real LAN endpoint (loopback), approve on the desktop, view state, permission + revoke."""
from __future__ import annotations

import json
import os
import tempfile
import tkinter as tk
import urllib.request
from pathlib import Path

import AI_Workbench as wb
from gui_smoke_helpers import wait_for_project_ready
from aiwb.companion import crypto


def post(port: int, env: dict) -> tuple[int, dict]:
    req = urllib.request.Request(f"http://127.0.0.1:{port}/aiwb/v1", data=json.dumps(env).encode(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="aiwb-companion-smoke-") as temp:
        os.environ["LOCALAPPDATA"] = str(Path(temp) / "appdata")
        project = Path(temp) / "Projekt ä"
        project.mkdir()
        (project / "main.py").write_text("print(1)\n", encoding="utf-8")
        root = tk.Tk()
        try:
            app = wb.WorkbenchApp(root)
            for name in ("showinfo", "showwarning", "showerror"):
                setattr(wb.messagebox, name, lambda *a, **k: None)
            app.set_workspace(project, focus_project=True)
            wait_for_project_ready(app, root, project)
            app.open_companion()
            w = app.companion_window
            app.companion_server.host = "127.0.0.1"
            app.companion_server.port = 0
            uri = w.do_pair()
            root.update()
            assert app.companion_server.running
            _, host, port, pid, secret = uri.split(":")
            port = int(port)
            secret = crypto.b64d(secret)
            dkey = os.urandom(32)
            code, out = post(port, crypto.seal(secret, pid, {"op": "pair_request", "device_name": "Smoke phone",
                                                              "device_key": crypto.b64e(dkey)}))
            assert code == 200 and crypto.open_json(secret, out)["status"] == "pending"
            w.refresh()
            assert str(w.approve_btn.cget("state")) == "normal"
            assert "Smoke phone" in w.pair_var.get()
            w.perm_vars["create_task"].set(True)
            w.do_decide(True)
            _, out = post(port, crypto.seal(secret, pid, {"op": "pair_status"}))
            st = crypto.open_json(secret, out)
            assert st["status"] == "approved", st
            did = st["device_id"]
            assert w.tree.exists(did)
            _, out = post(port, crypto.seal(dkey, did, {"op": "create_task", "title": "From phone", "objective": "o"}))
            created = crypto.open_json(dkey, out)
            assert created["ok"], created
            _, out = post(port, crypto.seal(dkey, did, {"op": "get_state"}))
            view = crypto.open_json(dkey, out)
            assert [t["title"] for t in view["tasks"]] == ["From phone"], view["tasks"]
            assert str(project) not in json.dumps(view)
            w.confirm = lambda *_a: True
            w.tree.selection_set(did)
            w.do_revoke()
            assert post(port, crypto.seal(dkey, did, {"op": "hello"}))[0] == 403
            w.close()
            app.on_close = lambda: None
            app.companion_server.stop()
            assert not app.companion_server.running
            print("PASS: Mobile Companion GUI smoke (pair, approve, create task, view, revoke)")
        finally:
            try:
                app.companion_server.stop()
            except Exception:  # noqa: BLE001
                pass
            root.destroy()


if __name__ == "__main__":
    main()
