"""The kit's Check-Outputs.ps1 on a real package: passes a genuine one, catches a damaged one."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from barbershop_tracks.cli import main
from cli_scores import LINES, quartet_xml
from host_support import host_environment, require_host
from synthetic_voicebank import SINGER_ID, build_voicebank

POWERSHELL = shutil.which("powershell") if sys.platform == "win32" else shutil.which("pwsh")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(POWERSHELL is None, reason="the kit's checker is a PowerShell script"),
]

SCRIPT = Path(__file__).resolve().parents[2] / "packaging" / "tester-kit" / "Check-Outputs.ps1"


@pytest.fixture(scope="module")
def package(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("checker")
    singers = root / "singers"
    build_voicebank(singers)
    score = root / "song.musicxml"
    score.write_text(quartet_xml(all_lyrics=True, word="la"), encoding="utf-8")
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("BLT_CONFIG", str(root / "no-config.json"))
        patch.setenv("BLT_DATA_DIR", str(root / "data"))
        patch.setenv("BLT_HOST_DIR", str(require_host()))
        for key, value in host_environment().items():
            if key == "DOTNET_ROOT":
                patch.setenv(key, value)
        arguments = [
            "generate",
            str(score),
            "--out",
            str(root / "out"),
            "--singers-dir",
            str(singers),
            "--singer",
            SINGER_ID,
        ]
        for role in ("tenor", "lead", "baritone", "bass"):
            arguments += ["--assign", f"{role.upper()}={LINES[role]}"]
        assert main(arguments) == 0
    return next((root / "out").iterdir())


def check(folder: Path) -> subprocess.CompletedProcess[str]:
    assert POWERSHELL is not None
    return subprocess.run(
        [
            POWERSHELL,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-Folder",
            str(folder),
        ],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


def test_a_genuine_package_passes_every_arithmetic_check(package: Path) -> None:
    done = check(package)
    assert done.returncode == 0, done.stdout
    assert "every arithmetic check passed" in done.stdout
    assert "FAIL" not in done.stdout
    assert done.stdout.count("add up to the Full Quartet") == 4


def test_two_swapped_solo_files_are_caught(package: Path, tmp_path: Path) -> None:
    damaged = tmp_path / "swapped"
    shutil.copytree(package, damaged)
    tenor, lead = damaged / "06_Tenor_Solo.wav", damaged / "07_Lead_Solo.wav"
    spare = damaged / "spare.wav"
    tenor.rename(spare)
    lead.rename(tenor)
    spare.rename(lead)
    done = check(damaged)
    assert done.returncode == 1
    assert "Tenor: Solo and Without Tenor add up" in done.stdout
    assert "FAIL" in done.stdout


def test_a_missing_file_is_reported_by_name(package: Path, tmp_path: Path) -> None:
    damaged = tmp_path / "missing"
    shutil.copytree(package, damaged)
    (damaged / "11_Without_Lead.wav").unlink()
    done = check(damaged)
    assert done.returncode == 1
    assert "11_Without_Lead.wav" in done.stdout
