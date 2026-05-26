from __future__ import annotations

import isotope.features.supervisor.workers.review as supervisor_worker_review
import isotope.features.supervisor.workers.review as worker_review


def test_worker_review_root_module_reexports_workers_implementation():
    assert supervisor_worker_review.collect_worker_reviews is worker_review.collect_worker_reviews
    assert (
        supervisor_worker_review.render_worker_review_plain
        is worker_review.render_worker_review_plain
    )

