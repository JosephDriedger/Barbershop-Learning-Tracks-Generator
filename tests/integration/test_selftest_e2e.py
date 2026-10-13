"""`blt selftest` against the real render host (what the installer smoke test relies on)."""

from pathlib import Path

import pytest

from barbershop_tracks.cli import main
from host_support import host_environment, require_host

pytestmark = pytest.mark.integration


def test_selftest_passes_with_the_real_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    host = require_host()
    for key, value in host_environment().items():
        if key == "DOTNET_ROOT":
            monkeypatch.setenv(key, value)
    monkeypatch.setenv("BLT_CONFIG", str(tmp_path / "no-config.json"))
    code = main(
        [
            "selftest",
            "--host-dir",
            str(host),
            "--data-dir",
            str(tmp_path / "data"),
            "--keep",
            str(tmp_path / "kept"),
        ]
    )
    out = capsys.readouterr().out
    assert code == 0, out
    assert "selftest passed" in out
    assert len(list((tmp_path / "kept" / "out").rglob("*.wav"))) == 13


def test_the_rendered_audio_is_byte_identical_to_the_stock_worldline_golden(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """BLT's own worldline.dll (no GPL spline) must reproduce what OpenUtau's stock DLL rendered."""
    import hashlib
    import json

    golden = json.loads((Path(__file__).parents[1] / "golden" / "selftest_audio.json").read_text())
    host = require_host()
    for key, value in host_environment().items():
        if key == "DOTNET_ROOT":
            monkeypatch.setenv(key, value)
    monkeypatch.setenv("BLT_CONFIG", str(tmp_path / "no-config.json"))
    code = main(
        [
            "selftest",
            "--host-dir",
            str(host),
            "--data-dir",
            str(tmp_path / "data"),
            "--keep",
            str(tmp_path / "kept"),
        ]
    )
    assert code == 0, capsys.readouterr().out
    rendered = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((tmp_path / "kept" / "out").rglob("*.wav"))
    }
    assert rendered == golden["files"]
