from isotope.platform.state import projector_checkpoint
from isotope.platform.state import projector_checkpoint_validation


def test_checkpoint_mixin_reuses_checkpoint_validation_mixin():
    assert issubclass(
        projector_checkpoint.RunProjectorCheckpointMixin,
        projector_checkpoint_validation.RunProjectorCheckpointValidationMixin,
    )
    assert (
        projector_checkpoint.RunProjectorCheckpointMixin._validate_checkpoint_artifact
        is projector_checkpoint_validation.RunProjectorCheckpointValidationMixin._validate_checkpoint_artifact
    )
