from isotope.platform.state import projector
from isotope.platform.state.projector_checkpoint import RunProjectorCheckpointMixin
from isotope.platform.state.projector_handlers import RunProjectorHandlersMixin
from isotope.platform.state.projector_state import RunState
from isotope.platform.state.projector_validation import RunProjectorValidationMixin


def test_run_projector_facade_preserves_public_entrypoint():
    assert projector.RunState is RunState
    assert issubclass(projector.RunProjector, RunProjectorCheckpointMixin)
    assert issubclass(projector.RunProjector, RunProjectorHandlersMixin)
    assert issubclass(projector.RunProjector, RunProjectorValidationMixin)
    assert projector.RunProjector().PROJECTOR_VERSION == "run_projector@v1"
