"""Project-local, auditable storage for AI Workbench prompt/response turns.

This module deliberately depends only on the Python standard library so it can be
used by the installed single-folder desktop application without additional packages.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
MAX_ENTRIES = 500
MAX_PROMPT_CHARS = 500_000
MAX_OUTPUT_CHARS = 12 * 1024 * 1024
MAX_NORMALIZED_OUTPUT_BYTES = 24 * 1024 * 1024
MAX_ENTRY_BYTES = MAX_NORMALIZED_OUTPUT_BYTES + 2_000_000
MAX_INDEX_BYTES = 4 * 1024 * 1024
MAX_ERROR_CHARS = 30_000
ENTRY_ID_RE = re.compile(r"^[0-9a-f]{32}$")


class ConversationStoreError(RuntimeError):
    """A safe, user-displayable conversation history error."""


def _safe_paths(root: Path, *, create: bool = False) -> tuple[Path, Path, Path]:
    try:
        project = root.expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ConversationStoreError("The active project folder is unavailable.") from exc
    if not project.is_dir():
        raise ConversationStoreError("The active project path is not a directory.")
    metadata = project / ".workbench"
    if metadata.is_symlink():
        raise ConversationStoreError("The project's .workbench folder is a symbolic link; history access was blocked.")
    if metadata.exists() and not metadata.is_dir():
        raise ConversationStoreError("The project's .workbench path is not a directory.")
    base = metadata / "conversation_history"
    entries = base / "entries"
    for candidate in (base, entries):
        if candidate.is_symlink():
            raise ConversationStoreError(f"Conversation history path is a symbolic link: {candidate.name}")
        if candidate.exists() and not candidate.is_dir():
            raise ConversationStoreError(f"Conversation history path is not a directory: {candidate.name}")
    if create:
        entries.mkdir(parents=True, exist_ok=True)
    try:
        base.resolve(strict=False).relative_to(project)
        entries.resolve(strict=False).relative_to(project)
    except (ValueError, OSError, RuntimeError) as exc:
        raise ConversationStoreError("Conversation history path escapes the project folder.") from exc
    return project, base, entries


def _atomic_json_write(path: Path, value: Any) -> None:
    raw = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
    fd, temp_name = tempfile.mkstemp(prefix=".aiwb-history-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if path.is_symlink():
            raise ConversationStoreError("Refusing to replace a symbolic link in conversation history.")
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def _index_path(base: Path) -> Path:
    return base / "index.json"


def _entry_path(entries_dir: Path, entry_id: str) -> Path:
    if not ENTRY_ID_RE.fullmatch(entry_id):
        raise ConversationStoreError("Invalid conversation history entry id.")
    return entries_dir / f"{entry_id}.json"


def _bounded_json_read(path: Path, limit: int, *, description: str) -> Any:
    """Read JSON only up to a fixed byte limit, including if the file grows while being read."""
    if path.is_symlink():
        raise ConversationStoreError(f"Refusing to read a symbolic link for {description}.")
    try:
        with path.open("rb") as stream:
            raw_bytes = stream.read(limit + 1)
    except OSError as exc:
        raise ConversationStoreError(f"Could not read {description}: {exc}") from exc
    if len(raw_bytes) > limit:
        raise ConversationStoreError(f"{description.capitalize()} exceeds the {limit:,}-byte safety limit.")
    try:
        return json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ConversationStoreError(f"{description.capitalize()} contains invalid UTF-8 JSON.") from exc


def _read_index(root: Path) -> dict[str, Any]:
    _project, base, _entries = _safe_paths(root, create=False)
    path = _index_path(base)
    if path.is_symlink():
        raise ConversationStoreError("Conversation history index is a symbolic link.")
    if not path.is_file():
        return {"schema_version": SCHEMA_VERSION, "entries": []}
    try:
        raw = _bounded_json_read(path, MAX_INDEX_BYTES, description="conversation history index")
    except ConversationStoreError as exc:
        raise ConversationStoreError("Conversation history index could not be read safely. Preserve the file and inspect it before continuing.") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != SCHEMA_VERSION or not isinstance(raw.get("entries"), list):
        raise ConversationStoreError("Conversation history index has an unsupported or damaged format.")
    if len(raw["entries"]) > MAX_ENTRIES:
        raise ConversationStoreError(f"Conversation history index exceeds the {MAX_ENTRIES}-entry limit.")
    clean: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw["entries"]:
        if not isinstance(item, dict):
            continue
        entry_id = item.get("id")
        if not isinstance(entry_id, str) or not ENTRY_ID_RE.fullmatch(entry_id) or entry_id in seen:
            continue
        seen.add(entry_id)
        clean.append(dict(item))
    return {"schema_version": SCHEMA_VERSION, "entries": clean}


def _write_index(root: Path, entries: list[dict[str, Any]]) -> None:
    _project, base, _entries_dir = _safe_paths(root, create=True)
    safe_entries = entries[-MAX_ENTRIES:]
    _atomic_json_write(_index_path(base), {"schema_version": SCHEMA_VERSION, "entries": safe_entries})


def list_history_metadata(root: Path) -> list[dict[str, Any]]:
    """Return lightweight index rows for the history tree without reading prompt/output bodies."""
    return [dict(item) for item in _read_index(root)["entries"]]


def list_history(root: Path) -> list[dict[str, Any]]:
    """Return valid full history entries, ordered oldest to newest."""
    _project, _base, entries_dir = _safe_paths(root, create=False)
    index = _read_index(root)
    results: list[dict[str, Any]] = []
    for meta in index["entries"]:
        try:
            path = _entry_path(entries_dir, str(meta["id"]))
            if path.is_symlink() or not path.is_file():
                continue
            entry = _bounded_json_read(path, MAX_ENTRY_BYTES, description="conversation history entry")
            if isinstance(entry, dict) and entry.get("id") == meta["id"]:
                results.append(entry)
        except (OSError, UnicodeError, json.JSONDecodeError, KeyError, ConversationStoreError):
            continue
    return results


def get_history_entry(root: Path, entry_id: str) -> dict[str, Any] | None:
    _project, _base, entries_dir = _safe_paths(root, create=False)
    path = _entry_path(entries_dir, entry_id)
    if path.is_symlink() or not path.is_file():
        return None
    try:
        entry = _bounded_json_read(path, MAX_ENTRY_BYTES, description="conversation history entry")
    except ConversationStoreError as exc:
        # Invalid JSON means the entry is not displayable. Oversize/read errors are raised so the UI can explain them.
        if "invalid utf-8 json" in str(exc).casefold():
            return None
        raise
    return entry if isinstance(entry, dict) and entry.get("id") == entry_id else None


def _persist_entry(root: Path, entry: dict[str, Any], *, add_to_index: bool) -> dict[str, Any]:
    _project, _base, entries_dir = _safe_paths(root, create=True)
    entry_id = str(entry.get("id", ""))
    path = _entry_path(entries_dir, entry_id)
    if path.is_symlink():
        raise ConversationStoreError("Refusing to write through a symbolic link in conversation history.")
    index = _read_index(root)
    entries = list(index["entries"])
    found = any(item.get("id") == entry_id for item in entries)
    if add_to_index and not found and len(entries) >= MAX_ENTRIES:
        raise ConversationStoreError(f"Conversation history reached the {MAX_ENTRIES}-entry limit. Export or remove old history before creating more entries.")
    raw = json.dumps(entry, ensure_ascii=False, indent=2).encode("utf-8")
    if len(raw) > MAX_NORMALIZED_OUTPUT_BYTES + 2_000_000:
        raise ConversationStoreError("This conversation entry exceeds the local history size limit. Shorten the prompt/output or export it separately.")
    _atomic_json_write(path, entry)
    found = False
    metadata = {key: entry.get(key) for key in (
        "id", "task_id", "sequence", "label", "kind", "stage", "output_format", "title", "feature",
        "project_version", "created_at", "updated_at", "status", "response_status", "parent_entry_id",
        "task_summary", "project_history_saved", "project_history_saved_at", "project_history_saved_sha256",
        "version_record_id",
    )}
    for i, item in enumerate(entries):
        if item.get("id") == entry_id:
            entries[i] = metadata
            found = True
            break
    if add_to_index and not found:
        if len(entries) >= MAX_ENTRIES:
            raise ConversationStoreError(f"Conversation history reached the {MAX_ENTRIES}-entry limit. Export or remove old history before creating more entries.")
        entries.append(metadata)
    elif not found:
        raise ConversationStoreError("The conversation entry is no longer indexed; refusing to recreate history silently.")
    _write_index(root, entries)
    return entry


def create_prompt_entry(
    root: Path, *, task_id: str, task_text: str, prompt_text: str, stage: str, output_format: str,
    kind: str = "prompt", title: str = "", feature: str = "", project_version: str = "",
    parent_entry_id: str = "", status: str = "Awaiting model response", app_version: str = "",
) -> dict[str, Any]:
    prompt = str(prompt_text)
    if len(prompt) > MAX_PROMPT_CHARS:
        raise ConversationStoreError(f"Prompt exceeds the {MAX_PROMPT_CHARS:,}-character history limit.")
    entries = list_history_metadata(root)
    task_entries = [item for item in entries if str(item.get("task_id", "")) == str(task_id)]
    sequence = max((int(item.get("sequence", 0) or 0) for item in task_entries), default=0) + 1
    now = datetime.now().isoformat(timespec="seconds")
    entry = {
        "schema_version": SCHEMA_VERSION,
        "id": uuid.uuid4().hex,
        "task_id": str(task_id)[:160],
        "sequence": sequence,
        "label": "Start" if sequence == 1 else f"Step {sequence - 1}",
        "kind": str(kind)[:40],
        "stage": str(stage)[:160],
        "output_format": str(output_format)[:160],
        "title": (str(title).strip() or (str(task_text).strip().splitlines()[0][:160] if str(task_text).strip() else "Untitled task"))[:240],
        "feature": str(feature)[:240],
        "project_version": str(project_version)[:80],
        "version_record_id": "",
        "project_history_saved": False,
        "project_history_saved_at": "",
        "project_history_saved_sha256": "",
        "app_version": str(app_version)[:40],
        "task_summary": str(task_text)[:6000],
        "prompt_text": prompt,
        "model_output": "",
        "normalized_output": None,
        "manual_error": None,
        "notes": "",
        "requested_context_ranges": [],
        "requested_user_uploads": [],
        "requested_project_history": [],
        "response_artifact": None,
        "response_status": "Not received",
        "status": str(status)[:120],
        "parent_entry_id": str(parent_entry_id)[:32],
        "created_at": now,
        "updated_at": now,
    }
    return _persist_entry(root, entry, add_to_index=True)


def create_prompt_revision(
    root: Path, source_entry_id: str, prompt_text: str, *, app_version: str = "",
) -> dict[str, Any]:
    """Create an editable-body revision as a new linked step; never overwrite the source prompt."""
    source = get_history_entry(root, source_entry_id)
    if source is None:
        raise ConversationStoreError("The source prompt step is no longer available.")
    prompt = str(prompt_text)
    if not prompt.strip():
        raise ConversationStoreError("An edited prompt revision cannot be empty.")
    if len(prompt) > MAX_PROMPT_CHARS:
        raise ConversationStoreError(f"Edited prompt exceeds the {MAX_PROMPT_CHARS:,}-character history limit.")
    revision = create_prompt_entry(
        root, task_id=str(source.get("task_id", "")), task_text=str(source.get("task_summary", "")),
        prompt_text=prompt, stage=str(source.get("stage", "")), output_format=str(source.get("output_format", "")),
        kind="prompt-revision", title=("Edited revision · " + str(source.get("title", "Prompt")))[:240],
        feature=str(source.get("feature", "")), project_version=str(source.get("project_version", "")),
        parent_entry_id=source_entry_id, app_version=app_version or str(source.get("app_version", "")),
        status="Prompt revision saved; awaiting model response",
    )
    try:
        update_context_requests(
            root, revision["id"],
            ranges=source.get("requested_context_ranges", []) if isinstance(source.get("requested_context_ranges", []), list) else [],
            uploads=source.get("requested_user_uploads", []) if isinstance(source.get("requested_user_uploads", []), list) else [],
            history_requests=source.get("requested_project_history", []) if isinstance(source.get("requested_project_history", []), list) else [],
        )
    except Exception:
        # The prompt body is already durably saved; a failure to copy ancillary context metadata must
        # not silently delete/overwrite that revision. Caller can inspect the source step.
        raise
    return get_history_entry(root, revision["id"]) or revision


def update_history_entry(root: Path, entry_id: str, changes: dict[str, Any]) -> dict[str, Any]:
    entry = get_history_entry(root, entry_id)
    if entry is None:
        raise ConversationStoreError("The selected conversation history entry is no longer available.")
    editable = {"title", "feature", "project_version", "notes", "label"}
    for key, value in changes.items():
        if key not in editable:
            raise ConversationStoreError(f"History field is not editable: {key}")
        if not isinstance(value, str):
            raise ConversationStoreError(f"History field must be text: {key}")
        limit = 240 if key in {"title", "feature", "label"} else 4000 if key == "notes" else 80
        entry[key] = value.strip()[:limit]
    entry["updated_at"] = datetime.now().isoformat(timespec="seconds")
    return _persist_entry(root, entry, add_to_index=False)


def update_context_requests(
    root: Path, entry_id: str, *, ranges: list[dict[str, Any]], uploads: list[dict[str, str]],
    history_requests: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Persist all model-requested context against the exact prompt/response step."""
    entry = get_history_entry(root, entry_id)
    if entry is None:
        raise ConversationStoreError("The selected conversation history entry is no longer available.")
    entry["requested_context_ranges"] = list(ranges[:100])
    entry["requested_user_uploads"] = list(uploads[:100])
    if history_requests is not None:
        entry["requested_project_history"] = list(history_requests[:20])
    entry["updated_at"] = datetime.now().isoformat(timespec="seconds")
    return _persist_entry(root, entry, add_to_index=False)


def update_entry_status(root: Path, entry_id: str, status: str, *, response_status: str | None = None) -> dict[str, Any]:
    entry = get_history_entry(root, entry_id)
    if entry is None:
        raise ConversationStoreError("The selected conversation history entry is no longer available.")
    entry["status"] = str(status)[:120]
    if response_status is not None:
        entry["response_status"] = str(response_status)[:120]
    entry["updated_at"] = datetime.now().isoformat(timespec="seconds")
    return _persist_entry(root, entry, add_to_index=False)


def attach_model_output(
    root: Path, entry_id: str, *, output_text: str = "", normalized_output: dict[str, Any] | None = None,
    status: str = "Response recorded", artifact: dict[str, Any] | None = None, error: str = "",
) -> dict[str, Any]:
    entry = get_history_entry(root, entry_id)
    if entry is None:
        raise ConversationStoreError("There is no active prompt history entry to associate this model output with.")
    raw = str(output_text)
    if len(raw) > MAX_OUTPUT_CHARS:
        raw = raw[:MAX_OUTPUT_CHARS] + "\n\n[History note: output was truncated at the local history limit.]"
    # A checkpoint describes one exact prompt/output pair. If the stored response changes or
    # a later validation fails, remove the checkpoint mark rather than letting stale metadata lie.
    previous_raw = str(entry.get("model_output", ""))
    previous_normalized = entry.get("normalized_output")
    output_changed = raw != previous_raw
    if normalized_output is not None and normalized_output != previous_normalized:
        output_changed = True
    if error or output_changed:
        entry["project_history_saved"] = False
        entry["project_history_saved_sha256"] = ""
        entry["project_history_saved_at"] = ""
    entry["model_output"] = raw
    if normalized_output is not None:
        encoded = json.dumps(normalized_output, ensure_ascii=False).encode("utf-8")
        if len(encoded) > MAX_NORMALIZED_OUTPUT_BYTES:
            raise ConversationStoreError("The parsed model output is too large to save in conversation history.")
        entry["normalized_output"] = normalized_output
    if artifact is not None:
        entry["response_artifact"] = {str(k): v for k, v in artifact.items() if k in {"filename", "sha256", "size_bytes", "files_imported", "uncompressed_bytes", "control_manifest_present", "missing_root_readme"}}
    entry["response_status"] = str(status)[:120]
    entry["status"] = str(status)[:120]
    if error:
        entry["import_error"] = str(error)[:MAX_ERROR_CHARS]
    elif str(status).startswith(("Validated", "Files Applied", "Actions queued", "Context plan received")):
        # A newly validated response supersedes an earlier import failure for this attempt.
        entry.pop("import_error", None)
    entry["updated_at"] = datetime.now().isoformat(timespec="seconds")
    return _persist_entry(root, entry, add_to_index=False)



def mark_project_history_saved(root: Path, entry_id: str, *, saved: bool = True) -> dict[str, Any]:
    """Mark an existing exact prompt/output pair as an explicit user-curated checkpoint.

    The audit entry itself remains canonical; this avoids duplicating large prompts and
    output bodies while letting users distinguish important successful turns.
    """
    import hashlib

    entry = get_history_entry(root, entry_id)
    if entry is None:
        raise ConversationStoreError("The selected conversation step is no longer available.")
    if saved and not str(entry.get("prompt_text", "")).strip():
        raise ConversationStoreError("This step has no recorded application prompt to save as a project-history checkpoint.")
    if saved and not (str(entry.get("model_output", "")).strip() or entry.get("normalized_output") is not None or entry.get("response_artifact")):
        raise ConversationStoreError("This step has no recorded model output to save as a project-history checkpoint.")
    if saved:
        response_status = str(entry.get("response_status", ""))
        status = str(entry.get("status", ""))
        valid_status = response_status.startswith(("Validated", "Files Applied", "Actions queued")) or status.startswith(("Validated", "Files Applied", "Actions queued"))
        if not valid_status or entry.get("import_error"):
            raise ConversationStoreError("Only a successfully validated response can be marked as a project-history checkpoint. Rejected or errored responses remain in the audit history but cannot be marked as validated checkpoints.")
    entry["project_history_saved"] = bool(saved)
    if saved:
        material = json.dumps({
            "prompt_text": entry.get("prompt_text", ""),
            "model_output": entry.get("model_output", ""),
            "normalized_output": entry.get("normalized_output"),
            "response_artifact": entry.get("response_artifact"),
        }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        entry["project_history_saved_sha256"] = hashlib.sha256(material.encode("utf-8")).hexdigest()
        entry["project_history_saved_at"] = datetime.now().isoformat(timespec="seconds")
    else:
        entry["project_history_saved_sha256"] = ""
        entry["project_history_saved_at"] = ""
    entry["updated_at"] = datetime.now().isoformat(timespec="seconds")
    return _persist_entry(root, entry, add_to_index=False)


def link_project_version(root: Path, entry_id: str, *, version: str, version_record_id: str) -> dict[str, Any]:
    """Attach a durable version identifier to the history step that produced it."""
    entry = get_history_entry(root, entry_id)
    if entry is None:
        raise ConversationStoreError("The source history step for this project version is no longer available.")
    entry["project_version"] = str(version)[:80]
    entry["version_record_id"] = str(version_record_id)[:32]
    entry["updated_at"] = datetime.now().isoformat(timespec="seconds")
    return _persist_entry(root, entry, add_to_index=False)


def reparent_history_entry(root: Path, entry_id: str, new_parent_entry_id: str = "") -> dict[str, Any]:
    """Change tree indentation by changing the parent link; reject cycles and invalid parents."""
    entry = get_history_entry(root, entry_id)
    if entry is None:
        raise ConversationStoreError("The selected history step no longer exists.")
    parent_id = str(new_parent_entry_id or "").strip()
    if parent_id == entry_id:
        raise ConversationStoreError("A history step cannot be its own parent.")
    if parent_id:
        parent = get_history_entry(root, parent_id)
        if parent is None:
            raise ConversationStoreError("The requested parent step does not exist in this project's history.")
        cursor = parent
        seen = {entry_id}
        while cursor:
            cursor_id = str(cursor.get("id", ""))
            if not cursor_id or cursor_id in seen:
                if cursor_id == entry_id:
                    raise ConversationStoreError("This parent change would create a circular history tree.")
                break
            seen.add(cursor_id)
            ancestor_id = str(cursor.get("parent_entry_id", ""))
            if not ancestor_id:
                break
            cursor = get_history_entry(root, ancestor_id)
    entry["parent_entry_id"] = parent_id
    entry["updated_at"] = datetime.now().isoformat(timespec="seconds")
    return _persist_entry(root, entry, add_to_index=False)


def reorder_history_entry(root: Path, entry_id: str, direction: int) -> bool:
    """Move an entry one slot among its siblings without changing chronology/body data."""
    if direction not in {-1, 1}:
        raise ConversationStoreError("History reorder direction must be -1 or 1.")
    index = _read_index(root)
    rows = list(index["entries"])
    pos = next((i for i, item in enumerate(rows) if item.get("id") == entry_id), None)
    if pos is None:
        raise ConversationStoreError("The selected history step is not indexed.")
    row = rows[pos]
    parent_id = str(row.get("parent_entry_id", ""))
    task_id = str(row.get("task_id", ""))
    sibling_positions = [i for i, item in enumerate(rows) if str(item.get("parent_entry_id", "")) == parent_id and (parent_id or str(item.get("task_id", "")) == task_id)]
    sibling_index = sibling_positions.index(pos)
    target_sibling_index = sibling_index + direction
    if target_sibling_index < 0 or target_sibling_index >= len(sibling_positions):
        return False
    target_pos = sibling_positions[target_sibling_index]
    rows[pos], rows[target_pos] = rows[target_pos], rows[pos]
    _write_index(root, rows)
    return True

def record_manual_error(root: Path, entry_id: str, *, stage: str, details: str, file_path: str = "", steps: str = "") -> dict[str, Any]:
    entry = get_history_entry(root, entry_id)
    if entry is None:
        raise ConversationStoreError("No conversation step is selected. Build or select a prompt before reporting its runtime error.")
    details = str(details).strip()
    if not details:
        raise ConversationStoreError("Enter the error message or observed failure before saving it.")
    entry["manual_error"] = {
        "stage": str(stage)[:160], "details": details[:MAX_ERROR_CHARS],
        "file_path": str(file_path)[:500], "steps": str(steps)[:8000],
        "reported_at": datetime.now().isoformat(timespec="seconds"),
    }
    entry["status"] = "Manual error reported"
    entry["updated_at"] = datetime.now().isoformat(timespec="seconds")
    return _persist_entry(root, entry, add_to_index=False)


def delete_history_entry(root: Path, entry_id: str) -> None:
    """Delete one entry and lift its direct children to its parent to preserve a valid tree."""
    _project, _base, entries_dir = _safe_paths(root, create=False)
    path = _entry_path(entries_dir, entry_id)
    parent = get_history_entry(root, entry_id)
    if parent is None:
        raise ConversationStoreError("The selected history entry was not found.")
    parent_id = str(parent.get("parent_entry_id", ""))
    index = _read_index(root)
    entries = list(index["entries"])
    if not any(item.get("id") == entry_id for item in entries):
        raise ConversationStoreError("The selected history entry was not found in the history index.")
    if path.is_symlink():
        raise ConversationStoreError("Refusing to delete a symbolic link in conversation history.")
    # Reparent children first. If a child write fails, retain the parent entry rather than
    # creating a dangling tree link that the UI could silently misrepresent.
    children = [str(item.get("id")) for item in entries if str(item.get("parent_entry_id", "")) == entry_id and str(item.get("id", "")) != entry_id]
    for child_id in children:
        child = get_history_entry(root, child_id)
        if child is None:
            continue
        child["parent_entry_id"] = parent_id
        child["updated_at"] = datetime.now().isoformat(timespec="seconds")
        _persist_entry(root, child, add_to_index=False)
    current_index = _read_index(root)
    remaining = [item for item in current_index["entries"] if item.get("id") != entry_id]
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        raise ConversationStoreError(f"Could not delete history entry: {exc}") from exc
    _write_index(root, remaining)
