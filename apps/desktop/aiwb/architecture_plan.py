"""Validated, round-trippable architecture plans for the project wizard."""
from __future__ import annotations
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

PROTOCOL = "workbench-architecture-v1"
MAX_BYTES = 512 * 1024
MAX_ITEMS = 100

class ArchitecturePlanError(ValueError):
    pass


def _text(value: Any, field: str, limit: int = 3000, *, required: bool = False) -> str:
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise ArchitecturePlanError(f"{field} must be {'non-empty ' if required else ''}text of at most {limit} characters.")
    return value.strip()


def _list(value: Any, field: str, limit: int = MAX_ITEMS) -> list[Any]:
    if not isinstance(value, list) or len(value) > limit:
        raise ArchitecturePlanError(f"{field} must be a list of at most {limit} items.")
    return value


def validate_plan(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict): raise ArchitecturePlanError("Architecture plan must be one JSON object.")
    if raw.get("protocol") != PROTOCOL: raise ArchitecturePlanError(f"Expected protocol {PROTOCOL}.")
    allowed = {"protocol", "plan_id", "title", "goal", "constraints", "decisions", "modules", "interfaces", "data_flows", "dependencies", "proposed_files", "risks", "acceptance_criteria", "open_questions", "assumptions", "next_steps", "status", "created_at", "updated_at"}
    unknown = set(raw) - allowed
    if unknown: raise ArchitecturePlanError("Unknown architecture-plan fields: " + ", ".join(sorted(str(x) for x in unknown)))
    title = _text(raw.get("title", ""), "title", 240, required=True)
    goal = _text(raw.get("goal", ""), "goal", 5000, required=True)
    clean: dict[str, Any] = {"protocol": PROTOCOL, "plan_id": _text(raw.get("plan_id", ""), "plan_id", 120), "title": title, "goal": goal}
    for field in ("constraints", "acceptance_criteria", "open_questions", "assumptions", "next_steps"):
        values = _list(raw.get(field, []), field, 100)
        clean[field] = [_text(x, f"{field}[{i}]", 2000, required=True) for i, x in enumerate(values)]
    object_fields = {
        "decisions": ({"topic", "choice", "rationale", "alternatives"}, {"topic": 240, "choice": 1000, "rationale": 3000, "alternatives": 1500}),
        "modules": ({"name", "path", "responsibilities", "depends_on"}, {"name": 240, "path": 500, "responsibilities": 2500}),
        "interfaces": ({"name", "from", "to", "contract"}, {"name": 240, "from": 500, "to": 500, "contract": 3000}),
        "data_flows": ({"name", "source", "destination", "description"}, {"name": 240, "source": 500, "destination": 500, "description": 2500}),
        "dependencies": ({"name", "purpose", "version_policy", "optional"}, {"name": 240, "purpose": 1200, "version_policy": 500}),
        "proposed_files": ({"path", "action", "purpose"}, {"path": 500, "purpose": 1500}),
        "risks": ({"description", "mitigation", "severity"}, {"description": 2000, "mitigation": 2000, "severity": 40}),
    }
    for field, (keys, limits) in object_fields.items():
        rows = _list(raw.get(field, []), field, 100)
        out = []
        for i, row in enumerate(rows):
            if not isinstance(row, dict) or set(row) - keys: raise ArchitecturePlanError(f"{field}[{i}] has an unsupported shape.")
            item: dict[str, Any] = {}
            for key in keys:
                if key not in row:
                    if key in {"alternatives", "depends_on"}: item[key] = []
                    elif key == "optional": item[key] = False
                    elif key == "severity": item[key] = "medium"
                    else: item[key] = ""
                    continue
                value = row[key]
                if key in {"alternatives", "depends_on"}:
                    seq = _list(value, f"{field}[{i}].{key}", 40)
                    item[key] = [_text(x, f"{field}[{i}].{key}[{j}]", 500) for j, x in enumerate(seq)]
                elif key == "optional":
                    if not isinstance(value, bool): raise ArchitecturePlanError(f"{field}[{i}].optional must be boolean.")
                    item[key] = value
                else:
                    item[key] = _text(value, f"{field}[{i}].{key}", limits.get(key, 2000), required=key in {"topic", "choice", "name", "description", "path"})
            if field in {"modules", "proposed_files"}:
                _validate_relative_path(item["path"], f"{field}[{i}].path")
            if field == "proposed_files" and item.get("action") not in {"create", "modify", "delete", "rename", "move", "review"}:
                raise ArchitecturePlanError(f"proposed_files[{i}].action is unsupported.")
            out.append(item)
        clean[field] = out
    status = raw.get("status", "draft")
    if status not in {"draft", "proposed", "approved", "blocked", "complete"}: raise ArchitecturePlanError("status is unsupported.")
    clean["status"] = status
    clean["created_at"] = _text(raw.get("created_at", ""), "created_at", 80)
    clean["updated_at"] = _text(raw.get("updated_at", ""), "updated_at", 80)
    encoded = json.dumps(clean, ensure_ascii=False).encode("utf-8")
    if len(encoded) > MAX_BYTES: raise ArchitecturePlanError("Architecture plan exceeds the 512 KB size limit.")
    return clean


def _validate_relative_path(value: str, field: str) -> None:
    if not value or "\\" in value or "\x00" in value or ":" in value or PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute() or any(p in {"", ".", ".."} for p in PurePosixPath(value).parts):
        raise ArchitecturePlanError(f"{field} must be a safe project-relative path.")
    blocked = {".git", ".workbench", ".ssh", ".aws", ".azure", ".gnupg"}
    if any(p.casefold() in blocked for p in PurePosixPath(value).parts): raise ArchitecturePlanError(f"{field} targets a protected path.")
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
    for part in PurePosixPath(value).parts:
        if any(c in part for c in '<>"|?*') or part.endswith((" ", ".")) or part.split(".", 1)[0].upper() in reserved:
            raise ArchitecturePlanError(f"{field} contains a Windows-invalid path component: {part}")


def parse_plan(text: str) -> dict[str, Any]:
    if not isinstance(text, str) or not text.strip(): raise ArchitecturePlanError("Paste or load one complete architecture-plan JSON object.")
    if len(text.encode("utf-8", errors="replace")) > MAX_BYTES: raise ArchitecturePlanError("Input exceeds the architecture plan size limit.")
    try: data = json.loads(text.lstrip("\ufeff"))
    except json.JSONDecodeError as exc: raise ArchitecturePlanError(f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc
    return validate_plan(data)


def new_plan(title: str, goal: str) -> dict[str, Any]:
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    return validate_plan({"protocol": PROTOCOL, "plan_id": "", "title": title, "goal": goal, "constraints": [], "decisions": [], "modules": [], "interfaces": [], "data_flows": [], "dependencies": [], "proposed_files": [], "risks": [], "acceptance_criteria": [], "open_questions": [], "assumptions": [], "next_steps": [], "status": "draft", "created_at": now, "updated_at": now})


def plan_path(root: Path) -> Path:
    root = root.resolve(strict=True)
    meta = root / ".workbench"
    if meta.is_symlink() or (meta.exists() and not meta.is_dir()): raise ArchitecturePlanError("Project metadata path is not a safe directory.")
    target = meta / "architecture_plan.json"
    if target.is_symlink(): raise ArchitecturePlanError("Architecture plan file cannot be a symbolic link.")
    return target


def save_plan(root: Path, plan: dict[str, Any]) -> Path:
    clean = validate_plan(plan)
    target = plan_path(root); target.parent.mkdir(parents=True, exist_ok=True)
    clean["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    data = json.dumps(clean, ensure_ascii=False, indent=2).encode("utf-8")
    fd, tmp = tempfile.mkstemp(prefix=".aiwb-architecture-", dir=str(target.parent))
    try:
        with os.fdopen(fd, "wb") as stream: stream.write(data); stream.flush(); os.fsync(stream.fileno())
        if target.is_symlink(): raise ArchitecturePlanError("Architecture plan path became a symbolic link.")
        os.replace(tmp, target)
    except Exception:
        try: os.unlink(tmp)
        except OSError: pass
        raise
    return target


def load_plan(root: Path) -> dict[str, Any] | None:
    target = plan_path(root)
    if not target.is_file(): return None
    if target.stat().st_size > MAX_BYTES: raise ArchitecturePlanError("Saved architecture plan exceeds the size limit.")
    try: return parse_plan(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as exc: raise ArchitecturePlanError(f"Cannot read architecture plan: {exc}") from exc


def schema_contract() -> str:
    """Return the canonical model-facing architecture-plan shape."""
    template = {
        "protocol": PROTOCOL, "plan_id": "short-id", "title": "Plan title", "goal": "What this architecture must achieve",
        "constraints": ["Hard constraints and non-goals"],
        "decisions": [{"topic": "Decision area", "choice": "Chosen option", "rationale": "Why", "alternatives": ["Alternative and trade-off"]}],
        "modules": [{"name": "Module/service name", "path": "relative/module/path.py", "responsibilities": "Single cohesive responsibility", "depends_on": ["Other module name"]}],
        "interfaces": [{"name": "Interface name", "from": "Producer module", "to": "Consumer module", "contract": "Input/output, ownership, errors, and compatibility rules"}],
        "data_flows": [{"name": "Flow name", "source": "Source", "destination": "Destination", "description": "When/how the data moves"}],
        "dependencies": [{"name": "package/tool", "purpose": "Why required", "version_policy": "Supported version range or standard-library-only", "optional": False}],
        "proposed_files": [{"path": "relative/path.ext", "action": "create", "purpose": "What it owns"}],
        "risks": [{"description": "Risk", "mitigation": "Mitigation", "severity": "low|medium|high"}],
        "acceptance_criteria": ["Observable, testable condition"], "open_questions": [], "assumptions": [], "next_steps": [], "status": "proposed",
    }
    return json.dumps(template, ensure_ascii=False, indent=2)


def render_plan_context(plan: dict[str, Any]) -> str:
    p = validate_plan(plan)
    return ("## Approved / current architecture plan context\n" + json.dumps(p, ensure_ascii=False, indent=2) +
            "\nTreat this plan as project context, not as authorization to apply proposed file operations. If implementation reveals a material conflict, explain it and propose a revised plan before applying high-impact changes.")


def render_plan_summary(plan: dict[str, Any]) -> str:
    p = validate_plan(plan)
    lines = [p["title"], p["goal"], f"Status: {p['status']}", f"Modules: {len(p['modules'])} · decisions: {len(p['decisions'])} · files proposed: {len(p['proposed_files'])}"]
    for module in p["modules"][:30]: lines.append(f"• {module['path']} — {module['name']}: {module['responsibilities']}")
    for item in p["proposed_files"][:30]: lines.append(f"• [{item['action']}] {item['path']} — {item['purpose']}")
    if p["open_questions"]: lines += ["Open questions:", *[f"? {x}" for x in p["open_questions"][:20]]]
    return "\n".join(lines)
