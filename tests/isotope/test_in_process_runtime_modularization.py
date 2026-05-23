from isotope.runtime.in_process import InProcessServer
from isotope.runtime.in_process_actions import InProcessActionMixin
from isotope.runtime.in_process_agent_loop import InProcessAgentLoopMixin
from isotope.runtime.in_process_approvals import InProcessApprovalMixin
from isotope.runtime.in_process_checkpoints import InProcessCheckpointMixin
from isotope.runtime.in_process_snapshots import InProcessSnapshotMixin
from isotope.runtime.in_process_workspace import InProcessWorkspaceMixin


def test_in_process_server_facade_preserves_runtime_mixin_boundaries():
    assert issubclass(InProcessServer, InProcessActionMixin)
    assert issubclass(InProcessServer, InProcessAgentLoopMixin)
    assert issubclass(InProcessServer, InProcessApprovalMixin)
    assert issubclass(InProcessServer, InProcessCheckpointMixin)
    assert issubclass(InProcessServer, InProcessSnapshotMixin)
    assert issubclass(InProcessServer, InProcessWorkspaceMixin)
