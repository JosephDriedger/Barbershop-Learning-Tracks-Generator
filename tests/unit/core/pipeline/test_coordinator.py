"""The coordinator with fake adapters: real parsing, readiness and planning; fake render and MP3."""

import json
import threading
from dataclasses import replace
from fractions import Fraction
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from barbershop_tracks.core.mixing import (
    AudioFormat,
    MixEncodingError,
    PackageResult,
)
from barbershop_tracks.core.mixing.audio import wav_bytes
from barbershop_tracks.core.mixing.timeline import duration_frames
from barbershop_tracks.core.pipeline import (
    EngineChoice,
    ErrorCategory,
    GenerateRequest,
    PipelineError,
    ResolvedConfig,
    Services,
    generate,
)
from barbershop_tracks.core.readiness import RoleAssignments
from barbershop_tracks.core.rendering import (
    CancelToken,
    OutputValidationError,
    RenderCancelledError,
    RenderConfigurationError,
    RenderResult,
    RenderTimeoutError,
    StemReport,
    SynthesisError,
)
from barbershop_tracks.core.runtime import RuntimeLayout
from barbershop_tracks.core.singer_names import SINGER_SEPARATOR as SEP
from barbershop_tracks.core.synthesis import VOICE_ORDER, LyricApproval, SynthesisPlan
from barbershop_tracks.models import VoiceRole
from cli_scores import LINES, quartet_xml

ASSIGN = RoleAssignments.of(
    {
        VoiceRole.TENOR: LINES["tenor"],
        VoiceRole.LEAD: LINES["lead"],
        VoiceRole.BARITONE: LINES["baritone"],
        VoiceRole.BASS: LINES["bass"],
    }
)


class FakeRenderer:
    """Writes four stems that follow the plan's notes (tone inside each note), like the host."""

    def __init__(self, error: Exception | None = None, hold: threading.Event | None = None) -> None:
        self.error = error
        self.calls: list[SynthesisPlan] = []
        self.overrides: list[Any] = []
        self.checks: list[Any] = []
        self.hold = hold

    def check_pronunciations(
        self,
        plan: SynthesisPlan,
        overrides: Any = None,
        *,
        cancel: Any = None,
        on_event: Any = None,
    ) -> dict[str, Any]:
        self.checks.append(overrides)
        if self.error is not None:
            raise self.error
        return {"status": "ok", "pronunciations": []}

    def render(
        self,
        plan: SynthesisPlan,
        destination: Path,
        *,
        cancel: Any = None,
        on_event: Any = None,
        replace: bool = False,
        overrides: Any = None,
    ) -> RenderResult:
        self.calls.append(plan)
        self.overrides.append(overrides)
        if on_event:
            on_event({"event": "phase", "name": "init", "elapsed_ms": 1})
        if self.hold is not None:
            self.hold.wait(timeout=20)
        if cancel is not None and cancel.cancelled:
            raise RenderCancelledError("RENDER_CANCELLED", "cancelled")
        if self.error is not None:
            raise self.error
        destination.mkdir(parents=True)
        reports = {}
        rate = 44100
        for voice in plan.voices:
            end = int(float(voice.end) * 60 / 100 * rate)
            samples = np.zeros(end, dtype=np.int16)
            for note in voice.notes:
                a = int(float(note.start) * 0.6 * rate)
                b = int(float(note.end) * 0.6 * rate)
                samples[a:b] = 4000
            path = destination / f"{voice.role.display_name}.wav"
            path.write_bytes(wav_bytes(samples))
            reports[voice.role] = StemReport(
                voice.role, path, end, rate, 1, 16, end / rate, 0.12, 0.0
            )
        if on_event:
            on_event({"event": "blt_stage", "stage": "stem_validation", "status": "started"})
            on_event({"event": "blt_stage", "stage": "stem_validation", "status": "finished"})
        return RenderResult(destination, reports, {"status": "ok"}, (), "job", 0.1)


class FakeEncoder:
    def __init__(self, fail_at: int | None = None) -> None:
        self.calls = 0
        self.fail_at = fail_at

    def settings(self) -> dict[str, Any]:
        return {"encoder": "fake"}

    def encode(self, wav: Path, mp3: Path, *, expected_frames: int, cancel: CancelToken) -> dict:  # type: ignore[type-arg]
        self.calls += 1
        if self.fail_at == self.calls:
            raise MixEncodingError("MIX_MP3_FAILED", "boom")
        mp3.write_bytes(b"ID3fake")
        return {"fake": True}


class Rig:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.score = root / "song.musicxml"
        self.write_score()
        (root / "singers" / "my-singer").mkdir(parents=True)
        (root / "singers" / "my-singer" / "character.txt").write_text("name=x", encoding="utf-8")
        self.renderer = FakeRenderer()
        self.encoder = FakeEncoder()
        self.config = ResolvedConfig(
            layout=RuntimeLayout.under(root / "bin", root / "data"),
            singers_dir=root / "singers",
            ffmpeg=root / "ffmpeg.exe",
            host_binaries=root / "host",
            dotnet_root=None,
            output_dir=None,
            singer="my-singer",
            phonemizer="OpenUtau.Core.DefaultPhonemizer",
            renderer="WORLDLINE-R",
            gain_profile=__import__(
                "barbershop_tracks.core.mixing", fromlist=["DEFAULT_PROFILE"]
            ).DEFAULT_PROFILE,
        )
        self.events: list[dict[str, Any]] = []

    def write_score(self, **options: Any) -> None:
        options.setdefault("all_lyrics", True)
        self.score.write_text(quartet_xml(**options), encoding="utf-8")

    def request(self, **overrides: Any) -> GenerateRequest:
        base = GenerateRequest(
            score=self.score,
            output=self.root / "out",
            assignments=ASSIGN,
            engine=EngineChoice("my-singer", "OpenUtau.Core.DefaultPhonemizer", "WORLDLINE-R"),
        )
        return replace(base, **overrides)

    def services(self) -> Services:
        return Services(
            make_renderer=lambda settings: self.renderer,
            make_encoder=lambda ffmpeg, quality: self.encoder,
        )

    def run(self, request: GenerateRequest | None = None, **kw: Any) -> Any:
        return generate(
            request or self.request(),
            kw.pop("config", self.config),
            services=self.services(),
            on_event=self.events.append,
            **kw,
        )

    def staging(self) -> list[str]:
        root = self.config.layout.staging
        return sorted(p.name for p in root.iterdir()) if root.is_dir() else []


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    return Rig(tmp_path)


def error_of(rig: Rig, request: GenerateRequest | None = None, **kw: Any) -> PipelineError:
    with pytest.raises(PipelineError) as info:
        rig.run(request, **kw)
    return info.value


# --- success ---


def test_a_complete_score_becomes_the_thirteen_track_package(rig: Rig) -> None:
    result = rig.run()
    assert result.destination == rig.root / "out" / "song_learning_tracks"
    names = sorted(p.name for p in result.destination.iterdir())
    assert len([n for n in names if n.endswith(".wav")]) == 13
    assert names[0] == "01_Full_Quartet.wav"
    assert "manifest.json" in names
    assert len(names) == 14  # tracks and manifest only: no stems, no USTX
    assert rig.staging() == []


def test_the_plan_reaches_the_renderer_with_the_right_voices_and_singers(rig: Rig) -> None:
    rig.run()
    (plan,) = rig.renderer.calls
    assert [v.role for v in plan.voices] == list(VOICE_ORDER)
    assert [v.line_id for v in plan.voices] == [LINES[r.value] for r in VOICE_ORDER]
    assert all(plan.engine_ref(r).singer == "my-singer" for r in VOICE_ORDER)
    assert plan.source.display_name == "song.musicxml"
    assert plan.output.performed_length == Fraction(8)  # eight quarter notes per part


def test_the_package_length_comes_from_the_score(rig: Rig) -> None:
    result = rig.run()
    plan = rig.renderer.calls[0]
    assert result.package.frames == duration_frames(plan.tempo, plan.output.performed_length, 44100)


def test_roles_follow_the_explicit_mapping_not_the_file_order(rig: Rig) -> None:
    swapped = RoleAssignments.of(
        {
            VoiceRole.TENOR: LINES["bass"],
            VoiceRole.LEAD: LINES["lead"],
            VoiceRole.BARITONE: LINES["baritone"],
            VoiceRole.BASS: LINES["tenor"],
        }
    )
    rig.run(rig.request(assignments=swapped))
    plan = rig.renderer.calls[0]
    assert plan.voice(VoiceRole.TENOR).line_id == LINES["bass"]
    assert plan.voice(VoiceRole.BASS).line_id == LINES["tenor"]


def test_events_report_every_stage_in_order_with_counted_progress_only_where_real(rig: Rig) -> None:
    rig.run(rig.request(formats=frozenset({AudioFormat.WAV, AudioFormat.MP3})))
    started = [e["stage"] for e in rig.events if e["event"] == "stage" and e["status"] == "started"]
    assert started == [
        "source_loading",
        "score_analysis",
        "readiness_validation",
        "ustx_preparation",
        "voicebank_discovery",
        "stem_rendering",
        "stem_validation",
        "mixing",
        "mp3_encoding",
        "package_publication",
    ]
    mixes = [e for e in rig.events if e["event"] == "progress" and e["stage"] == "mixing"]
    assert [e["completed"] for e in mixes] == list(range(1, 14))
    assert all(e["total"] == 13 for e in mixes)
    mp3 = [e for e in rig.events if e["event"] == "progress" and e["stage"] == "mp3_encoding"]
    assert len(mp3) == 13
    assert not any("percent" in e for e in rig.events)  # no invented percentages
    assert any(e["event"] == "host" for e in rig.events)
    json.dumps(rig.events)  # every event is plain JSON


def test_formats_select_exactly_the_files_published(rig: Rig) -> None:
    result = rig.run(rig.request(formats=frozenset({AudioFormat.MP3})))
    names = sorted(p.name for p in result.destination.iterdir())
    assert len([n for n in names if n.endswith(".mp3")]) == 13
    assert not [n for n in names if n.endswith(".wav")]
    assert rig.encoder.calls == 13


def test_extras_are_published_only_when_requested(rig: Rig) -> None:
    result = rig.run(rig.request(keep_stems=True, keep_project=True))
    extras = sorted(e["name"] for e in result.package.manifest["extras"])
    assert extras == [
        "project/project.ustx",
        "stems/Baritone.wav",
        "stems/Bass.wav",
        "stems/Lead.wav",
        "stems/Tenor.wav",
    ]
    assert (
        (result.destination / "project" / "project.ustx")
        .read_text(encoding="utf-8")
        .startswith("name:")
    )


def test_repeated_generation_gives_identical_packages(rig: Rig) -> None:
    first = rig.run()
    second = rig.run(rig.request(replace=True))
    assert first.package.manifest == second.package.manifest
    for path in sorted(second.destination.iterdir()):
        assert path.read_bytes() == path.read_bytes()
    assert rig.staging() == []


# --- source problems ---


def test_a_missing_tempo_is_a_source_error_not_a_default(rig: Rig) -> None:
    rig.write_score(tempo=False)
    error = error_of(rig)
    assert error.category is ErrorCategory.SOURCE
    assert error.code == "SOURCE_NOT_READY"
    assert any("TEMPO" in f["code"] for f in error.details["findings"])
    assert rig.renderer.calls == []


def test_a_score_that_does_not_load_is_a_source_error(rig: Rig) -> None:
    rig.score.write_text("<not-xml", encoding="utf-8")
    error = error_of(rig)
    assert error.category is ErrorCategory.SOURCE
    assert error.code == "SCORE_LOAD_FAILED"


def test_an_unmapped_voice_is_reported_before_any_work(rig: Rig) -> None:
    partial = RoleAssignments.of({VoiceRole.TENOR: LINES["tenor"], VoiceRole.LEAD: LINES["lead"]})
    error = error_of(rig, rig.request(assignments=partial))
    assert error.category is ErrorCategory.SOURCE
    assert rig.renderer.calls == []


def test_a_missing_score_file_is_a_source_error(rig: Rig) -> None:
    rig.score.unlink()
    assert error_of(rig).category is ErrorCategory.SOURCE


# --- lyrics ---


def test_missing_harmony_lyrics_block_with_a_review_report(rig: Rig) -> None:
    rig.write_score(all_lyrics=False, lyric_part=1)  # only the Lead sings words
    error = error_of(rig)
    assert error.category is ErrorCategory.REVIEW
    assert error.code == "LYRICS_NEED_REVIEW"
    report = error.details["review"]
    assert report["schema"] == "blt.lyric-review/1"
    assert report["ready"] is False
    voices = {item["voice"] for item in report["items"]}
    assert voices == {"tenor", "baritone", "bass"}  # the Lead is complete and never copied
    assert len(report["items"]) == 24  # 8 notes in each of the three harmony parts
    assert {i["reason"] for i in report["items"]} == {"lyric_absent"}
    assert len(report["approvals_template"]["approvals"]) == 24
    assert rig.renderer.calls == []
    assert not (rig.root / "out").exists()


def test_a_score_with_no_lyrics_at_all_needs_review_for_every_voice(rig: Rig) -> None:
    rig.write_score(all_lyrics=False, lyric_part=None)
    error = error_of(rig)
    assert error.code == "LYRICS_NEED_REVIEW"
    assert {i["voice"] for i in error.details["review"]["items"]} == {
        "tenor",
        "lead",
        "baritone",
        "bass",
    }


def test_explicit_approvals_resolve_the_review_and_are_used_verbatim(rig: Rig) -> None:
    rig.write_score(all_lyrics=False, lyric_part=1)
    items = error_of(rig).details["review"]["items"]
    approvals = tuple(
        LyricApproval(
            role=VoiceRole(i["voice"]), start=Fraction(i["start"]), text="ba", approved_by="tester"
        )
        for i in items
    )
    rig.run(rig.request(approvals=approvals))
    plan = rig.renderer.calls[0]
    tenor = plan.voice(VoiceRole.TENOR).notes[0].lyric
    assert tenor.state.value == "user_approved"
    assert tenor.text == "ba"
    assert plan.voice(VoiceRole.LEAD).notes[0].lyric.text == "la"


def test_an_approval_for_a_note_that_has_a_score_lyric_is_refused(rig: Rig) -> None:
    approvals = (
        LyricApproval(role=VoiceRole.TENOR, start=Fraction(0), text="zz", approved_by="tester"),
    )
    error = error_of(rig, rig.request(approvals=approvals))
    assert error.category is ErrorCategory.SOURCE
    assert error.code == "PLAN_APPROVAL_OVERRIDES_SCORE"


# --- configuration ---


def test_no_singer_chosen_is_reported_first(rig: Rig) -> None:
    request = rig.request(engine=EngineChoice(None, "p.P", "WORLDLINE-R"))
    error = error_of(rig, request)
    assert error.category is ErrorCategory.CONFIGURATION
    assert error.code == "SINGER_NOT_CHOSEN"


def test_an_uninstalled_singer_lists_what_is_installed(rig: Rig) -> None:
    request = rig.request(engine=EngineChoice("ghost", "p.P", "WORLDLINE-R"))
    error = error_of(rig, request)
    assert error.code == "SINGER_NOT_FOUND"
    assert error.details["installed"] == ["my-singer"]
    assert rig.renderer.calls == []


def test_a_voicebank_inside_a_pack_folder_is_known_by_its_path(rig: Rig) -> None:
    bank = rig.root / "singers" / "pack" / "inner"
    bank.mkdir(parents=True)
    (bank / "character.txt").write_text("name=y", encoding="utf-8")
    name = f"pack{SEP}inner"
    engine = EngineChoice(name, "OpenUtau.Core.DefaultPhonemizer", "WORLDLINE-R")
    rig.run(rig.request(engine=engine))
    assert rig.renderer.calls[0].engine_ref(VoiceRole.BASS).singer == name
    error = error_of(
        rig, rig.request(engine=EngineChoice("inner", engine.phonemizer, "WORLDLINE-R"), name="b")
    )
    assert error.code == "SINGER_NOT_FOUND"
    assert f"its name is '{name}'" in error.message


def test_a_voicebank_without_character_txt_is_explained(rig: Rig) -> None:
    bank = rig.root / "singers" / "bare"
    bank.mkdir()
    (bank / "oto.ini").write_text("a.wav=a,0,1,1,1,1\n", encoding="utf-8")
    error = error_of(rig, rig.request(engine=EngineChoice("bare", "p.P", "WORLDLINE-R")))
    assert error.code == "SINGER_NOT_FOUND"
    assert "character.txt" in error.message
    assert "name=bare" in error.message


def test_a_neural_voicebank_is_refused_before_it_renders_silence(rig: Rig) -> None:
    (rig.root / "singers" / "my-singer" / "character.yaml").write_text(
        "singer_type: diffsinger\n", encoding="utf-8"
    )
    error = error_of(rig, rig.request())
    assert error.code == "SINGER_KIND_UNSUPPORTED"
    assert "DiffSinger" in error.message
    assert rig.renderer.calls == []


def test_a_per_voice_singer_overrides_the_default(rig: Rig) -> None:
    engine = EngineChoice(
        "my-singer",
        "OpenUtau.Core.DefaultPhonemizer",
        "WORLDLINE-R",
        per_voice={VoiceRole.BASS: "my-singer"},
    )
    rig.run(rig.request(engine=engine))
    assert rig.renderer.calls[0].engine_ref(VoiceRole.BASS).singer == "my-singer"
    bad = EngineChoice(
        "my-singer",
        "OpenUtau.Core.DefaultPhonemizer",
        "WORLDLINE-R",
        per_voice={VoiceRole.BASS: "ghost"},
    )
    assert error_of(rig, rig.request(engine=bad, name="other")).code == "SINGER_NOT_FOUND"


def test_a_missing_singers_folder_is_a_configuration_error(rig: Rig) -> None:
    config = replace(rig.config, singers_dir=None)
    assert error_of(rig, config=config).code == "SINGERS_DIR_MISSING"


def test_a_missing_host_is_a_configuration_error(rig: Rig) -> None:
    config = replace(rig.config, host_binaries=None)
    assert error_of(rig, config=config).code == "HOST_NOT_FOUND"


def test_mp3_without_ffmpeg_is_refused_before_any_work(rig: Rig) -> None:
    config = replace(rig.config, ffmpeg=None)
    error = error_of(rig, rig.request(formats=frozenset({AudioFormat.MP3})), config=config)
    assert error.code == "FFMPEG_NOT_CONFIGURED"
    assert rig.renderer.calls == []


def test_a_tune_up_note_without_a_key_signature_is_refused_before_any_work(rig: Rig) -> None:
    error = error_of(rig, rig.request(tune_up=True))  # the test score has no key signature
    assert error.code == "MIX_TUNE_NO_KEY"
    assert error.category is ErrorCategory.CONFIGURATION
    assert rig.renderer.calls == []


def test_a_count_in_alone_needs_no_key_signature(rig: Rig) -> None:
    result = rig.run(rig.request(count_in=True))
    prelude = result.package.manifest["audio"]["prelude"]
    assert prelude["tune_up"] is None
    assert prelude["count_in"]["beats"] == 4
    assert result.package.manifest["audio"]["music_starts_at_frame"] == prelude["frames"]


def test_an_unusable_package_name_is_refused(rig: Rig) -> None:
    assert error_of(rig, rig.request(name="CON")).category is ErrorCategory.CONFIGURATION


# --- output location ---


def test_an_existing_package_is_not_replaced_unless_asked(rig: Rig) -> None:
    rig.run()
    error = error_of(rig)
    assert error.code == "OUTPUT_EXISTS"
    assert len(rig.renderer.calls) == 1  # refused before rendering again


def test_a_foreign_folder_with_the_package_name_is_never_replaced(rig: Rig) -> None:
    target = rig.root / "out" / "song_learning_tracks"
    target.mkdir(parents=True)
    (target / "mine.txt").write_text("keep", encoding="utf-8")
    error = error_of(rig, rig.request(replace=True))
    assert error.code == "OUTPUT_FOREIGN"
    assert (target / "mine.txt").read_text(encoding="utf-8") == "keep"


# --- failures after the plan: translation, rollback, cleanup ---


@pytest.mark.parametrize(
    ("failure", "category"),
    [
        (RenderConfigurationError("HOST_UNRESOLVED", "no singer"), ErrorCategory.CONFIGURATION),
        (SynthesisError("HOST_FAILED", "exit 5"), ErrorCategory.SYNTHESIS),
        (RenderTimeoutError("RENDER_TIMEOUT", "slow"), ErrorCategory.TIMEOUT),
        (OutputValidationError("STEM_SILENT", "silent"), ErrorCategory.AUDIO),
        (RenderCancelledError("RENDER_CANCELLED", "stop"), ErrorCategory.CANCELLED),
    ],
)
def test_render_failures_are_categorised_and_leave_nothing(
    rig: Rig, failure: Exception, category: ErrorCategory
) -> None:
    rig.renderer.error = failure
    error = error_of(rig)
    assert error.category is category
    assert not (rig.root / "out").exists()
    assert rig.staging() == []


def test_a_mixing_failure_is_an_audio_error_and_keeps_the_previous_package(rig: Rig) -> None:
    rig.run()
    before = {p.name: p.read_bytes() for p in (rig.root / "out" / "song_learning_tracks").iterdir()}

    def failing(*args: Any, **kwargs: Any) -> PackageResult:
        from barbershop_tracks.core.mixing import MixClippingError

        raise MixClippingError("MIX_CLIPPING", "too loud")

    services = Services(make_renderer=lambda settings: rig.renderer, package=failing)
    with pytest.raises(PipelineError) as info:
        generate(rig.request(replace=True), rig.config, services=services)
    assert info.value.category is ErrorCategory.AUDIO
    after = {p.name: p.read_bytes() for p in (rig.root / "out" / "song_learning_tracks").iterdir()}
    assert after == before
    assert rig.staging() == []


def test_an_mp3_failure_publishes_no_partial_set(rig: Rig) -> None:
    rig.encoder = FakeEncoder(fail_at=6)
    error = error_of(rig, rig.request(formats=frozenset({AudioFormat.WAV, AudioFormat.MP3})))
    assert error.category is ErrorCategory.AUDIO
    assert error.code == "MIX_MP3_FAILED"
    assert not (rig.root / "out" / "song_learning_tracks").exists()
    assert rig.staging() == []


def test_cancelling_before_rendering_starts(rig: Rig) -> None:
    token = CancelToken()
    token.cancel()
    error = error_of(rig, cancel=token)
    assert error.category is ErrorCategory.CANCELLED
    assert rig.renderer.calls == []
    assert rig.staging() == []


def test_cancelling_during_mixing_discards_everything(rig: Rig) -> None:
    token = CancelToken()

    def handler(event: dict[str, Any]) -> None:
        if event.get("event") == "progress" and event.get("completed") == 4:
            token.cancel()

    rig.events = []
    with pytest.raises(PipelineError) as info:
        generate(rig.request(), rig.config, services=rig.services(), cancel=token, on_event=handler)
    assert info.value.category is ErrorCategory.CANCELLED
    assert not (rig.root / "out" / "song_learning_tracks").exists()
    assert rig.staging() == []


def test_the_job_directory_exists_during_the_run_and_is_removed_after(rig: Rig) -> None:
    seen: list[list[str]] = []
    original = rig.renderer.render

    def spy(plan: SynthesisPlan, destination: Path, **kw: Any) -> RenderResult:
        seen.append(rig.staging())
        return original(plan, destination, **kw)

    rig.renderer.render = spy  # type: ignore[method-assign]
    rig.run()
    assert len(seen[0]) == 1
    assert seen[0][0].startswith(".staging-job-")
    assert rig.staging() == []


def test_concurrent_jobs_use_separate_directories_and_distinct_packages(rig: Rig) -> None:
    results: dict[int, Any] = {}

    def work(index: int) -> None:
        try:
            results[index] = generate(
                rig.request(name=f"song{index}"), rig.config, services=rig.services()
            )
        except BaseException as error:
            results[index] = error

    threads = [threading.Thread(target=work, args=(i,)) for i in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)
    assert all(not isinstance(r, BaseException) for r in results.values()), results
    assert sorted(p.name for p in (rig.root / "out").iterdir()) == [
        f"song{i}_learning_tracks" for i in range(3)
    ]
    assert rig.staging() == []


def test_unrelated_user_files_in_the_output_folder_are_untouched(rig: Rig) -> None:
    (rig.root / "out").mkdir()
    keepsake = rig.root / "out" / "notes.txt"
    keepsake.write_text("mine", encoding="utf-8")
    rig.run()
    assert keepsake.read_text(encoding="utf-8") == "mine"


def test_a_missing_microsoft_runtime_is_explained_before_anything_is_rendered(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    from barbershop_tracks.core.pipeline import coordinator
    from barbershop_tracks.core.runtime.vcruntime import RuntimeStatus

    monkeypatch.setattr(coordinator, "runtime_status", lambda: RuntimeStatus(None))
    error = error_of(rig)
    assert error.code == "VC_RUNTIME_MISSING"
    assert error.category is ErrorCategory.CONFIGURATION
    assert "Visual C++" in error.message
    assert rig.renderer.calls == []
    assert rig.staging() == []


@pytest.mark.parametrize(
    "name",
    [
        "OpenUtau.Plugin.Builtin.ArpasingPlusPhonemizer",
        "OpenUtau.Plugin.Builtin.EnglishCpVPhonemizer",
        "OpenUtau.Core.DiffSinger.DiffSingerARPAPlusEnglishPhonemizer",
        "ArpasingPlusPhonemizer",
    ],
)
def test_a_pronunciation_engine_this_version_does_not_contain_is_refused_before_any_work(
    rig: Rig, name: str
) -> None:
    request = rig.request(engine=EngineChoice("my-singer", name, "WORLDLINE-R"))
    error = error_of(rig, request)
    assert error.code == "PHONEMIZER_REMOVED"
    assert error.category is ErrorCategory.CONFIGURATION
    assert "ArpasingPhonemizer" in error.message  # it says what to use instead
    assert rig.renderer.calls == []
    assert rig.staging() == []


@pytest.mark.parametrize(
    "name",
    [
        "OpenUtau.Core.DefaultPhonemizer",
        "OpenUtau.Plugin.Builtin.ArpasingPhonemizer",
        "OpenUtau.Plugin.Builtin.EnglishVCCVPhonemizer",
        "OpenUtau.Plugin.Builtin.EnXSampaPhonemizer",
    ],
)
def test_the_supported_pronunciation_engines_are_not_refused(rig: Rig, name: str) -> None:
    result = rig.run(rig.request(engine=EngineChoice("my-singer", name, "WORLDLINE-R")))
    assert result.destination.is_dir()
