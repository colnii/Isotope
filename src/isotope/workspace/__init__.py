"""Workspace manager boundary for the Isotope v0.1 slice."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WorkspaceBinding:
    workspace_id: str
    mode: str


class WorkspaceManager:
    """Shared workspace binding boundary for the first slice."""

    def get_binding(self, grants: dict[str, Any]) -> WorkspaceBinding:
        if not isinstance(grants, dict):
            raise TypeError("workspace grants must be a dict")
        workspace_grant = grants.get("workspace")
        if not isinstance(workspace_grant, dict):
            raise PermissionError("workspace grant is required")
        mode = workspace_grant.get("mode")
        if not mode:
            raise PermissionError("workspace.mode is required")
        if mode != "shared_ro":
            raise PermissionError("workspace mode is not supported")
        return WorkspaceBinding(workspace_id="workspace_shared_ro", mode="shared_ro")
