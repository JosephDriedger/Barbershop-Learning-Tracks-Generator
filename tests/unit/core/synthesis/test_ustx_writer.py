"""The OpenUtau 0.1.565 / USTX 0.7 writer: determinism, structure, timing, lyrics, configuration."""

import json
from collections.abc import Callable, Sequence
from dataclasses import replace
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest
import yaml

from barbershop_tracks.core.synthesis import (
    LyricProvenance,
    LyricState,
    MeterPoint,
    NoteLyric,
    PlannedNote,
    PlanNotReadyError,
    SynthesisPlan,
    TempoPoint,
    VoiceEngineRef,
)
from barbershop_tracks.core.synthesis.openutau import (
    MAX_TEMPO_DRIFT_SECONDS,
    MIN_NOTE_TICKS,
    TARGET_0_1_565,
    OpenUtauTarget,
    UstxDocument,
    UstxError,
    read_ustx_version,
    require_ustx_version,
    target_for,
    validate_lyric_text,
    write_ustx,
)
from barbershop_tracks.models import Melisma, PerformedSong, Pitch, Step, TempoChange, VoiceRole
from midi_builders import performed_of
from readiness_builders import PITCHES, note, quartet_lines, tempo_at
from synth_builders import full_lyrics, plan_of, refs, sung, text

OBSERVATIONS = Path(__file__).resolve().parents[3] / "fixtures" / "openutau" / "observations"


def doc(plan: SynthesisPlan | None = None, **kwargs: Any) -> UstxDocument:
    return write_ustx(plan if plan is not None else plan_of(), **kwargs)


def parsed(plan: SynthesisPlan | None = None) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(doc(plan).text)
    return data


def code_of(call: Callable[[], object]) -> str:
    with pytest.raises(UstxError) as info:
        call()
    return info.value.code


def with_voice(plan: SynthesisPlan, role: VoiceRole, notes: Sequence[PlannedNote]) -> SynthesisPlan:
    voices = tuple(replace(v, notes=tuple(notes)) if v.role is role else v for v in plan.voices)
    return replace(plan, voices=voices, output=replace(plan.output, performed_length=Fraction(64)))


def planned(
    index: int,
    start: int | Fraction,
    duration: int | Fraction,
    lyric: NoteLyric,
    pitch: int = 60,
) -> PlannedNote:
    return PlannedNote(
        index=index,
        start=Fraction(start),
        duration=Fraction(duration),
        midi_pitch=pitch,
        lyric=lyric,
    )


def score_lyric(word: str) -> NoteLyric:
    prov = LyricProvenance(line_id="L", performed_start=Fraction(0), analysis_role="syllable")
    return NoteLyric(state=LyricState.SCORE_LYRIC, text=word, provenance=prov)


def continuation() -> NoteLyric:
    prov = LyricProvenance(
        line_id="L", performed_start=Fraction(0), analysis_role="melisma_continuation"
    )
    return NoteLyric(state=LyricState.SCORE_CONTINUATION, text=None, provenance=prov)


# --- target and version ---


def test_the_only_target_is_the_tested_release_and_declares_ustx_0_7() -> None:
    assert target_for("0.1.565") is TARGET_0_1_565
    assert (TARGET_0_1_565.ustx_version, TARGET_0_1_565.resolution) == ("0.7", 480)
    assert TARGET_0_1_565.source_commit == "a60ca5830b9064556157245d4bf8f5920d93e5f8"
    assert code_of(lambda: target_for("0.1.600")) == "USTX_TARGET_UNSUPPORTED"
    assert code_of(lambda: target_for("0.7")) == "USTX_TARGET_UNSUPPORTED"
    untested = OpenUtauTarget(
        openutau_version="9.9.9",
        ustx_version="0.7",
        resolution=480,
        renderers=TARGET_0_1_565.renderers,
        source_commit="0" * 40,
    )
    assert code_of(lambda: doc(target=untested)) == "USTX_TARGET_UNSUPPORTED"


def test_the_output_declares_the_target_version_and_a_foreign_version_is_detected() -> None:
    text_out = doc().text
    assert read_ustx_version(text_out) == "0.7"
    require_ustx_version(text_out, TARGET_0_1_565)
    assert code_of(
        lambda: require_ustx_version(text_out.replace('"0.7"', '"0.10"'), TARGET_0_1_565)
    ) == ("USTX_VERSION_MISMATCH")
    assert (
        code_of(lambda: require_ustx_version("name: x\n", TARGET_0_1_565))
        == "USTX_VERSION_MISMATCH"
    )


# --- determinism ---


def test_the_output_is_deterministic_and_carries_no_machine_or_time_detail() -> None:
    first, second = doc(), doc()
    assert first.text == second.text
    assert first.encode() == second.encode()
    raw = first.encode()
    assert b"\r" not in raw
    assert not raw.startswith(b"\xef\xbb\xbf")
    for forbidden in ("Users", "C:\\", "D:\\", "/home/", "T00:", "2026", "tmp"):
        assert forbidden not in first.text


# --- structure, against what OpenUtau 0.1.565 itself saved ---


def test_the_top_level_layout_matches_the_release_save_order() -> None:
    data = parsed()
    assert list(data) == [
        "name", "comment", "output_dir", "cache_dir", "ustx_version", "resolution", "bpm",
        "beat_per_bar", "beat_unit", "expressions", "exp_selectors", "exp_primary",
        "exp_secondary", "key", "time_signatures", "tempos", "tracks", "voice_parts", "wave_parts",
    ]  # fmt: skip
    assert data["resolution"] == 480
    assert data["wave_parts"] == []
    for required in ("dyn", "pitd", "clr", "eng", "vel", "vol", "atk", "dec"):
        assert required in data["expressions"]  # the loader's required expression set


def test_track_and_note_fields_equal_the_observed_openutau_fields() -> None:
    c01 = json.loads((OBSERVATIONS / "C01_USTX_STRUCTURE.json").read_text(encoding="utf-8"))
    data = parsed()
    assert set(data["tracks"][0]) == set(c01["details"]["track_fields"])
    assert set(data["voice_parts"][0]["notes"][0]) == set(c01["details"]["note_fields"])
    assert "velocity" not in data["voice_parts"][0]["notes"][0]  # none is stored by 0.1.565


def test_four_tracks_in_ttbb_order_with_matching_parts() -> None:
    data = parsed()
    assert [t["track_name"] for t in data["tracks"]] == ["Tenor", "Lead", "Baritone", "Bass"]
    assert [p["name"] for p in data["voice_parts"]] == ["Tenor", "Lead", "Baritone", "Bass"]
    assert [p["track_no"] for p in data["voice_parts"]] == [0, 1, 2, 3]
    assert all(p["position"] == 0 for p in data["voice_parts"])


def test_pitch_position_duration_and_lyric_of_every_note_come_from_the_plan() -> None:
    data = parsed()
    for voice, part in zip(plan_of().voices, data["voice_parts"], strict=True):
        got = [(n["position"], n["duration"], n["tone"], n["lyric"]) for n in part["notes"]]
        want = [
            (int(n.start * 480), int(n.duration * 480), n.midi_pitch, n.lyric.text)
            for n in voice.notes
        ]
        assert got == want
    assert [n["lyric"] for n in data["voice_parts"][1]["notes"]] == ["one", "two", "three", "four"]


def test_the_sounding_pitch_is_written_not_the_written_one() -> None:
    plan = plan_of()
    assert {n["tone"] for n in parsed(plan)["voice_parts"][1]["notes"]} == {
        PITCHES[VoiceRole.LEAD].midi_note
    }


# --- singer, phonemizer, renderer ---


def test_singer_phonemizer_and_renderer_are_written_exactly_and_per_voice() -> None:
    bass = VoiceEngineRef(
        singer="my-bass-bank",
        phonemizer="OpenUtau.Plugin.Builtin.ArpasingPhonemizer",
        renderer="CLASSIC",
    )
    data = parsed(plan_of(engine_refs=refs(bass=bass)))
    tenor, bass_track = data["tracks"][0], data["tracks"][3]
    assert (tenor["singer"], tenor["phonemizer"], tenor["renderer_settings"]) == (
        "test-singer", "OpenUtau.Core.DefaultPhonemizer", {"renderer": "WORLDLINE-R"}
    )  # fmt: skip
    assert (bass_track["singer"], bass_track["phonemizer"], bass_track["renderer_settings"]) == (
        "my-bass-bank", "OpenUtau.Plugin.Builtin.ArpasingPhonemizer", {"renderer": "CLASSIC"}
    )  # fmt: skip


def test_unusable_configuration_is_an_error_not_a_fallback() -> None:
    def with_ref(**kwargs: str) -> str:
        base = {"singer": "ok", "phonemizer": "A.B", "renderer": "WORLDLINE-R"} | kwargs
        return code_of(lambda: doc(plan_of(engine_refs=refs(lead=VoiceEngineRef(**base)))))

    assert with_ref(renderer="TURBO") == "USTX_RENDERER_UNKNOWN"
    assert with_ref(phonemizer="DefaultPhonemizer") == "USTX_PHONEMIZER_REF"
    assert with_ref(phonemizer="a b.C") == "USTX_PHONEMIZER_REF"
    assert with_ref(singer="..\\evil") == "USTX_SINGER_REF"
    assert with_ref(singer="a/b") == "USTX_SINGER_REF"


# --- readiness and lyrics ---


def test_a_plan_with_an_unresolved_lyric_cannot_be_written_and_no_default_is_inserted() -> None:
    plan = plan_of(
        voices={**full_lyrics(), "bass": sung(VoiceRole.BASS, ["one", None, "three", "four"])}
    )
    with pytest.raises(PlanNotReadyError) as info:
        write_ustx(plan)
    assert info.value.code == "PLAN_NOT_READY"
    assert info.value.items == 1


def test_a_melisma_continuation_is_written_as_the_documented_extender_only() -> None:
    lead = [
        note(0, 1, PITCHES[VoiceRole.LEAD], lyrics=text("won", melisma=Melisma.UNTYPED)),
        note(1, 1, PITCHES[VoiceRole.LEAD]),
        note(2, 1, PITCHES[VoiceRole.LEAD]),
        note(3, 1, PITCHES[VoiceRole.LEAD], lyrics=text("der")),
    ]
    lyrics = [
        n["lyric"]
        for n in parsed(plan_of(voices={**full_lyrics(), "lead": lead}))["voice_parts"][1]["notes"]
    ]
    assert lyrics == ["won", "+", "+", "der"]
    assert "+~" not in doc(plan_of(voices={**full_lyrics(), "lead": lead})).text


def test_a_continuation_with_nothing_to_continue_is_refused() -> None:
    plan = plan_of()
    voice = plan.voice(VoiceRole.LEAD)
    broken = with_voice(
        plan, VoiceRole.LEAD, [planned(0, 0, 1, continuation()), planned(1, 1, 1, score_lyric("x"))]
    )
    assert code_of(lambda: write_ustx(broken)) == "USTX_CONTINUATION_ORPHAN"
    assert voice.notes  # the original plan is untouched


@pytest.mark.parametrize(
    ("word", "code"),
    [
        ("+", "USTX_LYRIC_RESERVED"),
        ("+~", "USTX_LYRIC_RESERVED"),
        ("-", "USTX_LYRIC_RESERVED"),
        ("+2", "USTX_LYRIC_RESERVED"),
        ("read[r iy d]", "USTX_LYRIC_TEXT"),
        ("caf\u00e9", "USTX_LYRIC_TEXT"),
        (" la", "USTX_LYRIC_TEXT"),
        ("la\t", "USTX_LYRIC_TEXT"),
    ],
)
def test_lyric_text_whose_handling_is_not_established_is_refused(word: str, code: str) -> None:
    assert code_of(lambda: validate_lyric_text(word)) == code
    plan = plan_of()
    broken = with_voice(plan, VoiceRole.LEAD, [planned(0, 0, 1, score_lyric(word))])
    assert code_of(lambda: write_ustx(broken)) == code


@pytest.mark.parametrize("word", ["don't", "well-", "come,", "home.", "why?", "oh!", "la", "A"])
def test_ordinary_lyric_text_round_trips_exactly(word: str) -> None:
    plan = plan_of(
        voices={**full_lyrics(), "lead": sung(VoiceRole.LEAD, [word, "two", "three", "four"])}
    )
    assert parsed(plan)["voice_parts"][1]["notes"][0]["lyric"] == word


# --- timing: exact or refused, never rounded ---


def test_timing_on_the_480_grid_is_exact_including_tuplets_and_odd_ticks() -> None:
    third = Fraction(1, 3)
    values: list[tuple[Fraction, Fraction]] = [
        (Fraction(0), third),
        (third, third),
        (2 * third, third),
        (Fraction(1), Fraction(7, 12)),
        (Fraction(19, 12), Fraction(1, 32) * 3),
    ]
    plan = plan_of()
    notes = [planned(i, s, d, score_lyric("la")) for i, (s, d) in enumerate(values)]
    got = [
        (n["position"], n["duration"])
        for n in parsed(with_voice(plan, VoiceRole.LEAD, notes))["voice_parts"][1]["notes"]
    ]
    assert got == [(0, 160), (160, 160), (320, 160), (480, 280), (760, 45)]


@pytest.mark.parametrize(
    ("start", "duration"),
    [
        (Fraction(1, 7), Fraction(1)),
        (Fraction(0), Fraction(1, 7)),
        (Fraction(1, 64), Fraction(1)),
        (Fraction(0), Fraction(3, 64)),
    ],
)
def test_a_position_or_duration_off_the_grid_is_refused_never_rounded(
    start: Fraction, duration: Fraction
) -> None:
    plan = plan_of()
    broken = with_voice(plan, VoiceRole.LEAD, [planned(0, start, duration, score_lyric("la"))])
    assert code_of(lambda: write_ustx(broken)) == "USTX_TIMING_NOT_ON_GRID"


def test_notes_shorter_than_the_observed_minimum_are_refused() -> None:
    plan = plan_of()
    too_short = Fraction(MIN_NOTE_TICKS - 5, 480)  # integral ticks, but below the minimum
    assert (
        code_of(
            lambda: write_ustx(
                with_voice(plan, VoiceRole.LEAD, [planned(0, 0, too_short, score_lyric("la"))])
            )
        )
        == "USTX_NOTE_TOO_SHORT"
    )
    just_ok = Fraction(MIN_NOTE_TICKS, 480)
    ok = parsed(with_voice(plan, VoiceRole.LEAD, [planned(0, 0, just_ok, score_lyric("la"))]))
    assert ok["voice_parts"][1]["notes"][0]["duration"] == MIN_NOTE_TICKS


# --- tempo and meter ---


def song_with(tempos: list[TempoChange]) -> PerformedSong:
    return performed_of(quartet_lines(**full_lyrics()), tempos=tempos)


def test_tempo_events_are_preserved_with_their_tick_positions() -> None:
    plan = plan_of(song_with([tempo_at(0, 100), tempo_at(8, 120), tempo_at(12, 90)]))
    data = parsed(plan)
    assert data["tempos"] == [
        {"position": 0, "bpm": 100}, {"position": 3840, "bpm": 120}, {"position": 5760, "bpm": 90}
    ]  # fmt: skip
    assert data["bpm"] == 100
    result = doc(plan)
    assert result.warnings == (*[w for w in result.warnings if w.code != "USTX_TEMPO_QUANTIZED"],)
    assert all(r.error_bpm == 0 for r in result.tempo_records)


def test_a_tempo_a_double_cannot_hold_exactly_is_reported_not_silently_rounded() -> None:
    plan = plan_of(
        performed_of(
            quartet_lines(**full_lyrics()),
            tempos=[tempo_at(0, 100)],
        )
    )
    odd = replace(plan, tempo=(replace(plan.tempo[0], bpm=Fraction(100, 3)),))
    result = write_ustx(odd)
    record = result.tempo_records[0]
    assert record.bpm_exact == Fraction(100, 3)
    assert record.error_bpm != 0
    assert float(record.bpm_exact) == record.bpm_written
    assert [w.code for w in result.warnings if w.code == "USTX_TEMPO_QUANTIZED"] == [
        "USTX_TEMPO_QUANTIZED"
    ]


def meters(*points: tuple[int, int, int]) -> SynthesisPlan:
    """A ready plan whose meter events are set directly: (position, beats, beat_type)."""
    plan = plan_of()
    return replace(
        plan,
        meter=tuple(MeterPoint(position=Fraction(p), beats=n, beat_type=d) for p, n, d in points),
    )


def test_explicit_meters_become_bar_positions() -> None:
    plan = meters((0, 4, 4), (4, 3, 4), (7, 6, 8))
    assert parsed(plan)["time_signatures"] == [
        {"bar_position": 0, "beat_per_bar": 4, "beat_unit": 4},
        {"bar_position": 1, "beat_per_bar": 3, "beat_unit": 4},
        {"bar_position": 2, "beat_per_bar": 6, "beat_unit": 8},
    ]
    assert doc(plan).warnings == ()


def test_a_missing_meter_is_a_blocking_error_not_an_assumed_4_4() -> None:
    assert code_of(lambda: write_ustx(replace(plan_of(), meter=()))) == "USTX_METER_MISSING"


def test_a_first_meter_after_position_zero_is_a_blocking_error() -> None:
    assert code_of(lambda: write_ustx(meters((4, 3, 4)))) == "USTX_METER_MISSING"


def test_a_meter_change_off_the_bar_grid_is_a_blocking_error_not_dropped() -> None:
    # 5 is not a 4/4 bar line (a pickup or an irregular measure, say)
    assert code_of(lambda: write_ustx(meters((0, 4, 4), (5, 3, 4)))) == "USTX_METER_UNSUPPORTED"


def test_a_beat_unit_that_is_not_a_power_of_two_is_a_blocking_error() -> None:
    assert code_of(lambda: write_ustx(meters((0, 4, 3)))) == "USTX_METER_UNSUPPORTED"


def test_a_continuation_after_a_gap_is_refused_because_openutau_would_not_extend() -> None:
    plan = plan_of()
    gapped = with_voice(
        plan,
        VoiceRole.LEAD,
        [planned(0, 0, 1, score_lyric("x")), planned(1, 2, 1, continuation())],  # gap 1..2
    )
    assert code_of(lambda: write_ustx(gapped)) == "USTX_CONTINUATION_GAP"
    touching = with_voice(
        plan,
        VoiceRole.LEAD,
        [planned(0, 0, 1, score_lyric("x")), planned(1, 1, 1, continuation())],
    )
    assert write_ustx(touching).note_count > 0


# --- tempo tolerance ---


def with_tempos(*points: tuple[int, Fraction]) -> SynthesisPlan:
    plan = plan_of()
    return replace(plan, tempo=tuple(TempoPoint(position=Fraction(p), bpm=b) for p, b in points))


def test_exactly_representable_tempos_have_zero_drift() -> None:
    result = doc(with_tempos((0, Fraction(100)), (8, Fraction(125, 2))))
    assert result.tempo_drift_seconds == 0
    assert all(r.error_bpm == 0 for r in result.tempo_records)


def test_the_drift_of_an_inexact_tempo_is_measured_over_the_performed_score() -> None:
    plan = with_tempos((0, Fraction(100, 3)))
    result = doc(plan)
    quarters = plan.output.performed_length
    exact = quarters * 60 / Fraction(100, 3)
    stored = quarters * 60 / Fraction(float(Fraction(100, 3)))
    assert result.tempo_drift_seconds == abs(stored - exact)
    assert 0 < result.tempo_drift_seconds < MAX_TEMPO_DRIFT_SECONDS


def test_drift_accumulates_over_every_tempo_segment() -> None:
    one = doc(with_tempos((0, Fraction(100, 3)))).tempo_drift_seconds
    many = doc(
        with_tempos((0, Fraction(100, 3)), (4, Fraction(100, 3)), (8, Fraction(100, 3)))
    ).tempo_drift_seconds
    assert many == one  # the same total length, split into segments of the same tempo


def test_a_drift_beyond_the_tolerance_is_a_blocking_error() -> None:
    plan = with_tempos((0, Fraction(100, 3)))
    assert code_of(lambda: write_ustx(plan, tempo_tolerance_seconds=Fraction(0))) == (
        "USTX_TEMPO_DRIFT"
    )
    # the same plan passes with a tolerance that covers its measured drift
    needed = doc(plan).tempo_drift_seconds
    assert write_ustx(plan, tempo_tolerance_seconds=needed).tempo_drift_seconds == needed


def test_the_default_tolerance_is_one_microsecond_and_far_below_a_sample() -> None:
    assert Fraction(1, 1_000_000) == MAX_TEMPO_DRIFT_SECONDS
    assert Fraction(1, 44_100) > MAX_TEMPO_DRIFT_SECONDS


def test_a_very_long_inexact_score_is_measured_not_assumed() -> None:
    plan = with_tempos((0, Fraction(100, 3)))
    long_plan = replace(plan, output=replace(plan.output, performed_length=Fraction(10**7)))
    drift = doc(long_plan).tempo_drift_seconds
    assert drift > doc(plan).tempo_drift_seconds  # grows with length
    assert drift < MAX_TEMPO_DRIFT_SECONDS  # a double is still inside a microsecond at 10^7 beats


# --- regression evidence from the research series ---


def test_a_missing_lyric_event_never_becomes_the_openutau_default_a() -> None:
    """B02: OpenUtau turns an absent lyric into 'a'. The writer must never rely on that."""
    plan = plan_of(voices={**full_lyrics(), "lead": sung(VoiceRole.LEAD, ["la", None, "la", None])})
    assert not plan.is_ready
    with pytest.raises(PlanNotReadyError):
        write_ustx(plan)


def test_lyrics_stay_on_their_own_track() -> None:
    """B07/B08: lyrics are track-local; nothing is propagated between voices."""
    data = parsed()
    per_track = [[n["lyric"] for n in p["notes"]] for p in data["voice_parts"]]
    assert per_track == [["one", "two", "three", "four"]] * 4  # each voice's own (identical here)
    distinct = plan_of(
        voices={
            role.value: sung(role, [f"{role.value}{i}" for i in range(4)]) for role in VoiceRole
        }
    )
    lyrics = [[n["lyric"] for n in p["notes"]] for p in parsed(distinct)["voice_parts"]]
    assert lyrics[0][0] == "tenor0"
    assert lyrics[3][0] == "bass0"
    assert not set(lyrics[0]) & set(lyrics[1])


def test_the_hyphen_that_openutau_would_rewrite_is_never_emitted() -> None:
    """B05: a lyric of exactly '-' is rewritten to '+' on import; it is refused outright."""
    assert code_of(lambda: validate_lyric_text("-")) == "USTX_LYRIC_RESERVED"


def test_a_note_is_a_pitch_of_the_sounding_tone_in_every_octave_extreme() -> None:
    low, high = Pitch(Step.C, -1), Pitch(Step.G, 9)
    lead = [note(0, 2, low, lyrics=text("lo")), note(2, 2, high, lyrics=text("hi"))]
    notes = parsed(plan_of(voices={**full_lyrics(), "lead": lead}))["voice_parts"][1]["notes"]
    assert [n["tone"] for n in notes] == [0, 127]
