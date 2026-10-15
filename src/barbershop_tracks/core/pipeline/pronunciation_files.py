"""The pronunciations a person decides, as a file: schema ``blt.pronunciation-overrides/1``.

When the pronunciation dictionary has no entry for a word, BLT stops and names every place the word is
sung. A person then says how each of those places is pronounced; the decisions are written to (and read
from) this file, bound to the score they were made for. The score's own lyrics are never edited::

    {"schema": "blt.pronunciation-overrides/1",
     "source_sha256": "<the score's SHA-256>",
     "overrides": [{"voice": "lead", "start": "3/2", "where": "bar 1, beat 2",
                    "word": "ev'ry", "phonemizer": "OpenUtau.Plugin.Builtin.ArpasingPhonemizer",
                    "notation": "ARPAbet ... for example: eh v r iy",
                    "symbols": "eh v r iy", "approved_by": "A. Singer"}]}

Each entry is one voice at one note: ``voice`` and ``start`` (quarter notes) place it, ``word`` is the
word the engine receives there, ``phonemizer`` the engine whose notation ``symbols`` is written in.
``where`` and ``notation`` are for the reader and are ignored when the file is read. A template entry
whose ``symbols`` is still ``null`` is undecided: it stays a blocked word, nothing is guessed.
``source_sha256`` must be the score's, so decisions for another version of the score are refused;
whether an entry still matches the score (word, voice, engine) is checked when the project is built
(core/synthesis/openutau/overrides.py).
"""

import json
from collections.abc import Mapping, Sequence
from fractions import Fraction
from pathlib import Path
from typing import Any

from barbershop_tracks.core.pipeline.errors import ErrorCategory, PipelineError
from barbershop_tracks.core.synthesis import VOICE_ORDER, SynthesisPlan
from barbershop_tracks.core.synthesis.openutau import (
    ALPHABET_TITLES,
    ALPHABETS,
    OverrideError,
    PronunciationOverride,
    ResolvedOverrides,
    parse_symbols,
)
from barbershop_tracks.core.synthesis.positions import position_label

OVERRIDES_SCHEMA = "blt.pronunciation-overrides/1"
_ROLES = {role.value: role for role in VOICE_ORDER}


def _fail(code: str, message: str) -> PipelineError:
    return PipelineError(ErrorCategory.CONFIGURATION, code, message)


def notation_help(phonemizer: str | None) -> str:
    """How to write the symbols for ``phonemizer``, in a sentence."""
    alphabet = ALPHABETS.get(phonemizer or "")
    if alphabet is None:
        return "this pronunciation engine takes no pronunciations"
    text = ALPHABET_TITLES[alphabet]
    if alphabet != "arpabet":
        text += "; ARPAbet symbols (eh v r iy) are accepted too"
    return text


def overrides_document(
    overrides: Sequence[PronunciationOverride],
    source_sha256: str,
    *,
    where: Mapping[tuple[str, Fraction], str] | None = None,
) -> dict[str, Any]:
    """The overrides file for ``overrides`` (``where`` adds each entry's bar and beat for the reader)."""
    return {
        "schema": OVERRIDES_SCHEMA,
        "source_sha256": source_sha256,
        "overrides": [
            {
                "voice": o.role.value,
                "start": str(o.start),
                **(
                    {"where": where[(o.role.value, o.start)]}
                    if where and (o.role.value, o.start) in where
                    else {}
                ),
                "word": o.word,
                "phonemizer": o.phonemizer,
                "notation": notation_help(o.phonemizer),
                "symbols": o.hint,
                "approved_by": o.approved_by,
            }
            for o in overrides
        ],
    }


def template_document(
    unknown_words: Sequence[Mapping[str, Any]], source_sha256: str
) -> dict[str, Any]:
    """An overrides file with one undecided entry per blocked word and voice.

    ``unknown_words`` is ``details['unknown_words']`` of a ``PRONUNCIATION_UNKNOWN`` error.
    """
    entries: list[dict[str, Any]] = []
    for item in unknown_words:
        if item.get("role") is None or item.get("start") is None or not item.get("phonemizer"):
            continue  # a note BLT could not place cannot be given a pronunciation
        entries.append(
            {
                "voice": item["role"],
                "start": item["start"],
                "where": item.get("where", ""),
                "word": item["lyric"],
                "phonemizer": item["phonemizer"],
                "notation": notation_help(str(item["phonemizer"])),
                "symbols": None,
                "approved_by": None,
            }
        )
    return {"schema": OVERRIDES_SCHEMA, "source_sha256": source_sha256, "overrides": entries}


def _fraction(value: object, where: str) -> Fraction:
    if not isinstance(value, str | int) or isinstance(value, bool):
        raise _fail("OVERRIDES_INVALID", f"{where}: start must be a fraction string like '3/2'")
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError) as error:
        raise _fail("OVERRIDES_INVALID", f"{where}: {value!r} is not a fraction") from error


def read_overrides(path: Path, *, source_sha256: str) -> tuple[PronunciationOverride, ...]:
    """The decided overrides in ``path``; an entry without symbols stays undecided."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise _fail("OVERRIDES_UNREADABLE", f"cannot read {path}: {error}") from error
    except ValueError as error:
        raise _fail("OVERRIDES_INVALID", f"{path} is not valid JSON: {error}") from error
    return overrides_from_document(data, source_sha256=source_sha256, label=str(path))


def overrides_from_document(
    data: object, *, source_sha256: str, label: str = "the pronunciations"
) -> tuple[PronunciationOverride, ...]:
    if not isinstance(data, dict) or data.get("schema") != OVERRIDES_SCHEMA:
        raise _fail("OVERRIDES_INVALID", f"{label} must be a {OVERRIDES_SCHEMA} object")
    if data.get("source_sha256") != source_sha256:
        raise _fail(
            "OVERRIDES_WRONG_SCORE",
            "these pronunciations were decided for a different version of the score "
            f"(expected {source_sha256[:12]}..., {label} says "
            f"{str(data.get('source_sha256'))[:12]}...); decide them again for this score",
        )
    entries = data.get("overrides")
    if not isinstance(entries, list):
        raise _fail("OVERRIDES_INVALID", "'overrides' must be a list")
    found: list[PronunciationOverride] = []
    for index, entry in enumerate(entries):
        where = f"overrides[{index}]"
        if not isinstance(entry, dict):
            raise _fail("OVERRIDES_INVALID", f"{where} must be an object")
        role = _ROLES.get(str(entry.get("voice")))
        if role is None:
            raise _fail("OVERRIDES_INVALID", f"{where}: voice must be one of {sorted(_ROLES)}")
        symbols = entry.get("symbols")
        if symbols is None:
            continue  # undecided: the word stays blocked
        if not isinstance(symbols, str):
            raise _fail("OVERRIDES_INVALID", f"{where}: symbols must be text like 'eh v r iy'")
        word, phonemizer, by = entry.get("word"), entry.get("phonemizer"), entry.get("approved_by")
        if not isinstance(word, str) or not isinstance(phonemizer, str):
            raise _fail("OVERRIDES_INVALID", f"{where}: word and phonemizer must be text")
        if not isinstance(by, str) or not by.strip():
            raise _fail("OVERRIDES_INVALID", f"{where}: approved_by must name who decided")
        try:
            found.append(
                PronunciationOverride(
                    role=role,
                    start=_fraction(entry.get("start"), where),
                    word=word,
                    phonemizer=phonemizer,
                    symbols=parse_symbols(symbols),
                    approved_by=by,
                    source_sha256=source_sha256,
                )
            )
        except OverrideError as error:
            raise _fail(
                error.code.replace("OVERRIDE_", "OVERRIDES_", 1), f"{where}: {error.message}"
            ) from error
    return tuple(found)


def provenance_entries(
    plan: SynthesisPlan, resolved: ResolvedOverrides, host_result: Mapping[str, Any] | None
) -> list[dict[str, Any]]:
    """What the package records about each pronunciation used (score text and decision side by side).

    Every entry keeps the score's own lyric text on the notes of the word, the decision (symbols, who,
    for which engine and score), and the sounds the engine made of it, as the host reported them.
    A word the dictionary lacks that BLT built from dictionary pieces (``blt_composed`` in the host
    result) is an entry too, marked ``"source": "composed"`` with the pieces: no person decided it.
    """
    made: dict[tuple[str, int], list[str]] = {}
    for item in (host_result or {}).get("pronunciations") or []:
        if isinstance(item, Mapping) and isinstance(item.get("position"), int):
            made[(str(item.get("track")), int(item["position"]))] = [
                str(x) for x in item.get("phonemes") or []
            ]
    entries: list[dict[str, Any]] = []
    order = {role: i for i, role in enumerate(VOICE_ORDER)}
    for found in sorted(resolved.all(), key=lambda r: (r.override.start, order[r.override.role])):
        item = found.override
        tick = item.start * 480
        entries.append(
            {
                "voice": item.role.value,
                "start": str(item.start),
                "where": position_label(item.start, plan.meter, plan.measures),
                "word": item.word,
                "score_lyrics": list(found.score_lyrics),
                "phonemizer": item.phonemizer,
                "alphabet": item.alphabet,
                "symbols": item.hint,
                "source": "person",
                "approved_by": item.approved_by,
                "source_sha256": item.source_sha256,
                "scope": "this voice, this note, this word, this pronunciation engine",
                "effective_phonemes": made.get(
                    (item.role.display_name, int(tick)) if tick.denominator == 1 else ("", -1)
                ),
            }
        )
    for built in (host_result or {}).get("blt_composed") or []:
        if not isinstance(built, Mapping):
            continue
        start = Fraction(str(built["start"]))
        role = _ROLES[str(built["voice"])]
        tick = start * 480
        entries.append(
            {
                "voice": role.value,
                "start": str(start),
                "where": position_label(start, plan.meter, plan.measures),
                "word": built["word"],
                "score_lyrics": list(built.get("score_lyrics") or []),
                "phonemizer": built["phonemizer"],
                "alphabet": ALPHABETS[str(built["phonemizer"])],
                "symbols": built["symbols"],
                "source": "composed",
                "composed_from": list(built.get("pieces") or []),
                "composed_how": built.get("how") or "",
                "approved_by": None,
                "source_sha256": built.get("source_sha256"),
                "scope": "this voice, this note, this word, this pronunciation engine",
                "effective_phonemes": made.get(
                    (role.display_name, int(tick)) if tick.denominator == 1 else ("", -1)
                ),
            }
        )
    entries.sort(key=lambda e: (Fraction(e["start"]), order[_ROLES[e["voice"]]]))
    return entries


__all__ = [
    "OVERRIDES_SCHEMA",
    "notation_help",
    "overrides_document",
    "overrides_from_document",
    "provenance_entries",
    "read_overrides",
    "template_document",
]
