"""Stem validation against hand-made WAV files: every check, at and either side of its limit."""

from collections.abc import Callable
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import pytest

from barbershop_tracks.core.rendering import OutputValidationError, StemPolicy
from barbershop_tracks.core.rendering.stems import (
    host_file_name,
    seconds_at,
    validate_and_collect,
    voices_that_sing,
)
from barbershop_tracks.core.synthesis import SynthesisPlan, TempoPoint
from barbershop_tracks.models import VoiceRole
from synth_builders import ROLES, full_lyrics, plan_of, refs, sung
from wav_builders import RATE, chunk, fmt_chunk, pcm16, riff, tone, wav16, write

POLICY = StemPolicy()
FOUR_NOTES = full_lyrics(("la",) * 4)  # four quarter notes per voice: 2.4 s at 100 BPM


def plan() -> SynthesisPlan:
    return plan_of(voices=FOUR_NOTES, engine_refs=refs())


def host_out(
    tmp_path: Path,
    the_plan: SynthesisPlan,
    audio: Callable[[VoiceRole], bytes | None] = lambda role: wav16(tone(2.4)),
) -> Path:
    out = tmp_path / "host-out"
    out.mkdir()
    for voice in voices_that_sing(the_plan):
        data = audio(voice.role)
        if data is not None:
            write(out / host_file_name(voice.role), data)
    return out


def code_of(tmp_path: Path, the_plan: SynthesisPlan, out: Path, policy: StemPolicy = POLICY) -> str:
    with pytest.raises(OutputValidationError) as info:
        validate_and_collect(the_plan, out, tmp_path / "stems", policy)
    return info.value.code


def only_tenor(data: bytes) -> Callable[[VoiceRole], bytes]:
    return lambda role: data if role is VoiceRole.TENOR else wav16(tone(2.4))


# --- the happy path ---


def test_four_good_stems_are_validated_and_named_by_role(tmp_path: Path) -> None:
    the_plan = plan()
    reports = validate_and_collect(
        the_plan, host_out(tmp_path, the_plan), tmp_path / "stems", POLICY
    )
    assert sorted(p.name for p in (tmp_path / "stems").iterdir()) == [
        "Baritone.wav",
        "Bass.wav",
        "Lead.wav",
        "Tenor.wav",
    ]
    assert not list((tmp_path / "host-out").iterdir())  # moved, not copied
    tenor = reports[VoiceRole.TENOR]
    assert tenor.path == tmp_path / "stems" / "Tenor.wav"
    assert (tenor.sample_rate, tenor.bit_depth, tenor.channels) == (44100, 16, 1)
    assert tenor.duration_seconds == pytest.approx(2.4)
    assert tenor.first_audible_seconds == pytest.approx(0.0, abs=0.001)
    assert tenor.notes_checked == 4
    assert set(reports) == set(ROLES)


# --- files ---


def test_a_missing_stem_is_named(tmp_path: Path) -> None:
    the_plan = plan()
    out = host_out(tmp_path, the_plan, lambda r: None if r is VoiceRole.BASS else wav16(tone(2.4)))
    with pytest.raises(OutputValidationError) as info:
        validate_and_collect(the_plan, out, tmp_path / "stems", POLICY)
    assert info.value.code == "STEM_FILES_MISMATCH"
    assert info.value.details["missing"] == ["stem_Bass.wav"]


def test_unexpected_files_are_refused(tmp_path: Path) -> None:
    the_plan = plan()
    out = host_out(tmp_path, the_plan)
    (out / "extra.wav").write_bytes(wav16(tone(1)))
    (out / "subdir").mkdir()
    with pytest.raises(OutputValidationError) as info:
        validate_and_collect(the_plan, out, tmp_path / "stems", POLICY)
    assert info.value.code == "STEM_FILES_MISMATCH"
    assert info.value.details["unexpected"] == ["extra.wav", "subdir"]


def test_a_stem_that_is_a_directory_is_refused(tmp_path: Path) -> None:
    the_plan = plan()
    out = host_out(tmp_path, the_plan, lambda r: None if r is VoiceRole.LEAD else wav16(tone(2.4)))
    (out / host_file_name(VoiceRole.LEAD)).mkdir()
    assert code_of(tmp_path, the_plan, out) == "STEM_NOT_A_FILE"


def test_nothing_is_moved_when_any_stem_fails(tmp_path: Path) -> None:
    the_plan = plan()
    out = host_out(tmp_path, the_plan, only_tenor(b"junk"))
    assert code_of(tmp_path, the_plan, out) == "STEM_NOT_DECODABLE"
    assert not (tmp_path / "stems").exists()
    assert len(list(out.iterdir())) == 4


# --- decoding, format ---


def test_garbage_and_truncated_files_do_not_decode(tmp_path: Path) -> None:
    the_plan = plan()
    for data in (b"", b"garbage", wav16(tone(2.4))[:-5000]):
        folder = tmp_path / f"case{len(data)}"
        folder.mkdir()
        out = host_out(folder, the_plan, only_tenor(data))
        assert code_of(folder, the_plan, out) == "STEM_NOT_DECODABLE"


def test_a_wav_with_no_frames_is_empty(tmp_path: Path) -> None:
    the_plan = plan()
    out = host_out(tmp_path, the_plan, only_tenor(wav16([])))
    assert code_of(tmp_path, the_plan, out) == "STEM_EMPTY"


@pytest.mark.parametrize(
    "data",
    [
        wav16(tone(2.4, rate=48000), rate=48000),
        wav16(tone(2.4) * 2, channels=2),
        riff(fmt_chunk(bits=24), chunk(b"data", b"\x00\x00\x01" * RATE * 3)),
        riff(fmt_chunk(bits=32, tag=3), chunk(b"data", b"\x00\x00\x00\x3e" * RATE * 3)),
    ],
    ids=["48kHz", "stereo", "24bit", "float32"],
)
def test_unsupported_formats_are_refused_unless_the_policy_allows_them(
    tmp_path: Path, data: bytes
) -> None:
    the_plan = plan()
    out = host_out(tmp_path, the_plan, only_tenor(data))
    assert code_of(tmp_path, the_plan, out) == "STEM_FORMAT_UNSUPPORTED"


def test_a_wider_policy_accepts_what_it_names(tmp_path: Path) -> None:
    the_plan = plan()
    out = host_out(tmp_path, the_plan, only_tenor(wav16(tone(2.4, rate=48000), rate=48000)))
    wide = StemPolicy(sample_rates=(44100, 48000))
    reports = validate_and_collect(the_plan, out, tmp_path / "stems", wide)
    assert reports[VoiceRole.TENOR].sample_rate == 48000


# --- audibility ---


def test_an_all_zero_stem_is_silent(tmp_path: Path) -> None:
    the_plan = plan()
    out = host_out(tmp_path, the_plan, only_tenor(wav16([0.0] * int(2.4 * RATE))))
    assert code_of(tmp_path, the_plan, out) == "STEM_SILENT"


def test_the_silence_threshold_is_minus_80_dbfs_at_the_peak(tmp_path: Path) -> None:
    the_plan = plan()
    quiet = wav16(tone(2.4, amplitude=5e-5))
    assert code_of(tmp_path, the_plan, host_out(tmp_path, the_plan, only_tenor(quiet))) == (
        "STEM_SILENT"
    )


def test_a_note_that_renders_as_silence_is_named(tmp_path: Path) -> None:
    the_plan = plan()
    samples = tone(2.4)
    for i in range(int(0.6 * RATE), int(1.2 * RATE)):  # the second quarter note
        samples[i] = 0.0
    out = host_out(tmp_path, the_plan, only_tenor(wav16(samples)))
    with pytest.raises(OutputValidationError) as info:
        validate_and_collect(the_plan, out, tmp_path / "stems", POLICY)
    assert info.value.code == "STEM_NOTE_SILENT"
    assert info.value.details["notes"] == [1]


def test_a_note_too_short_to_judge_is_not_flagged(tmp_path: Path) -> None:
    notes = sung(VoiceRole.TENOR, ["la", "la", "la"])
    notes += sung(VoiceRole.TENOR, ["la"], duration=Fraction(1, 32), start=3)  # 0.019 s
    the_plan = plan_of(voices={**full_lyrics(("la",) * 4), "tenor": notes}, engine_refs=refs())
    samples = tone(seconds_at(the_plan, the_plan.voice(VoiceRole.TENOR).end))
    for i in range(int(1.8 * RATE), len(samples)):  # the last, tiny note is silent
        samples[i] = 0.0
    out = host_out(
        tmp_path, the_plan, lambda r: wav16(samples) if r is VoiceRole.TENOR else wav16(tone(2.4))
    )
    reports = validate_and_collect(the_plan, out, tmp_path / "stems", POLICY)
    assert reports[VoiceRole.TENOR].notes_checked == 3


# --- duration and origin ---


@pytest.mark.parametrize(
    ("seconds", "ok"),
    [(2.4, True), (2.36, True), (2.34, False), (2.89, True), (2.91, False), (1.2, False)],
)
def test_the_stem_length_must_be_close_to_the_last_note_end(
    tmp_path: Path, seconds: float, ok: bool
) -> None:
    the_plan = plan()
    out = host_out(tmp_path, the_plan, only_tenor(wav16(tone(seconds))))
    if ok:
        validate_and_collect(the_plan, out, tmp_path / "stems", POLICY)
    else:
        assert code_of(tmp_path, the_plan, out) == "STEM_DURATION"


LATE = {**full_lyrics(("la",) * 4), "tenor": sung(VoiceRole.TENOR, ["la"] * 4, start=4)}


@pytest.mark.parametrize(
    ("onset", "ok"),
    [
        (2.4, True),
        (2.35, True),
        (2.16, True),
        (2.14, False),
        (2.6, True),
        (2.91, False),
        (0.0, False),
    ],
)
def test_the_first_sound_must_be_near_the_first_note_start(
    tmp_path: Path, onset: float, ok: bool
) -> None:
    the_plan = plan_of(voices=LATE, engine_refs=refs())  # tenor starts at 2.4 s, ends at 4.8 s
    samples = tone(4.8, start=onset)
    out = host_out(
        tmp_path, the_plan, lambda r: wav16(samples) if r is VoiceRole.TENOR else wav16(tone(2.4))
    )
    if ok:
        validate_and_collect(the_plan, out, tmp_path / "stems", POLICY)
    else:
        assert code_of(tmp_path, the_plan, out) in {"STEM_ORIGIN", "STEM_NOTE_SILENT"}


def test_origin_failure_is_reported_as_such_when_every_note_is_audible(tmp_path: Path) -> None:
    the_plan = plan_of(voices=LATE, engine_refs=refs())
    samples = tone(4.8, start=0.0)  # sound from the very start, then continuous: wrong origin
    out = host_out(
        tmp_path, the_plan, lambda r: wav16(samples) if r is VoiceRole.TENOR else wav16(tone(2.4))
    )
    assert code_of(tmp_path, the_plan, out) == "STEM_ORIGIN"


# --- the tempo map decides what "expected" means ---


def test_seconds_follow_every_tempo_segment() -> None:
    base = plan()
    changed = replace(
        base,
        tempo=(
            TempoPoint(position=Fraction(0), bpm=Fraction(100)),
            TempoPoint(position=Fraction(2), bpm=Fraction(200)),
        ),
    )
    assert seconds_at(changed, Fraction(0)) == 0
    assert seconds_at(changed, Fraction(2)) == pytest.approx(1.2)
    assert seconds_at(changed, Fraction(4)) == pytest.approx(1.8)
    assert seconds_at(changed, Fraction(1)) == pytest.approx(0.6)


def test_expected_length_uses_the_changed_tempo(tmp_path: Path) -> None:
    changed = replace(
        plan(),
        tempo=(
            TempoPoint(position=Fraction(0), bpm=Fraction(100)),
            TempoPoint(position=Fraction(2), bpm=Fraction(200)),
        ),
    )
    out = host_out(tmp_path, changed, lambda role: wav16(tone(1.8)))
    validate_and_collect(changed, out, tmp_path / "stems", POLICY)


# --- a voice with nothing to sing ---


def test_a_voice_without_notes_expects_no_stem_and_refuses_one(tmp_path: Path) -> None:
    base = plan()
    voice = base.voice(VoiceRole.BASS)
    object.__setattr__(voice, "notes", ())  # the plan type forbids this; the validator must cope
    assert [v.role for v in voices_that_sing(base)] == [
        VoiceRole.TENOR,
        VoiceRole.LEAD,
        VoiceRole.BARITONE,
    ]
    out = host_out(tmp_path, base)
    assert not (out / host_file_name(VoiceRole.BASS)).exists()
    reports = validate_and_collect(base, out, tmp_path / "stems", POLICY)
    assert VoiceRole.BASS not in reports
    other = tmp_path / "other"
    other.mkdir()
    out2 = host_out(other, base)
    write(out2 / host_file_name(VoiceRole.BASS), wav16(tone(2.4)))
    assert code_of(other, base, out2) == "STEM_FILES_MISMATCH"


def test_pcm16_helper_clamps() -> None:
    assert pcm16([2.0, -2.0]) == pcm16([1.0, -1.0])
