"""The pronunciation review: blocked words listed by place, decided by a person, tied to a score."""

import json
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtCore import QItemSelectionModel, Qt
from PySide6.QtWidgets import QDialog
from pytestqt.qtbot import QtBot
from test_ui_window import Rig

from barbershop_tracks.core.pipeline import ErrorCategory, PipelineError
from barbershop_tracks.models import VoiceRole
from barbershop_tracks.ui.pronunciation_dialog import (
    COLUMNS,
    TEXT_COLUMN,
    PronunciationDialog,
)
from barbershop_tracks.ui.pronunciation_review import PronunciationRow, PronunciationState, RowState

pytestmark = pytest.mark.gui

ARPASING = "OpenUtau.Plugin.Builtin.ArpasingPhonemizer"
XSAMPA = "OpenUtau.Plugin.Builtin.EnXSampaPhonemizer"
SHA = "ab" * 32


def blocked(
    role: str = "lead",
    start: str = "1",
    word: str = "ev'ry",
    *,
    where: str = "bar 1, beat 2",
    phonemizer: str | None = ARPASING,
    lyrics: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    return {
        "voice": role.title(),
        "role": role,
        "note_index": 1,
        "start": start,
        "where": where,
        "lyric": word,
        "word": word,
        "fragment": False,
        "phonemizer": phonemizer,
        "score_lyrics": list(lyrics or (word,)),
    }


def four_voices(word: str = "ev'ry", start: str = "1") -> list[dict[str, Any]]:
    return [blocked(r, start, word) for r in ("tenor", "lead", "baritone", "bass")]


def status(row: PronunciationRow) -> str:
    return row.state.value


def state_with(*items: dict[str, Any]) -> PronunciationState:
    state = PronunciationState(SHA, approver="A. Singer")
    state.add_blocked(items)
    return state


# --- the state -----------------------------------------------------------------------------------


def test_one_row_per_voice_and_place_sorted_by_position_then_voice() -> None:
    state = state_with(
        blocked("bass", "9", "o'er", where="bar 3, beat 2"),
        *four_voices(),
        blocked("lead", "9", "o'er"),
    )
    assert [(r.start, r.role.value) for r in state.rows] == [
        (Fraction(1), "tenor"),
        (Fraction(1), "lead"),
        (Fraction(1), "baritone"),
        (Fraction(1), "bass"),
        (Fraction(9), "lead"),
        (Fraction(9), "bass"),
    ]
    assert all(status(r) == RowState.UNDECIDED.value for r in state.rows)
    assert state.undecided == 6
    assert state.overrides() == ()  # nothing is decided, so nothing is sent anywhere


def test_a_place_blt_could_not_locate_is_not_listed() -> None:
    state = state_with({"role": None, "start": None, "lyric": "x"})
    assert state.rows == []


def test_typing_decides_a_row_and_it_becomes_an_override_for_this_score() -> None:
    state = state_with(*four_voices())
    state.set_text(1, "  eh   v r iy ")
    row = state.rows[1]
    assert row.text == "eh v r iy"
    assert status(row) == RowState.DECIDED.value
    (decided,) = state.overrides()
    assert decided.role is VoiceRole.LEAD
    assert decided.start == Fraction(1)
    assert decided.word == "ev'ry"
    assert decided.symbols == ("eh", "v", "r", "iy")
    assert decided.phonemizer == ARPASING
    assert decided.source_sha256 == SHA
    assert decided.approved_by == "A. Singer"
    assert state.undecided == 3


def test_a_pronunciation_of_the_wrong_form_is_flagged_and_never_sent() -> None:
    state = state_with(*four_voices())
    state.set_text(0, "eh [v] r")
    assert status(state.rows[0]) == RowState.INVALID.value
    assert state.overrides() == ()
    state.set_text(0, "eh v r")
    assert status(state.rows[0]) == RowState.DECIDED.value
    state.set_text(0, "")
    assert status(state.rows[0]) == RowState.UNDECIDED.value


def test_same_for_the_other_voices_touches_only_this_place_and_word() -> None:
    state = state_with(*four_voices(), *four_voices("o'er", "9"), blocked("lead", "17", "ev'ry"))
    lead_at_one = next(
        i for i, r in enumerate(state.rows) if r.role is VoiceRole.LEAD and r.start == 1
    )
    state.set_text(lead_at_one, "eh v r iy")
    assert state.fill_same_place(lead_at_one) == 3
    texts = {(r.role.value, str(r.start)): r.text for r in state.rows if r.text}
    assert texts == {
        ("tenor", "1"): "eh v r iy",
        ("lead", "1"): "eh v r iy",
        ("baritone", "1"): "eh v r iy",
        ("bass", "1"): "eh v r iy",
    }
    # the same word in another bar and another word at the same bar are not touched
    assert next(r for r in state.rows if r.start == 17).text == ""
    assert all(r.text == "" for r in state.rows if r.word == "o'er")


def test_same_for_the_other_voices_needs_something_valid_to_copy() -> None:
    state = state_with(*four_voices())
    assert state.fill_same_place(0) == 0
    state.set_text(0, "bad [")
    assert state.fill_same_place(0) == 0
    assert all(r.text == "" for r in state.rows[1:])


def test_same_place_never_crosses_pronunciation_engines() -> None:
    state = state_with(blocked("tenor"), blocked("lead", phonemizer=XSAMPA))
    state.set_text(0, "eh v r iy")
    assert state.fill_same_place(0) == 0
    assert state.rows[1].text == ""


def test_an_engine_that_takes_no_pronunciations_cannot_be_decided() -> None:
    state = state_with(blocked("lead", phonemizer="OpenUtau.Core.DefaultPhonemizer"))
    state.set_text(0, "eh v r iy")
    assert state.rows[0].supported is False
    assert state.overrides() == ()  # BLT never sends a pronunciation to an engine that ignores it


def test_what_the_engine_refuses_is_marked_on_that_row_only() -> None:
    state = state_with(*four_voices())
    for i in range(4):
        state.set_text(i, "eh v r zzz")
    marked = state.mark_refused(
        [
            {"role": "lead", "start": "1", "symbol": "zzz", "reason": "symbol_unknown"},
            {"role": "bass", "start": "1", "symbol": None, "reason": "no_sound"},
        ]
    )
    assert marked == 2
    by_voice = {r.role.value: r for r in state.rows}
    assert status(by_voice["lead"]) == RowState.INVALID.value
    assert "zzz" in by_voice["lead"].error
    assert "no sound" in by_voice["bass"].error
    assert status(by_voice["tenor"]) == RowState.DECIDED.value
    assert {o.role.value for o in state.overrides()} == {"tenor", "baritone"}
    state.set_text(1, "eh v r iy")  # revising the text clears the refusal
    assert status(by_voice["lead"]) == RowState.DECIDED.value


def test_accepted_places_show_the_sounds_the_engine_made() -> None:
    state = state_with(*four_voices())
    state.set_text(1, "eh v r iy")
    state.mark_accepted([{"track": "Lead", "position": 480, "phonemes": ["aa eh", "eh v"]}])
    assert "aa eh, eh v" in state.rows[1].note


def test_revising_an_existing_decision_keeps_its_text() -> None:
    state = state_with(*four_voices())
    state.set_text(1, "eh v r iy")
    (kept,) = state.overrides()
    again = PronunciationState(SHA, approver="A. Singer")
    again.adopt([kept], {kept.key: "bar 1, beat 2"})
    assert [(r.role.value, r.text, r.where) for r in again.rows] == [
        ("lead", "eh v r iy", "bar 1, beat 2")
    ]


def test_a_file_made_for_another_score_is_refused_as_a_whole(tmp_path: Path) -> None:
    state = state_with(*four_voices())
    state.set_text(1, "eh v r iy")
    path = tmp_path / "p.json"
    path.write_text(json.dumps(state.document()), encoding="utf-8")
    other = PronunciationState("cd" * 32)
    other.add_blocked(four_voices())
    with pytest.raises(PipelineError) as error:
        other.load_file(path)
    assert error.value.code == "OVERRIDES_WRONG_SCORE"
    assert all(r.text == "" for r in other.rows)


def test_a_saved_file_applies_to_the_places_it_was_decided_for_and_nowhere_else(
    tmp_path: Path,
) -> None:
    state = state_with(*four_voices())
    state.set_text(1, "eh v r iy")
    path = tmp_path / "p.json"
    path.write_text(json.dumps(state.document()), encoding="utf-8")
    fresh = state_with(*four_voices(), blocked("lead", "9", "ev'ry"))
    applied, ignored = fresh.load_file(path)
    assert (applied, ignored) == (1, 0)
    assert [r.text for r in fresh.rows if r.text] == ["eh v r iy"]
    assert (
        next(r for r in fresh.rows if r.start == 9).text == ""
    )  # same word, other place: undecided
    other_word = state_with(blocked("lead", "1", "o'er"))
    assert other_word.load_file(path) == (0, 1)  # the place no longer holds that word: ignored


# --- the dialog ----------------------------------------------------------------------------------


class Box:
    def __init__(self, qtbot: QtBot, tmp_path: Path) -> None:
        self.rig = Rig(qtbot, tmp_path)
        self.rig.ready()
        self.state = state_with(*four_voices())
        self.rig.controller.pronunciation = self.state
        self.dialog = PronunciationDialog(
            self.state, self.rig.controller, self.rig.prompts, self.rig.window
        )
        qtbot.addWidget(self.dialog)
        self.dialog.show()

    def select(self, rows: list[int]) -> None:
        selection = self.dialog.table.selectionModel()
        selection.clearSelection()
        for row in rows:
            selection.select(
                self.dialog.model.index(row, 0),
                QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
            )

    def type(self, row: int, text: str) -> None:
        assert self.dialog.model.setData(
            self.dialog.model.index(row, TEXT_COLUMN), text, Qt.ItemDataRole.EditRole
        )

    def cell(self, row: int, name: str) -> str:
        return str(self.dialog.model.data(self.dialog.model.index(row, COLUMNS.index(name))))


@pytest.fixture
def box(qtbot: QtBot, tmp_path: Path) -> Box:
    return Box(qtbot, tmp_path)


def test_the_table_shows_each_place_with_the_scores_own_text(box: Box) -> None:
    model = box.dialog.model
    assert model.rowCount() == 4
    assert [box.cell(i, "Voice") for i in range(4)] == ["Tenor", "Lead", "Baritone", "Bass"]
    assert box.cell(0, "Where") == "bar 1, beat 2"
    assert box.cell(0, "The score says") == "ev'ry"
    assert box.cell(0, "Engine") == "Arpasing"
    assert box.cell(0, "Status") == RowState.UNDECIDED.value
    assert "4 still need a pronunciation" in box.dialog.summary.text()
    assert "ARPAbet" in box.dialog.notation.text()


def test_the_scores_syllables_are_shown_as_written(qtbot: QtBot, tmp_path: Path) -> None:
    box = Box(qtbot, tmp_path)
    box.state.rows.clear()
    box.state.add_blocked([blocked("lead", "0", "ev'ryone", lyrics=("ev'", "ry", "one"))])
    box.dialog.model.layoutChanged.emit()
    assert box.cell(0, "The score says") == "ev' · ry · one"
    assert box.cell(0, "Word sent to the engine") == "ev'ryone"


def test_only_the_pronunciation_column_is_editable(box: Box) -> None:
    model = box.dialog.model
    editable = [
        bool(model.flags(model.index(0, c)) & Qt.ItemFlag.ItemIsEditable)
        for c in range(len(COLUMNS))
    ]
    assert editable == [c == TEXT_COLUMN for c in range(len(COLUMNS))]


def test_typing_decides_one_row_and_the_summary_follows(box: Box) -> None:
    box.type(1, "eh v r iy")
    assert box.cell(1, "Status") == RowState.DECIDED.value
    assert "1 of 4 places decided" in box.dialog.summary.text()
    assert box.cell(0, "Status") == RowState.UNDECIDED.value
    box.type(2, "eh [v")
    assert RowState.INVALID.value in box.cell(2, "Status")
    assert "1 cannot be used" in box.dialog.summary.text()


def test_the_notation_note_follows_the_selected_engine(box: Box) -> None:
    box.state.rows[1].phonemizer = XSAMPA
    box.select([1])
    assert "X-SAMPA" in box.dialog.notation.text()
    box.select([0])
    assert "ARPAbet" in box.dialog.notation.text()


def test_same_for_other_voices_is_a_click_not_a_default(box: Box) -> None:
    box.type(1, "eh v r iy")
    assert [r.text for r in box.state.rows] == ["", "eh v r iy", "", ""]  # nothing spread by itself
    box.select([1])
    assert box.dialog.fill_same_place() == 3
    assert {r.text for r in box.state.rows} == {"eh v r iy"}


def test_clear_empties_the_selected_rows(box: Box) -> None:
    box.type(0, "eh v r iy")
    box.select([0])
    box.dialog.clear_selected()
    assert box.cell(0, "Status") == RowState.UNDECIDED.value


def test_cancel_leaves_the_decisions_as_they_were(box: Box) -> None:
    box.type(0, "eh v r iy")
    box.dialog.reject()
    assert box.state.rows[0].text == ""


def test_save_then_load_keeps_decisions_bound_to_the_score(box: Box, tmp_path: Path) -> None:
    box.type(1, "eh v r iy")
    path = tmp_path / "saved.json"
    box.rig.prompts.answers["save"] = str(path)
    box.dialog.save_file()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["source_sha256"] == SHA
    assert [e["voice"] for e in saved["overrides"]] == ["lead"]
    assert saved["overrides"][0]["word"] == "ev'ry"
    box.dialog.clear_selected()
    box.state.clear([0, 1, 2, 3])
    box.rig.prompts.answers["file"] = str(path)
    box.dialog.load_file()
    assert box.state.rows[1].text == "eh v r iy"
    assert "1 pronunciation applied" in box.rig.prompts.informed[-1]


def test_a_file_for_another_score_is_refused_with_a_message(box: Box, tmp_path: Path) -> None:
    path = tmp_path / "other.json"
    path.write_text(
        json.dumps(
            {"schema": "blt.pronunciation-overrides/1", "source_sha256": "cd" * 32, "overrides": []}
        ),
        encoding="utf-8",
    )
    box.rig.prompts.answers["file"] = str(path)
    box.dialog.load_file()
    assert "different version of the score" in box.rig.prompts.warnings[-1]


def test_check_asks_the_controller_and_shows_what_the_engine_says(
    box: Box, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[Any] = []

    def fake_check(request: Any, config: Any, *, cancel: Any, on_event: Any) -> dict[str, Any]:
        calls.append(request.pronunciations)
        return {
            "status": "ok",
            "pronunciations": [{"track": "Lead", "position": 480, "phonemes": ["eh v"]}],
        }

    monkeypatch.setattr("barbershop_tracks.ui.controller.check_pronunciations", fake_check)
    box.type(1, "eh v r iy")
    with box.rig.qtbot.waitSignal(box.rig.controller.pronunciation_checked, timeout=20000):
        assert box.dialog.check()
    assert [o.role.value for o in calls[0]] == ["lead"]
    assert "Accepted; the engine sings: eh v" in box.cell(1, "Status")
    assert box.rig.prompts.informed[-1].startswith("Nothing was rendered")


def test_check_shows_the_engines_refusal_and_marks_the_row(
    box: Box, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(request: Any, config: Any, *, cancel: Any, on_event: Any) -> dict[str, Any]:
        raise PipelineError(
            ErrorCategory.SOURCE,
            "PRONUNCIATION_INVALID",
            "1 pronunciation(s) given for this score cannot be used",
            {
                "invalid_hints": [
                    {
                        "voice": "Lead",
                        "role": "lead",
                        "start": "1",
                        "where": "bar 1, beat 2",
                        "lyric": "ev'ry",
                        "symbol": "zzz",
                        "reason": "symbol_unknown",
                    }
                ]
            },
        )

    monkeypatch.setattr("barbershop_tracks.ui.controller.check_pronunciations", refuse)
    box.type(1, "eh v r zzz")
    with box.rig.qtbot.waitSignal(box.rig.controller.pronunciation_checked, timeout=20000):
        box.dialog.check()
    assert RowState.INVALID.value in box.cell(1, "Status")
    assert "zzz" in box.cell(1, "Status")
    assert "'zzz'" in box.rig.prompts.warnings[-1]


# --- the window and the controller ---------------------------------------------------------------


@pytest.fixture
def rig(qtbot: QtBot, tmp_path: Path) -> Rig:
    made = Rig(qtbot, tmp_path)
    made.ready()
    return made


def stop_at_words(rig: Rig, words: list[dict[str, Any]]) -> None:
    rig.pipeline.error = PipelineError(
        ErrorCategory.SOURCE,
        "PRONUNCIATION_UNKNOWN",
        "the pronunciation dictionary has no entry for 1 word(s)",
        {"unknown_words": words},
    )
    rig.window.on_generate_clicked()
    rig.qtbot.waitUntil(lambda: not rig.controller.running, timeout=20000)


def test_a_stopped_run_lists_the_words_and_offers_the_pronunciations(rig: Rig) -> None:
    stop_at_words(rig, four_voices())
    section = rig.window.progress_section
    assert section.open_pronunciation.isEnabled()
    assert not section.open_pronunciation.isHidden()
    assert "does not know how to pronounce" in section.result_title.text()
    assert "Pronunciations" in section.result_text.text()
    state = rig.controller.pronunciation_state()
    assert state is not None
    assert len(state.rows) == 4
    assert rig.window.pronunciation_action.isEnabled()


def test_generating_stays_blocked_until_every_place_is_decided(rig: Rig) -> None:
    stop_at_words(rig, four_voices())
    assert not rig.window.generate.isEnabled()
    assert (
        "4 places with a word the dictionary lacks still need a pronunciation"
        in rig.window.why.text()
    )
    state = rig.controller.pronunciation_state()
    assert state is not None
    for i in range(4):
        state.set_text(i, "eh v r iy")
    rig.controller.state_changed.emit()
    assert rig.window.generate.isEnabled()


def test_the_next_run_carries_exactly_the_decisions_made(rig: Rig) -> None:
    stop_at_words(rig, four_voices())
    state = rig.controller.pronunciation_state()
    assert state is not None
    for i in range(4):
        state.set_text(i, "eh v r iy")
    rig.controller.state_changed.emit()
    rig.pipeline.error = None
    rig.window.on_generate_clicked()
    rig.qtbot.waitUntil(lambda: not rig.controller.running, timeout=20000)
    request = rig.pipeline.requests[-1]
    assert sorted(o.role.value for o in request.pronunciations) == [
        "baritone",
        "bass",
        "lead",
        "tenor",
    ]
    assert {o.source_sha256 for o in request.pronunciations} == {rig.controller.score.sha256}  # type: ignore[union-attr]
    assert {o.word for o in request.pronunciations} == {"ev'ry"}
    assert {o.symbols for o in request.pronunciations} == {("eh", "v", "r", "iy")}


def test_the_decisions_are_gone_when_another_score_is_opened(rig: Rig) -> None:
    stop_at_words(rig, four_voices())
    assert rig.controller.pronunciation_state() is not None
    rig.load(measures=3)  # a different score
    assert rig.controller.pronunciation_state() is None
    assert rig.controller.pronunciations == ()
    assert not rig.window.pronunciation_action.isEnabled()


def test_the_decisions_are_gone_when_the_voice_assignment_changes(rig: Rig) -> None:
    stop_at_words(rig, four_voices())
    assert rig.controller.pronunciation_state() is not None
    rig.controller.suggest()  # any change of the mapping starts the decisions afresh
    assert rig.controller.pronunciation_state() is None


def test_a_refusal_by_the_engine_marks_the_place_and_blocks_generating(rig: Rig) -> None:
    stop_at_words(rig, four_voices())
    state = rig.controller.pronunciation_state()
    assert state is not None
    for i in range(4):
        state.set_text(i, "eh v r zzz")
    rig.pipeline.error = PipelineError(
        ErrorCategory.SOURCE,
        "PRONUNCIATION_INVALID",
        "4 pronunciation(s) given for this score cannot be used",
        {
            "invalid_hints": [
                {
                    "voice": "Lead",
                    "role": "lead",
                    "start": "1",
                    "where": "bar 1, beat 2",
                    "lyric": "ev'ry",
                    "symbol": "zzz",
                    "reason": "symbol_unknown",
                }
            ]
        },
    )
    rig.controller.state_changed.emit()
    rig.window.on_generate_clicked()
    rig.qtbot.waitUntil(lambda: not rig.controller.running, timeout=20000)
    assert "cannot be used" in rig.window.progress_section.result_title.text()
    assert not rig.window.progress_section.open_pronunciation.isHidden()
    lead = next(r for r in state.rows if r.role is VoiceRole.LEAD)
    assert status(lead) == RowState.INVALID.value
    assert not rig.window.generate.isEnabled()
    state.set_text(1, "eh v r iy")  # revising it is enough
    rig.controller.state_changed.emit()
    assert rig.window.generate.isEnabled()


def test_the_window_opens_the_dialog_for_the_blocked_places(rig: Rig) -> None:
    stop_at_words(rig, four_voices())
    shown: list[QDialog] = []

    def remember(dialog: QDialog) -> bool:
        shown.append(dialog)
        return True

    rig.window.run_dialog = remember
    rig.window.open_pronunciations()
    assert isinstance(shown[0], PronunciationDialog)
    assert shown[0].model.rowCount() == 4


def test_with_nothing_blocked_the_menu_says_so_instead_of_opening_an_empty_dialog(rig: Rig) -> None:
    assert not rig.window.pronunciation_action.isEnabled()
    rig.window.open_pronunciations()
    assert "No word needs a pronunciation yet" in rig.prompts.informed[-1]


def test_a_stale_decision_is_explained_and_leads_to_the_review(rig: Rig) -> None:
    stop_at_words(rig, four_voices())
    rig.pipeline.error = PipelineError(
        ErrorCategory.CONFIGURATION,
        "OVERRIDE_WORD_MISMATCH",
        "Lead, 'ev'ry' at quarter 1: the score now has 'every' there",
    )
    state = rig.controller.pronunciation_state()
    assert state is not None
    for i in range(4):
        state.set_text(i, "eh v r iy")
    rig.controller.state_changed.emit()
    rig.window.on_generate_clicked()
    rig.qtbot.waitUntil(lambda: not rig.controller.running, timeout=20000)
    section = rig.window.progress_section
    assert "no longer fits this score" in section.result_title.text()
    assert not section.open_pronunciation.isHidden()
