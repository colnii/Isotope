"""Workspace manager boundary for the Isotope v0.1 slice."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WorkspaceBinding:
    workspace_id: str
    mode: str


class WorkspaceManager:
    """No-op/shared read-only workspace boundary for the first slice."""

    def get_binding(self, grants: dict[str, Any]) -> WorkspaceBinding:
        mode = grants.get("workspace", {}).get("mode")
        if mode != "shared_ro":
            raise PermissionError("workspace mode is not granted")
        return WorkspaceBinding(workspace_id="workspace_shared_ro", mode="shared_ro")
