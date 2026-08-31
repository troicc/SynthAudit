from typer.testing import CliRunner

from synthaudit import SCIENTIFIC_NOTICE, __version__
from synthaudit.cli.app import app


def test_version_and_notice_are_public() -> None:
    assert __version__ == "1.0.0"
    assert "does not establish experimental feasibility" in SCIENTIFIC_NOTICE


def test_version_cli_json() -> None:
    result = CliRunner().invoke(app, ["version", "--json"])
    assert result.exit_code == 0
    assert '"version": "1.0.0"' in result.stdout
