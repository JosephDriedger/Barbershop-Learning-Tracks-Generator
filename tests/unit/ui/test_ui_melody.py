"""Who has the melody in the window: the option, the dialog, and what a generation is asked for."""

from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot
from test_ui_window import Rig

from barbershop_tracks.core.melody import MelodyMark, beats_in_bar
from barbershop_tracks.models import VoiceRole
from barbershop_tracks.ui.melody_dialog import MelodyDialog, mark_text

pytestmark = pytest.mark.gui


@pytest.fixture
def rig(qtbot: QtBot, tmp_path: Path) -> Rig:
    return Rig(qtbot, tmp_path)


def test_the_full_quartet_follows_the_melody_unless_it_is_switched_off(rig: Rig) -> None:
    rig.ready()
    assert rig.window.output_section.follow_melody.isChecked()
    rig.window.generate.click()
    rig.qtbot.waitUntil(lambda: len(rig.pipeline.requests) == 1, timeout=10000)
    assert rig.pipeline.requests[0].follow_melody is True
    assert rig.pipeline.requests[0].melody_marks == ()


def test_switching_it_off_is_remembered_and_sent(rig: Rig) -> None:
    rig.ready()
    rig.window.output_section.follow_melody.setChecked(False)
    assert rig.prefs.follow_melody is False
    assert not rig.window.output_section.melody_button.isEnabled()
    rig.window.generate.click()
    rig.qtbot.waitUntil(lambda: len(rig.pipeline.requests) == 1, timeout=10000)
    assert rig.pipeline.requests[0].follow_melody is False


def test_the_melody_button_waits_for_a_score_and_voices(rig: Rig) -> None:
    assert not rig.window.output_section.melody_button.isEnabled()
    rig.window.open_melody()
    assert rig.prompts.informed  # says what is missing instead of opening nothing
    rig.ready()
    assert rig.window.output_section.melody_button.isEnabled()


def test_the_dialog_shows_the_melody_and_a_mark_changes_it(rig: Rig) -> None:
    rig.ready()
    plan = rig.controller.melody_plan()
    assert plan is not None
    dialog = MelodyDialog(plan, ())
    rig.qtbot.addWidget(dialog)
    first = [dialog.table.item(0, c).text() for c in range(3)]  # type: ignore[union-attr]
    assert first[1] == "Lead"
    assert "usual" in first[2]
    assert dialog.add_mark(VoiceRole.BASS, dialog.lowest, dialog.lowest)
    assert dialog.marks() == (MelodyMark(VoiceRole.BASS, dialog.lowest, dialog.lowest),)
    marked_rows = [
        dialog.table.item(r, 1).text()  # type: ignore[union-attr]
        for r in range(dialog.table.rowCount())
        if dialog.table.item(r, 2).text() == "You marked it"  # type: ignore[union-attr]
    ]
    assert marked_rows == ["Bass"]
    assert dialog.marks_list.count() == 1
    dialog.remove_mark(0)
    assert dialog.marks() == ()


def test_a_bar_the_score_lacks_is_refused_with_the_reason(rig: Rig) -> None:
    rig.ready()
    plan = rig.controller.melody_plan()
    assert plan is not None
    dialog = MelodyDialog(plan, ())
    rig.qtbot.addWidget(dialog)
    assert not dialog.add_mark(VoiceRole.TENOR, 1, 999)
    assert "999" in dialog.problem.text()
    assert dialog.marks() == ()


def test_ok_gives_the_marks_to_the_generation_and_cancel_changes_nothing(rig: Rig) -> None:
    rig.ready()

    def mark(dialog: object) -> bool:
        assert isinstance(dialog, MelodyDialog)
        dialog.add_mark(VoiceRole.TENOR, dialog.lowest, dialog.lowest)
        return True

    rig.window.run_dialog = mark
    rig.window.open_melody()
    assert rig.controller.melody_marks == (MelodyMark(VoiceRole.TENOR, 1, 1),)
    rig.window.run_dialog = lambda dialog: False  # cancel: nothing was marked in it
    rig.window.open_melody()
    assert rig.controller.melody_marks == (MelodyMark(VoiceRole.TENOR, 1, 1),)
    rig.window.generate.click()
    rig.qtbot.waitUntil(lambda: len(rig.pipeline.requests) == 1, timeout=10000)
    assert rig.pipeline.requests[0].melody_marks == (MelodyMark(VoiceRole.TENOR, 1, 1),)


def test_marks_belong_to_one_score(rig: Rig) -> None:
    rig.ready()
    rig.controller.set_melody_marks([MelodyMark(VoiceRole.BASS, 1, 1)])
    rig.load()  # another score is opened
    assert rig.controller.melody_marks == ()


def test_a_mark_reads_plainly() -> None:
    assert mark_text(MelodyMark(VoiceRole.TENOR, 30, 33)) == "Tenor: bars 30 to 33"
    assert mark_text(MelodyMark(VoiceRole.BARITONE, 5, 5)) == "Baritone: bar 5"


def test_a_mark_can_name_beats_and_says_so(rig: Rig) -> None:
    rig.ready()
    plan = rig.controller.melody_plan()
    assert plan is not None
    dialog = MelodyDialog(plan, ())
    rig.qtbot.addWidget(dialog)
    assert dialog.add_mark(VoiceRole.TENOR, 1, 1, 2, 3)
    assert dialog.marks() == (MelodyMark(VoiceRole.TENOR, 1, 1, 2, 3),)
    assert dialog.marks_list.item(0).text() == "Tenor: bar 1 beat 2 to bar 1 beat 3"  # type: ignore[union-attr]
    assert not dialog.add_mark(VoiceRole.TENOR, 1, 1, 9, None)
    assert "beats" in dialog.problem.text()


def test_the_beat_boxes_make_the_mark(rig: Rig) -> None:
    rig.ready()
    plan = rig.controller.melody_plan()
    assert plan is not None
    dialog = MelodyDialog(plan, ())
    rig.qtbot.addWidget(dialog)
    dialog.voice.setCurrentIndex(dialog.voice.findData(VoiceRole.BASS))
    dialog.first.setValue(dialog.lowest)
    dialog.last.setValue(dialog.lowest)
    dialog.first_beat.setValue(2)
    dialog.last_beat.setValue(0)  # the end of the bar
    dialog.add.click()
    assert dialog.marks() == (MelodyMark(VoiceRole.BASS, dialog.lowest, dialog.lowest, 2, None),)


def test_mark_text_names_the_beats() -> None:
    assert mark_text(MelodyMark(VoiceRole.TENOR, 30, 31, 3, 2)) == (
        "Tenor: bar 30 beat 3 to bar 31 beat 2"
    )
    assert (
        mark_text(MelodyMark(VoiceRole.BASS, 5, 5, 2)) == "Bass: bar 5 beat 2 to the end of bar 5"
    )


def test_the_beat_boxes_stop_at_the_beats_of_the_chosen_bar(rig: Rig) -> None:
    rig.ready()
    plan = rig.controller.melody_plan()
    assert plan is not None
    dialog = MelodyDialog(plan, ())
    rig.qtbot.addWidget(dialog)
    for bar in (dialog.lowest, dialog.highest):
        dialog.first.setValue(bar)
        dialog.last.setValue(bar)
        assert dialog.first_beat.maximum() == beats_in_bar(plan, bar)
        assert dialog.last_beat.maximum() == beats_in_bar(plan, bar)
