"""Write the English pronunciation acceptance scores (docs/acceptance/fixtures/) from one definition.

    python scripts/build_english_acceptance_fixture.py [--out docs/acceptance/fixtures] [--check]

One short original tune (8 bars, 4/4, 88 BPM, written at sounding pitch; the harmony is parallel thirds and
octaves around the melody: a TEST PATTERN for pitch, rhythm, synchronisation and words, not an arrangement) in
three versions that differ only in a few words:

* ``known``      every word is in the CMU pronunciation dictionary: it must generate;
* ``unknown``    the same tune with words that are NOT in the dictionary (``lov'd``, ``ev'ryone``, ``'neath``,
                 ``o'er`` in the Lead's lyrics, which the other three parts follow, and ``mammy`` in the Bass's
                 own words): BLT must stop before rendering and name each word, voice and bar;
* ``respelled``  the unknown words written with words the dictionary knows (``loved``, ``everyone``,
                 ``beneath``, ``over``, ``mommy``): it must generate.

The tune covers ordinary words, contractions (``don't``, ``we'll``, ``I'm``, ``ne'er``), a leading apostrophe
(``'cause``, ``'round``), words of two and three syllables spread over notes (``together``, ``always``), a
melisma (``sing`` over three notes), sustained notes (a half note and a whole note) and the Bass's own words
(``dum``). ``english-quartet.words.json`` lists every word with its place and its expected behaviour; the
integration tests compare that list with the real dictionary, so the fixture cannot drift from what it claims.

``english-quartet-unknown-words.pronunciations-<engine>.json`` are SAMPLE pronunciations of the five words the
dictionary lacks, in the notation of CMUdict (ARPAbet), one file per pronunciation engine and bound to the SHA-256 of
the ``unknown`` score: loading one makes that score generate without a single word of it being changed.

Everything here is original (the melody, the words) and may be used, copied and changed freely (CC0). With
``--check`` nothing is written: the script exits 1 if the committed files differ from what it would write.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tests"))

from xml_builders import (  # noqa: E402
    BASS,
    TREBLE,
    attributes,
    extend,
    lyric_xml,
    measure,
    note,
    score,
    syl,
    tempo_direction,
    text,
)

TEMPO = "88"
STEPS = {
    0: ("C", None),
    2: ("D", None),
    4: ("E", None),
    5: ("F", None),
    7: ("G", None),
    9: ("A", None),
    11: ("B", None),
}
NAMES = ["Tenor", "Lead", "Baritone", "Bass"]
THIRD_ABOVE = {0: 4, 2: 3, 4: 3, 5: 4, 7: 4, 9: 3, 11: 3}  # diatonic thirds in C major
THIRD_BELOW = {0: 3, 2: 3, 4: 4, 5: 3, 7: 3, 9: 4, 11: 4}


@dataclass(frozen=True)
class Syl:
    """One sung syllable of the Lead: its text, its place in the word, how many quarter notes it lasts."""

    text: str
    kind: str  # single / begin / middle / end
    pitches: tuple[int, ...]  # one MIDI pitch per note; more than one makes a melisma
    quarters: tuple[int, ...]  # the length of each of those notes, in quarter notes


def s(text: str, kind: str, pitch: int, q: int = 1) -> Syl:
    return Syl(text, kind, (pitch,), (q,))


def mel(text: str, pitches: tuple[int, ...]) -> Syl:
    return Syl(text, "single", pitches, (1,) * len(pitches))


C4, D4, E4, F4, G4, A4, B4, C5 = 60, 62, 64, 65, 67, 69, 71, 72


def lead_line(version: str) -> list[list[Syl]]:
    """The Lead's eight bars; the three versions differ only where the words differ."""
    unknown, respelled = version == "unknown", version == "respelled"
    first = "lov'd" if unknown else ("loved" if respelled else "Love")
    bars: list[list[Syl]] = [
        [
            s(first, "single", C4),
            s("is", "single", E4),
            s("a", "single", G4),
            s("song", "single", G4),
        ],
        [s("we", "single", A4), mel("sing", (G4, F4, E4))],
        [s("to", "begin", E4), s("geth", "middle", F4), s("er", "end", G4, 2)],
    ]
    if unknown:
        bars.append([s("ev'", "begin", G4), s("ry", "middle", A4), s("one", "end", G4, 2)])
    elif respelled:
        bars.append([s("ev", "begin", G4), s("ery", "middle", A4), s("one", "end", G4, 2)])
    else:
        bars.append([s("don't", "single", G4), s("you", "single", A4), s("know", "single", G4, 2)])
    bars.append(
        [
            s("'cause", "single", E4),
            s("we'll", "single", E4),
            s("al", "begin", D4),
            s("ways", "end", C4),
        ]
    )
    if unknown:
        bars.append([s("I'm", "single", G4), s("here", "single", G4), s("'neath", "single", A4, 2)])
    elif respelled:
        bars.append(
            [
                s("I'm", "single", G4),
                s("here", "single", G4),
                s("be", "begin", A4),
                s("neath", "end", A4),
            ]
        )
    else:
        bars.append([s("I'm", "single", G4), s("here", "single", G4), s("'round", "single", A4, 2)])
    if unknown:
        bars.append(
            [
                s("o'er", "single", C5),
                s("mind", "single", B4),
                s("the", "single", A4),
                s("heart", "single", G4),
            ]
        )
    elif respelled:
        bars.append(
            [
                s("o", "begin", C5),
                s("ver", "end", B4),
                s("the", "single", A4),
                s("heart", "single", G4),
            ]
        )
    else:
        bars.append(
            [
                s("ne'er", "single", C5),
                s("mind", "single", B4),
                s("the", "single", A4),
                s("heart", "single", G4),
            ]
        )
    bars.append([s("home", "single", C5, 4)])
    return bars


def bass_words(version: str) -> list[str]:
    """The Bass's own words in bar 2 (the other parts follow the Lead)."""
    last = "mammy" if version == "unknown" else ("mommy" if version == "respelled" else "dum")
    return ["dum", "dum", "dum", last]


def pitch_xml(midi: int) -> tuple[str, int]:
    octave, pc = divmod(midi, 12)
    step, _ = STEPS[pc]
    return step, octave - 1


def note_xml(midi: int, quarters: int, lyrics: str = "", notations: str = "") -> str:
    step, octave = pitch_xml(midi)
    return note(step, octave, 2 * quarters, lyrics=lyrics, notations=notations)


def lead_notes(bars: list[list[Syl]]) -> list[list[tuple[int, int, str, str]]]:
    """Per bar: (midi, quarters, lyric xml, notations xml) for every note of the Lead."""
    out: list[list[tuple[int, int, str, str]]] = []
    for bar in bars:
        row: list[tuple[int, int, str, str]] = []
        for syllable in bar:
            many = len(syllable.pitches) > 1
            for k, (pitch, quarters) in enumerate(
                zip(syllable.pitches, syllable.quarters, strict=True)
            ):
                lyrics, notations = "", ""
                if k == 0:
                    parts = [syl(syllable.kind), text(syllable.text)]
                    if many:
                        parts.append(extend())
                    lyrics = lyric_xml(*parts)
                if many and k == 0:
                    notations = '<slur type="start" number="1"/>'
                if many and k == len(syllable.pitches) - 1:
                    notations = '<slur type="stop" number="1"/>'
                row.append((pitch, quarters, lyrics, notations))
        out.append(row)
    return out


def build(version: str) -> str:
    bars = lead_line(version)
    lead = lead_notes(bars)
    parts: list[str] = []
    for index, name in enumerate(NAMES):
        body = ""
        for number, row in enumerate(lead, start=1):
            content = ""
            if number == 1 and index == 0:
                content += tempo_direction(TEMPO)
            for k, (midi, quarters, lyrics, notations) in enumerate(row):
                if name == "Lead":
                    content += note_xml(midi, quarters, lyrics, notations)
                    continue
                pc = midi % 12
                if name == "Tenor":
                    pitch = midi + THIRD_ABOVE[pc]
                elif name == "Baritone":
                    pitch = midi - THIRD_BELOW[pc]
                else:
                    pitch = midi - 12
                own = ""
                if name == "Bass" and number == 2:
                    own = lyric_xml(syl("single"), text(bass_words(version)[k]))
                    quarters = 1
                content += note_xml(pitch, quarters, own)
            clef = BASS if name == "Bass" else TREBLE
            body += measure(
                number,
                content,
                attrs=attributes(clefs=f"<clef>{clef}</clef>") if number == 1 else "",
            )
        parts.append(body)
    head = (
        f"<work><work-title>BLT English pronunciation test pattern ({version} words)"
        "</work-title></work>"
    )
    return score(*parts, names=NAMES, head=head)


# whole words that are NOT in the CMU dictionary (checked against the real dictionary by the tests)
OUTSIDE_THE_DICTIONARY = {"lov'd", "ev'ryone", "'neath", "o'er", "mammy"}


def words_manifest() -> dict[str, object]:
    """Every word of every version with its place and expected behaviour."""
    versions: dict[str, object] = {}
    for version in ("known", "unknown", "respelled"):
        entries: list[dict[str, object]] = []
        for number, bar in enumerate(lead_line(version), start=1):
            beat = 0
            word, word_beat = "", 0
            for syllable in bar:
                if not word:
                    word_beat = beat
                word += syllable.text
                if syllable.kind in ("single", "end"):
                    entries.append(
                        {
                            "word": word,
                            "sung_by": "Lead, followed by Tenor, Baritone and Bass",
                            "where": f"bar {number}, beat {word_beat + 1}",
                            "in_dictionary": word.lower() not in OUTSIDE_THE_DICTIONARY,
                        }
                    )
                    word = ""
                beat += sum(syllable.quarters)
        words = bass_words(version)
        entries.append(
            {
                "word": words[3],
                "sung_by": "Bass only (its own words)",
                "where": "bar 2, beat 4",
                "in_dictionary": words[3].lower() not in OUTSIDE_THE_DICTIONARY,
            }
        )
        versions[version] = {
            "expected": (
                "BLT stops before rendering and names every word with in_dictionary false, with its voices and bar"
                if version == "unknown"
                else "generates 13 tracks"
            ),
            "words": entries,
        }
    return {"tempo_bpm": int(TEMPO), "meter": "4/4", "bars": 8, "versions": versions}


# how each word the dictionary lacks is pronounced in the sample pronunciations (ARPAbet, the notation of the
# CMU dictionary: lower case, no stress digits). The three engines take ARPAbet.
SAMPLE_SYMBOLS = {
    "lov'd": "l ah v d",
    "ev'ryone": "eh v r iy w ah n",
    "'neath": "n iy th",
    "o'er": "ow er",
    "mammy": "m ae m iy",
}
ENGINES = {
    "arpasing": "OpenUtau.Plugin.Builtin.ArpasingPhonemizer",
    "vccv": "OpenUtau.Plugin.Builtin.EnglishVCCVPhonemizer",
    "xsampa": "OpenUtau.Plugin.Builtin.EnXSampaPhonemizer",
}
SAMPLE_APPROVER = "REPLACE WITH YOUR NAME (a sample decision, not a person's)"


def unknown_places() -> list[tuple[str, int, str, tuple[str, ...]]]:
    """(word, start in quarter notes, where, voices) for every word of the ``unknown`` version the dictionary lacks."""
    places: list[tuple[str, int, str, tuple[str, ...]]] = []
    for number, bar in enumerate(lead_line("unknown"), start=1):
        beat, word, word_beat = 0, "", 0
        for syllable in bar:
            if not word:
                word_beat = beat
            word += syllable.text
            if syllable.kind in ("single", "end"):
                if word.lower() in OUTSIDE_THE_DICTIONARY:
                    places.append(
                        (
                            word,
                            (number - 1) * 4 + word_beat,
                            f"bar {number}, beat {word_beat + 1}",
                            ("tenor", "lead", "baritone", "bass"),
                        )
                    )
                word = ""
            beat += sum(syllable.quarters)
    own = bass_words("unknown")[3]
    if own.lower() in OUTSIDE_THE_DICTIONARY:
        places.append((own, 4 + 3, "bar 2, beat 4", ("bass",)))
    return sorted(places, key=lambda place: place[1])


def pronunciation_file(engine: str, score_text: str) -> str:
    """The sample pronunciations of the ``unknown`` score for one engine: one entry per voice and place.

    Bound to the SHA-256 of that score as written here (the file has no line breaks, so the digest is the same
    on every machine). It decides exactly the five places the dictionary lacks; BLT refuses it for any other score.
    """
    entries = []
    for word, start, where, voices in unknown_places():
        for voice in voices:
            entries.append(
                {
                    "voice": voice,
                    "start": str(start),
                    "where": where,
                    "word": word,
                    "phonemizer": ENGINES[engine],
                    "notation": "ARPAbet (the notation of the CMU dictionary), lower case, for example: eh v r iy",
                    "symbols": SAMPLE_SYMBOLS[word],
                    "approved_by": SAMPLE_APPROVER,
                }
            )
    document = {
        "schema": "blt.pronunciation-overrides/1",
        "source_sha256": hashlib.sha256(score_text.encode("utf-8")).hexdigest(),
        "overrides": entries,
    }
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def render() -> dict[str, str]:
    files = {
        f"english-quartet-{v}-words.musicxml": build(v) for v in ("known", "unknown", "respelled")
    }
    manifest = words_manifest()
    files["english-quartet.words.json"] = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    unknown = files["english-quartet-unknown-words.musicxml"]
    for engine in ENGINES:
        files[f"english-quartet-unknown-words.pronunciations-{engine}.json"] = pronunciation_file(
            engine, unknown
        )
    return files


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=REPO / "docs" / "acceptance" / "fixtures")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    files = render()
    if args.check:
        stale = [
            n
            for n, t in files.items()
            if not (args.out / n).is_file()
            or (args.out / n).read_text(encoding="utf-8").replace("\r\n", "\n") != t
        ]
        for name in stale:
            print(f"out of date: {name}")
        return 1 if stale else 0
    args.out.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (args.out / name).write_text(content, encoding="utf-8", newline="\n")
        print(f"wrote {args.out / name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
