"""GUI smoke for the Team Planner (roadmap 2.4.0 stage 4, Gate A).

Workspace → Team: four account profiles, max two parallel chats, Plan team &
tasks (prompt only, not sent), paste a team proposal, review shows counts and an
invented account as an error, request changes (nothing applied), accept the
valid selection, tasks/agents/bindings exist and the graph is valid; FA (RTL)
renders the review.
"""
from __future__ import annotations

import json
import os
import tempfile
import tkinter as tk
from pathlib import Path

import AI_Workbench as wb
from gui_smoke_helpers import wait_for_project_ready
from aiwb.v2.tasks import validate_graph


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="aiwb-team-smoke-") as temp:
        os.environ["LOCALAPPDATA"] = str(Path(temp) / "appdata")
        project = Path(temp) / "Team project"
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
            w.win.geometry("1366x768+0+0")
            w.show("team")
            root.update()
            for n in ("GPT paid — work", "Gemini", "Claude", "GPT free"):
                assert w.dialog_add_account({"display_name": n, "provider": "Other", "plan": "unknown"})
            assert w.dialog_add_account({"display_name": "token: ghp_abcdefghijklmnopqrstu"}) is None
            assert "never stores model credentials" in w.status_var.get()
            w.show("team")
            w.parallel_var.set("2")
            assert w.save_team_settings()["max_parallel_chats"] == 2
            prompt = w.dialog_plan_team({"goal": "Todo web app", "platform": "Python"})
            assert "ACC-0004" in prompt and "at the same time: 2" in prompt
            assert "not sent yet" in w.status_var.get()
            assert "Team planning" in w.prompt_text.get("1.0", "end")
            rev = ctl.state()["state_revision"]
            before = (sorted(ctl.state()["agents"]), len(ctl.state()["tasks"]), len(ctl.state()["chat_bindings"]))
            ops = [{"operation": "create_agent", "agent_id": "agent-implementer-2", "role": "implementer", "name": "Impl 2"},
                   {"operation": "assign_account", "agent_id": "agent-implementer-2", "account_profile_id": "ACC-0002"},
                   {"operation": "assign_account", "agent_id": "agent-reviewer", "account_profile_id": "ACC-0077"},
                   {"operation": "create_task", "temporary_ref": "new-1", "title": "API", "objective": "a",
                    "owner_agent_id": "agent-implementer", "parallel_group": "A", "scope": {"include": ["src/api/**"]},
                    "acceptance_criteria": ["ok"]},
                   {"operation": "create_task", "temporary_ref": "new-2", "title": "UI", "objective": "u",
                    "owner_agent_id": "agent-implementer-2", "parallel_group": "A", "scope": {"include": ["src/ui/**"]},
                    "acceptance_criteria": ["ok"], "depends_on_refs": []},
                   {"operation": "create_task", "temporary_ref": "new-3", "title": "Glue", "objective": "g",
                    "owner_agent_id": "agent-implementer", "depends_on_refs": ["new-1", "new-2"],
                    "scope": {"include": ["src/app.py"]}, "acceptance_criteria": ["ok"]}]
            d = {"schema_version": "1.0", "proposal_type": "team_plan", "base_state_revision": rev, "summary": "Two workers",
                 "team": {"pm_counted": True, "total_agents": 5, "additional_workers": 4, "size_rationale": "API and UI are independent"},
                 "operations": ops}
            r = w.do_import("x\n<<<AIWB_MANAGER_PROPOSAL>>>\n" + json.dumps(d) + "\n<<<AIWB_END_MANAGER_PROPOSAL>>>")
            assert r.kind == "proposal", r.message
            root.update()
            assert w.wc.section == "team" and w.review_pid == r.reference_id
            kids = w.review_tree.get_children()
            assert len(kids) == 6
            assert "ACC-0077" in str(w.review_tree.item("2")["values"])
            assert "2" not in w.review_tree.selection(), "invalid item must not be preselected"
            snap = lambda: (sorted(ctl.state()["agents"]), len(ctl.state()["tasks"]), len(ctl.state()["chat_bindings"]))  # noqa: E731
            assert snap() == before, "import alone changed agents/tasks/bindings"
            rev = ctl.state()["state_revision"]  # the stored proposal itself is one revision
            # request changes: prompt only
            p = w.review_request_changes()
            assert "ACC-0077" in p and ctl.state()["state_revision"] == rev
            w.show("team")
            root.update()
            # FA review renders RTL
            w.lang_var.set("fa")
            w._set_lang()
            w.show("team")
            root.update()
            assert w.review_tree.heading("op")["text"] == "عملیات"
            w.lang_var.set("en")
            w._set_lang()
            w.show("team")
            root.update()
            out = w.review_accept()
            assert out and out["status"] == "accepted", out  # all valid items accepted; the invalid one is rejected
            st = ctl.state()
            assert "agent-implementer-2" in st["agents"] and len(st["tasks"]) == 3
            assert validate_graph(st["tasks"]) == []
            rows = {x["agent_id"]: x for x in w.wc.team_rows()}
            assert rows["agent-implementer-2"]["account"] == "Gemini"
            root.update()
            assert not w.review_pid, "reviewed proposal still shown"
            w.close()
            print("Team planner smoke passed: 4 profiles · 2 chats · plan prompt · review (counts, invented account) · "
                  "request changes · partial accept · RTL")
        finally:
            root.destroy()


if __name__ == "__main__":
    main()
