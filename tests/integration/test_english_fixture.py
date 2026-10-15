"""The English pronunciation acceptance scores, through the real CLI and the real (model-free) host.

``docs/acceptance/fixtures`` holds three versions of one tune. The real dictionary decides what each
word is: the ``unknown`` score must stop before rendering and name every word the dictionary lacks,
with its voices and its bar; the ``known`` and ``respelled`` scores must get past pronunciation with
every supported English phonemizer. (The synthetic voicebank cannot sing English phonemes, so those
two end later, at the stem check; what is shown here is that nothing is refused or silently dropped
for pronunciation.)
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from barbershop_tracks.cli import main
from host_support import host_environment, require_host
from synthetic_voicebank import SINGER_ID, build_voicebank

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "docs" / "acceptance" / "fixtures"
PHONEMIZERS = ["ArpasingPhonemizer", "EnglishVCCVPhonemizer", "EnXSampaPhonemizer"]
MANIFEST = json.loads((FIXTURES / "english-quartet.words.json").read_text(encoding="utf-8"))
ASSIGN = ["TENOR=P1/s1/v1", "LEAD=P2/s1/v1", "BARITONE=P3/s1/v1", "BASS=P4/s1/v1"]


def host_json(*arguments: str) -> dict[str, Any]:
    done = subprocess.run(
        [str(require_host() / "blt-render-host.exe"), *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=host_environment(),
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    result: dict[str, Any] = json.loads(done.stdout.strip().splitlines()[-1])
    return result


def model_in_host() -> bool:
    record = require_host() / "blt-host-build.json"
    return bool(json.loads(record.read_text(encoding="utf-8")).get("g2p_model") == "included")


def entries(version: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = MANIFEST["versions"][version]["words"]
    return found


def test_the_words_the_fixture_calls_known_or_unknown_are_what_the_dictionary_says() -> None:
    if model_in_host():
        pytest.skip("the internal research host's lookup includes the model's guesses")
    words = sorted({e["word"] for v in MANIFEST["versions"] for e in entries(v)})
    found = host_json("--lookup-words", "|".join(words))["lookup"]
    for version in MANIFEST["versions"]:
        for entry in entries(version):
            assert (found[entry["word"]] is not None) == entry["in_dictionary"], (version, entry)


def test_every_unknown_word_of_the_unknown_score_is_one_the_dictionary_lacks() -> None:
    lacking = {e["word"] for e in entries("unknown") if not e["in_dictionary"]}
    assert lacking == {"lov'd", "ev'ryone", "'neath", "o'er", "mammy"}
    assert all(e["in_dictionary"] for v in ("known", "respelled") for e in entries(v))


class Rig:
    def __init__(self, root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.root = root
        self.singers = root / "singers"
        build_voicebank(self.singers)
        monkeypatch.setenv("BLT_CONFIG", str(root / "no-config.json"))
        monkeypatch.setenv("BLT_DATA_DIR", str(root / "data"))
        monkeypatch.setenv("BLT_HOST_DIR", str(require_host()))
        monkeypatch.setenv(
            "BLT_FOLLOW_LEAD", "1"
        )  # the barbershop convention: the parts follow the Lead's words
        for key, value in host_environment().items():
            if key == "DOTNET_ROOT":
                monkeypatch.setenv(key, value)
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    def generate(self, version: str, phonemizer: str, *extra: str) -> int:
        score = FIXTURES / f"english-quartet-{version}-words.musicxml"
        arguments = [
            "generate",
            str(score),
            "--out",
            str(self.root / f"out-{version}-{phonemizer}"),
            "--singers-dir",
            str(self.singers),
            "--singer",
            SINGER_ID,
            "--phonemizer",
            f"OpenUtau.Plugin.Builtin.{phonemizer}",
        ]
        for assignment in ASSIGN:
            arguments += ["--assign", assignment]
        return main([*arguments, *extra])


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Rig:
    return Rig(tmp_path, monkeypatch)


@pytest.mark.parametrize("phonemizer", PHONEMIZERS)
def test_the_unknown_score_stops_before_rendering_and_names_every_word_voice_and_bar(
    rig: Rig, capsys: pytest.CaptureFixture[str], phonemizer: str
) -> None:
    if model_in_host():
        pytest.skip("the internal research host guesses pronunciations instead of stopping")
    assert rig.generate("unknown", phonemizer, "--no-composed-pronunciations") != 0
    shown = capsys.readouterr().err
    assert "PRONUNCIATION_UNKNOWN" in shown
    assert "nothing was rendered" in shown
    voices = "Tenor, Lead, Baritone, Bass"
    assert f'"lov\'d" (bar 1, beat 1; {voices})' in shown
    assert '"mammy" (bar 2, beat 4; Bass)' in shown  # the Bass's own word: only the Bass
    assert f'"ev\'ryone" (bar 4, beat 1; {voices})' in shown  # whole word of three syllables
    assert f'"\'neath" (bar 6, beat 3; {voices})' in shown
    assert f'"o\'er" (bar 7, beat 1; {voices})' in shown
    for fine in ("together", "always", "don't", "sing", "home"):
        assert f'"{fine}"' not in shown  # no word the dictionary has is blamed
    out = rig.root / f"out-unknown-{phonemizer}"
    assert not list(out.glob("*_learning_tracks"))  # no package was published
    assert [p.name for p in out.iterdir()] == [
        "english-quartet-unknown-words_learning_tracks.pronunciations-template.json"
    ]  # only the template


@pytest.mark.parametrize("version", ["known", "respelled"])
@pytest.mark.parametrize("phonemizer", PHONEMIZERS)
def test_scores_whose_words_the_dictionary_has_are_never_refused_for_pronunciation(
    rig: Rig, capsys: pytest.CaptureFixture[str], version: str, phonemizer: str
) -> None:
    code = rig.generate(version, phonemizer)
    shown = capsys.readouterr().err
    assert "PRONUNCIATION_UNKNOWN" not in shown, shown
    # the synthetic voicebank has no English sounds, so the run ends at the stem check (or, with a
    # voicebank that sings these phonemes, succeeds); it is never a pronunciation refusal
    assert code == 0 or "STEM_" in shown, shown
