"""Small builders for hand-written MusicXML used in parser tests (original, trivial scores)."""

from collections.abc import Sequence
from pathlib import Path

from barbershop_tracks.core.musicxml import ParseResult, parse_musicxml

TREBLE = "<sign>G</sign><line>2</line>"
BASS = "<sign>F</sign><line>4</line>"


def note(
    step: str,
    octave: int,
    duration: int | str,
    *,
    voice: str | None = "1",
    staff: int | None = None,
    alter: str | None = None,
    extra: str = "",
    tie: str = "",
    type_xml: str = "",
    notations: str = "",
) -> str:
    """A pitched note. ``tie`` is placed after ``<duration>``; ``notations`` at the end."""
    alter_xml = f"<alter>{alter}</alter>" if alter is not None else ""
    voice_xml = f"<voice>{voice}</voice>" if voice is not None else ""
    staff_xml = f"<staff>{staff}</staff>" if staff is not None else ""
    notations_xml = f"<notations>{notations}</notations>" if notations else ""
    return (
        f"<note>{extra}<pitch><step>{step}</step>{alter_xml}<octave>{octave}</octave></pitch>"
        f"<duration>{duration}</duration>{tie}{voice_xml}{type_xml}{staff_xml}{notations_xml}</note>"
    )


def tie_xml(*types: str) -> str:
    """``<tie>`` (sound) elements, e.g. ``tie_xml("stop", "start")`` for a chain member."""
    return "".join(f'<tie type="{kind}"/>' for kind in types)


def tied_xml(*types: str) -> str:
    """``<tied>`` (notation) elements for use inside ``notations``."""
    return "".join(f'<tied type="{kind}"/>' for kind in types)


def rest(duration: int | str, *, voice: str | None = "1", staff: int | None = None) -> str:
    voice_xml = f"<voice>{voice}</voice>" if voice is not None else ""
    staff_xml = f"<staff>{staff}</staff>" if staff is not None else ""
    return f"<note><rest/><duration>{duration}</duration>{voice_xml}{staff_xml}</note>"


def backup(duration: int) -> str:
    return f"<backup><duration>{duration}</duration></backup>"


def forward(duration: int) -> str:
    return f"<forward><duration>{duration}</duration></forward>"


def attributes(
    *,
    divisions: str | None = "2",
    time: tuple[int, int] | None = (4, 4),
    clefs: str | None = f"<clef>{TREBLE}</clef>",
    transpose: str = "",
    staves: int | None = None,
) -> str:
    parts = []
    if divisions is not None:
        parts.append(f"<divisions>{divisions}</divisions>")
    if time is not None:
        parts.append(f"<time><beats>{time[0]}</beats><beat-type>{time[1]}</beat-type></time>")
    if staves is not None:
        parts.append(f"<staves>{staves}</staves>")
    if clefs:
        parts.append(clefs)
    parts.append(transpose)
    return f"<attributes>{''.join(parts)}</attributes>"


def measure(number: int | str, body: str, *, attrs: str = "", implicit: bool = False) -> str:
    flag = ' implicit="yes"' if implicit else ""
    return f'<measure number="{number}"{flag}>{attrs}{body}</measure>'


def quarters(*steps: tuple[str, int], voice: str = "1") -> str:
    """Quarter notes at divisions=2 (duration 2 each)."""
    return "".join(note(step, octave, 2, voice=voice) for step, octave in steps)


def transpose_xml(
    *,
    diatonic: int | None = None,
    chromatic: str = "0",
    octave: int | None = None,
    number: int | None = None,
) -> str:
    number_attr = f' number="{number}"' if number is not None else ""
    diatonic_xml = f"<diatonic>{diatonic}</diatonic>" if diatonic is not None else ""
    octave_xml = f"<octave-change>{octave}</octave-change>" if octave is not None else ""
    return (
        f"<transpose{number_attr}>{diatonic_xml}<chromatic>{chromatic}</chromatic>"
        f"{octave_xml}</transpose>"
    )


def score(
    *parts: str,
    names: Sequence[str] | None = None,
    head: str = "",
    version: str = "4.0",
) -> str:
    """A score-partwise document; each ``parts`` item is the measures of one ``<part>``."""
    ids = [f"P{i}" for i in range(1, len(parts) + 1)]
    labels = list(names) if names is not None else ids
    listing = "".join(
        f'<score-part id="{pid}"><part-name>{label}</part-name></score-part>'
        for pid, label in zip(ids, labels, strict=True)
    )
    bodies = "".join(
        f'<part id="{pid}">{body}</part>' for pid, body in zip(ids, parts, strict=True)
    )
    return (
        f'<?xml version="1.0" encoding="UTF-8"?><score-partwise version="{version}">'
        f"{head}<part-list>{listing}</part-list>{bodies}</score-partwise>"
    )


def parse_text(directory: Path, xml: str, name: str = "score.musicxml") -> ParseResult:
    path = directory / name
    path.write_text(xml, encoding="utf-8")
    return parse_musicxml(path)
