"""GUI smoke for the Project Charter (roadmap 3.4.0 Gate).

Project Workbench → Overview "Design the whole project…" → charter prompt (copied, not sent) →
an incomplete answer is refused with a fix prompt and nothing changes → the corrected, chat-damaged
answer is imported once as a proposal → Team view review → accept → agents, tasks, milestones and
proposed versions exist → each AI's start prompt can be copied.
"""
from __future__ import annotations

import copy
import json
import os
import tempfile
import tkinter as tk
from pathlib import Path

import AI_Workbench as wb
from gui_smoke_helpers import wait_for_project_ready

FIXTURE = Path(__file__).resolve().parents[4] / "packages/contracts/fixtures/valid/project-charter.v1.todo.json"


def wrap(body: str) -> str:
    return "My design:\n<<<AIWB_PROJECT_CHARTER>>>\n" + body + "\n<<<AIWB_END_PROJECT_CHARTER>>>\n"


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="aiwb-charter-smoke-") as temp:
        os.environ["LOCALAPPDATA"] = str(Path(temp) / "appdata")
        project = Path(temp) / "Charter ä"
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
            w.show("overview")
            root.update()
            labels = [str(b.cget("text")) for b in _all(w.top) if b.winfo_class() == "TButton"]
            # 5.11.0 (A7): the duplicate "Design the whole project…" / "Plan project…" buttons are gone — the charter
            # prompt comes from the Next step (Home's card); dialog_charter stays for scripts
            assert "Design the whole project…" not in labels and "Plan project…" not in labels, labels
            assert "Plan & Tasks" in labels and "Project settings" in labels, labels
            prompt = w.dialog_charter({"goal": "Offline todo app for desktop and mobile"})
            assert "AIWB_PROJECT_CHARTER" in prompt and "how many AI chats work in parallel" in prompt
            from aiwb.v2.handoff import with_answer_rule  # 5.12.0 (B1): Copy adds the whole-answer rule
            assert w.do_copy() == root.clipboard_get() == with_answer_rule(prompt)
            good = json.loads(FIXTURE.read_text(encoding="utf-8"))
            good["base_state_revision"] = ctl.state()["state_revision"]

            # 5.10.0: a missing section is repaired; only a truly ambiguous answer (unknown dependency) is refused
            bad = copy.deepcopy(good)
            bad["tasks"][0]["depends_on_refs"] = ["t9"]
            rev = ctl.state()["state_revision"]
            r = w.do_import(wrap(json.dumps(bad)))
            assert r.kind == "charter_rejected", r.message
            assert "unknown task 't9'" in w.status_var.get(), w.status_var.get()
            assert "unknown task 't9'" in w.last_prompt
            assert ctl.state()["state_revision"] == rev and not ctl.state()["proposals"], "a rejected charter changes nothing"

            # ChatGPT-style damage: smart quotes around keys, escaped markers, trailing comma
            damaged = json.dumps(good, indent=1).replace('"summary"', "\u201csummary\u201d")
            damaged = damaged[:-1].rstrip() + ",\n}"
            text = wrap(damaged).replace("<<<AIWB_PROJECT_CHARTER>>>", "\\<\\<\\<AIWB\\_PROJECT\\_CHARTER>>>")
            r = w.do_import(text)
            assert r.kind == "proposal", r.message
            assert not ctl.state()["tasks"], "nothing is applied before review"
            root.update()
            assert w.wc.section == "plan" and w.review_pid == r.reference_id
            out = w.review_accept()
            assert out and out["status"] == "accepted", out
            st = ctl.state()
            assert {"agent-core-dev", "agent-desktop-dev", "agent-mobile-dev"} <= set(st["agents"])
            assert len(st["tasks"]) == 3 and len(st["milestones"]) == 2
            assert sorted(v["label"] for v in st["versions"].values()) == ["0.1.0", "0.2.0"]
            w.show("team")
            root.update()
            assert w.charter_agent_var.get() == "agent-core-dev"
            sp = w.copy_start_prompt("agent-mobile-dev")
            assert root.clipboard_get() == sp and "mobile/**" in sp and "NO access" in sp
        finally:
            root.destroy()
    print("PASS: Project Charter GUI smoke - prompt, refusal with fix prompt, tolerant import, review, start prompts")


def _all(w: tk.Misc):
    for ch in w.winfo_children():
        yield ch
        yield from _all(ch)


if __name__ == "__main__":
    main()
