"""Mobile Companion (Integration Spec §11, P3): secure local pairing, read-only project/build view,
create task and submit answers - always through the central desktop services."""
from .crypto import EnvelopeError, open_json, seal
from .service import DEFAULT_PERMISSIONS, PERMISSIONS, CompanionError, CompanionService, DeviceRegistry

__all__ = ["CompanionError", "CompanionService", "DEFAULT_PERMISSIONS", "DeviceRegistry", "EnvelopeError",
           "PERMISSIONS", "open_json", "seal"]
