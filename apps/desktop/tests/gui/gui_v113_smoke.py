"""GUI integration smoke for selective Apply, transaction manifests, Restore Manager and profiles."""
from __future__ import annotations
import json, os, tempfile, tkinter as tk
from pathlib import Path
from unittest.mock import patch
import AI_Workbench as wb
import validation_profiles as vp
from gui_smoke_helpers import wait_for_idle, wait_for_project_ready


def main() -> None:
    with tempfile.TemporaryDirectory(prefix='aiwb-v113-smoke-') as tmp:
        os.environ['LOCALAPPDATA']=str(Path(tmp)/'appdata')
        project=Path(tmp)/'Project with spaces'; project.mkdir()
        (project/'keep.txt').write_text('old keep\n',encoding='utf-8')
        (project/'leave.txt').write_text('must remain\n',encoding='utf-8')
        root=tk.Tk()
        try:
            app=wb.WorkbenchApp(root)
            wb.messagebox.showinfo=lambda *a,**k: None
            wb.messagebox.showwarning=lambda *a,**k: None
            wb.messagebox.showerror=lambda *a,**k: None
            app.set_workspace(project,focus_project=True)
            wait_for_project_ready(app,root,project); root.update()
            app.task_text.insert('1.0','Update keep.txt and create new.txt for selective apply testing.')
            app.build_prompt()
            payload={'protocol':wb.PROTOCOL_V2,'task_id':'selective-smoke','summary':'Selective Apply GUI smoke','files':[
                {'path':'keep.txt','action':'write','content':'new keep\n'},
                {'path':'leave.txt','action':'write','content':'must not change\n'},
                {'path':'new.txt','action':'write','content':'created\n'}], 'actions':[], 'next_steps':[], 'completion_status':'in_progress'}
            app.response_input.delete('1.0','end'); app.response_input.insert('1.0',json.dumps(payload))
            app.preview_response(); root.update()
            assert app.pending_changes and len(app.pending_changes)==3
            app.pending_apply_paths={'keep.txt','new.txt'}
            with patch.object(wb.messagebox,'askyesno',return_value=True): app.apply_pending_changes(app.pending_diff_window)
            root.update(); wait_for_idle(app,root)
            assert (project/'keep.txt').read_text(encoding='utf-8')=='new keep\n'
            assert (project/'new.txt').read_text(encoding='utf-8')=='created\n'
            assert (project/'leave.txt').read_text(encoding='utf-8')=='must remain\n'
            events=wb.read_execution_history(project)
            applied=[e for e in events if e.get('type') in {'files_applied','files_partially_applied'}][-1]
            assert set(applied['files'])=={'keep.txt','new.txt'}
            assert applied.get('transaction_id')
            txs=wb.restore_service.list_transactions(project,app._backup_base_for_workspace(project))
            assert txs and set(item['path'] for item in txs[0]['files'])=={'keep.txt','new.txt'}
            # Restore Manager is a real UI entry point; open it and verify it populates.
            app.open_restore_manager(); root.update()
            dialogs=[w for w in root.winfo_children() if isinstance(w,tk.Toplevel) and 'Restore Manager' in w.title()]
            assert dialogs, 'Restore Manager did not open'
            # Persist and reload a profile without executing it automatically.
            profile=vp.new_profile('Smoke profile',[{'name':'Python version','kind':'command','argv':['python','--version'],'cwd':'.','timeout_seconds':30,'expected_files':[]}])
            vp.save_profiles(project,[profile]); assert vp.load_profiles(project)[0]['name']=='Smoke profile'
            # Restore the selected files through the same service and verify old/new behavior.
            result=wb.restore_service.restore_selected(project,txs[0],{'keep.txt','new.txt'})
            assert (project/'keep.txt').read_text(encoding='utf-8')=='old keep\n'
            assert not (project/'new.txt').exists()
            txs2=wb.restore_service.list_transactions(project,app._backup_base_for_workspace(project))
            assert any(x.get('transaction_id')==result['restore_id'] for x in txs2), 'Restore itself must be reversible'
            print('v1.13 selective Apply + immutable transaction manifest + Restore Manager + validation profile persistence: PASS')
            app.on_close()
        finally:
            try: root.destroy()
            except tk.TclError: pass

if __name__=='__main__': main()
