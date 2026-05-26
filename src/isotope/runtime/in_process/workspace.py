"""Workspace, artifact, and worker handoff helpers for the in-process runtime."""

from __future__ import annotations

from .worker_handoff import InProcessWorkerHandoffMixin
from .workspace_artifacts import InProcessArtifactMixin
from .workspace_leases import InProcessWorkspaceLeaseMixin


class InProcessWorkspaceMixin(
    InProcessArtifactMixin,
    InProcessWorkspaceLeaseMixin,
    InProcessWorkerHandoffMixin,
):
    """Manage runtime workspace bindings, artifacts, and worker handoffs."""
