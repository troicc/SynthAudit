from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _offline_unit_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Declare the default test contract; integration tests opt in explicitly."""
    monkeypatch.setenv("SYNTHAUDIT_OFFLINE", os.environ.get("SYNTHAUDIT_OFFLINE", "1"))
