"""Handoff protocol and Response-Inbox connection (roadmap 1.18.0 / slice 2C).

A handoff moves a task from one agent/chat to another *without* the previous
chat history: the prompt contains the mission, acceptance criteria, accepted
decisions, outputs of prerequisites, the previous handoff and the expected
delivery format. The answer carries an ``AIWB_HANDOFF`` manifest block (JSON)
next to the normal AIWB file blocks. Parsing never writes project files.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .attempts import AttemptService
from .models import HANDOFF_OUTCOMES, SCHEMA_VERSION, ModelError, check_transition, now_utc
from .store import ProjectStore, emit, next_id, require

BLOCK_RE = re.compile(r"(?s)<<<AIWB_HANDOFF>>>\s*(.*?)\s*<<<AIWB_END_HANDOFF>>>")
MAX_LIST = 50


# How files must be delivered (3.9.1 / mobile 1.0.1). Chat apps render text outside code blocks as Markdown, so
# indentation and backticks are lost when the answer is copied. A four-backtick fence keeps the body verbatim
# (inner ``` blocks stay intact); the header has no body attribute, so a copy that lost its fences still parses.
FILE_RULES = [
    "- Files: one AIWB file block per file, complete files only. Wrap every file body in a fence of FOUR backticks (````)"
    " so the chat app keeps indentation and backticks when the answer is copied:",
    "<<<AIWB_FILE path=\"relative/path.ext\" action=\"write\">>>", "````", "(the complete file)", "````", "<<<AIWB_END_FILE>>>",
]

# 5.10.0 (A13): the other two answer formats of the New Project wizard. Workbench reads all three (and Markdown with
# file names) whatever was chosen; the choice only decides what the prompt asks for.
JSON_RULES = [
    "- Files: answer with ONE JSON object (it may sit in a ```json block) and nothing else after it:",
    '{"attempt_id": "<the AIWB_ATTEMPT_ID above>", "files": [{"path": "relative/path.ext", "content": "the complete '
    'file"}], "handoff": {<the manifest fields below>}}',
    "- Complete files only; escape newlines and quotes as JSON requires. No comments.",
]
ZIP_RULES = [
    "- Files: put every file in ONE downloadable ZIP with the project's folder layout (relative paths, no top folder "
    "needed), plus a file AIWB_HANDOFF.json at the ZIP root holding the manifest below.",
    "- In the chat, give the download link and repeat the manifest block below as text.",
    "- If you cannot create files, use AIWB file blocks instead:",
    *FILE_RULES[1:],
]


def format_rules(state: dict[str, Any], agent_id: str = "") -> list[str]:
    """The delivery rules for the answer format the user chose (per AI, else for the project; default AIWB)."""
    agent = (state.get("agents") or {}).get(agent_id) or {}
    fmt = agent.get("answer_format") or (state.get("settings") or {}).get("answer_format") or "aiwb"
    return {"json": JSON_RULES, "zip": ZIP_RULES}.get(fmt, FILE_RULES)


def find_manifest(text: str) -> dict[str, Any] | None:
    m = BLOCK_RE.search(text or "")
    if not m:
        return None
    body = m.group(1).strip()
    fence = re.match(r"(?s)^`{3,}\s*json\s*\n(.*?)\n`{3,}$", body)
    if fence:
        body = fence.group(1)
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ModelError(f"AIWB_HANDOFF manifest is not valid JSON: {exc.msg} (line {exc.lineno})") from None
    if not isinstance(data, dict):
        raise ModelError("AIWB_HANDOFF manifest must be a JSON object")
    return data


def _list(v: Any) -> list[str]:
    if not isinstance(v, list):
        return []
    return [str(x)[:1000] for x in v if isinstance(x, (str, int, float)) and str(x).strip()][:MAX_LIST]


class HandoffService:
    def __init__(self, store: ProjectStore) -> None:
        self.store = store
        self.attempts = AttemptService(store)

    def list(self, task_id: str = "") -> list[dict[str, Any]]:
        items = self.store.load()["handoffs"].values()
        return sorted([h for h in items if not task_id or h["task_id"] == task_id], key=lambda h: h["handoff_id"])

    def get(self, handoff_id: str) -> dict[str, Any] | None:
        return self.store.load()["handoffs"].get(handoff_id)

    def prepare(self, task_id: str, to_agent_id: str, *, from_agent_id: str = "", base_commit_sha: str = "",
                base_revision: str = "", expected_paths: list[str] | None = None, note: str = "") -> dict[str, Any]:
        """Create handoff + a fresh attempt for the target agent. Returns the handoff (with ``prompt``)."""
        state = self.store.load()
        task = state["tasks"].get(task_id)
        if task is None:
            raise ModelError(f"task {task_id} does not exist")
        agent = state["agents"].get(to_agent_id)
        if agent is None or not agent.get("enabled", True):
            raise ModelError(f"target agent {to_agent_id} does not exist or is disabled")
        if task["status"] in ("draft", "proposed", "blocked", "cancelled", "superseded", "done"):
            raise ModelError(f"{task_id} is {task['status']}; it must be ready or in progress for a handoff")
        prev = [h for h in state["handoffs"].values() if h["task_id"] == task_id and h["status"] == "accepted"]
        previous = sorted(prev, key=lambda h: h["handoff_id"])[-1] if prev else None
        att = self.attempts.create(task_id, agent_id=to_agent_id, kind="handoff", expected_paths=expected_paths,
                                   base_revision=base_revision,
                                   parent_attempt_id=(previous or {}).get("attempt_id", ""))
        with self.store.transaction("prepare handoff") as s:
            hid = next_id(s, "handoff")
            t = s["tasks"][task_id]
            h = {"schema_version": SCHEMA_VERSION, "handoff_id": hid, "project_id": s["project_id"],
                 "task_id": task_id, "task_revision": t["task_revision"], "attempt_id": att["attempt_id"],
                 "from_agent_id": from_agent_id or (previous or {}).get("to_agent_id", ""), "to_agent_id": to_agent_id,
                 "previous_handoff_id": (previous or {}).get("handoff_id", ""),
                 "base_state_revision": int(s["state_revision"]) + 1, "base_commit_sha": base_commit_sha,
                 "status": "prepared", "outcome": "", "summary": "", "completed_items": [], "unresolved_items": [],
                 "assumptions": [], "decision_requests": [], "artifact_refs": [], "validation_claims": [],
                 "verified_evidence_ids": [], "recommended_next_action": "", "source_response_id": "",
                 "issues": [], "note": note[:2000], "created_at": now_utc(), "updated_at": now_utc()}
            s["attempts"][att["attempt_id"]]["handoff_id"] = hid
            s["attempts"][att["attempt_id"]]["status"] = "prompt_ready"
            h["prompt"] = build_prompt(s, h, previous)
            s["handoffs"][hid] = h
            emit(s, "handoff_prepared", handoff_id=hid, task_id=task_id, to_agent_id=to_agent_id)
        return h

    def mark_exported(self, handoff_id: str, prompt_text: str = "") -> dict[str, Any]:
        h = self.get(handoff_id)
        if h is None:
            raise ModelError(f"handoff {handoff_id} does not exist")
        self.attempts.export(h["attempt_id"])
        with self.store.transaction("export handoff") as s:
            h = require(s, "handoffs", handoff_id)
            if prompt_text and prompt_text != h["prompt"]:
                h["prompt_edited"] = True
                h["prompt"] = prompt_text[:400_000]
            check_transition("handoff", h["status"], "prompt_exported")
            h["status"] = "prompt_exported"
            h["exported_at"] = now_utc()
            emit(s, "handoff_exported", handoff_id=handoff_id)
            return h

    def ingest(self, handoff_id: str, response_id: str, text: str, *, file_hashes: dict[str, str] | None = None,
               parse_ok: bool = True, current_commit: str = "", declared_attempt: str = "") -> dict[str, Any]:
        """Attach an Inbox response: parse the manifest, reconcile IDs/revisions, record model claims.

        ``file_hashes`` are the files Workbench itself parsed from the same answer (path → sha256);
        they become artifact refs. Nothing is applied.
        """
        issues: list[str] = []
        try:
            manifest = find_manifest(text) or {}
            if not manifest:
                issues.append("no AIWB_HANDOFF manifest; delivery summary unavailable (files are still kept)")
        except ModelError as exc:
            manifest, parse_ok = {}, parse_ok and bool(file_hashes)
            issues.append(str(exc))
        state = self.store.load()
        h0 = state["handoffs"].get(handoff_id)
        if h0 is None:
            raise ModelError(f"handoff {handoff_id} does not exist")
        claimed_attempt = declared_attempt or str(manifest.get("attempt_id", ""))
        if claimed_attempt and claimed_attempt != h0["attempt_id"]:
            other = state["attempts"].get(claimed_attempt)
            raise ModelError(f"this answer belongs to attempt {claimed_attempt}"
                             + (f" (task {other['task_id']})" if other else "")
                             + f", not to {handoff_id} ({h0['attempt_id']}). It stays in the Inbox; nothing was linked.")
        for key, want in (("task_id", h0["task_id"]), ("handoff_id", handoff_id)):
            if manifest.get(key) and str(manifest[key]) != want:
                raise ModelError(f"manifest {key} {manifest[key]!r} does not match {want!r}; nothing was linked.")
        self.attempts.attach_response(h0["attempt_id"], response_id, parsed=parse_ok)
        stale_reasons = []
        task = state["tasks"][h0["task_id"]]
        if int(task["task_revision"]) != int(h0["task_revision"]):
            stale_reasons.append(f"task changed to revision {task['task_revision']} after this handoff (revision {h0['task_revision']})")
        if manifest.get("task_revision") not in (None, "") and str(manifest["task_revision"]) != str(h0["task_revision"]):
            stale_reasons.append(f"answer is for task revision {manifest['task_revision']}")
        if current_commit and h0["base_commit_sha"] and current_commit != h0["base_commit_sha"]:
            stale_reasons.append(f"project commit moved from {h0['base_commit_sha'][:10]} to {current_commit[:10]}")
        if task.get("active_attempt_id") != h0["attempt_id"]:
            stale_reasons.append("a newer attempt is active for this task (late answer)")
        outcome = manifest.get("outcome") if manifest.get("outcome") in HANDOFF_OUTCOMES else ("partial" if issues else "")
        with self.store.transaction("ingest handoff") as s:
            h = require(s, "handoffs", handoff_id)
            for step in ("response_received", "parsed"):
                if step == "parsed" and not parse_ok:
                    break
                if h["status"] in ("prompt_exported", "prepared", "response_received"):
                    if h["status"] == "prepared":
                        check_transition("handoff", "prepared", "prompt_exported")
                        h["status"] = "prompt_exported"
                    if h["status"] != step:
                        check_transition("handoff", h["status"], step)
                        h["status"] = step
            h.update(source_response_id=response_id, outcome=outcome or h["outcome"],
                     summary=str(manifest.get("summary", ""))[:4000],
                     completed_items=_list(manifest.get("completed_items")),
                     unresolved_items=_list(manifest.get("unresolved_items")),
                     assumptions=_list(manifest.get("assumptions")),
                     decision_requests=_list(manifest.get("decision_requests")),
                     validation_claims=_list(manifest.get("validation_claims")),
                     recommended_next_action=str(manifest.get("recommended_next_action", ""))[:1000],
                     updated_at=now_utc())
            arts = []
            for path, sha in sorted((file_hashes or {}).items()):
                aid = next_id(s, "artifact")
                art = {"artifact_id": aid, "logical_path": path, "sha256": sha, "media_type": "text/plain",
                       "source_response_id": response_id, "handoff_id": handoff_id, "attempt_id": h["attempt_id"]}
                s["artifacts"][aid] = art
                arts.append(art)
            h["artifact_refs"] = arts
            expected = s["attempts"][h["attempt_id"]].get("expected_paths") or []
            missing = [p for p in expected if p not in (file_hashes or {})]
            if missing:
                h["unresolved_items"] = list(dict.fromkeys(h["unresolved_items"] + [f"missing file: {p}" for p in missing]))
                if h["outcome"] == "complete":
                    h["outcome"] = "partial"
                issues.append(f"{len(missing)} expected file(s) missing: {', '.join(missing)}")
            claims_text = "; ".join(h["validation_claims"])
            if claims_text:
                eid = next_id(s, "evidence")
                s["evidence"][eid] = {
                    "schema_version": SCHEMA_VERSION, "evidence_id": eid, "type": "model_report", "subject_type": "task",
                    "subject_id": h["task_id"], "attempt_id": h["attempt_id"], "task_revision": h["task_revision"],
                    "source": {"kind": "model", "run_id": "", "commit_sha": ""}, "result": "claimed", "verified": False,
                    "verification_method": "unverified model claim", "summary": claims_text[:2000],
                    "observed_at_utc": now_utc(), "state_revision": int(s["state_revision"]) + 1,
                    "artifact_sha256": "", "details": {"handoff_id": handoff_id}}
                emit(s, "evidence_recorded", evidence_id=eid, subject_id=h["task_id"], verified=False, kind="model_report")
            h["issues"] = issues
            if stale_reasons and h["status"] in ("parsed", "response_received"):
                target = "stale" if any("late answer" in r for r in stale_reasons) else "reconciliation_required"
                if h["status"] == "response_received" and target == "reconciliation_required":
                    target = "stale"
                check_transition("handoff", h["status"], target)
                h["status"] = target
                h["stale_reasons"] = stale_reasons
            elif h["status"] == "parsed":
                check_transition("handoff", "parsed", "reconciled")
                h["status"] = "reconciled"
            emit(s, "handoff_ingested", handoff_id=handoff_id, response_id=response_id, status=h["status"],
                 artifacts=len(arts))
            return h

    def resolve(self, handoff_id: str, accept: bool, reason: str = "") -> dict[str, Any]:
        """User decision. Accepting a handoff never applies files and never marks the task done."""
        with self.store.transaction("resolve handoff") as s:
            h = require(s, "handoffs", handoff_id)
            if accept and h["status"] in ("stale", "reconciliation_required"):
                if not reason.strip():
                    raise ModelError("accepting a stale handoff needs an explicit reconciliation note")
                check_transition("handoff", h["status"], "reconciled")
                h["status"] = "reconciled"
            target = "accepted" if accept else "rejected"
            check_transition("handoff", h["status"], target)
            h["status"] = target
            h["resolution"] = {"accepted": accept, "reason": reason[:2000], "at": now_utc()}
            att = s["attempts"].get(h["attempt_id"])
            if att and att["status"] in ("parsed", "reconciliation_required", "ready_for_review", "stale"):
                if att["status"] in ("parsed", "reconciliation_required") and accept:
                    att["status"] = "ready_for_review"
                if att["status"] == "parsed" and not accept:
                    att["status"] = "rejected"
                elif att["status"] in ("ready_for_review", "stale", "reconciliation_required"):
                    att["status"] = "accepted" if accept else "rejected"
            for other in s["handoffs"].values():
                if accept and other["task_id"] == h["task_id"] and other["handoff_id"] != handoff_id \
                        and other["status"] == "accepted":
                    other["status"] = "superseded"
            t = s["tasks"][h["task_id"]]
            if accept and t["status"] == "in_progress" and h["outcome"] in ("complete", "partial"):
                t["status"] = "in_review"
                emit(s, "task_status", task_id=t["task_id"], old="in_progress", new="in_review",
                     why=f"handoff {handoff_id} accepted ({h['outcome']})")
            if accept and h["outcome"] in ("blocked", "needs_decision") and t["status"] == "in_progress":
                t["status"] = "blocked" if h["outcome"] == "blocked" else "needs_decision"
                t["blocked_reason"] = "; ".join(h["unresolved_items"] or h["decision_requests"])[:500]
                emit(s, "task_status", task_id=t["task_id"], old="in_progress", new=t["status"], why="handoff outcome")
            emit(s, "handoff_" + target, handoff_id=handoff_id)
            return h


def _section(title: str, lines: list[str]) -> list[str]:
    return ["", "## " + title] + (lines or ["- (none)"])


def build_prompt(s: dict[str, Any], h: dict[str, Any], previous: dict[str, Any] | None) -> str:
    """Self-contained prompt: works in a fresh chat with no history (spec 11.4)."""
    t = s["tasks"][h["task_id"]]
    agent = s["agents"][h["to_agent_id"]]
    decisions = [d for d in s["decisions"].values() if d["status"] == "accepted"
                 and (not d["affected_task_ids"] or h["task_id"] in d["affected_task_ids"])]
    rejected = [d for d in s["decisions"].values() if d["status"] == "rejected" and h["task_id"] in d["affected_task_ids"]]
    deps = [s["tasks"][d] for d in t.get("depends_on", []) if d in s["tasks"]]
    dep_lines = []
    for d in deps:
        last = sorted([x for x in s["handoffs"].values() if x["task_id"] == d["task_id"] and x["status"] == "accepted"],
                      key=lambda x: x["handoff_id"])
        dep_lines.append(f"- {d['task_id']} {d['title']} — status {d['status']}"
                         + (f"; delivered: {last[-1]['summary'][:400]}" if last and last[-1]["summary"] else ""))
        for a in (last[-1]["artifact_refs"] if last else [])[:20]:
            dep_lines.append(f"  - artifact {a['logical_path']} sha256 {a['sha256'][:16]}…")
    lines = [f"AIWB_ATTEMPT_ID: {h['attempt_id']}",
             "(Repeat the line above as the first line of your answer.)", "",
             f"# AI Workbench handoff {h['handoff_id']} — you are {agent['name']} ({agent['agent_id']}, role {agent['role']})",
             "You have NO access to earlier chats. Everything you may rely on is below. Do not assume anything else."]
    from .agent_hub import note_lines  # roadmap 5.6.0: the owner's memory note of this AI rides along
    lines += _section("1. Your role", [f"- Purpose: {agent['purpose']}"] + [f"- {i}" for i in agent["instructions"]]
                      + note_lines(s, agent["agent_id"]))
    lines += _section("2. Mission", [f"- Task {t['task_id']} revision {t['task_revision']}: {t['title']}",
                                     f"- Objective: {t['objective']}",
                                     f"- Project state revision {h['base_state_revision']}"
                                     + (f", base commit {h['base_commit_sha']}" if h['base_commit_sha'] else "")])
    lines += _section("3. Acceptance criteria and limits",
                      [f"- [ ] {c}" for c in t["acceptance_criteria"]]
                      + [f"- Scope include: {', '.join(t['scope']['include']) or '(not restricted)'}",
                         f"- Scope exclude: {', '.join(t['scope']['exclude']) or '(none)'}",
                         f"- Deliverables: {', '.join(t['deliverables']) or '(see objective)'}"])
    lines += _section("4. Accepted decisions (binding)",
                      [f"- {d['decision_id']} {d['title']}: {d['decision']}" for d in decisions]
                      + [f"- REJECTED {d['decision_id']} {d['title']}: {d['rationale']} — do not propose it again"
                         for d in rejected])
    lines += _section("5. Prerequisites and their outputs", dep_lines)
    if previous:
        lines += _section(f"6. Previous handoff {previous['handoff_id']} ({previous['outcome'] or 'n/a'})",
                          [f"- Summary: {previous['summary'] or '(none)'}"]
                          + [f"- Done: {x}" for x in previous["completed_items"]]
                          + [f"- Open: {x}" for x in previous["unresolved_items"]]
                          + [f"- Assumption: {x}" for x in previous["assumptions"]]
                          + [f"- Claimed (NOT verified): {x}" for x in previous["validation_claims"]])
    else:
        lines += _section("6. Previous handoff", ["- This is the first handoff for this task."])
    lines += _section("7. Relevant files", [f"- {p}" for p in t.get("context_refs", [])]
                      + ["- If you need a file that is not here, answer ONLY with an AIWB_CONTEXT_REQUEST."])
    lines += _section("8. Conflicts / do not assume", (t.get("flags") or [])
                      + ["- Do not claim that you ran tests or builds; Workbench records real evidence separately."])
    if h.get("note"):
        lines += _section("Note from the user", [h["note"]])
    lines += _section("9. Expected delivery", [
        *format_rules(s, h["to_agent_id"]),
        "- Then exactly one manifest block:",
        "<<<AIWB_HANDOFF>>>",
        json.dumps({"schema_version": "1.0", "handoff_id": h["handoff_id"], "task_id": h["task_id"],
                    "task_revision": h["task_revision"], "attempt_id": h["attempt_id"],
                    "outcome": "complete|partial|blocked|needs_decision|failed", "summary": "…",
                    "completed_items": ["done and delivered"], "unresolved_items": ["not done"],
                    "assumptions": ["what you assumed"], "decision_requests": ["what the user must decide"],
                    "validation_claims": ["what you believe works (unverified)"],
                    "recommended_next_action": "…"}, ensure_ascii=False, indent=1),
        "<<<AIWB_END_HANDOFF>>>",
        "- Keep separate: done, proposed, not run, needs decision."])
    return "\n".join(lines)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
