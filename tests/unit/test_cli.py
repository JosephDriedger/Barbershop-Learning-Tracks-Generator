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


def test_output_with_characters_the_console_encoding_lacks_does_not_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import io
    import sys

    from barbershop_tracks.cli import _tolerate_unencodable_output

    raw = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(raw, encoding="cp1252"))
    _tolerate_unencodable_output()
    print("Jörg 日本")  # cp1252 has the o-umlaut but not the kanji
    sys.stdout.flush()
    assert raw.getvalue().startswith(b"J\xf6rg ")
