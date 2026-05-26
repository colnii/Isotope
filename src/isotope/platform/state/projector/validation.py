"""RunProjector canonical-event validation mixin facade."""

from __future__ import annotations

from .domain_validation import RunProjectorDomainValidationMixin
from .lifecycle_validation import RunProjectorLifecycleValidationMixin
from .payload_validation import RunProjectorPayloadValidationMixin


class RunProjectorValidationMixin(
    RunProjectorLifecycleValidationMixin,
    RunProjectorPayloadValidationMixin,
    RunProjectorDomainValidationMixin,
):
    """Combine projector validation helpers under one import boundary."""
