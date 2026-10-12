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
