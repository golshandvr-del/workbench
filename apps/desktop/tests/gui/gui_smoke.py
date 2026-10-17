import os, tempfile, tkinter as tk
from pathlib import Path
from gui_smoke_helpers import wait_for_project_ready
with tempfile.TemporaryDirectory() as tmp:
    os.environ['LOCALAPPDATA'] = str(Path(tmp) / 'AppData')
    import AI_Workbench as wb
    root=tk.Tk()
    app=wb.WorkbenchApp(root)
    root.update()
    assert app.projects_tree.winfo_exists()
    assert app.profile_tab.winfo_exists()
    p=wb.create_project_folder(Path(tmp), 'Smoke Project', 'Smoke description', 'Python desktop application', True)
    app.set_workspace(p, focus_project=True)
    wait_for_project_ready(app, root, p)
    root.update()
    assert app.workspace == p.resolve()
    assert app.projects_tree.exists(str(p.resolve()))
    assert app.profile_vars['languages'].get() == 'Python'
    assert (p / '.workbench' / 'project.json').exists()
    app.output_format_var.set(wb.OUTPUT_FORMAT_GEMINI)
    app.task_text.insert('1.0', 'Build a small GUI demo with tests.')
    app.profile_vars['prompt_stage'].set('Implementation / build')
    app.build_prompt()
    generated_prompt = app.prompt_output.get('1.0', 'end-1c')
    assert 'workbench-files-v1' in generated_prompt
    assert '<<<AIWB_FILE path="src/relative/path.ext" action="write" body="raw">>>' in generated_prompt
    gemini_response = '''<<<AIWB_FILE path="src/generated.py" action="write">>>
````python
def generated() -> bool:
    return True
````
<<<AIWB_END_FILE>>>'''
    root.clipboard_clear()
    root.clipboard_append(gemini_response)
    app.paste_response()
    root.update()
    assert app.pending_changes and app.pending_changes[0].path == 'src/generated.py'
    assert app.pending_response_format == 'AI Workbench file/action blocks'
    if app.pending_diff_window is not None:
        app.pending_diff_window.destroy()
    # Switch to a second workspace and confirm per-project values reload.
    q=wb.create_project_folder(Path(tmp), 'Other Project', 'Other', 'Web application', False)
    app.set_workspace(q, focus_project=True)
    wait_for_project_ready(app, root, q)
    root.update()
    assert app.profile_vars['languages'].get() == 'TypeScript'
    assert app.projects_tree.exists(str(p.resolve())) and app.projects_tree.exists(str(q.resolve()))
    root.destroy()
print('GUI smoke: PASS')
