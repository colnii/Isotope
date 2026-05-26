from __future__ import annotations

import isotope.features.supervisor.planner.merge_work_order as supervisor_merge_work_order
import isotope.features.supervisor.planner.merge_work_order as planner_merge_work_order


def test_merge_work_order_root_module_reexports_planner_implementation():
    assert (
        supervisor_merge_work_order.build_merge_work_order_prompt
        is planner_merge_work_order.build_merge_work_order_prompt
    )
