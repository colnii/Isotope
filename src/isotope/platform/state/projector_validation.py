"""RunProjector canonical-event validation mixin facade."""

from __future__ import annotations

from .projector_domain_validation import RunProjectorDomainValidationMixin
from .projector_lifecycle_validation import RunProjectorLifecycleValidationMixin
from .projector_payload_validation import RunProjectorPayloadValidationMixin


class RunProjectorValidationMixin(
    RunProjectorLifecycleValidationMixin,
    RunProjectorPayloadValidationMixin,
    RunProjectorDomainValidationMixin,
):
    """Combine projector validation helpers under one import boundary."""
