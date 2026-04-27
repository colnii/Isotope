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

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def make_artifact_ref(run_id: str, artifact_id: str) -> ResourceRef:
    """Build the only ResourceRef variant supported in this slice."""

    return ResourceRef(
        ref_type="artifact",
        scope="run",
        run_id=run_id,
        artifact_id=artifact_id,
    )
