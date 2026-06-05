from __future__ import annotations

from datetime import datetime, timezone

import pytest

from isotope.features.supervisor import flow as supervisor_flow
from helpers import NOW


@pytest.fixture(autouse=True)
def _freeze_supervisor_flow_now(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(supervisor_flow, "_utc_now", lambda: NOW)
