"""GUI integration smoke for v1.14 typed-workflow additions (runs under Xvfb)."""
from __future__ import annotations
import os
import tempfile
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from gui_smoke_helpers import wait_for_project_ready


def descendants(widget):
    found = []
    for child in widget.winfo_children():
        found.append(child)
        found.extend(descendants(child))
    return found


with tempfile.TemporaryDirectory() as temp:
    os.environ["LOCALAPPDATA"] = str(Path(temp) / "AppData")
    import AI_Workbench as wb
    from aiwb import architecture_plan, candidate_store

    wb.messagebox.showinfo = lambda *args, **kwargs: None
    wb.messagebox.showwarning = lambda *args, **kwargs: None
    wb.messagebox.showerror = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError(f"Unexpected GUI error: {args}"))

    root = tk.Tk()
    app = wb.WorkbenchApp(root)
    root.update()

    # Architecture plan round-trip inside the New Project Wizard.
    app.new_project()
    root.update()
    wizard = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel) and w.title() == "Create a new project")
    wizard_widgets = descendants(wizard)
    next(b for b in wizard_widgets if isinstance(b, ttk.Button) and b.cget("text") == "Architecture plan…").invoke()
    root.update()
    editor_window = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel) and w.title().startswith("Architecture Plan"))
    editor = next(w for w in descendants(editor_window) if isinstance(w, tk.Text))
    # Exercise edit + validate + explicit save-to-wizard; no project source files are touched.
    plan = architecture_plan.new_plan("Smoke modular project", "Round-trip a reviewed plan through the wizard.")
    plan["modules"] = [{"name": "Domain service", "path": "aiwb/domain.py", "responsibilities": "Own business rules", "depends_on": []}]
    editor.delete("1.0", "end")
    editor.insert("1.0", __import__("json").dumps(plan, indent=2))
    next(b for b in descendants(editor_window) if isinstance(b, ttk.Button) and b.cget("text") == "Validate and save plan").invoke()
    root.update()
    assert not editor_window.winfo_exists(), "validated architecture editor did not close/save to wizard"

    wizard_widgets = descendants(wizard)
    entries = [w for w in wizard_widgets if isinstance(w, (tk.Entry, ttk.Entry))]
    assert len(entries) >= 3, "project wizard form entries not found"
    entries[0].insert(0, "v114 GUI Smoke")
    entries[1].delete(0, "end"); entries[1].insert(0, temp)
    entries[2].insert(0, "Testing v1.14 integration")
    next(b for b in wizard_widgets if isinstance(b, ttk.Button) and b.cget("text") == "Create project").invoke()
    root.update()
    project = Path(temp) / "v114 GUI Smoke"
    wait_for_project_ready(app, root, project)
    saved_plan = architecture_plan.load_plan(project)
    assert saved_plan and saved_plan["modules"][0]["path"] == "aiwb/domain.py", "wizard failed to persist the validated architecture plan"

    # The selected playbook is saved and placed in the actual generated prompt.
    app.task_playbook_var.set("Bug investigation and repair")
    app.task_text.insert("1.0", "Investigate and fix a reproducible project defect.")
    app.build_prompt()
    root.update()
    prompt = app.prompt_output.get("1.0", "end-1c")
    assert "Task playbook: Bug investigation and repair" in prompt, "selected task playbook was not embedded in the prompt"
    assert "Saved project architecture plan" in prompt, "persisted architecture plan was not included as reference context"
    assert app.settings_data.get("task_playbook") == "Bug investigation and repair", "playbook selection was not persisted"

    # Candidate comparison defaults every destination to Skip and performs no mutation.
    payload_a = {"protocol": "workbench-v1", "task_id": "a", "summary": "A", "files": [{"path": "src/demo.py", "content": "A = 1\n"}], "actions": [], "next_steps": [], "completion_status": "in_progress"}
    payload_b = {"protocol": "workbench-v1", "task_id": "b", "summary": "B", "files": [{"path": "src/demo.py", "content": "A = 2\n"}], "actions": [], "next_steps": [], "completion_status": "in_progress"}
    candidate_store.save_candidate(project, name="GPT A", payload=payload_a, raw_response="candidate A", source_format="smoke")
    candidate_store.save_candidate(project, name="Gemini B", payload=payload_b, raw_response="candidate B", source_format="smoke")
    source_path = project / "src" / "demo.py"
    app.compare_response_candidates()
    root.update()
    compare = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel) and w.title().startswith("Compare candidates"))
    combos = [w for w in descendants(compare) if isinstance(w, ttk.Combobox)]
    assert combos and combos[0].get() == "— Skip this path —", "candidate row did not default to Skip"
    assert not source_path.exists(), "candidate comparison changed a project file before approval"
    compare.destroy()

    # The standalone dependency analyzer returns through a main-thread poller.
    app.show_dependency_analysis_window()
    root.update()
    impact = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel) and w.title() == "Static dependency graph and impact hints")
    deadline = time.monotonic() + 5
    status_labels = [w for w in descendants(impact) if isinstance(w, ttk.Label)]
    while time.monotonic() < deadline:
        root.update()
        statuses = []
        for label in status_labels:
            variable_name = str(label.cget("textvariable"))
            if variable_name:
                try: statuses.append(str(root.getvar(variable_name)))
                except tk.TclError: pass
        if any("Finished" in value for value in statuses):
            break
        time.sleep(0.02)
    assert any("Finished" in value for value in statuses), "dependency analysis did not report completion in its window"
    impact.destroy()
    root.update()
    root.destroy()

print("v1.14 architecture wizard + task playbook + candidate comparison + dependency GUI: PASS")
