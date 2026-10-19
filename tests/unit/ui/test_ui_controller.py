"""The controller with the real parser and readiness, and a fake generate function."""

import threading
from pathlib import Path
from typing import Any

import pytest
from pytestqt.qtbot import QtBot

from barbershop_tracks.core.mixing import AudioFormat
from barbershop_tracks.core.pipeline import ErrorCategory, GenerateRequest, PipelineError
from barbershop_tracks.core.rendering import CancelToken
from barbershop_tracks.models import VoiceRole
from barbershop_tracks.ui.assignments import Ignore
from barbershop_tracks.ui.controller import AppController, ValidationView
from barbershop_tracks.ui.preferences import Preferences
from cli_scores import LINES, write_quartet

ROLES = {
    "tenor": VoiceRole.TENOR,
    "lead": VoiceRole.LEAD,
    "baritone": VoiceRole.BARITONE,
    "bass": VoiceRole.BASS,
}


class FakeGenerate:
    """Stands in for the pipeline: emits stage events, then returns or raises."""

    def __init__(self) -> None:
        self.requests: list[GenerateRequest] = []
        self.event_threads: set[int] = set()
        self.error: PipelineError | None = None
        self.hold = threading.Event()
        self.hold.set()
        self.started = threading.Event()

    def __call__(
        self, request: GenerateRequest, config: Any, *, cancel: CancelToken, on_event: Any
    ) -> Any:
        self.requests.append(request)
        self.started.set()
        on_event({"event": "stage", "stage": "source_loading", "status": "started"})
        self.event_threads.add(threading.get_ident())
        on_event({"event": "progress", "stage": "mixing", "completed": 1, "total": 13})
        while not self.hold.wait(0.01):
            if cancel.cancelled:
                raise PipelineError(ErrorCategory.CANCELLED, "CANCELLED", "cancelled")
        if self.error is not None:
            raise self.error
        return "RESULT"


@pytest.fixture
def prefs(tmp_path: Path) -> Preferences:
    return Preferences.at(tmp_path / "prefs.ini")


@pytest.fixture
def fake() -> FakeGenerate:
    return FakeGenerate()


@pytest.fixture
def controller(
    qtbot: QtBot, prefs: Preferences, fake: FakeGenerate, tmp_path: Path
) -> AppController:
    environ = {"BLT_CONFIG": str(tmp_path / "none.json"), "BLT_DATA_DIR": str(tmp_path / "data")}
    ctrl = AppController(
        prefs, generate_fn=fake, environ=environ, config_file=tmp_path / "none.json", debounce_ms=1
    )
    return ctrl


def load(qtbot: QtBot, controller: AppController, path: Path) -> None:
    with qtbot.waitSignal(controller.score_loaded, timeout=20000):
        controller.load_score(path)


def assign_all(controller: AppController) -> None:
    for name, role in ROLES.items():
        assert controller.set_choice(LINES[name], role)


def validated(qtbot: QtBot, controller: AppController) -> ValidationView:
    qtbot.waitUntil(lambda: not controller.validating, timeout=20000)
    assert controller.validation is not None
    return controller.validation


def ready_to_generate(qtbot: QtBot, controller: AppController, tmp_path: Path) -> None:
    score = write_quartet(tmp_path, all_lyrics=True)
    load(qtbot, controller, score)
    assign_all(controller)
    validated(qtbot, controller)
    (tmp_path / "voices").mkdir(exist_ok=True)
    controller.prefs.singers_dir = str(tmp_path / "voices")
    controller.installed = ["alto-voice"]
    controller.use_same_singer("alto-voice")
    controller.set_output_dir(str(tmp_path / "out"))


# --- loading ---


def test_loading_a_score_lists_its_lines_and_remembers_the_folder(
    qtbot: QtBot, controller: AppController, prefs: Preferences, tmp_path: Path
) -> None:
    score = write_quartet(tmp_path, all_lyrics=True)
    load(qtbot, controller, score)
    assert controller.score is not None
    assert [info.line_id for info in controller.score.lines] == list(LINES.values())
    assert controller.score.path == score
    assert len(controller.score.sha256) == 64
    assert controller.assignments is not None
    assert all(choice is None for choice in controller.assignments.choices.values())
    assert prefs.last_score_dir == str(tmp_path)
    assert not controller.loading


def test_a_file_that_is_not_a_score_is_reported_not_raised(
    qtbot: QtBot, controller: AppController, tmp_path: Path
) -> None:
    junk = tmp_path / "junk.musicxml"
    junk.write_text("<not-xml", encoding="utf-8")
    with qtbot.waitSignal(controller.score_failed, timeout=20000) as blocker:
        controller.load_score(junk)
    error = blocker.args[0]
    assert isinstance(error, PipelineError)
    assert error.category is ErrorCategory.SOURCE
    assert controller.score is None
    assert not controller.loading


def test_a_missing_file_is_a_source_error(
    qtbot: QtBot, controller: AppController, tmp_path: Path
) -> None:
    with qtbot.waitSignal(controller.score_failed, timeout=20000) as blocker:
        controller.load_score(tmp_path / "gone.musicxml")
    assert blocker.args[0].code == "SCORE_UNREADABLE"


# --- assignments and validation ---


def test_nothing_is_validated_until_the_mapping_is_complete(
    qtbot: QtBot, controller: AppController, tmp_path: Path
) -> None:
    load(qtbot, controller, write_quartet(tmp_path, all_lyrics=True))
    controller.set_choice(LINES["tenor"], VoiceRole.TENOR)
    qtbot.wait(50)
    assert controller.validation is None
    assert any("Choose a part" in b for b in controller.blockers())


def test_a_complete_mapping_is_checked_in_the_background(
    qtbot: QtBot, controller: AppController, tmp_path: Path
) -> None:
    load(qtbot, controller, write_quartet(tmp_path, all_lyrics=True))
    assign_all(controller)
    view = validated(qtbot, controller)
    assert view.source_ready
    assert view.unresolved == 0
    assert view.generatable
    assert controller.review is None  # nothing to review


def test_missing_harmony_lyrics_create_the_review_and_block_generation(
    qtbot: QtBot, controller: AppController, tmp_path: Path
) -> None:
    load(qtbot, controller, write_quartet(tmp_path))  # only the Lead has words
    assign_all(controller)
    view = validated(qtbot, controller)
    assert view.source_ready
    assert view.unresolved == 24
    assert controller.review is not None
    assert {row.role for row in controller.review.rows} == {
        VoiceRole.TENOR,
        VoiceRole.BARITONE,
        VoiceRole.BASS,
    }
    assert any("24 notes still need a lyric" in b for b in controller.blockers())


def test_approving_every_note_clears_the_review(
    qtbot: QtBot, controller: AppController, tmp_path: Path
) -> None:
    load(qtbot, controller, write_quartet(tmp_path))
    assign_all(controller)
    validated(qtbot, controller)
    review = controller.review
    assert review is not None
    review.fill_text(list(range(len(review.rows))), "la")
    review.approve(list(range(len(review.rows))))
    controller.set_approvals(review.approvals())
    view = validated(qtbot, controller)
    assert view.unresolved == 0
    assert view.generatable
    assert view.baseline is not None
    assert len(view.baseline.review_items) == 24  # the review table keeps its rows


def test_a_score_without_a_tempo_is_reported_in_plain_words(
    qtbot: QtBot, controller: AppController, tmp_path: Path
) -> None:
    load(qtbot, controller, write_quartet(tmp_path, all_lyrics=True, tempo=False))
    assign_all(controller)
    view = validated(qtbot, controller)
    assert not view.source_ready
    assert any(m.severity == "error" for m in view.messages)
    assert "TEMPO" in view.technical
    assert any("needs attention" in b for b in controller.blockers())


def test_changing_the_mapping_discards_lyric_approvals(
    qtbot: QtBot, controller: AppController, tmp_path: Path
) -> None:
    load(qtbot, controller, write_quartet(tmp_path))
    assign_all(controller)
    validated(qtbot, controller)
    assert controller.review is not None
    controller.review.fill_text([0], "la")
    controller.review.approve([0])
    controller.set_approvals(controller.review.approvals())
    assert controller.approvals
    controller.set_choice(LINES["bass"], Ignore.IGNORE)
    assert controller.approvals == ()
    assert controller.review is None


def test_one_voice_cannot_be_given_to_two_lines(
    qtbot: QtBot, controller: AppController, tmp_path: Path
) -> None:
    load(qtbot, controller, write_quartet(tmp_path, all_lyrics=True))
    assert controller.set_choice(LINES["tenor"], VoiceRole.LEAD)
    assert not controller.set_choice(LINES["lead"], VoiceRole.LEAD)


def test_suggestions_need_confirming_before_generation(
    qtbot: QtBot, controller: AppController, tmp_path: Path
) -> None:
    load(qtbot, controller, write_quartet(tmp_path, all_lyrics=True))
    assert controller.suggest() == 4
    assert any("confirm" in b.lower() for b in controller.blockers())
    controller.confirm_suggestions()
    view = validated(qtbot, controller)
    assert view.source_ready


def test_the_same_score_reopened_keeps_the_users_choices(
    qtbot: QtBot, controller: AppController, tmp_path: Path
) -> None:
    score = write_quartet(tmp_path, all_lyrics=True)
    load(qtbot, controller, score)
    assign_all(controller)
    other = write_quartet(tmp_path, "other.musicxml", all_lyrics=True, word="ba")
    load(qtbot, controller, other)
    assert controller.assignments is not None
    assert all(c is None for c in controller.assignments.choices.values())
    load(qtbot, controller, score)
    assert controller.assignments.holder(VoiceRole.BASS) == LINES["bass"]


# --- singers ---


def test_voices_are_discovered_in_the_background_and_a_missing_one_is_flagged(
    qtbot: QtBot, controller: AppController, prefs: Preferences, tmp_path: Path
) -> None:
    voices = tmp_path / "voices"
    (voices / "alto-voice").mkdir(parents=True)
    (voices / "alto-voice" / "character.txt").write_text("name=a", encoding="utf-8")
    prefs.singers_dir = str(voices)
    controller.singers[VoiceRole.BASS] = "gone-voice"
    with qtbot.waitSignal(controller.voices_changed, timeout=20000) as blocker:
        controller.refresh_voices()
    assert blocker.args[0] == ["alto-voice"]
    assert controller.singer_problem(VoiceRole.BASS) == (
        "The voice \u201cgone-voice\u201d for Bass is not installed."
    )
    assert controller.singer_problem(VoiceRole.TENOR) == "Choose a singing voice for Tenor."
    controller.set_singer(VoiceRole.TENOR, "alto-voice")
    assert controller.singer_problem(VoiceRole.TENOR) is None


def test_chosen_voices_are_remembered_between_launches(
    qtbot: QtBot, controller: AppController, prefs: Preferences
) -> None:
    controller.set_singer(VoiceRole.LEAD, "my-voice")
    prefs.sync()
    again = AppController(Preferences(prefs._s), environ={}, config_file=None)
    assert again.singers[VoiceRole.LEAD] == "my-voice"
    assert again.singers[VoiceRole.TENOR] == ""  # nothing chosen on its own


def test_no_voice_is_ever_chosen_automatically(
    qtbot: QtBot, controller: AppController, tmp_path: Path
) -> None:
    voices = tmp_path / "voices"
    (voices / "only-voice").mkdir(parents=True)
    (voices / "only-voice" / "oto.ini").write_text("", encoding="utf-8")
    (voices / "only-voice" / "character.txt").write_text("name=only", encoding="utf-8")
    controller.prefs.singers_dir = str(voices)
    with qtbot.waitSignal(controller.voices_changed, timeout=20000):
        controller.refresh_voices()
    assert all(not v for v in controller.singers.values())


# --- output options ---


def test_options_are_remembered(controller: AppController, prefs: Preferences) -> None:
    controller.set_options(
        audio_format="both", gain_preset="custom", mp3_quality=5, keep_stems=True
    )
    controller.set_output_dir("C:/Tracks")
    prefs.sync()
    assert prefs.audio_format == "both"
    assert prefs.gain_preset == "custom"
    assert prefs.mp3_quality == 5
    assert prefs.keep_stems is True
    assert prefs.output_dir == "C:/Tracks"


def test_the_expected_location_and_name(
    qtbot: QtBot, controller: AppController, tmp_path: Path
) -> None:
    load(qtbot, controller, write_quartet(tmp_path, all_lyrics=True))
    assert controller.expected_location() is None  # no output folder yet
    controller.set_output_dir(str(tmp_path / "out"))
    assert controller.expected_location() == tmp_path / "out" / "quartet_learning_tracks"
    controller.set_options(name="My Song!")
    assert controller.expected_location() == tmp_path / "out" / "My_Song_learning_tracks"
    controller.set_options(name="CON")
    assert controller.package_name() is None
    assert any("folder name" in b for b in controller.blockers())


def test_custom_gains_are_validated(controller: AppController) -> None:
    controller.set_options(gain_preset="custom", custom_focus=0.3, custom_others=0.4)
    assert controller.gain_problem() is not None
    controller.set_options(custom_focus=0.6, custom_others=0.1)
    assert controller.gain_problem() is None
    profile = controller.gain_profile()
    assert (profile.predominant_focus, profile.predominant_others) == (0.6, 0.1)


# --- generation ---


def test_generation_runs_in_the_background_and_reports_back_on_the_gui_thread(
    qtbot: QtBot, controller: AppController, fake: FakeGenerate, tmp_path: Path
) -> None:
    ready_to_generate(qtbot, controller, tmp_path)
    assert controller.blockers() == []
    handler_threads: set[int] = set()
    controller.generation_event.connect(lambda e: handler_threads.add(threading.get_ident()))
    with qtbot.waitSignal(controller.generation_finished, timeout=20000) as blocker:
        assert controller.start_generation()
    assert blocker.args[0] == "RESULT"
    assert not controller.running
    assert fake.event_threads
    assert threading.get_ident() not in fake.event_threads  # events came from the worker thread
    assert handler_threads == {threading.get_ident()}  # delivered on the GUI thread


def test_the_tune_up_note_and_the_count_in_reach_the_request(
    qtbot: QtBot, controller: AppController, fake: FakeGenerate, tmp_path: Path
) -> None:
    ready_to_generate(qtbot, controller, tmp_path)
    assert not controller.options.tune_up
    assert not controller.options.count_in
    controller.set_options(tune_up=True, count_in=True)
    assert controller.prefs.tune_up is True  # remembered for the next start
    assert controller.prefs.count_in is True
    with qtbot.waitSignal(controller.generation_finished, timeout=20000):
        assert controller.start_generation()
    (request,) = fake.requests
    assert request.tune_up
    assert request.count_in


def test_the_request_carries_exactly_what_the_user_chose(
    qtbot: QtBot, controller: AppController, fake: FakeGenerate, tmp_path: Path
) -> None:
    ready_to_generate(qtbot, controller, tmp_path)
    controller.set_singer(VoiceRole.BASS, "alto-voice")
    controller.set_options(audio_format="both", mp3_quality=4, keep_stems=True, name="Song")
    (tmp_path / "ffmpeg.exe").write_bytes(b"x")
    controller.prefs.ffmpeg_path = str(tmp_path / "ffmpeg.exe")
    with qtbot.waitSignal(controller.generation_finished, timeout=20000):
        assert controller.start_generation()
    (request,) = fake.requests
    assert request.formats == frozenset({AudioFormat.WAV, AudioFormat.MP3})
    assert request.mp3_quality == 4
    assert request.keep_stems
    assert not request.keep_project
    assert not request.replace
    assert request.name == "Song"
    assert request.output == tmp_path / "out"
    assert dict(request.engine.per_voice) == dict.fromkeys(ROLES.values(), "alto-voice")
    assert {role.value: line for role, line in request.assignments.entries} == LINES


def test_a_second_click_while_running_is_refused(
    qtbot: QtBot, controller: AppController, fake: FakeGenerate, tmp_path: Path
) -> None:
    ready_to_generate(qtbot, controller, tmp_path)
    fake.hold.clear()
    assert controller.start_generation()
    assert fake.started.wait(10)
    assert controller.running
    assert not controller.start_generation()
    assert controller.blockers() == ["A generation is already running."]
    with qtbot.waitSignal(controller.generation_finished, timeout=20000):
        fake.hold.set()
    assert len(fake.requests) == 1


def test_cancelling_reaches_the_pipelines_token(
    qtbot: QtBot, controller: AppController, fake: FakeGenerate, tmp_path: Path
) -> None:
    ready_to_generate(qtbot, controller, tmp_path)
    fake.hold.clear()
    assert controller.start_generation()
    assert fake.started.wait(10)
    with qtbot.waitSignal(controller.generation_failed, timeout=20000) as blocker:
        controller.cancel_generation()
    assert blocker.args[0].category is ErrorCategory.CANCELLED
    assert not controller.running
    assert controller.last_result is None


def test_a_pipeline_failure_arrives_as_a_pipeline_error(
    qtbot: QtBot, controller: AppController, fake: FakeGenerate, tmp_path: Path
) -> None:
    ready_to_generate(qtbot, controller, tmp_path)
    fake.error = PipelineError(ErrorCategory.AUDIO, "STEM_SILENT", "silent")
    with qtbot.waitSignal(controller.generation_failed, timeout=20000) as blocker:
        assert controller.start_generation()
    assert blocker.args[0].code == "STEM_SILENT"
    assert not controller.running


def test_an_unexpected_exception_is_not_swallowed(
    qtbot: QtBot, controller: AppController, fake: FakeGenerate, tmp_path: Path
) -> None:
    ready_to_generate(qtbot, controller, tmp_path)

    def broken(*args: Any, **kwargs: Any) -> Any:
        raise OSError("disk exploded")

    controller._generate = broken
    with qtbot.waitSignal(controller.generation_failed, timeout=20000) as blocker:
        controller.start_generation()
    assert blocker.args[0].category is ErrorCategory.CONFIGURATION  # a filesystem problem
    assert "disk exploded" in blocker.args[0].message


def test_generation_will_not_start_while_anything_blocks_it(
    qtbot: QtBot, controller: AppController, fake: FakeGenerate, tmp_path: Path
) -> None:
    ready_to_generate(qtbot, controller, tmp_path)
    controller.set_singer(VoiceRole.LEAD, "")
    assert not controller.start_generation()
    assert fake.requests == []
