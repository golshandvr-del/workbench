"""Local, bounded candidate storage for comparing alternative model responses."""
from __future__ import annotations
import hashlib
import json
import os
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

MAX_CANDIDATES = 30
MAX_CANDIDATE_BYTES = 12 * 1024 * 1024

class CandidateStoreError(ValueError):
    pass


def _base(root: Path) -> Path:
    root = root.expanduser().resolve(strict=True)
    meta = root / ".workbench"
    if meta.is_symlink() or (meta.exists() and not meta.is_dir()): raise CandidateStoreError("Candidate storage path is not safe.")
    path = meta / "candidates"
    if path.is_symlink() or (path.exists() and not path.is_dir()): raise CandidateStoreError("Candidate directory is not safe.")
    return path


def list_candidates(root: Path) -> list[dict[str, Any]]:
    base = _base(root)
    if not base.is_dir(): return []
    rows=[]
    for path in base.glob("*.json"):
        try:
            if path.is_symlink() or path.stat().st_size > MAX_CANDIDATE_BYTES: continue
            item=json.loads(path.read_text(encoding="utf-8"))
            if isinstance(item,dict) and item.get("schema_version")==1 and isinstance(item.get("payload"),dict):
                item["_path"] = str(path)
                rows.append(item)
        except (OSError, UnicodeError, json.JSONDecodeError): continue
    rows.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
    return rows[:MAX_CANDIDATES]


def save_candidate(root: Path, *, name: str, payload: dict[str, Any], raw_response: str, source_format: str) -> dict[str, Any]:
    if not isinstance(payload,dict) or not isinstance(raw_response,str): raise CandidateStoreError("Candidate payload/response is invalid.")
    if len(raw_response.encode("utf-8",errors="replace"))>MAX_CANDIDATE_BYTES: raise CandidateStoreError("Candidate response is too large.")
    base=_base(root); base.mkdir(parents=True,exist_ok=True)
    if len(list_candidates(root))>=MAX_CANDIDATES: raise CandidateStoreError(f"At most {MAX_CANDIDATES} candidates are retained per project; remove one before saving another.")
    clean_name=" ".join(str(name or "").split())[:160] or "Candidate"
    candidate_id=uuid.uuid4().hex
    created=datetime.now().astimezone().isoformat(timespec="seconds")
    item={"schema_version":1,"id":candidate_id,"name":clean_name,"created_at":created,"source_format":str(source_format)[:200],
          "response_sha256":hashlib.sha256(raw_response.encode("utf-8")).hexdigest(),"payload":payload,"raw_response":raw_response}
    data=json.dumps(item,ensure_ascii=False,separators=(",",":" )).encode("utf-8")
    if len(data)>MAX_CANDIDATE_BYTES: raise CandidateStoreError("Normalized candidate exceeds the storage size limit.")
    dest=base/(candidate_id+".json")
    fd,tmp=tempfile.mkstemp(prefix=".aiwb-candidate-",dir=str(base))
    try:
        with os.fdopen(fd,"wb") as stream: stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(tmp,dest)
    except Exception:
        try: os.unlink(tmp)
        except OSError: pass
        raise
    item["_path"]=str(dest)
    return item


def delete_candidate(root: Path, candidate_id: str) -> None:
    if not isinstance(candidate_id,str) or not candidate_id.isalnum() or len(candidate_id)>80: raise CandidateStoreError("Invalid candidate id.")
    base=_base(root); target=base/(candidate_id+".json")
    if target.is_symlink(): raise CandidateStoreError("Refusing to delete a linked candidate file.")
    target.unlink(missing_ok=True)


def candidate_file_rows(candidate: dict[str, Any]) -> dict[str, dict[str, Any]]:
    payload=candidate.get("payload",{})
    out: dict[str,dict[str,Any]]={}
    for item in payload.get("files",[]) if isinstance(payload,dict) else []:
        if isinstance(item,dict) and isinstance(item.get("path"),str): out[item["path"].casefold()]={**item,"path":item["path"],"candidate_id":candidate.get("id"),"candidate_name":candidate.get("name")}
    for item in payload.get("operations",[]) if isinstance(payload,dict) else []:
        if not isinstance(item,dict): continue
        op_type=item.get("type")
        key=item.get("path") if op_type in {"write","delete"} else item.get("destination_path")
        if isinstance(key,str): out[key.casefold()]={**item,"path":key,"action":op_type,"candidate_id":candidate.get("id"),"candidate_name":candidate.get("name")}
    return out


def merge_candidate_payloads(root_protocol: str, selected_rows: list[dict[str, Any]], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Compose an explicit per-destination selection as workbench-v3 operations.

    Candidate commands/actions are intentionally not merged: a file-level choice must
    never silently import shell commands from a second response.
    """
    from uuid import uuid4
    by_id = {str(c.get("id")): c for c in candidates}
    operations: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in selected_rows:
        candidate = by_id.get(str(row.get("candidate_id")))
        if candidate is None:
            raise CandidateStoreError("A selected candidate is no longer available; reopen comparison.")
        original = row.get("operation")
        if not isinstance(original, dict):
            raise CandidateStoreError("A candidate row lacks its validated operation data.")
        key = str(row.get("path", "")).casefold()
        if not key or key in seen:
            raise CandidateStoreError("Only one candidate may be selected for each destination path.")
        seen.add(key)
        operation = dict(original)
        if operation.get("type") not in {"write", "delete", "rename", "move"}:
            # Backward-compatible candidates use normalized files with action=write.
            action = operation.get("action", "write")
            if action != "write" or not isinstance(operation.get("path"), str) or not isinstance(operation.get("content"), str):
                raise CandidateStoreError("Legacy candidate rows support write operations only; save a workbench-v3 response for Delete/Rename/Move.")
            operation = {"type": "write", "path": operation["path"], "content": operation["content"]}
        # Strip storage-only metadata and keep only fields valid for the selected operation.
        kind = operation.get("type")
        if kind == "write":
            operation = {k: operation[k] for k in ("id", "type", "path", "content") if k in operation}
        elif kind == "delete":
            operation = {k: operation[k] for k in ("id", "type", "path") if k in operation}
        else:
            operation = {k: operation[k] for k in ("id", "type", "source_path", "destination_path") if k in operation}
        # IDs belong to the new merged response, not their source candidate. Generating
        # new IDs prevents two otherwise valid candidates from colliding after composition.
        operation["id"] = "candidate-op-" + uuid4().hex[:10]
        operations.append(operation)
    if not operations:
        raise CandidateStoreError("Select at least one candidate file.")
    return {
        "protocol": "workbench-v3",
        "task_id": "candidate-merge-" + uuid4().hex[:10],
        "summary": "Per-file selection merged from saved response candidates.",
        "operations": operations,
        "actions": [],
        "next_steps": ["Review this merged preview carefully; candidate selection does not imply tests passed."],
        "completion_status": "in_progress",
    }
