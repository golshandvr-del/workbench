"""Roadmap 5.6.0 gate: the Agents hub on the real application.

* A 4-AI project where one builder holds most of the work: the Agents page shows one card per AI, numbered like
  the Mission Map lanes, the overloaded/idle alerts and a suggested move under Balance.
* Clicking a card selects that AI (Selected AI shows its queue); Copy briefing puts a self-contained sheet on the
  clipboard and writes nothing.
* Memory note… saves the note in one transaction; the next prompt of that AI carries it.
* Apply suggested moves moves only unstarted ready tasks and evens the load; Midnight and Daylight both draw.
* ``AIWB_SCREENSHOT_DIR=dir`` writes ``agents_midnight.png`` / ``agents_daylight.png``.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
import tkinter as tk
from pathlib import Path

import AI_Workbench as wb
from aiwb.ui import mission_model
from aiwb.v2 import agent_hub
from aiwb.v2.models import normalize_agent
from gui_smoke_helpers import wait_for_project_ready


def settle(root: tk.Tk, n: int = 6) -> None:
    for _ in range(n):
        root.update()
        time.sleep(0.02)


def shot(root: tk.Tk, name: str) -> None:
    out = os.environ.get("AIWB_SCREENSHOT_DIR")
    if not out or not shutil.which("import"):
        return
    Path(out).mkdir(parents=True, exist_ok=True)
    settle(root, 12)
    geo = f"{root.winfo_width()}x{root.winfo_height()}+{root.winfo_rootx()}+{root.winfo_rooty()}"
    subprocess.run(["import", "-window", "root", "-crop", geo, "+repage", str(Path(out) / name)], check=False,
                   timeout=30)


def plan(ctl) -> None:
    p = ctl.project
    with p.store.transaction("smoke agents") as s:
        for aid, name in (("agent-b1", "Builder One"), ("agent-b2", "Builder Two"), ("agent-b3", "Builder Three")):
            s["agents"][aid] = normalize_agent({"agent_id": aid, "role": "implementer", "name": name,
                                                "template_id": ""})
    for k in range(5):
        t = p.tasks.create({"title": f"Feature {k + 1}", "objective": "o", "owner_agent_id": "agent-b1",
                            "scope": {"include": [f"f{k}/**"]}, "acceptance_criteria": ["ok"]})
        p.tasks.transition(t["task_id"], "ready")
    t = p.tasks.create({"title": "Small fix", "objective": "o", "owner_agent_id": "agent-b2",
                        "scope": {"include": ["fix/**"]}, "acceptance_criteria": ["ok"]})
    p.tasks.transition(t["task_id"], "ready")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="aiwb-v5-agents-") as temp:
        os.environ["LOCALAPPDATA"] = str(Path(temp) / "appdata")
        project = Path(temp) / "Agents six"
        project.mkdir()
        (project / "main.py").write_text("print(1)\n", encoding="utf-8")
        root = tk.Tk()
        root.geometry("1280x860+0+0")
        try:
            app = wb.WorkbenchApp(root)
            for name in ("showinfo", "showwarning", "showerror"):
                setattr(wb.messagebox, name, lambda *a, **k: (_ for _ in ()).throw(AssertionError(a)))
            sh = app.shell
            app.set_workspace(project, focus_project=True)
            wait_for_project_ready(app, root, project)
            sh.show("workbench")
            settle(root, 10)
            ctl = app.workspace_window.wc.ctl
            plan(ctl)
            sh.show("agents")
            settle(root, 10)
            app.refresh_agents_page()
            settle(root, 6)
            st = ctl.state()
            rows = app.agents_rows
            enabled = [a for a in st["agents"].values() if a.get("enabled", True)]
            assert len(rows) == len(enabled), (len(rows), len(enabled))
            lanes = {ln["agent_id"]: ln["number"] for ln in mission_model.build(st)["lanes"]}
            for r in rows:
                if r["agent_id"] in lanes:
                    assert r["number"] == lanes[r["agent_id"]], (r["agent_id"], r["number"], lanes)
            assert app.agents_cards.find_all(), "cards drawn"
            b1 = next(r for r in rows if r["agent_id"] == "agent-b1")
            assert "overloaded" in b1["alerts"], b1
            bal = app.agents_balance_var.get()
            assert "Suggest: move" in bal and "from Builder One" in bal, bal  # 5.13.0 (C6): AI names, not ids
            assert app.agents_balance_bar.winfo_manager(), "moves listed → Apply suggested moves is shown"
            # select a card by clicking it
            cards = app.agents_cards
            idx = [r["agent_id"] for r in rows].index("agent-b1")
            per_row = max(1, (cards.winfo_width() - cards.GAP) // (cards.CARD_W + cards.GAP))
            cx = cards.GAP + (idx % per_row) * (cards.CARD_W + cards.GAP) + 120
            cy = cards.GAP + (idx // per_row) * (cards.CARD_H + cards.GAP) + 60
            cards.event_generate("<ButtonPress-1>", x=cx, y=cy)
            settle(root, 4)
            assert cards.selected == "agent-b1", cards.selected
            assert "Builder One" in app.agents_who_var.get() and "Queue:" in app.agents_who_var.get()
            # briefing: clipboard, no write
            rev = ctl.project.store.revision
            text = app.agents_copy_briefing()
            assert text.startswith("# Briefing — you are Builder One") and root.clipboard_get() == text
            assert ctl.project.store.revision == rev, "briefing wrote state"
            # memory note: saved and carried by the next prompt of that AI
            out = app.agents_edit_note("Use type hints everywhere.")
            assert out == "Use type hints everywhere." and agent_hub.note(ctl.state(), "agent-b1") == out
            assert "Memory note: Use type hints" in app.agents_who_var.get()
            for theme in ("dark", "light"):
                app.prefs.set_theme(theme)
                settle(root, 6)
                app.refresh_agents_page()
                shot(root, f"agents_{'midnight' if theme == 'dark' else 'daylight'}.png")
            app.prefs.set_theme("dark")
            # balance: only unstarted ready tasks move, load evens out
            before = {r["agent_id"]: r["open"] for r in agent_hub.agent_stats(ctl.state())}
            moved = app.agents_apply_moves(confirm=False)
            assert moved, "a move was suggested and applied"
            after = {r["agent_id"]: r["open"] for r in agent_hub.agent_stats(ctl.state())}
            assert after["agent-b1"] < before["agent-b1"], (before, after)
            workers = [k for k in after if k in ("agent-b1", "agent-b2", "agent-b3")]
            assert max(after[k] for k in workers) - min(after[k] for k in workers) <= 1, after
            assert not agent_hub.rebalance(ctl.state()), "balanced after applying"
            assert not app.agents_balance_bar.winfo_manager(), "no moves → no Apply suggested moves (C6)"
            settle(root, 4)
            print(f"5.6.0 Agents hub: {len(rows)} cards = lanes, alerts, briefing, note, {len(moved)} move(s): PASS")
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass


if __name__ == "__main__":
    main()
