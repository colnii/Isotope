from isotope.agents.scheduler import fanout
from isotope.agents.scheduler import fanout_status


def test_fanout_facade_reuses_status_summary_module():
    assert fanout.build_fanout_status_summary is fanout_status.build_fanout_status_summary
    assert fanout.FANOUT_STATUS_VALUES is fanout_status.FANOUT_STATUS_VALUES
