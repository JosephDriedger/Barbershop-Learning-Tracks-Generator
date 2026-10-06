import pytest

from barbershop_tracks import __version__
from barbershop_tracks.cli import main


def test_cli_runs_and_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "barbershop-tracks" in capsys.readouterr().out


def test_cli_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out
