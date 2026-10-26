"""GUI smoke for the Project Workbench shell (roadmap 2.3.0 stage 3, Gate E subset).

Opens the workspace from the main window and checks, at 1280×720, 1366×768 and
1920×1080 plus the minimum size: every section renders, the next-action button
and the inspector stay inside the window, the inspector stacks below 1100 px,
FA (RTL) / EN switch, theme switch, and that view changes never bump the
project state revision or the event ledger.
"""
from __future__ import annotations

import os
import tempfile
import tkinter as tk
from pathlib import Path

import AI_Workbench as wb
from gui_smoke_helpers import wait_for_project_ready
from aiwb.workspace.controller import SECTIONS

SIZES = [(1280, 720), (1366, 768), (1920, 1080), (960, 600)]


def inside(widget: tk.Misc, win: tk.Misc) -> bool:
    widget.update_idletasks()
    x, y = widget.winfo_rootx() - win.winfo_rootx(), widget.winfo_rooty() - win.winfo_rooty()
    return widget.winfo_ismapped() and x >= 0 and y >= 0 and x + widget.winfo_width() <= win.winfo_width() + 1 \
        and y + widget.winfo_height() <= win.winfo_height() + 1


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="aiwb-workspace-smoke-") as temp:
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
            app.open_project_workbench()
            w = app.workspace_window
            wc = w.wc
            ctl = wc.ctl
            # some data: two tasks, an account and a binding
            t = ctl.project.tasks.create({"title": "Implement a very long task title " * 4, "objective": "x",
                                          "owner_agent_id": "agent-implementer"})
            ctl.project.tasks.transition(t["task_id"], "ready")
            acc = w.dialog_add_account({"display_name": "GPT paid — work", "provider": "GPT", "plan": "paid"})
            assert acc and acc["account_profile_id"] == "ACC-0001"
            assert w.dialog_bind_chat("agent-implementer", "ACC-0001", "impl chat")
            rev, n = ctl.project.store.revision, ctl.project.store.ledger.count()
            for (wd, ht) in SIZES:
                w.top.geometry(f"{wd}x{ht}+0+0")
                for _ in range(5):
                    root.update()
                for s in SECTIONS:
                    w.show(s)
                    root.update()
                    assert inside(w.next_btn, w.top), (wd, ht, s, "next action button out of window")
                    if wc.inspector_open:
                        assert inside(w.inspector, w.top), (wd, ht, s, "inspector out of window")
                # The window manager may clamp the requested size to the screen (CI runners are small):
                # the layout must follow the *actual* width, which is what users see.
                real = w.top.winfo_width()
                expect = "side" if real >= 1100 else "stacked"
                assert w.layout["inspector"] == expect, (wd, real, w.layout)
            # inspector + sidebar collapse
            w.toggle_inspector()
            root.update()
            assert not w.inspector.winfo_ismapped()
            w.toggle_inspector()
            w.toggle_sidebar()
            root.update()
            assert not w.sidebar.winfo_ismapped()
            w.toggle_sidebar()
            # task selection → inspector actions → prompt (not sent)
            w.top.geometry("1366x768+0+0")
            wc.select("task", t["task_id"])
            w.show("tasks")
            root.update()
            assert t["task_id"] in w.insp_title.get()
            out = w.inspector_action("start_task")
            assert out and out["prompt"].startswith("AIWB_ATTEMPT_ID")
            assert "AIWB_ATTEMPT_ID" in w.prompt_text.get("1.0", "end")
            copied = []
            w.clipboard = copied.append
            w.do_copy()
            assert copied and "does not mean it was sent" in w.status_var.get()
            # language + theme switch: labels change, data does not
            rev, n = ctl.project.store.revision, ctl.project.store.ledger.count()
            w.lang_var.set("fa")
            w._set_lang()
            root.update()
            assert w.nav["plan"].cget("text") == "برنامه و وظایف", w.nav["plan"].cget("text")  # 5.11.0: 3 sections
            assert str(w.next_label.cget("anchor")) == "e"
            w.theme_var.set("dark")
            w._set_theme()
            w.show("timeline")  # 5.13.0 (B3): an old key — opens Plan & Tasks (milestones/versions are on the map)
            root.update()
            assert w.wc.section == "plan", w.wc.section
            w.lang_var.set("en")
            w._set_lang()
            assert (ctl.project.store.revision, ctl.project.store.ledger.count()) == (rev, n), "view change wrote state"
            # an event → inspector
            first = w.wc.timeline_page(0)["items"][0]["event_id"]
            w.wc.select("event", first)
            w._render_inspector()
            root.update()
            assert w.insp_title.get()
            w.close()
            print("Workspace smoke passed: sizes", ", ".join(f"{a}x{b}" for a, b in SIZES), "· RTL/LTR · light/dark")
        finally:
            root.destroy()


if __name__ == "__main__":
    main()
