"""How far a held syllable's line runs, read from a MuseScore project."""

import zipfile
from fractions import Fraction
from pathlib import Path

from barbershop_tracks.core.musicxml.mscx_lyrics import ProjectLyric, read_project_lyrics


def chord(
    text: str, *, ticks_f: str | None = None, ticks: int | None = None, verse: int | None = None
) -> str:
    extra = ""
    if ticks_f is not None:
        extra += f"<ticks_f>{ticks_f}</ticks_f>"
    if ticks is not None:
        extra += f"<ticks>{ticks}</ticks>"
    if verse is not None:
        extra += f"<no>{verse}</no>"
    return (
        "<Chord><durationType>quarter</durationType>"
        f"<Lyrics>{extra}<text>{text}</text></Lyrics></Chord>"
    )


def score(*staves: str) -> str:
    listing = "".join(f'<Part><Staff id="{i}"/></Part>' for i in range(1, len(staves) + 1))
    music = "".join(f'<Staff id="{i}">{body}</Staff>' for i, body in enumerate(staves, start=1))
    head = '<?xml version="1.0"?><museScore version="4.40"><Score>'
    return f"{head}{listing}{music}</Score></museScore>"


def measure(*voices: str) -> str:
    return "<Measure>" + "".join(f"<voice>{v}</voice>" for v in voices) + "</Measure>"


def project(tmp_path: Path, xml: str, name: str = "Hymn.mscz") -> Path:
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Hymn.mscx", xml)
        archive.writestr("META-INF/container.xml", "<container/>")
    return path


def test_a_lines_length_is_in_quarter_notes_from_its_note(tmp_path: Path) -> None:
    xml = score(measure(chord("doo", ticks_f="9/8") + chord("so")))
    assert read_project_lyrics(project(tmp_path, xml)) == {
        1: [[ProjectLyric("doo", Fraction(9, 2)), ProjectLyric("so", None)]]
    }


def test_the_older_length_in_ticks_is_read_too(tmp_path: Path) -> None:
    xml = score(measure(chord("loo", ticks=960)))
    assert read_project_lyrics(project(tmp_path, xml))[1][0][0].line == 2


def test_voices_and_staves_are_kept_apart_in_the_order_they_are_written(tmp_path: Path) -> None:
    upper = measure(chord("ooh", ticks_f="3/4") + chord("sing"), chord("What") + chord("child"))
    lower = measure(chord("doo", ticks_f="1/2"))
    found = read_project_lyrics(project(tmp_path, score(upper, lower)))
    assert [[x.text for x in v] for v in found[1]] == [["ooh", "sing"], ["What", "child"]]
    assert [[x.text for x in v] for v in found[2]] == [["doo"]]


def test_a_voice_keeps_one_list_across_its_measures(tmp_path: Path) -> None:
    body = measure(chord("one")) + measure(chord("two")) + measure(chord("three"))
    found = read_project_lyrics(project(tmp_path, score(body)))
    assert [x.text for x in found[1][0]] == ["one", "two", "three"]


def test_only_the_first_verse_is_read(tmp_path: Path) -> None:
    body = measure(chord("one") + chord("second", verse=1) + chord("two", verse=0))
    found = read_project_lyrics(project(tmp_path, score(body)))
    assert [x.text for x in found[1][0]] == ["one", "two"]


def test_a_plain_mscx_file_is_read_as_it_is(tmp_path: Path) -> None:
    path = tmp_path / "Hymn.mscx"
    path.write_text(score(measure(chord("doo", ticks_f="1/4"))), encoding="utf-8")
    assert read_project_lyrics(path)[1][0][0].line == 1


def test_a_project_that_cannot_be_read_gives_nothing(tmp_path: Path) -> None:
    broken = tmp_path / "broken.mscz"
    broken.write_bytes(b"not a zip file")
    assert read_project_lyrics(broken) == {}
    assert read_project_lyrics(tmp_path / "missing.mscz") == {}
    two = tmp_path / "two.mscz"
    with zipfile.ZipFile(two, "w") as archive:
        archive.writestr("a.mscx", score())
        archive.writestr("b.mscx", score())
    assert read_project_lyrics(two) == {}
    hostile = project(
        tmp_path, '<!DOCTYPE x [<!ENTITY a "b">]><museScore>&a;</museScore>', "x.mscz"
    )
    assert read_project_lyrics(hostile) == {}
