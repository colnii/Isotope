from __future__ import annotations

import isotope.features.supervisor.integration_review as supervisor_integration_review
import isotope.features.supervisor.workers.integration_review as worker_integration_review


def test_integration_review_root_module_reexports_workers_implementation():
    assert (
        supervisor_integration_review.collect_integration_reviews
        is worker_integration_review.collect_integration_reviews
    )
    assert (
        supervisor_integration_review.review_managed_record_integration
        is worker_integration_review.review_managed_record_integration
    )
    assert (
        supervisor_integration_review.render_integration_review_plain
        is worker_integration_review.render_integration_review_plain
    )
