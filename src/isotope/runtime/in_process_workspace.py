"""Workspace, artifact, and worker handoff helpers for the in-process runtime."""

from __future__ import annotations

from .in_process_worker_handoff import InProcessWorkerHandoffMixin
from .in_process_workspace_artifacts import InProcessArtifactMixin
from .in_process_workspace_leases import InProcessWorkspaceLeaseMixin


class InProcessWorkspaceMixin(
    InProcessArtifactMixin,
    InProcessWorkspaceLeaseMixin,
    InProcessWorkerHandoffMixin,
):
    """Manage runtime workspace bindings, artifacts, and worker handoffs."""
