"""GUI smoke for the Team Dashboard, Needs Attention queue and change routes (roadmap 2.6.0; Gate C, E subset).

Ten synthetic agents: Team view shows status counts, "needs you" and the current
step; compact density starts with "needs action only"; Overview shows the grouped
queue (decision first), opening an item selects the task in the Inspector, mark
as read hides it without touching history; Request a change → new task; RTL
renders; the window fits 1280×720 and 1366×768.
"""
from __future__ import annotations

import os
import sys
import tempfile
import tkinter as tk
from pathlib import Path

import AI_Workbench as wb
from gui_smoke_helpers import wait_for_project_ready

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fixtures_ten_agents as fx  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="aiwb-dash-smoke-") as temp:
        os.environ["LOCALAPPDATA"] = str(Path(temp) / "appdata")
        project = Path(temp) / "Dash project"
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
            ctl = w.wc.ctl
            # build the synthetic team inside the opened project
            fx_data = fx.build_into(ctl)
            sp = fx_data["special"]
            for size in ("1366x768+0+0", "1280x720+0+0"):
                w.win.geometry(size)
                w.show("team")
                root.update()
                assert w.team_attention_only.get(), "10 agents should start with 'needs action only'"
                shown = w.fill_team()
                assert "agent-fx-03" in shown and all(w.team_tree.set(a, "attention") != "—" for a in shown), shown
                w.team_attention_only.set(False)
                assert len(w.fill_team()) >= 10
                assert "needs action" in w.team_status_var.get()
                assert w.win.winfo_width() <= w.win.winfo_screenwidth()
            rev = ctl.state()["state_revision"]
            events = ctl.project.store.ledger.count()
            w.show("overview")
            root.update()
            items = w.attention_items
            assert items[0]["ref"] == sp["decision"], items[0]
            assert any(i["kind"] == "more" for i in items) or len(items) <= 30
            stale_key = next(i["key"] for i in items if i["ref"] == sp["stale"])
            section, ref = w.open_attention_selected(stale_key)
            assert (section, ref) == ("tasks", sp["stale"]) and w.wc.selection == ("task", sp["stale"])
            assert "older attempt" in w.insp_text.get("1.0", "end")
            w.show("overview")
            w.mark_attention_seen([stale_key])
            assert stale_key not in [i["key"] for i in w.attention_items]
            assert ctl.state()["state_revision"] == rev and ctl.project.store.ledger.count() == events
            more = next((i for i in w.attention_items if i["kind"] == "more"), None)
            if more:
                assert w.open_attention_selected(more["key"])
            # change request from the inspector
            tid = fx_data["tasks"]["agent-fx-06"][0]
            w.wc.select("task", tid)
            w.show("tasks")
            labels = [b.cget("text") for b in w.insp_actions.winfo_children()]
            assert "Request a change…" in labels, labels
            out = w.dialog_change_request(tid, "add a new feature: CSV export", route="new_task")
            assert out and out["route"] == "new_task" and w.wc.selection[1] == out["task_id"]
            w.wc.set_language("fa")
            w.show("overview")
            w.show("team")
            root.update()
            assert "نیازمند اقدام" in w.team_status_var.get()
            w.wc.set_language("en")
            w.close()
            print("Dashboard smoke passed: 10 agents · compact default · status counts · ranked queue with reasons · "
                  "open via Inspector · mark as read (no history change) · change request · RTL")
        finally:
            root.destroy()


if __name__ == "__main__":
    main()
