from __future__ import annotations

from pathlib import Path

import pytest

streamlit = pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402


@pytest.mark.integration
def test_all_five_streamlit_pages_start_without_exceptions() -> None:
    root = Path("app")
    pages = (root / "Home.py", *sorted((root / "pages").glob("*.py")))
    for path in pages:
        app = AppTest.from_file(path.resolve(), default_timeout=20).run()
        assert not app.exception, f"{path}: {app.exception}"
