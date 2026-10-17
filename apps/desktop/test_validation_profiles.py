from __future__ import annotations
import tempfile, unittest
from pathlib import Path
import validation_profiles as vp

class ValidationProfileTests(unittest.TestCase):
    def setUp(self): self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name); (self.root/'.workbench').mkdir()
    def tearDown(self): self.tmp.cleanup()
    def test_save_load_profile(self):
        profile=vp.new_profile('Python tests',[{'name':'Unit tests','kind':'command','argv':['python','-m','unittest'],'cwd':'.','timeout_seconds':60,'expected_files':[]}])
        vp.save_profiles(self.root,[profile]); loaded=vp.load_profiles(self.root)
        self.assertEqual(loaded[0]['name'],'Python tests'); self.assertEqual(loaded[0]['steps'][0]['argv'],['python','-m','unittest'])
    def test_reject_shell_string_as_argv(self):
        with self.assertRaises(vp.ProfileError): vp.new_profile('Bad',[{'name':'step','kind':'command','argv':'python -m unittest','cwd':'.'}])
    def test_reject_absolute_cwd_and_traversal_expected_file(self):
        for step in [
            {'name':'step','kind':'command','argv':['python'],'cwd':'/tmp'},
            {'name':'step','kind':'command','argv':['python'],'cwd':'.','expected_files':['../escape']},
        ]:
            with self.assertRaises(vp.ProfileError): vp.new_profile('Bad',[step])
    def test_reject_unknown_execution_field(self):
        with self.assertRaises(vp.ProfileError): vp.new_profile('Bad',[{'name':'step','kind':'manual','command':'danger'}])
    def test_reject_truthy_string_for_boolean_and_windows_absolute_paths(self):
        with self.assertRaises(vp.ProfileError): vp.new_profile('Bad',[{'name':'step','kind':'manual','continue_on_failure':'false'}])
        with self.assertRaises(vp.ProfileError): vp.new_profile('Bad',[{'name':'step','kind':'command','argv':['python'],'cwd':'C:\\Windows'}])
        with self.assertRaises(vp.ProfileError): vp.new_profile('Bad',[{'name':'step','kind':'command','argv':['python'],'cwd':'.','expected_files':['C:\\temp\\log.txt']}])
