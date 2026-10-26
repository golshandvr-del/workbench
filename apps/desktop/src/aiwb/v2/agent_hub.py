"""Agents hub (roadmap 5.6.0): what each AI is doing, how well it goes, and what to do about it — pure, no Tk.

Everything here reads a V2 state dict and returns plain data; nothing writes state except :func:`set_note`,
which changes a state dict *inside* a store transaction (the caller owns the transaction).

* :func:`agent_stats` — per AI: open / done tasks, rework rate (rejected or repaired deliveries ÷ deliveries),
  average delivery time (prompt prepared → answer received), last activity, current task, workload share.
* :func:`alerts` — *idle* (no open task while others wait), *stuck* (one task in the same stage too long),
  *overloaded* (more than its fair share of the open work) and *scope overlap* (two AIs' open tasks touch the
  same files).
* :func:`rebalance` — which not-yet-started task to move from an overloaded AI to an idle/light one of a
  compatible role; only tasks nobody has started (no attempt) are ever suggested.
* :func:`queue` — the delivery queue of one AI in the order it will work.
* :func:`briefing` — a self-contained sheet to paste as the first message of a fresh chat with that AI.
* notes — a per-AI memory (``state["settings"]["agent_notes"][agent_id]``) added to every prompt it gets.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .models import TERMINAL_TASK, ModelError
from .team import scopes_overlap
from .workflow import task_stage

STUCK_HOURS = 24.0          # same stage for longer than this = stuck
OVERLOAD_FACTOR = 1.5       # more than 1.5 × the fair share of open tasks = overloaded
NOTE_MAX = 2000
# roles that can take each other's implementation work when balancing
COMPATIBLE = {"implementer": {"implementer", "architect"}, "architect": {"architect", "implementer"},
              "reviewer": {"reviewer"}, "researcher": {"researcher", "architect"},
              "project_manager": {"project_manager"}}
WORKING_STAGES = ("ready_to_prepare", "prompt_prepared", "prompt_copied", "waiting_for_response",
                  "context_request_pending", "answer_received", "needs_user_review", "validation_pending")


def _ts(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _hours(a: datetime | None, b: datetime | None) -> float | None:
    if a is None or b is None:
        return None
    return max(0.0, (b - a).total_seconds() / 3600.0)


def _now(now: datetime | None) -> datetime:
    return now or datetime.now(timezone.utc)


def enabled_agents(state: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted((a for a in state["agents"].values() if a.get("enabled", True)),
                  key=lambda a: (a["role"] != "project_manager", a["agent_id"]))


def _owned(state: dict[str, Any], aid: str, *, open_only: bool) -> list[dict[str, Any]]:
    out = [t for t in state["tasks"].values() if t.get("owner_agent_id") == aid]
    if open_only:
        out = [t for t in out if t["status"] not in TERMINAL_TASK and t["status"] not in ("draft",)]
    return sorted(out, key=lambda t: t["task_id"])


def _handoffs_to(state: dict[str, Any], aid: str) -> list[dict[str, Any]]:
    return sorted((h for h in state["handoffs"].values() if h.get("to_agent_id") == aid), key=lambda h: h["handoff_id"])


def _received_at(h: dict[str, Any]) -> datetime | None:
    if h["status"] in ("prepared", "prompt_exported"):
        return None
    return _ts((h.get("resolution") or {}).get("at")) or _ts(h.get("updated_at"))


def _last_activity(state: dict[str, Any], aid: str) -> str:
    stamps = [h.get("updated_at") or h.get("created_at") for h in _handoffs_to(state, aid)]
    stamps += [t.get("updated_at") for t in _owned(state, aid, open_only=False)]
    stamps = [s for s in stamps if _ts(s)]
    return max(stamps, key=lambda s: _ts(s)) if stamps else ""


def agent_stats(state: dict[str, Any], *, now: datetime | None = None) -> list[dict[str, Any]]:
    """One row per enabled AI (the Project Manager first). Numbers only from recorded facts."""
    t_now = _now(now)
    open_total = sum(len(_owned(state, a["agent_id"], open_only=True)) for a in enabled_agents(state))
    rows = []
    for a in enabled_agents(state):
        aid = a["agent_id"]
        open_tasks = _owned(state, aid, open_only=True)
        done = [t for t in _owned(state, aid, open_only=False) if t["status"] == "done"]
        hs = _handoffs_to(state, aid)
        delivered = [h for h in hs if h["status"] not in ("prepared", "prompt_exported")]
        rework = [h for h in delivered if h["status"] == "rejected"
                  or (h.get("previous_handoff_id") and h.get("note", "").lower().startswith("repair"))]
        hours = [x for x in (_hours(_ts(h.get("created_at")), _received_at(h)) for h in delivered) if x is not None]
        stages = sorted((task_stage(state, t["task_id"]) for t in open_tasks),
                        key=lambda s: WORKING_STAGES.index(s["stage"]) if s["stage"] in WORKING_STAGES else 99)
        cur = stages[0] if stages else None
        last = _last_activity(state, aid)
        rows.append({
            "agent_id": aid, "name": a["name"], "role": a["role"],
            "open": len(open_tasks), "done": len(done), "delivered": len(delivered),
            "rework_rate": round(len(rework) / len(delivered), 2) if delivered else 0.0,
            "avg_delivery_hours": round(sum(hours) / len(hours), 1) if hours else None,
            "last_activity": last,
            "idle_hours": round(_hours(_ts(last), t_now), 1) if last else None,
            "current_task_id": cur["task_id"] if cur else "", "current_stage": cur["stage"] if cur else "",
            "load_share": round(len(open_tasks) / open_total, 2) if open_total else 0.0,
            "note": note(state, aid),
        })
    return rows


def _stage_since(state: dict[str, Any], t: dict[str, Any]) -> datetime | None:
    hs = [h for h in state["handoffs"].values() if h["task_id"] == t["task_id"]]
    stamps = [_ts(h.get("updated_at")) for h in hs] + [_ts(t.get("updated_at"))]
    stamps = [s for s in stamps if s]
    return max(stamps) if stamps else None


# 5.13.0 (owner audit C6): a "stuck" alert says what to do next, not only how long it has waited.
STUCK_NEXT = {
    "prompt_copied": "paste the prompt into its chat, or copy it again on Home",
    "waiting_for_response": "paste the chat's answer on Home (a cut-off answer gets a continue prompt)",
    "needs_user_review": "review the delivery on Home",
    "validation_pending": "record the tests/build result on Home",
    "blocked": "on Home: 'It can continue now' or 'Ask the project manager to re-plan'",
    "needs_decision": "open it on Home and decide",
}


def _age(hours: float) -> str:
    """'5 h', or '3 days' from 48 h on (\"blocked for 93 h\" read as a bug to the owner)."""
    return f"{hours:.0f} h" if hours < 48 else f"{hours / 24:.0f} days"


def alerts(state: dict[str, Any], *, now: datetime | None = None, stuck_hours: float = STUCK_HOURS
           ) -> list[dict[str, Any]]:
    """Every idle / stuck / overloaded / overlap finding, most urgent first."""
    t_now = _now(now)
    rows = agent_stats(state, now=t_now)
    out: list[dict[str, Any]] = []
    workers = [r for r in rows if r["role"] != "project_manager"]
    open_total = sum(r["open"] for r in workers)
    fair = open_total / len(workers) if workers else 0.0
    waiting = any(r["open"] > 1 for r in workers)
    for r in workers:
        if r["open"] == 0 and waiting:
            out.append({"kind": "idle", "agent_id": r["agent_id"], "rank": 3,
                        "text": f"{r['name']} has no open task while others wait."})
        if fair and r["open"] >= 2 and r["open"] > OVERLOAD_FACTOR * fair:
            out.append({"kind": "overloaded", "agent_id": r["agent_id"], "rank": 2,
                        "text": f"{r['name']} holds {r['open']} open tasks (fair share {fair:.1f})."})
    for a in enabled_agents(state):
        for t in _owned(state, a["agent_id"], open_only=True):
            st = task_stage(state, t["task_id"])["stage"]
            if st not in ("prompt_copied", "waiting_for_response", "needs_user_review", "validation_pending",
                          "blocked", "needs_decision"):
                continue
            h = _hours(_stage_since(state, t), t_now)
            if h is not None and h > stuck_hours:
                out.append({"kind": "stuck", "agent_id": a["agent_id"], "task_id": t["task_id"], "rank": 1,
                            "text": f"{a['name']}: {t['task_id']} has been '{st.replace('_', ' ')}' for {_age(h)}"
                                    f" — {STUCK_NEXT.get(st, 'open it on Home')}."})
    out += overlaps(state)
    return sorted(out, key=lambda x: (x["rank"], x["agent_id"], x.get("task_id", "")))


def overlaps(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Open tasks of *different* AIs whose file scopes touch the same paths."""
    open_tasks = [t for t in state["tasks"].values() if t["status"] not in TERMINAL_TASK
                  and t["status"] != "draft" and t.get("owner_agent_id")]
    open_tasks.sort(key=lambda t: t["task_id"])
    out = []
    for i, a in enumerate(open_tasks):
        for b in open_tasks[i + 1:]:
            if a["owner_agent_id"] == b["owner_agent_id"]:
                continue
            hit = scopes_overlap(a.get("scope") or {}, b.get("scope") or {})
            if hit:
                out.append({"kind": "overlap", "agent_id": a["owner_agent_id"], "other_agent_id": b["owner_agent_id"],
                            "task_id": a["task_id"], "other_task_id": b["task_id"], "rank": 0, "paths": hit,
                            "text": f"{a['task_id']} and {b['task_id']} (different AIs) both touch {hit[0]}."})
    return out


def rebalance(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Suggested moves ``{task_id, from_agent_id, to_agent_id, reason}`` that even out open work.

    Only tasks without any attempt (nobody started them) move, only between compatible roles, and a move is
    suggested only when it narrows the gap (``from`` keeps at least as many as ``to`` gets).
    """
    load = {r["agent_id"]: r["open"] for r in agent_stats(state) if r["role"] != "project_manager"}
    role = {a["agent_id"]: a["role"] for a in enabled_agents(state)}
    moves = []
    while True:
        best = None
        for src in sorted(load, key=lambda k: (-load[k], k)):
            movable = [t for t in _owned(state, src, open_only=True)
                       if not t.get("active_attempt_id") and t["status"] == "ready"
                       and t["task_id"] not in {m["task_id"] for m in moves}]
            dst = [d for d in load if d != src and role[d] in COMPATIBLE.get(role[src], {role[src]})]
            dst.sort(key=lambda k: (load[k], k))
            if movable and dst and load[src] - load[dst[0]] >= 2:
                best = (movable[-1], src, dst[0])
                break
        if best is None:
            return moves
        t, src, dst = best
        moves.append({"task_id": t["task_id"], "title": t["title"], "from_agent_id": src, "to_agent_id": dst,
                      "reason": f"{src} has {load[src]} open tasks, {dst} has {load[dst]}"})
        load[src] -= 1
        load[dst] += 1


def queue(state: dict[str, Any], agent_id: str) -> list[dict[str, Any]]:
    """The open tasks of one AI in working order: in progress first, then ready, then blocked/planned."""
    order = {"in_progress": 0, "in_review": 1, "validation_pending": 1, "needs_decision": 2, "ready": 3,
             "blocked": 4, "proposed": 5}
    rows = []
    for t in _owned(state, agent_id, open_only=True):
        st = task_stage(state, t["task_id"])
        rows.append({"task_id": t["task_id"], "title": t["title"], "status": t["status"], "stage": st["stage"],
                     "rank": order.get(t["status"], 6)})
    return sorted(rows, key=lambda r: (r["rank"], r["task_id"]))


def note(state: dict[str, Any], agent_id: str) -> str:
    return str(((state.get("settings") or {}).get("agent_notes") or {}).get(agent_id, ""))


def set_note(state: dict[str, Any], agent_id: str, text: str) -> str:
    """Store the memory note of one AI in a state dict (call inside a store transaction)."""
    if agent_id not in state["agents"]:
        raise ModelError(f"agent {agent_id} does not exist")
    clean = "\n".join(line.rstrip() for line in str(text).strip().splitlines())[:NOTE_MAX]
    notes = state.setdefault("settings", {}).setdefault("agent_notes", {})
    if clean:
        notes[agent_id] = clean
    else:
        notes.pop(agent_id, None)
    return clean


def note_lines(state: dict[str, Any], agent_id: str) -> list[str]:
    """The note as prompt lines (empty when there is none) — appended to the role section of every prompt."""
    text = note(state, agent_id)
    return [f"- Note from the project owner: {line}" for line in text.splitlines() if line.strip()]


def briefing(state: dict[str, Any], agent_id: str, *, project_name: str = "") -> str:
    """A self-contained introduction for a fresh chat with this AI (no task prompt — that comes next)."""
    a = state["agents"].get(agent_id)
    if a is None:
        raise ModelError(f"agent {agent_id} does not exist")
    q = queue(state, agent_id)
    team = [x for x in enabled_agents(state) if x["agent_id"] != agent_id]
    done = [t for t in _owned(state, agent_id, open_only=False) if t["status"] == "done"]
    lines = [f"# Briefing — you are {a['name']} ({a['agent_id']}, role {a['role'].replace('_', ' ')})",
             f"Project: {project_name or state.get('project_id', '')}",
             "You have no access to earlier chats. This sheet introduces you; your first task prompt follows in "
             "the next message. Answer this sheet with one line: READY.", "", "## Your role",
             f"- Purpose: {a.get('purpose') or '(not set)'}"]
    lines += [f"- {i}" for i in a.get("instructions", [])]
    lines += note_lines(state, agent_id)
    lines += ["", "## Your team"]
    lines += [f"- {x['name']} ({x['agent_id']}, {x['role'].replace('_', ' ')})" for x in team] or ["- (you work alone)"]
    lines += ["", "## Your queue"]
    lines += [f"- {r['task_id']} {r['title']} — {r['status'].replace('_', ' ')}" for r in q] or ["- (empty)"]
    if done:
        lines += ["", "## Already done by you"]
        lines += [f"- {t['task_id']} {t['title']}" for t in done[-10:]]
    scopes = sorted({p for t in _owned(state, agent_id, open_only=True) for p in (t.get("scope") or {}).get("include", [])})
    lines += ["", "## Files you own", *([f"- {p}" for p in scopes] or ["- (not restricted)"]),
              "", "Rules: stay inside your files; never mark a task done yourself; answer in the aiwb-handoff-v1 "
              "format each task prompt asks for."]
    return "\n".join(lines) + "\n"
