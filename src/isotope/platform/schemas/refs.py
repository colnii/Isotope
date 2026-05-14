"""ResourceRef boundary for the Isotope v0.1 slice."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ResourceRef:
    """Slice-only structured ref; not the final ResourceRef protocol."""

    ref_type: str
    scope: str
    run_id: str
    artifact_id: str

    def __post_init__(self) -> None:
        for field_name in ("ref_type", "scope", "run_id", "artifact_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty string")

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def make_artifact_ref(run_id: str, artifact_id: str) -> ResourceRef:
    """Build the only ResourceRef variant supported in this slice."""

    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run_id must be a non-empty string")
    if not isinstance(artifact_id, str) or not artifact_id:
        raise ValueError("artifact_id must be a non-empty string")
    return ResourceRef(
        ref_type="artifact",
        scope="run",
        run_id=run_id,
        artifact_id=artifact_id,
    )
