"""CLI smoke tests using click.testing.CliRunner."""

from click.testing import CliRunner

from gq_terminal import __version__
from gq_terminal.cli import main


def test_version_flag() -> None:
    result = CliRunner().invoke(main, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_help_lists_subcommands() -> None:
    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0
    for cmd in ("info", "monitor", "log", "history", "key", "config"):
        assert cmd in result.output


def test_info_help_lists_common_options() -> None:
    result = CliRunner().invoke(main, ["info", "--help"])
    assert result.exit_code == 0
    assert "--port" in result.output
    assert "--baudrate" in result.output
