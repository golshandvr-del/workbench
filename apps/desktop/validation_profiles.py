"""User-owned, project-local validation profiles for repeatable checks.

Profiles are never synthesized from model output and never run automatically. A saved
profile is reviewed local configuration; each invocation still requires an explicit
UI action and uses the Workbench bounded process runner.
"""
from __future__ import annotations
import json, re, uuid
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

SCHEMA_VERSION=1
MAX_PROFILE_BYTES=256*1024
MAX_STEPS=40
MAX_TIMEOUT=300
PROFILE_FILE='.workbench/validation_profiles.json'

class ProfileError(ValueError): pass

def _validate_profile(raw: Any) -> dict[str, Any]:
    if not isinstance(raw,dict): raise ProfileError('Profile must be a JSON object.')
    allowed={'schema_version','id','name','description','steps','created_at','updated_at'}
    unknown=set(raw)-allowed
    if unknown: raise ProfileError('Unknown profile field(s): '+', '.join(sorted(unknown)))
    if raw.get('schema_version')!=SCHEMA_VERSION: raise ProfileError('Unsupported validation-profile schema version.')
    pid=raw.get('id')
    if not isinstance(pid,str) or not re.fullmatch(r'[0-9a-f]{32}',pid): raise ProfileError('Invalid profile id.')
    name=raw.get('name'); desc=raw.get('description',''); steps=raw.get('steps')
    if not isinstance(name,str) or not name.strip() or len(name)>120: raise ProfileError('Profile name must be 1–120 characters.')
    if not isinstance(desc,str) or len(desc)>2000: raise ProfileError('Profile description is too long.')
    if not isinstance(steps,list) or not 1<=len(steps)<=MAX_STEPS: raise ProfileError(f'Profile must have 1–{MAX_STEPS} steps.')
    clean=[]
    for i,s in enumerate(steps,1):
        if not isinstance(s,dict): raise ProfileError(f'Step {i} must be an object.')
        allowed_step={'id','name','kind','argv','cwd','timeout_seconds','expected_files','manual_note','continue_on_failure'}
        if set(s)-allowed_step: raise ProfileError(f'Step {i} has unknown fields: '+', '.join(sorted(set(s)-allowed_step)))
        kind=s.get('kind')
        if kind not in {'command','manual'}: raise ProfileError(f'Step {i} kind must be command or manual.')
        sid=s.get('id')
        if not isinstance(sid,str) or not re.fullmatch(r'[0-9a-f]{32}',sid): raise ProfileError(f'Step {i} has invalid id.')
        continue_on_failure=s.get('continue_on_failure',False)
        if not isinstance(continue_on_failure,bool): raise ProfileError(f'Step {i} continue_on_failure must be a boolean.')
        step_name=s.get('name')
        if not isinstance(step_name,str) or not step_name.strip() or len(step_name)>160: raise ProfileError(f'Step {i} needs a name.')
        row={'id':sid,'name':step_name.strip(),'kind':kind,'continue_on_failure':continue_on_failure}
        if kind=='command':
            argv=s.get('argv'); cwd=s.get('cwd','.')
            if not isinstance(argv,list) or not argv or len(argv)>100 or any(not isinstance(a,str) or len(a)>4000 or '\x00' in a for a in argv): raise ProfileError(f'Step {i} argv must be a non-empty list of strings.')
            cwd_parts=PurePosixPath(cwd).parts if isinstance(cwd,str) else ()
            if (not isinstance(cwd,str) or not cwd or len(cwd)>500 or '\\' in cwd or ':' in cwd or PureWindowsPath(cwd).is_absolute() or PurePosixPath(cwd).is_absolute() or '..' in cwd_parts): raise ProfileError(f'Step {i} working directory must be relative to the project.')
            timeout=s.get('timeout_seconds',120)
            if isinstance(timeout,bool) or not isinstance(timeout,int) or not 1<=timeout<=MAX_TIMEOUT: raise ProfileError(f'Step {i} timeout must be 1–{MAX_TIMEOUT} seconds.')
            ef=s.get('expected_files',[])
            if not isinstance(ef,list) or len(ef)>40 or any(not isinstance(x,str) or not x or '\\' in x or ':' in x or PureWindowsPath(x).is_absolute() or PurePosixPath(x).is_absolute() or '..' in PurePosixPath(x).parts for x in ef): raise ProfileError(f'Step {i} expected_files must contain safe relative paths.')
            row.update(argv=argv,cwd=cwd,timeout_seconds=timeout,expected_files=ef)
        else:
            note=s.get('manual_note','')
            if not isinstance(note,str) or len(note)>2000: raise ProfileError(f'Step {i} manual note is invalid.')
            row['manual_note']=note
        clean.append(row)
    return {'schema_version':SCHEMA_VERSION,'id':pid,'name':name.strip(),'description':desc,'steps':clean,
            'created_at':str(raw.get('created_at',''))[:80],'updated_at':str(raw.get('updated_at',''))[:80]}

def profile_path(root: Path) -> Path:
    root=root.resolve(strict=True)
    meta=root/'.workbench'
    if meta.is_symlink(): raise ProfileError('Project metadata directory is a symbolic link.')
    if meta.exists() and not meta.is_dir(): raise ProfileError('Project metadata path is not a directory.')
    path=meta/'validation_profiles.json'
    if path.is_symlink(): raise ProfileError('Validation profile file is a symbolic link.')
    return path

def load_profiles(root: Path) -> list[dict[str, Any]]:
    path=profile_path(root)
    if not path.exists(): return []
    if path.stat().st_size>MAX_PROFILE_BYTES: raise ProfileError('Validation profile file exceeds the size limit.')
    try: data=json.loads(path.read_text(encoding='utf-8'))
    except (OSError,UnicodeError,json.JSONDecodeError) as exc: raise ProfileError(f'Cannot read validation profiles: {exc}') from exc
    if not isinstance(data,dict) or data.get('schema_version')!=SCHEMA_VERSION or not isinstance(data.get('profiles'),list): raise ProfileError('Validation profile store has an unsupported format.')
    profiles=[_validate_profile(x) for x in data['profiles']]
    ids=[x['id'] for x in profiles]
    if len(set(ids))!=len(ids): raise ProfileError('Duplicate validation profile ids.')
    return profiles

def save_profiles(root: Path, profiles: list[dict[str, Any]]) -> Path:
    path=profile_path(root)
    if not isinstance(profiles,list) or len(profiles)>100: raise ProfileError('Too many validation profiles.')
    clean=[_validate_profile(x) for x in profiles]
    if len({x['id'] for x in clean})!=len(clean): raise ProfileError('Duplicate validation profile ids.')
    path.parent.mkdir(parents=True,exist_ok=True)
    data=json.dumps({'schema_version':SCHEMA_VERSION,'profiles':clean},ensure_ascii=False,indent=2).encode('utf-8')
    if len(data)>MAX_PROFILE_BYTES: raise ProfileError('Validation profile store exceeds the size limit.')
    import os,tempfile
    fd,tmp=tempfile.mkstemp(prefix='.aiwb-profile-',dir=str(path.parent))
    try:
        with os.fdopen(fd,'wb') as f: f.write(data); f.flush(); os.fsync(f.fileno())
        if path.is_symlink(): raise ProfileError('Validation profile file became a symbolic link.')
        os.replace(tmp,path)
    except Exception:
        try: os.unlink(tmp)
        except OSError: pass
        raise
    return path

def new_profile(name: str, steps: list[dict[str, Any]], description: str='') -> dict[str, Any]:
    from datetime import datetime
    now=datetime.now().astimezone().isoformat(timespec='seconds')
    normalized=[]
    for step in steps:
        item=dict(step); item.setdefault('id',uuid.uuid4().hex); normalized.append(item)
    return _validate_profile({'schema_version':SCHEMA_VERSION,'id':uuid.uuid4().hex,'name':name,'description':description,'steps':normalized,'created_at':now,'updated_at':now})
