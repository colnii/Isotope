from __future__ import annotations

import isotope.features.supervisor.workers.test_gate as supervisor_worker_test_gate
import isotope.features.supervisor.workers.test_gate as worker_test_gate


def test_worker_test_gate_root_module_reexports_workers_implementation():
    assert (
        supervisor_worker_test_gate.collect_worker_test_gate
        is worker_test_gate.collect_worker_test_gate
    )
    assert supervisor_worker_test_gate.TEST_GATE_COMMAND is worker_test_gate.TEST_GATE_COMMAND

