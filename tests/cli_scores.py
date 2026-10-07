"""Synthetic MusicXML quartet scores for the CLI tests (original, trivial; written to tmp_path)."""

from pathlib import Path

from xml_builders import attributes, lyric_xml, measure, note, score, syl, tempo_direction, text

NAMES = ["Tenor", "Lead", "Baritone", "Bass"]
LINES = {name.lower(): f"P{i}/s1/v1" for i, name in enumerate(NAMES, start=1)}
STEPS = ["E", "C", "G", "C"]
OCTAVES = [4, 4, 3, 3]


def _part(
    index: int,
    *,
    tempo: bool,
    lyrics: bool,
    chord: bool,
    partial_lyrics: bool,
    measures: int,
) -> str:
    body = ""
    for number in range(1, measures + 1):
        content = ""
        if number == 1 and index == 0 and tempo:
            content += tempo_direction("100")
        for beat in range(4):
            lyric = ""
            if lyrics and not (partial_lyrics and number == 2 and beat >= 2):
                lyric = lyric_xml(syl("single"), text("la"))
            content += note(STEPS[index], OCTAVES[index], 2, lyrics=lyric)
            if chord and number == 1 and beat == 0:
                content += note("D", OCTAVES[index], 2, extra="<chord/>")
        body += measure(number, content, attrs=attributes() if number == 1 else "")
    return body


def quartet_xml(
    *,
    tempo: bool = True,
    lyric_part: int | None = 1,
    chord_in: int | None = None,
    partial_lyrics: bool = False,
    measures: int = 2,
    names: bool = True,
) -> str:
    """Four one-voice parts (Tenor, Lead, Baritone, Bass) of eight quarter notes each.

    ``lyric_part`` is the index of the part that carries lyrics (``None``: nobody); ``chord_in``
    adds a chord to that part's first note; ``partial_lyrics`` leaves the last two notes of the
    lyric part without a lyric.
    """
    parts = [
        _part(
            i,
            tempo=tempo,
            lyrics=i == lyric_part,
            chord=i == chord_in,
            partial_lyrics=partial_lyrics,
            measures=measures,
        )
        for i in range(4)
    ]
    return score(*parts, names=NAMES if names else None)


def write_quartet(directory: Path, name: str = "quartet.musicxml", **options: object) -> Path:
    path = directory / name
    path.write_text(quartet_xml(**options), encoding="utf-8")  # type: ignore[arg-type]
    return path
