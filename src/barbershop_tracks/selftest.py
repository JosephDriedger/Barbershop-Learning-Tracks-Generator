"""Installation self-test: generate the 13 tracks from a built-in score with a built-in voicebank.

``blt selftest`` exercises exactly what a user's generation uses (the installed render host, the
per-user runtime copy, staging, validation, mixing, publication) without needing any score or
voicebank of theirs. The "voicebank" is a few generated sine waves (``build_voicebank``): it proves
that the installation works, and says nothing about how real voices sound. The same generator backs
the test suite.
"""

import hashlib
import json
import math
import struct
import tempfile
import wave
from collections.abc import Callable
from pathlib import Path

SINGER_ID = "blt-synthetic"
ALIASES = ("la", "ba")
SAMPLE_RATE = 44100
_PARTS = (("Tenor", "E", 4), ("Lead", "C", 4), ("Baritone", "G", 3), ("Bass", "C", 3))
LINES = {name.lower(): f"P{i}/s1/v1" for i, (name, _, _) in enumerate(_PARTS, start=1)}


def _sine(path: Path, frequency: float, seconds: float = 1.0) -> None:
    frames = int(SAMPLE_RATE * seconds)
    fade = int(SAMPLE_RATE * 0.02)
    samples = []
    for i in range(frames):
        envelope = min(1.0, i / fade, (frames - i) / fade)
        samples.append(int(12000 * envelope * math.sin(2 * math.pi * frequency * i / SAMPLE_RATE)))
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        out.writeframes(struct.pack(f"<{len(samples)}h", *samples))


def build_voicebank(singers_dir: Path) -> Path:
    """Create ``<singers_dir>/blt-synthetic``: sine "syllables" for the aliases in ALIASES only."""
    folder = singers_dir / SINGER_ID
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "character.txt").write_text("name=BLT Synthetic\n", encoding="utf-8")
    lines = []
    for index, alias in enumerate(ALIASES):
        _sine(folder / f"{alias}.wav", 220.0 + 20 * index)
        lines.append(f"{alias}.wav={alias},0,200,-300,50,50")
    (folder / "oto.ini").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return folder


def selftest_score(word: str = "la", measures: int = 2) -> str:
    """A tiny four-part MusicXML score (original, trivial): every note sung to ``word``."""
    parts = []
    for index, (_, step, octave) in enumerate(_PARTS, start=1):
        body = []
        for number in range(1, measures + 1):
            content = ""
            if number == 1:
                content += (
                    "<attributes><divisions>1</divisions><time><beats>4</beats>"
                    "<beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef>"
                    "</attributes>"
                )
                if index == 1:
                    content += (
                        "<direction><direction-type></direction-type>"
                        '<sound tempo="100"/></direction>'
                    )
            for _ in range(4):
                content += (
                    f"<note><pitch><step>{step}</step><octave>{octave}</octave></pitch>"
                    '<duration>1</duration><voice>1</voice><lyric number="1"><syllabic>single'
                    f"</syllabic><text>{word}</text></lyric></note>"
                )
            body.append(f'<measure number="{number}">{content}</measure>')
        parts.append(f'<part id="P{index}">{"".join(body)}</part>')
    names = "".join(
        f'<score-part id="P{i}"><part-name>{name}</part-name></score-part>'
        for i, (name, _, _) in enumerate(_PARTS, start=1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?><score-partwise version="4.0">'
        f"<part-list>{names}</part-list>{''.join(parts)}</score-partwise>"
    )


def run_selftest(
    report: Callable[[str], None],
    *,
    work_dir: Path | None = None,
    data_dir: Path | None = None,
    host_dir: Path | None = None,
) -> int:
    """Run the whole pipeline on the built-in score; returns 0 if every check passed."""
    from barbershop_tracks.core.pipeline import (
        EngineChoice,
        GenerateRequest,
        PipelineError,
        config_path,
        generate,
        load_config_file,
        resolve_config,
    )
    from barbershop_tracks.core.readiness import RoleAssignments
    from barbershop_tracks.core.rendering.wav import inspect_file
    from barbershop_tracks.models import VoiceRole

    with tempfile.TemporaryDirectory(prefix="blt-selftest-") as scratch:
        root = work_dir or Path(scratch)
        root.mkdir(parents=True, exist_ok=True)
        singers = root / "voices"
        build_voicebank(singers)
        score = root / "selftest.musicxml"
        score.write_text(selftest_score(), encoding="utf-8")
        config = resolve_config(
            load_config_file(config_path()),
            overrides={
                "singers_dir": str(singers),
                "host_dir": str(host_dir) if host_dir else None,
                "data_dir": str(data_dir) if data_dir else None,
            },
        )
        report(f"host:     {config.host_binaries}")
        report(f"data:     {config.layout.data}")
        request = GenerateRequest(
            score=score,
            output=root / "out",
            assignments=RoleAssignments.of(
                {
                    VoiceRole.TENOR: LINES["tenor"],
                    VoiceRole.LEAD: LINES["lead"],
                    VoiceRole.BARITONE: LINES["baritone"],
                    VoiceRole.BASS: LINES["bass"],
                }
            ),
            engine=EngineChoice(SINGER_ID, config.phonemizer, config.renderer),
        )
        try:
            result = generate(request, config)
        except PipelineError as error:
            report(f"FAILED [{error.code}] {error.message}")
            return 1
        folder = result.destination
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        problems: list[str] = []
        wavs = sorted(folder.glob("*.wav"))
        if len(wavs) != 13:
            problems.append(f"expected 13 WAV files, found {len(wavs)}")
        frames = manifest["audio"]["frames"]
        for track in manifest["tracks"]:
            for entry in track["files"]:
                path = folder / entry["name"]
                if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
                    problems.append(f"{entry['name']}: checksum differs from the manifest")
                info, _ = inspect_file(path)
                if info.frames != frames:
                    problems.append(f"{entry['name']}: {info.frames} frames, expected {frames}")
        report(f"tracks:   {len(wavs)} WAV files of {frames} frames, manifest verified")
        if problems:
            for problem in problems:
                report(f"FAILED {problem}")
            return 1
        report("selftest passed: the installation can generate the 13 tracks")
        return 0
