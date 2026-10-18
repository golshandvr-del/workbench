"""Response Inbox and import pipeline (roadmap 1.16.x).

UI-independent services:

* ``store``     raw-first storage with stable ``response_id`` (1.16.0)
* ``attempts``  stable ``attempt_id`` per exported prompt (1.16.0)
* ``classify``  parser suggestions, truncation detection (1.16.0)
* ``pipeline``  Capture → Classify → Parse → Validate → Reconcile, reparse (1.16.0/1.16.1)
* ``errors``    stable error codes + plain-language explanations (1.16.1)
* ``salvage``   partial-output recovery + focused repair prompt (1.16.1)
"""
from .attempts import Attempt, AttemptRegistry, declared_attempt_id, prompt_identity_block
from .errors import ERROR_CODES, ImportIssue, explain
from .pipeline import ImportPipeline, PipelineOutcome
from .salvage import SalvageResult, repair_prompt, salvage_aiwb_blocks
from .store import InboxStore, RawResponse

__all__ = ["Attempt", "AttemptRegistry", "ERROR_CODES", "ImportIssue", "ImportPipeline", "InboxStore",
           "PipelineOutcome", "RawResponse", "SalvageResult", "declared_attempt_id", "explain",
           "prompt_identity_block", "repair_prompt", "salvage_aiwb_blocks"]
