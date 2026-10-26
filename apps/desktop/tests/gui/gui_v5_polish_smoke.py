"""Roadmap 5.7.0 gate: one job per page, on the real application.

* Home shows only the active project: Mission Map, Map view, Task details and Next step — no project library.
* Projects owns the library: one card per project (active first); clicking a card selects that project,
  double-click opens it; the search box filters the cards.
* Home › Map view: "Hide finished tasks" removes done circles, "Only AIs with open work" removes finished lanes
  (lane numbers unchanged); "Copy map summary" puts every lane on the clipboard and writes nothing.
* History › Timeline draws the open project's ledger events in the 5.x palette (Midnight and Daylight).
* ``AIWB_SCREENSHOT_DIR=dir`` writes ``home_<theme>.png``, ``projects_<theme>.png`` and ``history_<theme>.png``.
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
from aiwb.ui import ui_map
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
    subprocess.run(["import", "-window", "root", "-crop", geo, "+repage", str(Path(out) / name)], timeout=30)


def plan(ctl) -> None:
    p = ctl.project
    with p.store.transaction("polish smoke") as s:
        for i in (1, 2, 3):
            aid = f"agent-p{i}"
            s["agents"][aid] = normalize_agent({"agent_id": aid, "role": "implementer", "name": f"Builder {i}",
                                                "template_id": ""})
    cols: list[list[str]] = [[], []]
    for i in (1, 2, 3):
        for k in (0, 1):
            t = p.tasks.create({"title": f"B{i} step {k + 1}", "objective": "o", "owner_agent_id": f"agent-p{i}",
                                "scope": {"include": [f"m{i}/{k}/**"]}, "acceptance_criteria": ["ok"]})
            cols[k].append(t["task_id"])
    for k, label in enumerate(("0.1.0", "0.2.0")):
        p.timeline.propose_version({"label": label, "task_ids": cols[k]})
    with p.store.transaction("polish smoke: B2 finished") as s:  # Builder 2 is done; one step of B1 is done
        for tid, t in s["tasks"].items():
            if t["owner_agent_id"] == "agent-p2" or tid == cols[0][0]:
                t["status"] = "done"


def section_labels(tree: dict, page: str) -> list[str]:
    rail = next(c for c in tree["children"] if c["label"] == "Rail")
    pg = next(c for c in rail["children"] if c["label"] == page)
    return [c["label"] for c in pg["children"] if c["kind"] == "section"]


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="aiwb-v5-polish-") as temp:
        os.environ["LOCALAPPDATA"] = str(Path(temp) / "appdata")
        first = Path(temp) / "Alpha site"
        first.mkdir()
        (first / "a.py").write_text("x = 1\n", encoding="utf-8")
        project = Path(temp) / "Polish project"
        project.mkdir()
        (project / "main.py").write_text("print(1)\n", encoding="utf-8")
        root = tk.Tk()
        root.geometry("1440x900+0+0")
        app = wb.WorkbenchApp(root)
        for n in ("showinfo", "showwarning", "showerror"):
            setattr(wb.messagebox, n, lambda *a, **k: None)
        clip: list[str] = []
        app._copy_text_to_clipboard = lambda text: clip.append(text)  # type: ignore[method-assign]
        try:
            app.set_workspace(first, focus_project=True)
            wait_for_project_ready(app, root, first)
            app.set_workspace(project, focus_project=True)
            wait_for_project_ready(app, root, project)
            app.shell.show("workbench")
            settle(root)
            ctl = app.workspace_window.wc.ctl
            plan(ctl)
            state_file = project / ".workbench" / "v2" / "state.json"
            before = state_file.read_bytes() if state_file.exists() else b""

            # -- one job per page (App Map of the live app)
            app.shell.prefs.set_mode("advanced")
            tree = ui_map.extract(app)
            home = section_labels(tree, "Home")
            assert home == ["Mission Map", "Map view", "Task details", "Next step"], home
            assert "Project" in section_labels(tree, "Settings"), section_labels(tree, "Settings")  # 5.13.0
            assert "Projects" not in [c["label"] for c in tree["children"][1]["children"]], "Projects left the rail"
            assert not ui_map.audit(tree), ui_map.audit(tree)

            # -- Toolbar › project switcher › All projects…: the library as cards (5.13.0: its own window)
            items = app.switcher_items()
            assert [lab for lab, _f, _o in items][0] == "Polish project" and items[0][2], items
            assert "Alpha site" in [lab for lab, _f, _o in items], items
            app.open_all_projects()
            settle(root)
            cards = app.project_cards
            paths = [r["path"] for r in cards.rows]
            assert paths[0] == str(project.resolve()) and str(first.resolve()) in paths, paths
            assert cards.rows[0]["state"] == "Active", cards.rows[0]
            app._project_card_selected(str(first.resolve()))
            assert app.projects_tree.selection() == (str(first.resolve()),), app.projects_tree.selection()
            app.project_search_var.set("alpha")
            settle(root)
            assert [r["path"] for r in cards.rows] == [str(first.resolve())], cards.rows
            app.project_search_var.set("")
            settle(root)
            assert len(cards.rows) == 2, cards.rows
            app.projects_win.withdraw()

            # -- Home › Map view
            app.shell.show("home")
            app.refresh_mission(ctl.state(), force=True)
            settle(root)
            m = app.mission.model
            assert len(m["lanes"]) == 3 and m["counts"]["done"] == 3, (len(m["lanes"]), m["counts"])
            app.mission_hide_done_var.set(True)
            m = app.mission_apply_view()
            assert all(n["state"] != "done" for ln in m["lanes"] for n in ln["nodes"]), m["lanes"]
            app.mission_open_only_var.set(True)
            m = app.mission_apply_view()
            assert [ln["number"] for ln in m["lanes"]] == [1, 3], [ln["number"] for ln in m["lanes"]]
            assert "2 done" not in app.mission_summary_var.get() and "3 done" in app.mission_summary_var.get()
            text = app.mission_copy_summary()
            assert clip and clip[-1] == text and "AI 2 (Builder 2)" in text and "B3 step 2" in text, text
            app.mission_hide_done_var.set(False)
            app.mission_open_only_var.set(False)
            m = app.mission_apply_view()
            assert len(m["lanes"]) == 3, m["lanes"]

            # -- History › Timeline, both themes
            for theme in ("dark", "light"):
                app.shell.prefs.set_theme(theme)
                settle(root)
                app.shell.show("history")
                model = app.refresh_history_timeline()
                assert model is not None and model["events"], "History › Timeline shows the project's events"
                assert "event(s)" in app.history_tl_var.get(), app.history_tl_var.get()
                from aiwb.ui.tokens5 import palette5
                assert app.history_tl.cget("background") == palette5(theme)["panel"], theme
                tag = "midnight" if theme == "dark" else "daylight"
                shot(root, f"history_{tag}.png")
                app.shell.show("home")
                shot(root, f"home_{tag}.png")
                app.shell.show("settings")
                shot(root, f"settings_{tag}.png")
            after = state_file.read_bytes() if state_file.exists() else b""
            assert after == before, "5.7.0 views read the project state, never write it"

            # -- 5.13.0: Toolbar › "<name> ▾" — the real menu: recent projects (open one marked), All projects…, Reveal
            tb = app.shell.toolbar
            assert tb.project_btn.text_lbl.cget("text") == "Polish project", tb.project_btn.text_lbl.cget("text")
            rows = tb.fill_project_menu()
            assert rows[-2:] == ["All projects…", "Reveal folder"] and "Alpha site" in rows, rows
            menu = tb.project_menu
            labels = {menu.entrycget(i, "label"): i for i in range(int(menu.index("end")) + 1)
                      if menu.type(i) == "command"}
            assert "● Polish project" in labels, labels
            app.shell.show("agents")
            menu.invoke(labels["    Alpha site"])
            wait_for_project_ready(app, root, first)
            settle(root)
            assert app.workspace.resolve() == first.resolve() and app.shell.current == "home", (app.workspace,
                                                                                                 app.shell.current)
            assert tb.project_var.get() == "Alpha site", tb.project_var.get()
            tb.fill_project_menu()
            labels = {menu.entrycget(i, "label"): i for i in range(int(menu.index("end")) + 1)
                      if menu.type(i) == "command"}
            menu.invoke(labels["All projects…"])
            settle(root)
            assert app.projects_win.state() != "withdrawn", "All projects… shows the library window"
            app.projects_win.protocol("WM_DELETE_WINDOW")  # closing only hides it
            app.projects_win.withdraw()
            menu.invoke(labels["    Polish project"])
            wait_for_project_ready(app, root, project)
            settle(root)
            assert tb.project_var.get() == "Polish project" and app.shell.current == "home"
            print("5.7.0 polish: Home = active project, switcher menu + All projects = library cards, Map view, History timeline: PASS")
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass


if __name__ == "__main__":
    main()
