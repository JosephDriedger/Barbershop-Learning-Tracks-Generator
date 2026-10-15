"""The pronunciations file: bound to one score, one voice and place, and never half-read."""

import json
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest

from barbershop_tracks.core.pipeline import (
    OVERRIDES_SCHEMA,
    PipelineError,
    overrides_document,
    provenance_entries,
    read_overrides,
    template_document,
)
from barbershop_tracks.core.synthesis import VoiceEngineRef
from barbershop_tracks.core.synthesis.openutau import (
    PronunciationOverride,
    parse_symbols,
    resolve_overrides,
)
from barbershop_tracks.models import Lyric, Syllabic, VoiceRole
from readiness_builders import PITCHES, note
from synth_builders import ROLES, SOURCE, plan_of

ARPASING = "OpenUtau.Plugin.Builtin.ArpasingPhonemizer"
SHA = SOURCE.sha256 or ""


def blocked(role: str = "lead", start: str = "3/2", word: str = "ev'ry") -> dict[str, Any]:
    return {
        "role": role,
        "start": start,
        "where": "bar 1, beat 2",
        "lyric": word,
        "word": word,
        "phonemizer": ARPASING,
        "voice": role.title(),
    }


def entry(**changes: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "voice": "lead",
        "start": "3/2",
        "word": "ev'ry",
        "phonemizer": ARPASING,
        "symbols": "eh v r iy",
        "approved_by": "A. Singer",
    }
    base.update(changes)
    return base


def write(path: Path, entries: list[dict[str, Any]], **header: Any) -> Path:
    document = {"schema": OVERRIDES_SCHEMA, "source_sha256": SHA, "overrides": entries, **header}
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_the_template_has_one_undecided_entry_per_blocked_voice_and_place() -> None:
    template = template_document(
        [blocked("lead"), blocked("tenor"), blocked("lead", "8", "o'er")], SHA
    )
    assert template["schema"] == OVERRIDES_SCHEMA
    assert template["source_sha256"] == SHA
    entries = template["overrides"]
    assert [(e["voice"], e["start"], e["word"]) for e in entries] == [
        ("lead", "3/2", "ev'ry"),
        ("tenor", "3/2", "ev'ry"),
        ("lead", "8", "o'er"),
    ]
    assert all(e["symbols"] is None and e["approved_by"] is None for e in entries)
    assert "ARPAbet" in entries[0]["notation"]


def test_a_place_blt_could_not_locate_is_left_out_of_the_template() -> None:
    lost = {"role": None, "start": None, "lyric": "x", "phonemizer": ARPASING}
    assert template_document([lost], SHA)["overrides"] == []


def test_an_undecided_template_decides_nothing(tmp_path: Path) -> None:
    template = template_document([blocked()], SHA)
    path = tmp_path / "t.json"
    path.write_text(json.dumps(template), encoding="utf-8")
    assert read_overrides(path, source_sha256=SHA) == ()


def test_a_filled_in_entry_becomes_an_override_bound_to_the_score(tmp_path: Path) -> None:
    (found,) = read_overrides(write(tmp_path / "p.json", [entry()]), source_sha256=SHA)
    assert found.role is VoiceRole.LEAD
    assert found.start == Fraction(3, 2)
    assert found.word == "ev'ry"
    assert found.symbols == ("eh", "v", "r", "iy")
    assert found.source_sha256 == SHA
    assert found.approved_by == "A. Singer"


def test_the_file_round_trips() -> None:
    original = PronunciationOverride(
        role=VoiceRole.BASS,
        start=Fraction(7, 2),
        word="o'er",
        phonemizer=ARPASING,
        symbols=parse_symbols("ow er"),
        approved_by="A. Singer",
        source_sha256=SHA,
    )
    document = overrides_document(
        [original], SHA, where={("bass", Fraction(7, 2)): "bar 1, beat 4"}
    )
    from barbershop_tracks.core.pipeline import overrides_from_document

    (again,) = overrides_from_document(document, source_sha256=SHA)
    assert again == original
    assert document["overrides"][0]["where"] == "bar 1, beat 4"


def test_decisions_for_another_version_of_the_score_are_refused_as_a_whole(tmp_path: Path) -> None:
    path = write(tmp_path / "p.json", [entry()], source_sha256="cd" * 32)
    with pytest.raises(PipelineError) as error:
        read_overrides(path, source_sha256=SHA)
    assert error.value.code == "OVERRIDES_WRONG_SCORE"
    assert "decide them again" in error.value.message


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"voice": "soprano"}, "OVERRIDES_INVALID"),
        ({"start": "soon"}, "OVERRIDES_INVALID"),
        ({"symbols": 7}, "OVERRIDES_INVALID"),
        ({"symbols": "eh [v] r"}, "OVERRIDES_SYMBOL_FORM"),
        ({"symbols": "   "}, "OVERRIDES_EMPTY"),
        ({"approved_by": ""}, "OVERRIDES_INVALID"),
        ({"approved_by": None}, "OVERRIDES_INVALID"),
        ({"word": 4}, "OVERRIDES_INVALID"),
        ({"phonemizer": "OpenUtau.Core.DefaultPhonemizer"}, "OVERRIDES_PHONEMIZER_UNSUPPORTED"),
    ],
)
def test_an_entry_that_cannot_be_used_is_refused_not_skipped(
    tmp_path: Path, change: dict[str, Any], code: str
) -> None:
    with pytest.raises(PipelineError) as error:
        read_overrides(write(tmp_path / "p.json", [entry(**change)]), source_sha256=SHA)
    assert error.value.code == code


@pytest.mark.parametrize("text", ["{", "[]", '{"schema": "other/1"}'])
def test_a_file_that_is_not_ours_is_refused(tmp_path: Path, text: str) -> None:
    path = tmp_path / "x.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(PipelineError) as error:
        read_overrides(path, source_sha256=SHA)
    assert error.value.code in ("OVERRIDES_INVALID", "OVERRIDES_UNREADABLE")


def test_a_missing_file_is_reported_by_name(tmp_path: Path) -> None:
    with pytest.raises(PipelineError) as error:
        read_overrides(tmp_path / "absent.json", source_sha256=SHA)
    assert error.value.code == "OVERRIDES_UNREADABLE"
    assert "absent.json" in error.value.message


def test_the_package_record_keeps_the_score_text_beside_the_decision() -> None:
    syllables = [
        note(
            i,
            1,
            PITCHES[VoiceRole.LEAD],
            lyrics=(Lyric(text=text, syllabic=kind),),
        )
        for i, (text, kind) in enumerate(
            [("ev'", Syllabic.BEGIN), ("ry", Syllabic.MIDDLE), ("one", Syllabic.END)]
        )
    ]
    voices = {r.value: [note(0, 1, PITCHES[r], lyrics=(Lyric(text="la"),))] for r in ROLES}
    voices["lead"] = syllables
    engine = VoiceEngineRef(singer="s", phonemizer=ARPASING, renderer="WORLDLINE-R")
    plan = plan_of(voices=voices, engine_refs=dict.fromkeys(ROLES, engine))
    decided = PronunciationOverride(
        role=VoiceRole.LEAD,
        start=Fraction(0),
        word="ev'ryone",
        phonemizer=ARPASING,
        symbols=parse_symbols("eh v r iy w ah n"),
        approved_by="A. Singer",
        source_sha256=SHA,
    )
    resolved = resolve_overrides(plan, [decided], source_sha256=SHA)
    host = {"pronunciations": [{"track": "Lead", "position": 0, "phonemes": ["- eh", "eh v"]}]}
    (record,) = provenance_entries(plan, resolved, host)
    assert record["score_lyrics"] == ["ev'", "ry", "one"]  # the score's text, not replaced
    assert record["word"] == "ev'ryone"
    assert record["symbols"] == "eh v r iy w ah n"
    assert record["alphabet"] == "arpabet"
    assert record["approved_by"] == "A. Singer"
    assert record["source_sha256"] == SHA
    assert record["where"] == "bar 1, beat 1"
    assert record["effective_phonemes"] == ["- eh", "eh v"]
    assert provenance_entries(plan, resolved, None)[0]["effective_phonemes"] is None
    assert provenance_entries(plan, resolve_overrides(plan, [], source_sha256=SHA), host) == []
