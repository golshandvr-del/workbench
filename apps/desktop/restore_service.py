"""Hash-guarded, reversible restore operations for AI Workbench.

The service never trusts manifest paths or backup paths. A restore is permitted only
when the current file still matches the exact post-apply hash recorded for that
transaction. No force-overwrite mode is provided.
"""
from __future__ import annotations
import hashlib, json, os, tempfile, uuid
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA_VERSION = 1
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_FILE_BYTES = 64 * 1024 * 1024

class RestoreError(RuntimeError):
    pass

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def _safe_root(root: Path) -> Path:
    try: result = root.expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc: raise RestoreError('Project root is unavailable.') from exc
    if not result.is_dir(): raise RestoreError('Project root is not a directory.')
    return result

def _safe_rel(root: Path, value: Any) -> tuple[str, Path]:
    if not isinstance(value, str) or not value or '\x00' in value or '\\' in value:
        raise RestoreError('Manifest contains an invalid relative path.')
    p = PurePosixPath(value)
    if p.is_absolute() or any(part in ('', '.', '..') for part in p.parts): raise RestoreError(f'Unsafe restore path: {value}')
    if p.parts[0].casefold() in {'.git', '.workbench', '.ssh', '.aws'}: raise RestoreError(f'Protected path cannot be restored: {value}')
    target = root.joinpath(*p.parts)
    cur = root
    for part in p.parts[:-1]:
        cur = cur / part
        if cur.is_symlink(): raise RestoreError(f'Symbolic-link parent is not allowed: {value}')
    if target.is_symlink(): raise RestoreError(f'Symbolic-link target is not allowed: {value}')
    try: target.resolve(strict=False).relative_to(root)
    except (ValueError, OSError, RuntimeError) as exc: raise RestoreError(f'Restore path escapes project: {value}') from exc
    return p.as_posix(), target

def write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.aiwb-restore-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        if path.is_symlink(): raise RestoreError(f'Refusing to replace symbolic link: {path.name}')
        os.replace(tmp, path)
    except Exception:
        try: os.unlink(tmp)
        except OSError: pass
        raise

def write_apply_manifest(root: Path, backup_dir: Path, changes: list[Any], transaction_id: str, *, task_id: str = '', history_entry_id: str = '', summary: str = '', states: dict[str, dict[str, bytes | None]] | None = None) -> Path:
    """Persist the exact before/after state of every affected path.

    ``states`` is the generalized path ledger used by typed v3 operations. The legacy
    path remains for pre-v1.14 callers and existing tests. An after hash of ``None``
    explicitly means the path is expected to be absent (delete/move source).
    """
    root = _safe_root(root); backup_dir = backup_dir.resolve(strict=True)
    if not transaction_id or any(c not in '0123456789abcdef-' for c in transaction_id.lower()): raise RestoreError('Invalid transaction id.')
    rows = []
    if states is not None:
        if not isinstance(states, dict) or len(states) > 2 * 100:
            raise RestoreError('Transaction path ledger is invalid or exceeds the operation limit.')
        for raw_rel, state in states.items():
            rel, target = _safe_rel(root, raw_rel)
            if not isinstance(state, dict) or set(state) - {'before', 'after'}:
                raise RestoreError(f'Invalid transaction state for {rel}.')
            before, expected_after = state.get('before'), state.get('after')
            if before is not None and not isinstance(before, bytes): raise RestoreError(f'Invalid pre-apply bytes for {rel}.')
            if expected_after is not None and not isinstance(expected_after, bytes): raise RestoreError(f'Invalid post-apply bytes for {rel}.')
            current = target.read_bytes() if target.is_file() else None
            if current != expected_after:
                raise RestoreError(f'Post-apply state does not match the transaction ledger for {rel}; transaction manifest not recorded.')
            existed_before = before is not None
            backup = None
            if existed_before:
                backup_path = backup_dir.joinpath(*rel.split('/'))
                if not backup_path.is_file() or backup_path.is_symlink(): raise RestoreError(f'Pre-apply backup missing for {rel}')
                if sha256_bytes(backup_path.read_bytes()) != sha256_bytes(before): raise RestoreError(f'Pre-apply backup hash mismatch for {rel}')
                backup = str(backup_path)
            rows.append({'path': rel, 'existed_before': existed_before, 'backup_path': backup,
                         'before_sha256': sha256_bytes(before) if before is not None else None,
                         'after_sha256': sha256_bytes(current) if current is not None else None,
                         'before_size': len(before) if before is not None else None,
                         'after_size': len(current) if current is not None else None,
                         'content_kind': 'binary-or-text-bytes'})
    else:
        for change in changes:
            rel, target = _safe_rel(root, change.path)
            current = target.read_bytes() if target.is_file() else None
            if current is None: raise RestoreError(f'Applied file is missing; transaction manifest not recorded: {rel}')
            before = change.original_bytes if change.exists else None
            backup = None
            if change.exists:
                backup_path = backup_dir.joinpath(*rel.split('/'))
                if not backup_path.is_file() or backup_path.is_symlink(): raise RestoreError(f'Pre-apply backup missing for {rel}')
                if sha256_bytes(backup_path.read_bytes()) != sha256_bytes(before or b''): raise RestoreError(f'Pre-apply backup hash mismatch for {rel}')
                backup = str(backup_path)
            rows.append({'path': rel, 'existed_before': bool(change.exists), 'backup_path': backup,
                         'before_sha256': sha256_bytes(before) if before is not None else None,
                         'after_sha256': sha256_bytes(current), 'before_size': len(before) if before is not None else None,
                         'after_size': len(current), 'content_kind': 'binary-or-text-bytes'})
    manifest = {'schema_version': SCHEMA_VERSION, 'transaction_id': transaction_id, 'kind': 'apply',
                'created_at': datetime.now().astimezone().isoformat(timespec='seconds'), 'project_root': str(root),
                'task_id': str(task_id)[:160], 'history_entry_id': str(history_entry_id)[:160], 'summary': str(summary)[:2000], 'files': rows}
    out = backup_dir / 'aiwb-apply-transaction.json'
    write_atomic(out, json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8'))
    return out

def list_transactions(root: Path, backup_base: Path) -> list[dict[str, Any]]:
    root = _safe_root(root); rows=[]
    if not backup_base.is_dir() or backup_base.is_symlink(): return rows
    for manifest_path in backup_base.glob('*/aiwb-apply-transaction.json'):
        try:
            if manifest_path.is_symlink() or manifest_path.stat().st_size > MAX_MANIFEST_BYTES: continue
            data=json.loads(manifest_path.read_text(encoding='utf-8'))
            if not isinstance(data,dict) or data.get('schema_version') != SCHEMA_VERSION or Path(str(data.get('project_root',''))).resolve() != root: continue
            if not isinstance(data.get('files'),list): continue
            data['_manifest_path']=str(manifest_path)
            rows.append(data)
        except (OSError, ValueError, json.JSONDecodeError, RuntimeError): continue
    rows.sort(key=lambda r: str(r.get('created_at','')), reverse=True)
    return rows

def preview_restore(root: Path, transaction: dict[str, Any], selected_paths: set[str] | None = None) -> list[dict[str, Any]]:
    root = _safe_root(root); result=[]
    manifest_path=Path(str(transaction.get('_manifest_path','')))
    if not manifest_path.is_file() or manifest_path.is_symlink(): raise RestoreError('Transaction manifest is unavailable.')
    base=manifest_path.parent.resolve(strict=True)
    for row in transaction.get('files',[]):
        if not isinstance(row,dict): continue
        rel,target=_safe_rel(root,row.get('path'))
        if selected_paths is not None and rel not in selected_paths: continue
        exists=target.is_file()
        digest=None
        if exists:
            if target.stat().st_size > MAX_FILE_BYTES: status='conflict: current file exceeds restore safety limit'
            else: digest=sha256_bytes(target.read_bytes()); status='ready' if digest == row.get('after_sha256') else 'conflict: file changed since Apply'
        else: status='ready' if row.get('after_sha256') is None else 'conflict: file is missing'
        backup_path=None
        if row.get('existed_before'):
            raw=row.get('backup_path')
            if not isinstance(raw,str): status='blocked: required backup path missing'
            else:
                candidate=Path(raw)
                try: candidate.resolve(strict=True).relative_to(base)
                except (ValueError,OSError,RuntimeError): status='blocked: backup path escapes transaction storage'
                else:
                    if candidate.is_symlink() or not candidate.is_file(): status='blocked: required backup is missing'
                    elif candidate.stat().st_size > MAX_FILE_BYTES: status='blocked: backup exceeds safety limit'
                    elif sha256_bytes(candidate.read_bytes()) != row.get('before_sha256'): status='blocked: backup hash mismatch'
                    else: backup_path=candidate
        result.append({'path':rel,'target':target,'status':status,'existed_before':bool(row.get('existed_before')),'backup_path':backup_path,'current_sha256':digest,'after_sha256':row.get('after_sha256'),'before_sha256':row.get('before_sha256')})
    return result

def restore_selected(root: Path, transaction: dict[str, Any], selected_paths: set[str], *, task_id: str = '', history_entry_id: str = '') -> dict[str, Any]:
    root=_safe_root(root)
    if not selected_paths: raise RestoreError('Select at least one restorable file.')
    preview=preview_restore(root,transaction,selected_paths)
    blocked=[x for x in preview if x['status']!='ready']
    if blocked: raise RestoreError('Restore stopped; resolve conflicts before changing files: '+ '; '.join(f"{x['path']} ({x['status']})" for x in blocked))
    # Snapshot the current state first; any failure attempts to return to this state.
    originals={x['path']:(x['target'].read_bytes() if x['target'].is_file() else None) for x in preview}
    completed=[]
    restore_id=uuid.uuid4().hex
    source_manifest=Path(str(transaction['_manifest_path'])).resolve(strict=True)
    backup_base=source_manifest.parent.parent
    restore_backup_dir=backup_base / (datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '-restore-' + restore_id[:8])
    restore_backup_dir.mkdir(parents=True,exist_ok=False)
    restore_rows=[]
    try:
        for item in preview:
            # Recheck hash immediately before each mutation.
            target=item['target']; rel=item['path']
            now=target.read_bytes() if target.is_file() else None
            if (sha256_bytes(now) if now is not None else None) != item['after_sha256']:
                raise RestoreError(f'{rel} changed after restore preview; preview again.')
            before=originals[rel]
            backup_path=None
            if before is not None:
                backup_path=restore_backup_dir.joinpath(*rel.split('/'))
                backup_path.parent.mkdir(parents=True,exist_ok=True)
                write_atomic(backup_path,before)
            if item['existed_before']:
                data=item['backup_path'].read_bytes()
                if sha256_bytes(data)!=item['before_sha256']: raise RestoreError(f'Backup hash changed for {rel}.')
                write_atomic(target,data)
            else:
                if target.is_symlink(): raise RestoreError(f'Refusing to remove symbolic link: {rel}')
                target.unlink(missing_ok=True)
            after=target.read_bytes() if target.is_file() else None
            restore_rows.append({'path':rel,'existed_before':before is not None,'backup_path':str(backup_path) if backup_path else None,
                'before_sha256':sha256_bytes(before) if before is not None else None,'after_sha256':sha256_bytes(after) if after is not None else None,
                'before_size':len(before) if before is not None else None,'after_size':len(after) if after is not None else None,'content_kind':'binary-or-text-bytes'})
            completed.append(rel)
        manifest={'schema_version':SCHEMA_VERSION,'transaction_id':restore_id,'kind':'restore','created_at':datetime.now().astimezone().isoformat(timespec='seconds'),
            'project_root':str(root),'task_id':str(task_id)[:160],'history_entry_id':str(history_entry_id)[:160],'source_transaction_id':transaction.get('transaction_id'),'summary':'Undoable restore transaction','files':restore_rows}
        write_atomic(restore_backup_dir/'aiwb-apply-transaction.json',json.dumps(manifest,ensure_ascii=False,indent=2).encode('utf-8'))
    except Exception as exc:
        rollback_errors=[]
        for rel in reversed(completed):
            target=_safe_rel(root,rel)[1]
            try:
                old=originals[rel]
                if old is None: target.unlink(missing_ok=True)
                else: write_atomic(target,old)
            except Exception as rollback_exc: rollback_errors.append(f'{rel}: {rollback_exc}')
        suffix=(' Rollback errors: '+'; '.join(rollback_errors)) if rollback_errors else ' The pre-restore state was restored where needed.'
        raise RestoreError(f'Restore failed: {exc}.{suffix}') from exc
    return {'restore_id':restore_id,'transaction_id':transaction.get('transaction_id'),'restore_manifest':str(restore_backup_dir/'aiwb-apply-transaction.json'),'restored_files':completed,'created_at':datetime.now().astimezone().isoformat(timespec='seconds'),'status':'Restored; reversible restore transaction recorded'}
