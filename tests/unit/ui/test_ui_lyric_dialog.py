"""The lyric review dialog and the window's lyric workflow."""

import json
from pathlib import Path

import pytest
from PySide6.QtCore import QItemSelectionModel, Qt
from PySide6.QtWidgets import QDialog
from pytestqt.qtbot import QtBot
from test_ui_window import Rig

from barbershop_tracks.core.pipeline import approvals_document
from barbershop_tracks.core.synthesis import SynthesisPlan
from barbershop_tracks.models import VoiceRole
from barbershop_tracks.ui.dialogs import COLUMNS, LYRIC_COLUMN, LyricReviewDialog
from barbershop_tracks.ui.lyric_review import LyricReviewState, RowState
from gui_support import FakePrompts
from synth_builders import full_lyrics, plan_of, sung

pytestmark = pytest.mark.gui


def plan() -> SynthesisPlan:
    voices = {
        **full_lyrics(("one", "two", "three", "four")),
        "tenor": sung(VoiceRole.TENOR, [None, "two", None, None]),
        "bass": sung(VoiceRole.BASS, [None, None, "three", "four"]),
    }
    return plan_of(voices=voices)


class Dialog:
    def __init__(self, qtbot: QtBot) -> None:
        self.plan = plan()
        self.state = LyricReviewState(self.plan, approver="Joe")
        self.prompts = FakePrompts()
        self.dialog = LyricReviewDialog(self.state, self.plan, self.prompts)
        qtbot.addWidget(self.dialog)
        self.dialog.show()

    def select(self, rows: list[int]) -> None:
        selection = self.dialog.table.selectionModel()
        selection.clearSelection()
        for row in rows:
            index = self.dialog.proxy.mapFromSource(self.dialog.model.index(row, 0))
            selection.select(
                index,
                QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
            )

    def type(self, row: int, text: str) -> None:
        index = self.dialog.model.index(row, LYRIC_COLUMN)
        assert self.dialog.model.setData(index, text, Qt.ItemDataRole.EditRole)

    def cell(self, row: int, name: str) -> str:
        return str(self.dialog.model.data(self.dialog.model.index(row, COLUMNS.index(name))))


@pytest.fixture
def rig(qtbot: QtBot, tmp_path: Path) -> Rig:
    return Rig(qtbot, tmp_path)


@pytest.fixture
def dlg(qtbot: QtBot) -> Dialog:
    return Dialog(qtbot)


def test_the_table_lists_exactly_the_notes_without_a_lyric(dlg: Dialog) -> None:
    assert dlg.dialog.model.rowCount() == 5
    assert dlg.dialog.model.columnCount() == len(COLUMNS)
    assert [dlg.cell(i, "Voice") for i in range(5)] == ["Tenor", "Tenor", "Tenor", "Bass", "Bass"]
    assert dlg.cell(0, "Where") == "bar 1, beat 1"
    assert dlg.cell(0, "Pitch") == "E4"
    assert dlg.cell(0, "Why it needs a lyric") == "No lyric in the score"
    assert dlg.cell(0, "Lead sings") == "one"
    assert dlg.cell(0, "Status") == RowState.UNDECIDED.value
    assert "5 still need a lyric" in dlg.dialog.summary.text()


def test_only_the_lyric_column_is_editable(dlg: Dialog) -> None:
    model = dlg.dialog.model
    editable = [
        bool(model.flags(model.index(0, c)) & Qt.ItemFlag.ItemIsEditable)
        for c in range(len(COLUMNS))
    ]
    assert editable == [c == LYRIC_COLUMN for c in range(len(COLUMNS))]


def test_typing_then_approving_note_by_note(dlg: Dialog) -> None:
    dlg.type(0, "la")
    assert dlg.cell(0, "Status") == RowState.DRAFT.value
    assert "typed but not approved" in dlg.dialog.summary.text()
    dlg.select([0])
    assert dlg.dialog.approve_selected() == 1
    assert dlg.cell(0, "Status") == RowState.APPROVED.value
    assert "1 of 5 notes approved" in dlg.dialog.summary.text()
    assert [a.text for a in dlg.state.approvals()] == ["la"]


def test_invalid_text_is_flagged_and_not_approved(dlg: Dialog) -> None:
    dlg.type(1, "+")
    assert dlg.cell(1, "Status") == RowState.INVALID.value
    tip = dlg.dialog.model.data(dlg.dialog.model.index(1, 0), Qt.ItemDataRole.ToolTipRole)
    assert tip
    dlg.select([1])
    assert dlg.dialog.approve_selected() == 0
    assert dlg.state.approvals() == ()


def test_approve_all_typed_leaves_untyped_rows_alone(dlg: Dialog) -> None:
    dlg.type(0, "la")
    dlg.type(3, "ba")
    assert dlg.dialog.approve_typed() == 2
    assert {r.state for r in dlg.state.rows} == {RowState.APPROVED, RowState.UNDECIDED}
    assert dlg.state.unresolved == 3


def test_the_lead_is_copied_only_after_an_explicit_confirmed_action(dlg: Dialog) -> None:
    assert all(r.text == "" for r in dlg.state.rows)
    dlg.select([0, 1])
    dlg.prompts.confirm_answer = False
    dlg.dialog.copy_lead()
    assert all(r.text == "" for r in dlg.state.rows)  # declined: nothing happened
    dlg.prompts.confirm_answer = True
    dlg.dialog.copy_lead()
    assert [r.text for r in dlg.state.rows[:2]] == ["one", "three"]
    assert all(r.state is RowState.DRAFT for r in dlg.state.rows[:2])  # still to be approved
    assert dlg.state.approvals() == ()


def test_unapprove_and_clear(dlg: Dialog) -> None:
    dlg.type(0, "la")
    dlg.select([0])
    dlg.dialog.approve_selected()
    dlg.dialog.unapprove_selected()
    assert dlg.cell(0, "Status") == RowState.DRAFT.value
    dlg.dialog.clear_selected()
    assert dlg.cell(0, "Status") == RowState.UNDECIDED.value


def test_filters_by_voice_and_hides_approved(dlg: Dialog) -> None:
    dialog = dlg.dialog
    assert dialog.proxy.rowCount() == 5
    dialog.voice_filter.setCurrentIndex(dialog.voice_filter.findData("bass"))
    assert dialog.proxy.rowCount() == 2
    dialog.voice_filter.setCurrentIndex(0)
    dlg.type(0, "la")
    dlg.select([0])
    dialog.approve_selected()
    dialog.open_only.setChecked(True)
    assert dialog.proxy.rowCount() == 4


def test_cancel_restores_every_decision(dlg: Dialog) -> None:
    dlg.type(0, "la")
    dlg.select([0])
    dlg.dialog.approve_selected()
    dlg.dialog.reject()
    assert dlg.state.approvals() == ()
    assert dlg.state.rows[0].text == ""


def test_done_keeps_the_decisions(dlg: Dialog) -> None:
    dlg.type(0, "la")
    dlg.select([0])
    dlg.dialog.approve_selected()
    dlg.dialog.accept()
    assert len(dlg.state.approvals()) == 1


def test_approvals_can_be_saved_and_loaded_again(dlg: Dialog, tmp_path: Path) -> None:
    dlg.type(0, "la")
    dlg.type(4, "ba")
    dlg.dialog.approve_typed()
    target = tmp_path / "approvals.json"
    dlg.prompts.answers["save"] = str(target)
    dlg.prompts.save_file = lambda *a, **k: str(target)  # type: ignore[method-assign]
    dlg.dialog.save_file()
    document = json.loads(target.read_text(encoding="utf-8"))
    assert document["schema"] == "blt.lyric-approvals/1"
    assert document["source_sha256"] == dlg.plan.source.sha256
    assert len(document["approvals"]) == 2

    other = Dialog.__new__(Dialog)
    other.plan = plan()
    other.state = LyricReviewState(other.plan, approver="Joe")
    other.prompts = FakePrompts()
    other.prompts.answers["file"] = str(target)
    other.dialog = LyricReviewDialog(other.state, other.plan, other.prompts)
    other.dialog.load_file()
    assert other.state.approved_count == 2
    assert other.prompts.informed == ["Approvals loaded", "2 approval(s) applied."] or any(
        "2 approval(s) applied." in text for text in other.prompts.informed
    )


def test_approvals_for_another_score_are_refused_with_a_message(
    dlg: Dialog, tmp_path: Path
) -> None:
    wrong = tmp_path / "wrong.json"
    wrong.write_text(json.dumps(approvals_document((), "cd" * 32)), encoding="utf-8")
    dlg.prompts.answers["file"] = str(wrong)
    dlg.dialog.load_file()
    assert any("different version of the score" in w for w in dlg.prompts.warnings)
    assert dlg.state.approved_count == 0


def test_the_review_report_can_be_exported(dlg: Dialog, tmp_path: Path) -> None:
    target = tmp_path / "report.json"
    dlg.prompts.save_file = lambda *a, **k: str(target)  # type: ignore[method-assign]
    dlg.dialog.export_report()
    report = json.loads(target.read_text(encoding="utf-8"))
    assert report["schema"] == "blt.lyric-review/1"
    assert len(report["items"]) == 5


# --- through the main window ---


class Review:
    """A window with a score whose harmony parts have no lyrics."""

    def __init__(self, rig: Rig) -> None:
        self.rig = rig
        rig.load(all_lyrics=False)
        rig.assign()
        rig.choose_voices()
        rig.prompts.answers["Where should the tracks be saved?"] = str(rig.tmp / "out")
        rig.window.choose_output_folder()


def test_unresolved_lyrics_block_generation_and_the_review_resolves_them(rig: Rig) -> None:
    review = Review(rig)
    window = rig.window
    assert not window.generate.isEnabled()
    assert any("24 notes still need a lyric" in b for b in rig.controller.blockers())
    assert window.validation_section.review.isEnabled()
    assert "24 notes" in window.validation_section.review.text()
    assert "24 notes have no lyric yet" in window.validation_section.list.item(0).text()
    window.on_generate_clicked()  # even a stray call cannot start it
    assert rig.pipeline.requests == []

    def approve_everything(dialog: QDialog) -> bool:
        assert isinstance(dialog, LyricReviewDialog)
        count = dialog.model.rowCount()
        dialog.state.fill_text(list(range(count)), "la")
        dialog.model.changed_all()
        assert dialog.approve_typed() == count
        dialog.accept()
        return True

    window.run_dialog = approve_everything
    window.open_review()
    rig.qtbot.waitUntil(lambda: not rig.controller.validating, timeout=20000)
    assert window.generate.isEnabled()
    assert (
        "The score and lyrics are complete."
        in window.validation_section.list.item(window.validation_section.list.count() - 1).text()
    )
    with rig.qtbot.waitSignal(rig.controller.generation_finished, timeout=20000):
        window.generate.click()
    (request,) = rig.pipeline.requests
    assert len(request.approvals) == 24
    assert {a.role for a in request.approvals} == {
        VoiceRole.TENOR,
        VoiceRole.BARITONE,
        VoiceRole.BASS,
    }  # the Lead had its own words; nothing was copied or invented for it
    assert all(a.text == "la" and a.approved_by for a in request.approvals)
    assert review.rig is rig


def test_cancelling_the_review_keeps_generation_blocked(rig: Rig) -> None:
    Review(rig)

    def type_but_cancel(dialog: QDialog) -> bool:
        assert isinstance(dialog, LyricReviewDialog)
        dialog.state.fill_text([0, 1, 2], "la")
        dialog.state.approve([0, 1, 2])
        dialog.reject()
        return False

    rig.window.run_dialog = type_but_cancel
    rig.window.open_review()
    rig.qtbot.wait(100)
    assert rig.controller.approvals == ()
    assert not rig.window.generate.isEnabled()


def test_approvals_do_not_follow_the_user_to_a_different_score(rig: Rig) -> None:
    Review(rig)
    review = rig.controller.review
    assert review is not None
    review.fill_text([0], "la")
    review.approve([0])
    rig.controller.set_approvals(review.approvals())
    other = rig.tmp / "other.musicxml"
    from cli_scores import write_quartet

    write_quartet(rig.tmp, "other.musicxml", all_lyrics=False, word="ba")
    with rig.qtbot.waitSignal(rig.controller.score_loaded, timeout=20000):
        rig.window.open_score(other)
    assert rig.controller.approvals == ()
    assert rig.controller.review is None


def test_the_review_button_needs_a_review(rig: Rig) -> None:
    rig.load(all_lyrics=True)
    rig.assign()
    assert not rig.window.validation_section.review.isEnabled()
    assert rig.window.create_review_dialog() is None
