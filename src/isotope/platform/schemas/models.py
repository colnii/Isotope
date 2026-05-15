"""Compatibility proxy.

New paths:
    isotope.platform.schemas.actions
    isotope.platform.schemas.artifacts
    isotope.platform.schemas.memory
    isotope.platform.schemas.snapshots

Planned removal:
    after import-map confirms no active internal imports.
"""

from isotope.platform.schemas.actions import ActionExecution, ActionProposal, PolicyDecision
from isotope.platform.schemas.artifacts import Artifact
from isotope.platform.schemas.memory import MemoryRecord
from isotope.platform.schemas.snapshots import ImportedSnapshot

__all__ = [
    "ActionExecution",
    "ActionProposal",
    "Artifact",
    "ImportedSnapshot",
    "MemoryRecord",
    "PolicyDecision",
]
