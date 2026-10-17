import os, tempfile, tkinter as tk
from pathlib import Path
from gui_smoke_helpers import wait_for_project_ready
with tempfile.TemporaryDirectory() as tmp:
    os.environ['LOCALAPPDATA'] = str(Path(tmp) / 'AppData')
    import AI_Workbench as wb
    root = tk.Tk()
    app = wb.WorkbenchApp(root)
    root.update()
    wb.messagebox.showinfo = lambda *args, **kwargs: None
    wb.messagebox.showwarning = lambda *args, **kwargs: None
    app.new_project()
    root.update()
    dialogs=[w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]
    assert dialogs, 'new project dialog did not open'
    dlg=dialogs[-1]
    def descendants(widget):
        result=[]
        for child in widget.winfo_children():
            result.append(child)
            result.extend(descendants(child))
        return result
    entries=[w for w in descendants(dlg) if isinstance(w, tk.Entry) or w.winfo_class() == 'TEntry']
    assert len(entries) >= 3, f'expected name, parent and description entries, got {len(entries)}'
    entries[0].insert(0, 'Wizard Smoke Project')
    entries[1].delete(0, 'end'); entries[1].insert(0, tmp)
    entries[2].insert(0, 'Wizard integration test')
    buttons=[w for w in descendants(dlg) if isinstance(w, tk.Button) or w.winfo_class() == 'TButton']
    create=next((b for b in buttons if 'Create project' in str(b.cget('text'))),None)
    assert create is not None, 'create button not found'
    create.invoke()
    root.update()
    project=Path(tmp)/'Wizard Smoke Project'
    assert project.is_dir(), 'project directory was not created'
    assert app.workspace == project.resolve(), 'new project did not become active'
    wait_for_project_ready(app, root, project)
    assert (project/'.workbench'/'project.json').is_file()
    assert app.projects_tree.exists(str(project.resolve()))
    root.destroy()
print('New Project wizard GUI integration: PASS')
