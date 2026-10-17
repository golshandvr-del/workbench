from __future__ import annotations
import tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
import restore_service as rs

class RestoreServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)/'project'; self.root.mkdir()
        self.backups=Path(self.tmp.name)/'backups'; self.backups.mkdir()
    def tearDown(self): self.tmp.cleanup()
    def _apply_tx(self, rel, before, after):
        target=self.root/rel; target.parent.mkdir(parents=True,exist_ok=True)
        if before is not None: target.write_bytes(before)
        change=SimpleNamespace(path=rel,target=target,exists=before is not None,original_bytes=before)
        backup=self.backups/'tx1'; backup.mkdir()
        if before is not None:
            bp=backup/rel; bp.parent.mkdir(parents=True,exist_ok=True); bp.write_bytes(before)
        target.write_bytes(after)
        manifest=rs.write_apply_manifest(self.root,backup,[change],'a'*32)
        return rs.list_transactions(self.root,self.backups)[0]
    def test_restore_existing_file_and_restore_itself_is_undoable(self):
        tx=self._apply_tx('src/a.txt',b'old',b'new')
        p=rs.preview_restore(self.root,tx); self.assertEqual(p[0]['status'],'ready')
        result=rs.restore_selected(self.root,tx,{'src/a.txt'})
        self.assertEqual((self.root/'src/a.txt').read_bytes(),b'old')
        self.assertTrue(Path(result['restore_manifest']).is_file())
        tx2=next(x for x in rs.list_transactions(self.root,self.backups) if x['transaction_id']==result['restore_id'])
        self.assertEqual(rs.preview_restore(self.root,tx2)[0]['status'],'ready')
        rs.restore_selected(self.root,tx2,{'src/a.txt'})
        self.assertEqual((self.root/'src/a.txt').read_bytes(),b'new')
    def test_new_file_restore_deletes_only_if_hash_matches(self):
        tx=self._apply_tx('new.txt',None,b'created')
        (self.root/'new.txt').write_bytes(b'user edit')
        self.assertIn('conflict',rs.preview_restore(self.root,tx)[0]['status'])
        with self.assertRaises(rs.RestoreError): rs.restore_selected(self.root,tx,{'new.txt'})
        self.assertEqual((self.root/'new.txt').read_bytes(),b'user edit')
    def test_backup_hash_mismatch_blocks_restore(self):
        tx=self._apply_tx('a.txt',b'old',b'new')
        backup=Path(tx['files'][0]['backup_path']); backup.write_bytes(b'corrupt')
        self.assertIn('blocked',rs.preview_restore(self.root,tx)[0]['status'])
    def test_path_traversal_rejected(self):
        tx=self._apply_tx('a.txt',b'old',b'new')
        tx['files'][0]['path']='../escape'
        with self.assertRaises(rs.RestoreError): rs.preview_restore(self.root,tx)
