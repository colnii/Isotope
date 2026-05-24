"""Low-sensitive capability catalog metadata.

This module is intentionally a catalog, not a capability runner. It exposes
stable metadata for app shells without constructing providers or executing work.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
import os
import re
from typing import Any, Mapping


_CAPABILITY_ID_RE = re.compile(r"^[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*)+$")
_SHELVES = frozenset(
    {"product_candidate", "prototype", "diagnostic", "experimental"}
)


def _as_tuple(value: tuple[str, ...] | list[str] | None, *, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field_name} must be a list or tuple")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            raise ValueError(f"{field_name} entries must be non-empty strings")
        result.append(item)
    return tuple(result)


def _validate_capability_id(capability_id: str) -> str:
    if not isinstance(capability_id, str) or not _CAPABILITY_ID_RE.fullmatch(capability_id):
        raise ValueError("capability_id must be a stable dotted identifier")
    return capability_id


def _validate_shelf(shelf: str) -> str:
    if shelf not in _SHELVES:
        raise ValueError(f"unknown capability shelf: {shelf}")
    return shelf


@dataclass(frozen=True)
class Capability:
    capability_id: str
    title: str
    description: str
    maturity: str
    shelf: str
    domain_tags: tuple[str, ...]
    input_contract: Mapping[str, Any]
    output_contract: Mapping[str, Any]
    safety_boundaries: tuple[str, ...]
    default_enabled: bool = True
    required_env: tuple[str, ...] = ()
    network_required: bool = False
    provider: str | None = None
    model: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "capability_id", _validate_capability_id(self.capability_id))
        object.__setattr__(self, "shelf", _validate_shelf(self.shelf))
        for field_name in ("title", "description", "maturity"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty string")
        if not isinstance(self.default_enabled, bool):
            raise ValueError("default_enabled must be bool")
        if not isinstance(self.network_required, bool):
            raise ValueError("network_required must be bool")
        if not isinstance(self.input_contract, Mapping):
            raise ValueError("input_contract must be a mapping")
        if not isinstance(self.output_contract, Mapping):
            raise ValueError("output_contract must be a mapping")
        object.__setattr__(
            self,
            "domain_tags",
            _as_tuple(self.domain_tags, field_name="domain_tags"),
        )
        object.__setattr__(
            self,
            "safety_boundaries",
            _as_tuple(self.safety_boundaries, field_name="safety_boundaries"),
        )
        object.__setattr__(
            self,
            "required_env",
            _as_tuple(self.required_env, field_name="required_env"),
        )

    def to_manifest_dict(self) -> dict[str, Any]:
        manifest = {
            "capability_id": self.capability_id,
            "title": self.title,
            "description": self.description,
            "maturity": self.maturity,
            "shelf": self.shelf,
            "domain_tags": list(self.domain_tags),
            "input_contract": copy.deepcopy(dict(self.input_contract)),
            "output_contract": copy.deepcopy(dict(self.output_contract)),
            "safety_boundaries": list(self.safety_boundaries),
            "default_enabled": self.default_enabled,
            "required_env": list(self.required_env),
            "network_required": self.network_required,
        }
        if self.provider is not None:
            manifest["provider"] = self.provider
        if self.model is not None:
            manifest["model"] = self.model
        return manifest


class CapabilityCatalog:
    def __init__(self, *, capabilities: list[Capability] | tuple[Capability, ...] | None = None):
        self._capabilities: dict[str, Capability] = {}
        for capability in capabilities or ():
            if not isinstance(capability, Capability):
                raise ValueError("capabilities must contain Capability objects")
            if capability.capability_id in self._capabilities:
                raise ValueError(f"duplicate capability_id: {capability.capability_id}")
            self._capabilities[capability.capability_id] = capability

    @classmethod
    def default(cls) -> "CapabilityCatalog":
        return cls(
            capabilities=[
                _builtin_capability(
                    "approval.tool.runner",
                    title="Approval Tool Runner",
                    description="Exercise approval-gated tool execution through core boundaries.",
                    tags=("approval", "tool", "runner"),
                ),
                _builtin_capability(
                    "artifact.review",
                    title="Artifact Review",
                    description="Review artifact summaries through ResourceRef and content-policy boundaries.",
                    tags=("artifact", "review"),
                ),
                _builtin_capability(
                    "external.snapshot.review",
                    title="External Snapshot Review",
                    description="Review imported snapshot observations without overriding native state.",
                    tags=("external", "snapshot", "review"),
                ),
                Capability(
                    capability_id="supervisor.request_context",
                    title="Supervisor Request Context",
                    description=(
                        "Retrieve ranked project context through the existing "
                        "Supervisor request_project_context path."
                    ),
                    maturity="v0.2",
                    shelf="product_candidate",
                    domain_tags=("supervisor", "request_context", "context", "search"),
                    input_contract={
                        "type": "object",
                        "required": ["codex_home", "cwd", "query"],
                        "properties": {
                            "codex_home": {
                                "type": "string",
                                "description": "Codex home directory used for existing context result storage.",
                            },
                            "cwd": {
                                "type": "string",
                                "description": "Workspace directory to search.",
                            },
                            "query": {
                                "type": "string",
                                "description": "Project context query.",
                            },
                            "max_results": {
                                "type": "integer",
                                "description": "Maximum ranked context items to return.",
                                "default": 5,
                            },
                        },
                    },
                    output_contract={
                        "type": "object",
                        "fields": [
                            "result_id",
                            "backend",
                            "item_count",
                            "items",
                        ],
                    },
                    safety_boundaries=(
                        "workspace_read_only",
                        "writes_existing_supervisor_context_store",
                        "low_sensitive_summary_only",
                    ),
                    default_enabled=True,
                    network_required=False,
                ),
            ]
        )

    def list_capabilities(
        self,
        *,
        shelf: str | None = None,
        include_diagnostics: bool = False,
        include_experimental: bool = False,
    ) -> list[dict[str, Any]]:
        if shelf is not None:
            _validate_shelf(shelf)
        visible = []
        for capability in self._capabilities.values():
            if shelf is not None and capability.shelf != shelf:
                continue
            if capability.shelf == "diagnostic" and not include_diagnostics and shelf != "diagnostic":
                continue
            if capability.shelf == "experimental" and not include_experimental:
                continue
            if capability.shelf not in {"product_candidate", "prototype", "diagnostic", "experimental"}:
                continue
            visible.append(capability.to_manifest_dict())
        return sorted(visible, key=lambda entry: entry["capability_id"])

    def get_manifest(
        self,
        *,
        env: Mapping[str, str] | None = None,
        include_diagnostics: bool = False,
        include_experimental: bool = False,
    ) -> dict[str, Any]:
        capabilities = []
        for entry in self.list_capabilities(
            include_diagnostics=include_diagnostics,
            include_experimental=include_experimental,
        ):
            entry = dict(entry)
            entry["readiness"] = self.get_capability_status(
                entry["capability_id"], env=env
            )
            capabilities.append(entry)
        return {"kind": "capability_manifest", "capabilities": capabilities}

    def get_capability_status(
        self, capability_id: str, *, env: Mapping[str, str] | None = None
    ) -> dict[str, Any]:
        capability_id = _validate_capability_id(capability_id)
        try:
            capability = self._capabilities[capability_id]
        except KeyError as exc:
            raise KeyError(capability_id) from exc
        env_mapping = os.environ if env is None else env
        missing_env = [
            name for name in capability.required_env if not env_mapping.get(name)
        ]
        ready = capability.default_enabled and not missing_env
        if not capability.default_enabled:
            status = "disabled"
        elif missing_env:
            status = "missing_configuration"
        else:
            status = "ready"
        result = {
            "capability_id": capability.capability_id,
            "default_enabled": capability.default_enabled,
            "ready": ready,
            "status": status,
            "missing_env": missing_env,
            "network_required": capability.network_required,
            "provider": capability.provider,
            "model": capability.model,
        }
        return result


def _builtin_capability(
    capability_id: str, *, title: str, description: str, tags: tuple[str, ...]
) -> Capability:
    return Capability(
        capability_id=capability_id,
        title=title,
        description=description,
        maturity="v0.2",
        shelf="product_candidate",
        domain_tags=tags,
        input_contract={"type": "object"},
        output_contract={"type": "object"},
        safety_boundaries=("low_sensitive_manifest_only", "no_execution"),
        default_enabled=True,
    )


def default_catalog() -> CapabilityCatalog:
    return CapabilityCatalog.default()


def list_capabilities(**kwargs: Any) -> list[dict[str, Any]]:
    return default_catalog().list_capabilities(**kwargs)


def get_manifest(**kwargs: Any) -> dict[str, Any]:
    return default_catalog().get_manifest(**kwargs)


def get_capability_status(capability_id: str, **kwargs: Any) -> dict[str, Any]:
    return default_catalog().get_capability_status(capability_id, **kwargs)
