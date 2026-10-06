"""Literal reading of ``<lyric>`` elements into the source ``Lyric`` model (M3c1).

This module records what the file says and nothing more. It does **not** infer which later
notes belong to a melisma, join syllables into words, choose a verse, fill missing lyrics, or
produce any OpenUtau text. A missing ``<syllabic>`` stays ``UNSPECIFIED``, a missing ``number``
stays ``None``, an untyped ``<extend/>`` stays ``UNTYPED``, and the text is kept verbatim (no
stripping). Structures that cannot be stored without guessing are reported as problems.

MusicXML 4.0 content model: ``(syllabic?, text, (elision?, syllabic?, text)*, extend?) |
extend | laughing | humming``, with "a second ``<syllabic>`` not allowed unless preceded by an
``<elision>``". MuseScore writes an elision differently (see ``MUSESCORE_ELISION_GLYPH``).
"""

import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from barbershop_tracks.models import Lyric, LyricSegment, Melisma, Syllabic

# MuseScore Studio 4.7.4 writes an elision as `<text>a</text><text>U+E551</text><text>b</text>`
# (SMuFL "lyricsElisionNarrow"), for every elision it exports, whatever the source form. Only
# this exact character is recognized; other private-use characters (including U+E550 and
# U+E552, for which there is no MuseScore evidence) are NOT treated as elisions.
MUSESCORE_ELISION_GLYPH = chr(0xE551)

WARNING_CODES = frozenset({"LYRIC_EMPTY"})
_PREVIEW_LIMIT = 60
_SYLLABIC = {s.value: s for s in Syllabic if s is not Syllabic.UNSPECIFIED}
_EXTEND_TYPES = {"start": Melisma.START, "continue": Melisma.CONTINUE, "stop": Melisma.STOP}


@dataclass(frozen=True, slots=True)
class LyricProblem:
    """Something about a lyric that was reported instead of guessed."""

    code: str
    message: str

    @property
    def is_warning(self) -> bool:
        return self.code in WARNING_CODES


@dataclass(frozen=True, slots=True)
class LyricRead:
    lyrics: tuple[Lyric, ...]
    problems: tuple[LyricProblem, ...]


@dataclass(frozen=True, slots=True)
class _Piece:
    syllabic: Syllabic
    text: str
    joiner: str = ""
    joiner_smufl: str | None = None


def has_lyrics(note: ET.Element) -> bool:
    return note.find("lyric") is not None


def read_lyrics(note: ET.Element) -> LyricRead:
    """Read every ``<lyric>`` of ``note`` in document order (see the module docstring)."""
    lyrics: list[Lyric] = []
    problems: list[LyricProblem] = []
    for element in note.findall("lyric"):
        lyric = _read_one(element, problems)
        if lyric is not None:
            lyrics.append(lyric)
    problems.extend(_duplicate_verse_problems(lyrics))
    return LyricRead(lyrics=tuple(lyrics), problems=tuple(problems))


def describe_lyrics(note: ET.Element) -> str:
    """A short literal description of the lyrics on ``note``, for diagnostics."""
    parts: list[str] = []
    for element in note.findall("lyric"):
        texts = [(t.text or "") for t in element.findall("text")]
        if texts:
            shown = "".join(texts)
        elif element.find("humming") is not None:
            shown = "<humming/>"
        elif element.find("laughing") is not None:
            shown = "<laughing/>"
        elif element.find("extend") is not None:
            shown = "<extend/>"
        else:
            shown = ""
        if len(shown) > _PREVIEW_LIMIT:
            shown = shown[: _PREVIEW_LIMIT - 3] + "..."
        number = element.get("number")
        parts.append(f"{shown!r}" + (f" (verse {number})" if number is not None else ""))
    return ", ".join(parts)


# --- one <lyric> -----------------------------------------------------------------------


def _read_one(element: ET.Element, problems: list[LyricProblem]) -> Lyric | None:
    verse = element.get("number")
    if verse == "":
        problems.append(LyricProblem("LYRIC_NUMBER_INVALID", "a <lyric> has an empty number"))
        verse = None
    name = element.get("name")
    time_only = element.get("time-only")
    if time_only is not None:
        problems.append(
            LyricProblem(
                "LYRIC_TIME_ONLY_UNSUPPORTED",
                f"a <lyric> has time-only={time_only!r}, which makes it depend on the repeat "
                "pass and is not supported",
            )
        )

    voices = [c.tag for c in element if c.tag in ("humming", "laughing")]
    if voices:
        others = [c for c in element if c.tag in ("text", "syllabic", "elision", "extend")]
        if len(voices) > 1 or others:
            _unsupported(problems, "humming/laughing mixed with other lyric content")
            return None
        factory = Lyric.humming if voices[0] == "humming" else Lyric.laughing
        return factory(verse=verse, name=name, time_only=time_only)

    extends = element.findall("extend")
    if len(extends) > 1:
        _unsupported(problems, "more than one <extend>")
        return None
    melisma = Melisma.NONE
    if extends:
        parsed = _extend_form(extends[0], problems)
        if parsed is None:
            return None
        melisma = parsed

    texts = element.findall("text")
    if not texts or (len(texts) == 1 and not (texts[0].text or "")):
        if melisma is not Melisma.NONE:
            return Lyric.extension(melisma, verse=verse, name=name, time_only=time_only)
        problems.append(LyricProblem("LYRIC_EMPTY", "a <lyric> has no text and was skipped"))
        return None

    pieces = _pieces(element, texts, problems)
    if pieces is None:
        return None
    first, rest = pieces[0], pieces[1:]
    return Lyric(
        text=first.text,
        syllabic=first.syllabic,
        melisma=melisma,
        elided=tuple(
            LyricSegment(
                text=p.text, syllabic=p.syllabic, joiner=p.joiner, joiner_smufl=p.joiner_smufl
            )
            for p in rest
        ),
        verse=verse,
        name=name,
        time_only=time_only,
    )


def _unsupported(problems: list[LyricProblem], why: str) -> None:
    problems.append(
        LyricProblem("LYRIC_TEXT_STRUCTURE_UNSUPPORTED", f"unsupported lyric structure: {why}")
    )


def _extend_form(extend: ET.Element, problems: list[LyricProblem]) -> Melisma | None:
    kind = extend.get("type")
    if kind is None:
        return Melisma.UNTYPED
    form = _EXTEND_TYPES.get(kind)
    if form is None:
        problems.append(
            LyricProblem(
                "LYRIC_EXTEND_TYPE_INVALID",
                f"<extend> has type {kind!r}; only start, continue and stop are valid",
            )
        )
    return form


# --- text, syllabic and elision pieces ------------------------------------------------


def _pieces(
    element: ET.Element, texts: Sequence[ET.Element], problems: list[LyricProblem]
) -> list[_Piece] | None:
    if element.find("elision") is None:
        if len(texts) == 1:
            return _single(element, texts[0], problems)
        return _musescore_pieces(element, texts, problems)
    return _standard_pieces(element, problems)


def _single(
    element: ET.Element, text: ET.Element, problems: list[LyricProblem]
) -> list[_Piece] | None:
    syllabics = element.findall("syllabic")
    if len(syllabics) > 1:
        _unsupported(problems, "a second <syllabic> without an <elision>")
        return None
    value = Syllabic.UNSPECIFIED
    if syllabics:
        parsed = _syllabic_value(syllabics[0], problems)
        if parsed is None:
            return None
        value = parsed
    return [_Piece(value, text.text or "")]


def _syllabic_value(element: ET.Element, problems: list[LyricProblem]) -> Syllabic | None:
    value = _SYLLABIC.get((element.text or "").strip())
    if value is None:
        _unsupported(problems, f"<syllabic> value {element.text!r} is not single/begin/middle/end")
    return value


def _standard_pieces(element: ET.Element, problems: list[LyricProblem]) -> list[_Piece] | None:
    """MusicXML sequence: [syllabic] text {elision [syllabic] text}."""
    pieces: list[_Piece] = []
    syllabic: Syllabic | None = None
    joiner: tuple[str, str | None] | None = None
    phase = "start"  # start | after_elision | after_text
    for child in element:
        tag = child.tag
        if tag == "syllabic":
            if phase == "after_text" or syllabic is not None:
                _unsupported(problems, "a <syllabic> that does not start a syllable")
                return None
            syllabic = _syllabic_value(child, problems)
            if syllabic is None:
                return None
        elif tag == "elision":
            if phase != "after_text":
                _unsupported(problems, "an <elision> that does not follow a <text>")
                return None
            joiner = (child.text or "", child.get("smufl"))
            phase = "after_elision"
        elif tag == "text":
            if phase == "after_text":
                _unsupported(problems, "consecutive <text> elements without an <elision>")
                return None
            text = child.text or ""
            if not text:
                _unsupported(problems, "an empty <text> among several syllables")
                return None
            pieces.append(
                _Piece(
                    syllabic or Syllabic.UNSPECIFIED,
                    text,
                    joiner[0] if joiner else "",
                    joiner[1] if joiner else None,
                )
            )
            syllabic, joiner, phase = None, None, "after_text"
    if phase != "after_text":
        _unsupported(problems, "an <elision> with no <text> after it")
        return None
    return pieces


def _musescore_pieces(
    element: ET.Element, texts: Sequence[ET.Element], problems: list[LyricProblem]
) -> list[_Piece] | None:
    """MuseScore's pattern: ``t0, GLYPH, t1, GLYPH, t2`` and nothing else (deterministic)."""
    values = [t.text or "" for t in texts]
    syllabics = element.findall("syllabic")
    is_pattern = (
        len(values) % 2 == 1
        and len(syllabics) <= 1
        and all(v == MUSESCORE_ELISION_GLYPH for v in values[1::2])
        and all(v and v != MUSESCORE_ELISION_GLYPH for v in values[0::2])
    )
    if not is_pattern:
        _unsupported(
            problems,
            f"{len(values)} <text> elements that do not match a known elision pattern",
        )
        return None
    first = Syllabic.UNSPECIFIED
    if syllabics:
        parsed = _syllabic_value(syllabics[0], problems)
        if parsed is None:
            return None
        first = parsed
    pieces = [_Piece(first, values[0])]
    pieces += [_Piece(Syllabic.UNSPECIFIED, v, MUSESCORE_ELISION_GLYPH) for v in values[2::2]]
    return pieces


# --- duplicates ------------------------------------------------------------------------


def _duplicate_verse_problems(lyrics: Sequence[Lyric]) -> list[LyricProblem]:
    """Two lyrics in the same logical verse on one note: nothing may choose between them."""
    counts = Counter(lyric.logical_verse for lyric in lyrics)
    problems: list[LyricProblem] = []
    for verse, count in counts.items():
        if count > 1:
            texts = ", ".join(
                repr(_label(lyric)) for lyric in lyrics if lyric.logical_verse == verse
            )
            problems.append(
                LyricProblem(
                    "LYRIC_DUPLICATE_VERSE",
                    f"{count} lyrics in verse {verse!r} are on one note ({texts}); none is chosen",
                )
            )
    return problems


def _label(lyric: Lyric) -> str:
    if lyric.has_text:
        return lyric.full_text
    return f"<{lyric.kind.value}>"
