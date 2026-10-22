"""Open a score that is not MusicXML by converting it first, with a program the person has installed.

BLT reads MusicXML. Two other kinds of file are common, and each is handled by an external program, never by
code of BLT's own:

* a **MuseScore project** (``.mscz``, ``.mscx``) is exported to MusicXML by MuseScore's own command line
  (``MuseScore4.exe -o score.musicxml project.mscz``). That is an export from the program that wrote the file,
  not a guess; the result is read like any MusicXML.
* a **PDF or image of the printed music** has no notes in it. Its notes, rhythms and words are *recognised* by an
  optical-music-recognition program (Audiveris: ``Audiveris -batch -export -output DIR file.pdf``). Recognition
  makes mistakes, so BLT treats it differently: it runs only when the person has said, in so many words, that
  they accept a recognised score (``accept_recognition``), the result is flagged ``recognised`` everywhere
  (the package's record, the window's messages), and what the recognition missed is still refused by the
  usual readiness checks (a missing tempo or time signature, a note without a lyric).

Neither program is part of BLT (MuseScore is GPL-3, Audiveris AGPL-3: they are started as separate programs, the
licences of BLT are unaffected, and BLT ships neither). A missing program is an error that says where to get it, or
how to export MusicXML by hand.

**Identity.** Everything that is bound to a score (lyric approvals, pronunciations, the package's record) is bound
to the SHA-256 of the file the person chose (``OpenedScore.sha256``), not to the converted MusicXML: MuseScore writes
the date into every export, so a hash of the export would change from day to day. The converted copy is kept in
BLT's cache, keyed by the file's hash and the program that made it, so the same file is converted once and the
conversion used is always the same bytes (recorded as ``converted_sha256``).
"""

import contextlib
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from barbershop_tracks.core.errors import ScoreConversionError

if TYPE_CHECKING:  # imported lazily: the rendering package imports the score model
    from barbershop_tracks.core.rendering.cancel import CancelToken

MUSESCORE_SUFFIXES = (".mscz", ".mscx")
RECOGNITION_SUFFIXES = (".pdf", ".png", ".jpg", ".jpeg")
CONVERTED_SUFFIXES = (*MUSESCORE_SUFFIXES, *RECOGNITION_SUFFIXES)

MUSESCORE_TIMEOUT_SECONDS = 180.0
RECOGNITION_TIMEOUT_SECONDS = 20 * 60.0
_CACHE_DAYS = 30
_MUSICXML_OUTPUT = (".mxl", ".musicxml", ".xml")

MUSESCORE_HELP = (
    "install MuseScore (musescore.org) and BLT will use it, or set BLT_MUSESCORE to MuseScore's program "
    "file; or open the project in MuseScore yourself and choose File > Export > MusicXML"
)
AUDIVERIS_HELP = (
    "install Audiveris (github.com/Audiveris/audiveris, free) and BLT will use it, or set BLT_AUDIVERIS to "
    "its program file; or recognise the PDF in a program of your choice, check the result in a notation "
    "program, and export MusicXML from there"
)


@dataclass(frozen=True, slots=True)
class Conversion:
    """How a score came from a file that is not MusicXML (recorded in the package)."""

    tool: str  # "MuseScore" or "Audiveris"
    program: str  # the program file that was run
    kind: str  # "export" (by the program that wrote the file) or "recognition" (of a picture)
    converted_sha256: str  # of the MusicXML that was analysed
    recognised: (
        bool  # True: notes were recognised from a picture and have not been checked by a person
    )
    note: str

    def as_record(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "program": self.program,
            "kind": self.kind,
            "converted_sha256": self.converted_sha256,
            "recognised": self.recognised,
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class OpenedScore:
    """A score ready to parse: the file to read, and the identity of the file the person chose."""

    parse_path: Path  # a MusicXML file (the person's own file, or the converted copy)
    original: Path
    sha256: str  # of the original file: what approvals and pronunciations are bound to
    conversion: Conversion | None
    # MuseScore's own MIDI export of the project: what it plays, tempo changes included (a
    # ritardando, a fermata, "a tempo"); None for any other kind of score or if it could not be made
    playback_midi: Path | None = None

    @property
    def display_name(self) -> str:
        return self.original.name


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def is_converted_kind(path: Path | str) -> bool:
    return Path(path).suffix.lower() in CONVERTED_SUFFIXES


def needs_recognition(path: Path | str) -> bool:
    """True for a picture of music (PDF, image): the notes would have to be recognised."""
    return Path(path).suffix.lower() in RECOGNITION_SUFFIXES


# --- finding the programs ---------------------------------------------------------------------


def _candidates(environ: Mapping[str, str], variable: str, relative: Sequence[str]) -> list[Path]:
    found: list[Path] = []
    explicit = environ.get(variable)
    if explicit:
        found.append(Path(explicit))
    for base in (
        environ.get("ProgramFiles"),
        environ.get("ProgramFiles(x86)"),
        environ.get("ProgramW6432"),
        environ.get("LOCALAPPDATA") and str(Path(environ["LOCALAPPDATA"]) / "Programs"),
    ):
        if base:
            found.extend(Path(base) / piece for piece in relative)
    return found


_MACOS_MUSESCORE_APPS = ("MuseScore 4.app", "MuseScore Studio.app", "MuseScore 3.app")


def find_musescore(environ: Mapping[str, str] | None = None) -> Path | None:
    """MuseScore's command-line program: ``BLT_MUSESCORE``, else the usual install folders, else the PATH."""
    env = os.environ if environ is None else environ
    names = (
        "MuseScore 4/bin/MuseScore4.exe",
        "MuseScore Studio 4/bin/MuseScore4.exe",
        "MuseScore Studio/bin/MuseScore4.exe",
        "MuseScore 3/bin/MuseScore3.exe",
    )
    for path in _candidates(env, "BLT_MUSESCORE", names):
        if path.is_file():
            return path
    for name in ("MuseScore4", "MuseScore3", "mscore"):
        located = shutil.which(name, path=env.get("PATH"))
        if located:
            return Path(located)
    if sys.platform == "darwin":
        for app in _MACOS_MUSESCORE_APPS:
            for base in (Path("/Applications"), Path.home() / "Applications"):
                program = base / app / "Contents" / "MacOS" / "mscore"
                if program.is_file():
                    return program
    return None


def find_audiveris(environ: Mapping[str, str] | None = None) -> Path | None:
    """Audiveris: ``BLT_AUDIVERIS``, else the usual install folders, else the PATH."""
    env = os.environ if environ is None else environ
    for path in _candidates(env, "BLT_AUDIVERIS", ("Audiveris/Audiveris.exe",)):
        if path.is_file():
            return path
    for name in ("Audiveris", "audiveris"):
        located = shutil.which(name, path=env.get("PATH"))
        if located:
            return Path(located)
    return None


# --- running them -----------------------------------------------------------------------------


def clean_environment(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """The environment to start MuseScore or Audiveris in: BLT's own Qt and Python settings left out.

    MuseScore is itself a Qt program. Started with BLT's variables it can fail before showing anything
    ("no Qt platform plugin could be initialized": ``QT_QPA_PLATFORM`` set for BLT's own use, or BLT's Qt
    libraries found first on the ``PATH``) and then waits for someone to click OK. So the child gets the
    person's environment without any ``QT_*``/``QML*`` variable, without Python's own, and with the folders of
    BLT's program (its bundled Qt among them) taken out of the ``PATH``.
    """
    source = dict(os.environ if environ is None else environ)
    drop = ("QT_", "QML", "PYTHON", "PYI", "_MEI", "_PYI")
    env = {k: v for k, v in source.items() if not k.upper().startswith(drop)}
    ours = {Path(p).resolve() for p in (getattr(sys, "_MEIPASS", None), sys.prefix) if p}
    if getattr(sys, "frozen", False):
        ours.add(Path(sys.executable).resolve().parent)

    def foreign(entry: str) -> bool:
        try:
            here = Path(entry).resolve()
        except (OSError, ValueError):
            return True
        return not any(here == base or base in here.parents for base in ours)

    for key in [k for k in env if k.upper() == "PATH"]:
        env[key] = os.pathsep.join(e for e in env[key].split(os.pathsep) if e and foreign(e))
    return env


def _tail(text: str, limit: int = 600) -> str:
    text = text.strip()
    return text if len(text) <= limit else "..." + text[-limit:]


def _run(
    command: Sequence[str],
    *,
    cwd: Path,
    timeout: float,
    cancel: "CancelToken | None",
    tool: str,
) -> tuple[int, str]:
    """Run ``command`` as an owned process; returns (exit code, the end of its output)."""
    from barbershop_tracks.core.rendering.process import OwnedProcess

    try:
        owned = OwnedProcess(command, cwd=cwd, env=clean_environment())
    except OSError as error:
        raise ScoreConversionError(
            "CONVERSION_FAILED", f"{tool} could not be started: {error}", tool=tool
        ) from error
    deadline = time.monotonic() + timeout
    try:
        while owned.poll() is None:
            if cancel is not None and cancel.cancelled:
                owned.terminate_tree()
                owned.finish()
                raise ScoreConversionError("CONVERSION_CANCELLED", "cancelled", tool=tool)
            if time.monotonic() > deadline:
                owned.terminate_tree()
                owned.finish()
                raise ScoreConversionError(
                    "CONVERSION_TIMEOUT",
                    f"{tool} did not finish within {timeout / 60:.0f} minutes and was stopped",
                    tool=tool,
                )
            time.sleep(0.1)
        code = owned.finish()
    except BaseException:
        owned.terminate_tree()
        owned.finish()
        raise
    return code, _tail(owned.stderr_text or "\n".join(owned.stdout_lines))


def _convert_with_musescore(
    source: Path, program: Path, work: Path, cancel: "CancelToken | None", timeout: float
) -> Path:
    target = work / (source.stem + ".musicxml")
    code, said = _run(
        [str(program), "-o", str(target), str(source)],
        cwd=work,
        timeout=timeout,
        cancel=cancel,
        tool="MuseScore",
    )
    if code != 0:
        raise ScoreConversionError(
            "CONVERSION_FAILED",
            f"MuseScore could not export {source.name} as MusicXML (it stopped with code {code}"
            + (f": {said}" if said else "")
            + "). A project saved by a newer MuseScore than the one installed here is a common cause",
            tool="MuseScore",
        )
    if not target.is_file() or target.stat().st_size == 0:
        raise ScoreConversionError(
            "CONVERSION_NO_OUTPUT",
            f"MuseScore ran but wrote no MusicXML for {source.name}",
            tool="MuseScore",
        )
    return target


def _convert_with_audiveris(
    source: Path, program: Path, work: Path, cancel: "CancelToken | None", timeout: float
) -> Path:
    out = work / "recognised"
    out.mkdir()
    code, said = _run(
        [str(program), "-batch", "-export", "-output", str(out), str(source)],
        cwd=work,
        timeout=timeout,
        cancel=cancel,
        tool="Audiveris",
    )
    produced = sorted(
        p for p in out.rglob("*") if p.is_file() and p.suffix.lower() in _MUSICXML_OUTPUT
    )
    if code != 0 and not produced:
        raise ScoreConversionError(
            "CONVERSION_FAILED",
            f"Audiveris could not recognise {source.name} (it stopped with code {code}"
            + (f": {said}" if said else "")
            + ")",
            tool="Audiveris",
        )
    if not produced:
        raise ScoreConversionError(
            "CONVERSION_NO_OUTPUT",
            f"Audiveris found no music it could write out in {source.name}",
            tool="Audiveris",
        )
    if len(produced) > 1:
        raise ScoreConversionError(
            "CONVERSION_AMBIGUOUS",
            f"Audiveris recognised {len(produced)} separate pieces in {source.name} "
            f"({', '.join(p.name for p in produced[:4])}); BLT needs one score and will not choose "
            "between them: split the PDF so that it holds one piece",
            tool="Audiveris",
        )
    return produced[0]


def _export_playback_midi(
    source: Path, program: Path, work: Path, cancel: "CancelToken | None", timeout: float
) -> Path | None:
    """MuseScore's MIDI export of ``source``, or None. It only refines the score, so a failure
    here is never a reason to refuse it (cancelling still cancels)."""
    target = work / (source.stem + ".mid")
    try:
        code, _said = _run(
            [str(program), "-o", str(target), str(source)],
            cwd=work,
            timeout=timeout,
            cancel=cancel,
            tool="MuseScore",
        )
    except ScoreConversionError as error:
        if error.code == "CONVERSION_CANCELLED":
            raise
        return None
    if code != 0 or not target.is_file() or target.stat().st_size == 0:
        return None
    return target


# --- the cache ---------------------------------------------------------------------------------


def _program_fingerprint(program: Path) -> str:
    try:
        info = program.stat()
    except OSError:
        return program.name
    return f"{program.name}:{info.st_size}:{int(info.st_mtime)}"


def _prune(cache: Path) -> None:
    cutoff = time.time() - _CACHE_DAYS * 86400
    for entry in cache.glob("*"):
        with contextlib.suppress(OSError):
            if entry.stat().st_mtime < cutoff:
                entry.unlink()


def _cached(cache: Path | None, key: str) -> Path | None:
    """The converted MusicXML kept for ``key`` (under the extension its content needs), if any."""
    if cache is None or not cache.is_dir():
        return None
    for entry in sorted(cache.glob(f"{key}.*")):
        if entry.suffix.lower() in _MUSICXML_OUTPUT and entry.stat().st_size > 0:
            return entry
    return None


def _cached_midi(cache: Path | None, key: str) -> Path | None:
    if cache is None:
        return None
    entry = cache / f"{key}.mid"
    return entry if entry.is_file() and entry.stat().st_size > 0 else None


def _store_midi(cache: Path, key: str, produced: Path) -> Path:
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / f"{key}.mid"
    temporary = target.with_name(target.name + ".part")
    shutil.copyfile(produced, temporary)
    temporary.replace(target)
    return target


def _store(cache: Path, key: str, produced: Path, digest: str, tool: str, program: Path) -> Path:
    cache.mkdir(parents=True, exist_ok=True)
    _prune(cache)
    target = cache / f"{key}{produced.suffix.lower()}"
    temporary = target.with_name(target.name + ".part")
    shutil.copyfile(produced, temporary)
    temporary.replace(target)  # a half-written copy is never mistaken for a conversion
    (cache / f"{key}.json").write_text(
        json.dumps({"original_sha256": digest, "tool": tool, "program": str(program)}),
        encoding="utf-8",
    )
    return target


# --- the entry point ---------------------------------------------------------------------------


@contextmanager
def opened_score(
    path: str | os.PathLike[str],
    *,
    accept_recognition: bool = False,
    cache: Path | None = None,
    cancel: "CancelToken | None" = None,
    environ: Mapping[str, str] | None = None,
) -> Iterator[OpenedScore]:
    """The score at ``path`` ready to parse; converts a MuseScore project or a PDF first.

    A MusicXML file is passed through untouched (its identity is its own SHA-256). Raises
    :class:`ScoreConversionError` (``code`` says why) when the program is missing, fails, finds nothing or
    several pieces, or, for a picture of music, when ``accept_recognition`` was not given.
    """
    original = Path(path)
    suffix = original.suffix.lower()
    if suffix not in CONVERTED_SUFFIXES:
        yield OpenedScore(original, original, file_sha256(original), None)
        return
    if not original.is_file():
        raise ScoreConversionError("CONVERSION_FAILED", f"cannot read {original.name}")
    env = os.environ if environ is None else environ
    recognition = suffix in RECOGNITION_SUFFIXES
    tool = "Audiveris" if recognition else "MuseScore"
    if recognition and not accept_recognition:
        raise ScoreConversionError(
            "RECOGNITION_NOT_CONFIRMED",
            f"{original.name} is a picture of music. Its notes, rhythms and words would have to be "
            "recognised by a program, and recognition makes mistakes (a wrong note, a missed tie, a "
            "word under the wrong note); BLT only goes on if you accept a recognised score and check "
            "it against the original",
            tool=tool,
        )
    program = find_audiveris(env) if recognition else find_musescore(env)
    if program is None:
        raise ScoreConversionError(
            "CONVERTER_NOT_FOUND",
            f"{original.name} needs {tool} to be read, and {tool} was not found: "
            + (AUDIVERIS_HELP if recognition else MUSESCORE_HELP),
            tool=tool,
        )
    digest = file_sha256(original)
    key = hashlib.sha256(f"{digest}|{tool}|{_program_fingerprint(program)}".encode()).hexdigest()[
        :24
    ]
    converted = _cached(cache, key)
    scratch: Path | None = None
    if converted is None:
        scratch = Path(tempfile.mkdtemp(prefix="blt-convert-"))
        try:
            if recognition:
                converted = _convert_with_audiveris(
                    original, program, scratch, cancel, RECOGNITION_TIMEOUT_SECONDS
                )
            else:
                converted = _convert_with_musescore(
                    original, program, scratch, cancel, MUSESCORE_TIMEOUT_SECONDS
                )
            if cache is not None:
                converted = _store(cache, key, converted, digest, tool, program)
        except BaseException:
            shutil.rmtree(scratch, ignore_errors=True)
            raise
    try:
        playback_midi: Path | None = None
        if not recognition:
            playback_midi = _cached_midi(cache, key)
            if playback_midi is None:
                if scratch is None:
                    scratch = Path(tempfile.mkdtemp(prefix="blt-convert-"))
                playback_midi = _export_playback_midi(
                    original, program, scratch, cancel, MUSESCORE_TIMEOUT_SECONDS
                )
                if playback_midi is not None and cache is not None:
                    playback_midi = _store_midi(cache, key, playback_midi)
        conversion = Conversion(
            tool=tool,
            program=program.name,
            kind="recognition" if recognition else "export",
            converted_sha256=file_sha256(converted),
            recognised=recognition,
            note=(
                "recognised from a picture of the music by Audiveris; recognition makes mistakes "
                "and the result was not checked by BLT"
                if recognition
                else "exported to MusicXML by MuseScore, the program that wrote the project"
            ),
        )
        yield OpenedScore(converted, original, digest, conversion, playback_midi)
    finally:
        if scratch is not None:
            shutil.rmtree(scratch, ignore_errors=True)


__all__ = [
    "AUDIVERIS_HELP",
    "CONVERTED_SUFFIXES",
    "MUSESCORE_HELP",
    "MUSESCORE_SUFFIXES",
    "RECOGNITION_SUFFIXES",
    "Conversion",
    "OpenedScore",
    "clean_environment",
    "file_sha256",
    "find_audiveris",
    "find_musescore",
    "is_converted_kind",
    "needs_recognition",
    "opened_score",
]
