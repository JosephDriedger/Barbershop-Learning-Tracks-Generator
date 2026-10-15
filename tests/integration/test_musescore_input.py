"""A genuine MuseScore project as input, converted by the real MuseScore, through the real render host.

Skipped where MuseScore is not installed. The project is made by MuseScore itself from the test quartet (so it is
a real ``.mscz`` / ``.mscx``), and the tracks made from it must be the very tracks made from the MusicXML.
"""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from barbershop_tracks.cli import main
from barbershop_tracks.core.musicxml.convert import clean_environment, find_musescore
from cli_scores import LINES, quartet_xml
from host_support import host_environment, require_host
from synthetic_voicebank import SINGER_ID, build_voicebank

pytestmark = pytest.mark.integration

ASSIGN = [f"{role.upper()}={LINES[role]}" for role in ("tenor", "lead", "baritone", "bass")]


class Rig:
    def __init__(self, root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.root = root
        self.singers = root / "singers"
        build_voicebank(self.singers)
        monkeypatch.setenv("BLT_CONFIG", str(root / "none.json"))
        monkeypatch.setenv("BLT_DATA_DIR", str(root / "data"))
        monkeypatch.setenv("BLT_HOST_DIR", str(require_host()))
        for key, value in host_environment().items():
            if key == "DOTNET_ROOT":
                monkeypatch.setenv(key, value)
        self.musicxml = root / "quartet.musicxml"
        self.musicxml.write_text(
            quartet_xml(all_lyrics=True, word="la", measures=4), encoding="utf-8"
        )

    def make(self, name: str) -> Path:
        """A real MuseScore file of the quartet, written by MuseScore itself."""
        program = find_musescore()
        assert program is not None
        target = self.root / name
        done = subprocess.run(
            [str(program), "-o", str(target), str(self.musicxml)],
            capture_output=True,
            timeout=180,
            check=False,
            env=clean_environment(),
        )
        assert done.returncode == 0, done.stderr
        assert target.is_file()
        return target

    def generate(self, score: Path, out: str) -> tuple[int, Path]:
        destination = self.root / out
        code = main(
            [
                "generate",
                str(score),
                "--out",
                str(destination),
                "--singers-dir",
                str(self.singers),
                "--singer",
                SINGER_ID,
                "--progress",
                "none",
                *[a for assign in ASSIGN for a in ("--assign", assign)],
            ]
        )
        return code, destination / f"{score.stem}_learning_tracks"


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Rig:
    require_host()
    if find_musescore() is None:
        pytest.skip("MuseScore is not installed here")
    return Rig(tmp_path, monkeypatch)


def full_quartet(package: Path) -> str:
    return hashlib.sha256((package / "01_Full_Quartet.wav").read_bytes()).hexdigest()


@pytest.mark.parametrize("name", ["Hymn.mscz", "Hymn.mscx"])
def test_a_real_musescore_project_makes_the_same_tracks_as_its_musicxml(
    rig: Rig, name: str
) -> None:
    project = rig.make(name)
    assert project.suffix in (".mscz", ".mscx")
    plain_code, plain = rig.generate(rig.musicxml, "out-plain")
    code, package = rig.generate(project, "out-project")
    assert (plain_code, code) == (0, 0)
    assert full_quartet(package) == full_quartet(plain)  # byte for byte the same audio
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    source = manifest["source"]
    assert source["display_name"] == name
    assert source["sha256"] == hashlib.sha256(project.read_bytes()).hexdigest()  # the project's own
    assert source["conversion"]["tool"] == "MuseScore"
    assert source["conversion"]["recognised"] is False
    assert len(list(package.glob("*.wav"))) == 13


def test_the_same_project_gives_the_same_identity_and_tracks_on_a_second_run(rig: Rig) -> None:
    project = rig.make("Hymn.mscz")
    first_code, first = rig.generate(project, "out-1")
    second_code, second = rig.generate(project, "out-2")
    assert (first_code, second_code) == (0, 0)
    one = json.loads((first / "manifest.json").read_text(encoding="utf-8"))["source"]
    two = json.loads((second / "manifest.json").read_text(encoding="utf-8"))["source"]
    assert one == two  # the conversion is kept, so even MuseScore's dated export cannot change it
    assert full_quartet(first) == full_quartet(second)


def test_a_pdf_that_musescore_wrote_is_still_a_picture_and_is_not_recognised_silently(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    program = find_musescore()
    assert program is not None
    pdf = rig.root / "Hymn.pdf"
    done = subprocess.run(
        [str(program), "-o", str(pdf), str(rig.musicxml)],
        capture_output=True,
        timeout=180,
        check=False,
        env=clean_environment(),
    )
    assert done.returncode == 0
    code, _ = rig.generate(pdf, "out-pdf")
    assert code != 0
    assert "RECOGNITION_NOT_CONFIRMED" in capsys.readouterr().err
