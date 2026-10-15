"""The acceptance score with pronunciations, end to end through the CLI and the real render host.

``docs/acceptance/fixtures`` holds the "unknown words" score (five words the dictionary lacks) and a sample
pronunciations file for it. The path a singer takes, here without a person: BLT stops and names the places and
writes a template; the pronunciations are decided; BLT generates, the package records the score's own words next
to the decisions; a refused or stale decision publishes nothing. The synthetic voicebank cannot sing English
sounds, so the test first gives it a recording for every sound the engine asks for (a stand-in for a real
voicebank; it says nothing about how English sounds).
"""

import hashlib
import json
import math
import os
import struct
import subprocess
import wave
from pathlib import Path
from typing import Any

import pytest

from barbershop_tracks.cli import main
from barbershop_tracks.core.pipeline import prepare, read_overrides
from barbershop_tracks.core.readiness import RoleAssignments
from barbershop_tracks.core.synthesis import SourceIdentity, VoiceEngineRef
from barbershop_tracks.core.synthesis.openutau import resolve_overrides, write_ustx
from barbershop_tracks.models import VoiceRole
from host_support import host_environment, require_host
from synthetic_voicebank import SINGER_ID, build_voicebank

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "docs" / "acceptance" / "fixtures"
UNKNOWN = FIXTURES / "english-quartet-unknown-words.musicxml"
SAMPLE = FIXTURES / "english-quartet-unknown-words.pronunciations-arpasing.json"
ARPASING = "OpenUtau.Plugin.Builtin.ArpasingPhonemizer"
ASSIGN = ["TENOR=P1/s1/v1", "LEAD=P2/s1/v1", "BARITONE=P3/s1/v1", "BASS=P4/s1/v1"]
ROLES = (VoiceRole.TENOR, VoiceRole.LEAD, VoiceRole.BARITONE, VoiceRole.BASS)
EXPECTED_PLACES = 17  # four unknown words sung by all four voices, and the Bass's own "mammy"


def model_in_host() -> bool:
    record = require_host() / "blt-host-build.json"
    return bool(json.loads(record.read_text(encoding="utf-8")).get("g2p_model") == "included")


class Rig:
    def __init__(self, root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.root = root
        self.singers = root / "singers"
        build_voicebank(self.singers)
        self.score = root / "unknown.musicxml"
        self.score.write_bytes(UNKNOWN.read_bytes())
        monkeypatch.setenv("BLT_CONFIG", str(root / "no-config.json"))
        monkeypatch.setenv("BLT_DATA_DIR", str(root / "data"))
        monkeypatch.setenv("BLT_HOST_DIR", str(require_host()))
        monkeypatch.setenv("BLT_FOLLOW_LEAD", "1")
        for key, value in host_environment().items():
            if key == "DOTNET_ROOT":
                monkeypatch.setenv(key, value)
        self.out = root / "out"

    def sha(self) -> str:
        return hashlib.sha256(self.score.read_bytes()).hexdigest()

    def pronunciations(self, edit: Any = None, name: str = "pronunciations.json") -> Path:
        document = json.loads(SAMPLE.read_text(encoding="utf-8"))
        document["source_sha256"] = self.sha()
        for item in document["overrides"]:
            item["approved_by"] = "A. Singer"
        if edit is not None:
            edit(document)
        path = self.root / name
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def generate(self, *extra: str, phonemizer: str = ARPASING) -> int:
        arguments = [
            "generate",
            str(self.score),
            "--out",
            str(self.out),
            "--singers-dir",
            str(self.singers),
            "--singer",
            SINGER_ID,
            "--phonemizer",
            phonemizer,
            *extra,
        ]
        for assignment in ASSIGN:
            arguments += ["--assign", assignment]
        return main(arguments)

    def templates(self) -> list[Path]:
        return sorted(self.out.glob("*.pronunciations-template.json")) if self.out.is_dir() else []

    def staging_empty(self) -> bool:
        staging = self.root / "data" / "runtime" / "staging"
        return not staging.is_dir() or not any(staging.iterdir())

    # --- a stand-in voicebank that has a recording for every sound the engine asks for ---------

    def complete_voicebank(self, pronunciations: Path) -> int:
        """Add recordings until the engine asks for no sound the bank lacks; returns how many."""
        plan = prepare(
            __import__(
                "barbershop_tracks.core.musicxml", fromlist=["parse_musicxml"]
            ).parse_musicxml(self.score),
            RoleAssignments(
                entries=tuple((role, f"P{i}/s1/v1") for i, role in enumerate(ROLES, start=1))
            ),
            identity=SourceIdentity(display_name=self.score.name, sha256=self.sha()),
            engine_refs={
                role: VoiceEngineRef(singer=SINGER_ID, phonemizer=ARPASING, renderer="WORLDLINE-R")
                for role in ROLES
            },
            follow_lead=True,
        ).plan
        assert plan is not None
        resolved = resolve_overrides(
            plan, read_overrides(pronunciations, source_sha256=self.sha()), source_sha256=self.sha()
        )
        project = self.root / "bank-probe.ustx"
        project.write_text(write_ustx(plan, overrides=resolved).text, encoding="utf-8")
        bank = self.singers / SINGER_ID
        added: set[str] = set()
        for _round in range(30):
            done = subprocess.run(
                [
                    str(require_host() / "blt-render-host.exe"),
                    "--project",
                    str(project),
                    "--phonemize-only",
                    "--singers-dir",
                    str(self.singers),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=host_environment(),
                timeout=180,
                check=False,
            )
            result = json.loads(done.stdout.strip().splitlines()[-1])
            assert result["status"] == "ok", result
            missing = {u["alias"] for u in result.get("unsung_phonemes", [])} - added
            if not missing and result["unsung_phoneme_count"] == 0:
                return len(added)
            assert missing, result  # an alias the host keeps listing was already added
            lines: list[str] = []
            for alias in sorted(missing):
                name = f"s{len(added) + len(lines)}.wav"
                _sine(bank / name, 200.0 + 7 * (len(added) + len(lines)))
                lines.append(f"{name}={alias},0,200,-300,50,50")
            with (bank / "oto.ini").open("a", encoding="utf-8") as handle:
                handle.write("\n".join(lines) + "\n")
            added |= missing
        raise AssertionError("the stand-in voicebank never became complete")


def _sine(path: Path, frequency: float, seconds: float = 1.0) -> None:
    rate = 44100
    frames = int(rate * seconds)
    fade = int(rate * 0.02)
    samples = [
        int(
            12000
            * min(1.0, i / fade, (frames - i) / fade)
            * math.sin(2 * math.pi * frequency * i / rate)
        )
        for i in range(frames)
    ]
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(struct.pack(f"<{len(samples)}h", *samples))


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Rig:
    require_host()
    if model_in_host():
        pytest.skip("the research host guesses pronunciations instead of stopping")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return Rig(tmp_path, monkeypatch)


def test_the_stopped_run_writes_a_template_with_one_undecided_entry_per_place(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    assert rig.generate() != 0
    shown = capsys.readouterr().err
    assert "PRONUNCIATION_UNKNOWN" in shown
    assert "pronunciations template written to" in shown
    assert "--approve-pronunciations" in shown
    (path,) = rig.templates()
    template = json.loads(path.read_text(encoding="utf-8"))
    assert template["schema"] == "blt.pronunciation-overrides/1"
    assert template["source_sha256"] == rig.sha()
    entries = template["overrides"]
    assert len(entries) == EXPECTED_PLACES
    assert all(e["symbols"] is None and e["approved_by"] is None for e in entries)
    assert all(e["phonemizer"] == ARPASING for e in entries)
    assert {(e["word"], e["where"]) for e in entries} == {
        ("lov'd", "bar 1, beat 1"),
        ("mammy", "bar 2, beat 4"),
        ("ev'ryone", "bar 4, beat 1"),
        ("'neath", "bar 6, beat 3"),
        ("o'er", "bar 7, beat 1"),
    }
    assert [e["voice"] for e in entries if e["word"] == "mammy"] == ["bass"]
    # the unfilled template decides nothing: the same words still stop the run
    assert rig.generate("--approve-pronunciations", str(path), "--replace") != 0
    assert "PRONUNCIATION_UNKNOWN" in capsys.readouterr().err
    assert not (rig.out / "unknown_learning_tracks").exists()


def test_the_sample_pronunciations_cover_exactly_the_places_the_real_run_names(rig: Rig) -> None:
    sample = json.loads(SAMPLE.read_text(encoding="utf-8"))
    assert len(sample["overrides"]) == EXPECTED_PLACES
    assert sample["source_sha256"] == rig.sha()  # tied to the score exactly as shipped
    assert rig.generate() != 0
    (path,) = rig.templates()
    template = json.loads(path.read_text(encoding="utf-8"))
    key = lambda e: (e["voice"], e["start"], e["word"], e["phonemizer"])  # noqa: E731
    assert sorted(map(key, template["overrides"])) == sorted(map(key, sample["overrides"]))


def test_decided_pronunciations_generate_and_the_package_keeps_the_scores_own_words(
    rig: Rig,
) -> None:
    decided = rig.pronunciations()
    rig.complete_voicebank(decided)
    score_before = rig.score.read_bytes()
    code = rig.generate("--approve-pronunciations", str(decided), "--keep-project")
    assert code == 0
    assert rig.score.read_bytes() == score_before  # the score is never touched
    package = rig.out / "unknown_learning_tracks"
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    records = manifest["pronunciation"]["overrides"]
    assert len(records) == EXPECTED_PLACES
    assert manifest["source"]["sha256"] == rig.sha()
    assert {r["source_sha256"] for r in records} == {rig.sha()}
    assert {r["phonemizer"] for r in records} == {ARPASING}
    ev = next(r for r in records if r["word"] == "ev'ryone" and r["voice"] == "lead")
    assert ev["score_lyrics"] == ["ev'", "ry", "one"]  # the syllables as the score has them
    assert ev["symbols"] == "eh v r iy w ah n"
    assert ev["where"] == "bar 4, beat 1"
    assert ev["effective_phonemes"]  # what the engine made of it, from the engine itself
    assert ev["approved_by"] == "A. Singer"
    mammy = [r for r in records if r["word"] == "mammy"]
    assert [r["voice"] for r in mammy] == ["bass"]
    ustx = (package / "project" / "project.ustx").read_text(encoding="utf-8")
    assert 'lyric: "ev\'ryone[eh v r iy w ah n]"' in ustx  # written only as a phonetic hint
    assert 'lyric: "o\'er[ow er]"' in ustx
    assert 'lyric: "together"' in ustx  # words with an entry are left exactly alone
    hinted = [
        line for line in ustx.splitlines() if line.strip().startswith("lyric:") and "[" in line
    ]
    assert len(hinted) == EXPECTED_PLACES  # one hint per decided place, nowhere else
    assert (package / "01_Full_Quartet.wav").is_file()
    assert rig.staging_empty()


def test_a_decision_for_only_some_voices_still_stops_at_the_others(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    def only_the_lead(document: dict[str, Any]) -> None:
        document["overrides"] = [e for e in document["overrides"] if e["voice"] == "lead"]

    assert rig.generate("--approve-pronunciations", str(rig.pronunciations(only_the_lead))) != 0
    shown = capsys.readouterr().err
    assert "PRONUNCIATION_UNKNOWN" in shown
    assert '"lov\'d" (bar 1, beat 1; Tenor, Baritone, Bass)' in shown  # the Lead was decided
    assert '"mammy" (bar 2, beat 4; Bass)' in shown  # the Bass's own word was not
    assert not (rig.out / "unknown_learning_tracks").exists()


def test_a_symbol_the_engine_does_not_know_stops_before_rendering_and_is_named(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    def spoil(document: dict[str, Any]) -> None:
        for item in document["overrides"]:
            if item["word"] == "o'er" and item["voice"] == "lead":
                item["symbols"] = "ow zzz"

    assert rig.generate("--approve-pronunciations", str(rig.pronunciations(spoil))) != 0
    shown = capsys.readouterr().err
    assert "PRONUNCIATION_INVALID" in shown
    assert "'zzz'" in shown
    assert '"o\'er" (bar 7, beat 1; Lead)' in shown
    assert "nothing was rendered" in shown
    assert not (rig.out / "unknown_learning_tracks").exists()
    assert rig.staging_empty()


def test_a_refusal_leaves_a_package_that_was_already_there_exactly_as_it_was(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    decided = rig.pronunciations()
    rig.complete_voicebank(decided)
    assert rig.generate("--approve-pronunciations", str(decided)) == 0
    package = rig.out / "unknown_learning_tracks"
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in package.iterdir()}

    def spoil(document: dict[str, Any]) -> None:
        document["overrides"][0]["symbols"] = "l zzz"

    capsys.readouterr()
    assert (
        rig.generate(
            "--approve-pronunciations", str(rig.pronunciations(spoil, "spoiled.json")), "--replace"
        )
        != 0
    )
    assert "PRONUNCIATION_INVALID" in capsys.readouterr().err
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in package.iterdir()}
    assert after == before  # not one file of the earlier package changed
    assert rig.staging_empty()
    # and the corrected file then replaces it
    assert rig.generate("--approve-pronunciations", str(decided), "--replace") == 0


def test_pronunciations_decided_for_another_version_of_the_score_are_refused(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    decided = rig.pronunciations()
    rig.score.write_bytes(rig.score.read_bytes().replace(b"We", b"we", 1) + b"<!-- edited -->")
    assert rig.sha() != json.loads(decided.read_text(encoding="utf-8"))["source_sha256"]
    assert rig.generate("--approve-pronunciations", str(decided)) != 0
    shown = capsys.readouterr().err
    assert "OVERRIDES_WRONG_SCORE" in shown
    assert "different version of the score" in shown
    assert not rig.out.exists() or not any(rig.out.glob("*_learning_tracks"))


def test_a_decision_the_score_no_longer_matches_is_refused_not_skipped(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    def wrong_word(document: dict[str, Any]) -> None:
        document["overrides"][0]["word"] = "o'er"  # the first place holds "lov'd"

    assert rig.generate("--approve-pronunciations", str(rig.pronunciations(wrong_word))) != 0
    shown = capsys.readouterr().err
    assert "OVERRIDE_WORD_MISMATCH" in shown
    assert "'lov'd'" in shown or '"lov\'d"' in shown or "lov'd" in shown


def test_a_decision_written_for_another_engine_is_refused(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    code = rig.generate(
        "--approve-pronunciations",
        str(rig.pronunciations()),
        phonemizer="OpenUtau.Plugin.Builtin.EnXSampaPhonemizer",
    )
    assert code != 0
    shown = capsys.readouterr().err
    assert "OVERRIDE_PHONEMIZER_MISMATCH" in shown
    assert "ArpasingPhonemizer" in shown
