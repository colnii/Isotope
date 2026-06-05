"""Shared helpers for capability definition modules."""
from __future__ import annotations
from typing import Any

from isotope.capabilities.catalog import Capability


def builtin_capability(
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
        safety_boundaries=("public_metadata_manifest_only", "no_execution"),
        default_enabled=True,
    )
