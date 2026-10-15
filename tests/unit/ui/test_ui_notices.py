"""A finished run lists what BLT guessed or chose for the person, so it is never a surprise."""

from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from barbershop_tracks.ui.sections import NOTICE_LIMIT, ProgressSection

pytestmark = pytest.mark.gui


def test_a_finished_run_with_no_notices_says_only_where_the_tracks_are(qtbot: QtBot) -> None:
    section = ProgressSection()
    qtbot.addWidget(section)
    section.show_success(Path("out"), 13, ["wav"])
    assert "13 tracks" in section.result_text.text()
    assert "check these by ear" not in section.result_text.text()


def test_notices_are_listed_under_the_result(qtbot: QtBot) -> None:
    section = ProgressSection()
    qtbot.addWidget(section)
    notices = [
        "the voice's sounds are made for EnXSampaPhonemizer, so that engine is used",
        "'cappuci' (bar 1, beat 4; Tenor, Lead) was guessed from its spelling",
    ]
    section.show_success(Path("out"), 13, ["wav"], notices)
    text = section.result_text.text()
    assert "Please check these by ear" in text
    assert "• the voice's sounds are made for EnXSampaPhonemizer" in text
    assert "• 'cappuci' (bar 1, beat 4; Tenor, Lead) was guessed" in text
    assert section.result_title.text().startswith("✔")


def test_a_long_list_is_cut_and_says_how_many_more(qtbot: QtBot) -> None:
    section = ProgressSection()
    qtbot.addWidget(section)
    notices = [f"word {i}" for i in range(NOTICE_LIMIT + 3)]
    section.show_success(Path("out"), 13, ["wav"], notices)
    text = section.result_text.text()
    assert f"word {NOTICE_LIMIT - 1}" in text
    assert f"word {NOTICE_LIMIT}" not in text
    assert "and 3 more" in text
