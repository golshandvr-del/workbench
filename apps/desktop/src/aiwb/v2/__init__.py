"""V2 multi-agent project management services (roadmap 1.17.x → 2.0.0).

UI-independent. One local source of truth (:class:`ProjectStore`); every
service mutates it through transactions and the central state machines in
:mod:`.models`. GitHub only receives a published projection (:mod:`.publisher`).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .agents import AgentRegistry
from .attempts import AttemptService
from .handoff import HandoffService
from .ledger import DecisionLedger, EvidenceService
from .models import ModelError, SCHEMA_VERSION
from .next_action import compute_next_actions
from .proposals import ProposalService
from .snapshot import build_snapshot, render_status_md
from .store import ProjectStore, StoreError
from .tasks import TaskService, validate_graph


class V2Project:
    """Facade bundling all services for one project directory."""

    def __init__(self, root: Path, project_id: str = "") -> None:
        self.store = ProjectStore(root, project_id)
        self.agents = AgentRegistry(self.store)
        self.tasks = TaskService(self.store)
        self.attempts = AttemptService(self.store)
        self.handoffs = HandoffService(self.store)
        self.decisions = DecisionLedger(self.store)
        self.evidence = EvidenceService(self.store)
        self.proposals = ProposalService(self.store)

    def open(self, legacy: dict[str, Any] | None = None) -> list[str]:
        """Create/migrate the store (idempotent) and install base agents once."""
        notes = self.store.ensure_migrated(legacy_loader=(lambda: legacy or {}))
        if not self.store.load()["agents"]:
            self.agents.install_templates()
        return notes

    def next_actions(self, **kw: Any) -> list[dict[str, Any]]:
        return compute_next_actions(self.store.load(), **kw)


__all__ = ["AgentRegistry", "AttemptService", "DecisionLedger", "EvidenceService", "HandoffService", "ModelError",
           "ProjectStore", "ProposalService", "SCHEMA_VERSION", "StoreError", "TaskService", "V2Project",
           "build_snapshot", "compute_next_actions", "render_status_md", "validate_graph"]
