"""Add a voicebank to BLT's voices folder, from a folder or a .zip file the person has.

BLT never downloads or ships voicebanks; this only copies one the person already has into the
voices folder, where it is found like any other. Nothing already there is replaced or deleted, and
nothing is written outside the voices folder: a zip is unpacked into a hidden scratch folder inside
it, checked, and only then moved into place.

A voicebank is a folder with a ``character.txt`` (the singing engine lists a bank only by that
file) or, failing that, an ``oto.ini``. A bank without a ``character.txt`` gets a one-line one in
the copy, so that the engine can see it. Several banks in one archive are installed one by one,
keeping the folders they were in (``Pack\\Bank``).
"""

import shutil
import tempfile
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from barbershop_tracks.core.rendering.engine_detect import neural_kind
from barbershop_tracks.core.singer_names import join_singer_name

MAX_ENTRIES = 200_000
MAX_BYTES = 12 * 1024**3  # an unpacked bank larger than this is not a voicebank
_WINDOWS_RESERVED = frozenset({"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10))})
_WINDOWS_RESERVED |= frozenset(f"lpt{i}" for i in range(1, 10))
Progress = Callable[[str], None]


class VoiceInstallError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class Installed:
    name: str  # as the singing engine knows it (a path: ``Pack\Bank``, ``Pack/Bank`` on macOS)
    path: Path
    notes: tuple[str, ...] = field(default=())  # things worth telling the person


def _fix_name(info: zipfile.ZipInfo) -> str:
    """The entry's name. Zips made on Japanese Windows store Shift-JIS names without saying so,
    which Python reads as cp437 ("mojibake"); the recordings would then not match the oto.ini."""
    name = info.filename
    if info.flag_bits & 0x800 or name.isascii():
        return name
    try:
        return name.encode("cp437").decode("shift_jis")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name


def _safe_parts(name: str) -> tuple[str, ...]:
    parts = tuple(p for p in PurePosixPath(name.replace("\\", "/")).parts if p not in ("", "."))
    bad = any(
        p == ".."
        or ":" in p
        or p.startswith("/")
        or any(c in p for c in '<>"|?*\x00')
        or p.split(".")[0].lower() in _WINDOWS_RESERVED
        for p in parts
    )
    if bad:
        raise VoiceInstallError(
            "VOICE_UNSAFE_PATH", f"the file holds a path BLT will not unpack: {name!r}"
        )
    return parts


def _unpack(archive: Path, into: Path, say: Progress) -> None:
    try:
        zf = zipfile.ZipFile(archive)
    except (zipfile.BadZipFile, OSError) as error:
        raise VoiceInstallError(
            "VOICE_NOT_A_ZIP", f"{archive.name} is not a readable zip: {error}"
        ) from error
    with zf:
        infos = zf.infolist()
        if len(infos) > MAX_ENTRIES or sum(i.file_size for i in infos) > MAX_BYTES:
            raise VoiceInstallError("VOICE_TOO_BIG", f"{archive.name} is too big to be a voicebank")
        if any(i.flag_bits & 0x1 for i in infos):
            raise VoiceInstallError(
                "VOICE_ENCRYPTED", f"{archive.name} is password protected; unzip it first"
            )
        say(f"unpacking {archive.name} …")
        for info in infos:
            parts = _safe_parts(_fix_name(info))
            if not parts:
                continue
            target = into.joinpath(*parts)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as source, target.open("wb") as out:
                shutil.copyfileobj(source, out, 1024 * 1024)


def _has(folder: Path, name: str) -> bool:
    return (folder / name).is_file()


def bank_roots(tree: Path) -> list[Path]:
    """The folders under ``tree`` (or ``tree`` itself) that are voicebanks, outermost first.

    A folder with a ``character.txt`` is a root; what is below it belongs to it. When no folder
    has one, the folder that holds the ``oto.ini`` files is the root: the outermost folder that
    has any beneath it, stepping inward while it holds nothing but a single folder.
    """
    roots: list[Path] = []

    def walk(folder: Path) -> None:
        if _has(folder, "character.txt"):
            roots.append(folder)
            return
        for child in sorted(c for c in folder.iterdir() if c.is_dir()):
            walk(child)

    walk(tree)
    if roots:
        return roots
    if not any(tree.rglob("oto.ini")):
        return []
    top = tree
    while not _has(top, "oto.ini") and not _has(top, "character.yaml"):
        children = list(top.iterdir())
        folders = [c for c in children if c.is_dir()]
        if len(folders) != 1 or len(children) != 1:
            break
        top = folders[0]
    return [top]


def _free_name(parent: Path, relative: tuple[str, ...]) -> Path:
    target = parent.joinpath(*relative)
    if target.exists():
        raise VoiceInstallError(
            "VOICE_EXISTS",
            f"a voice named {join_singer_name(relative)!r} is already in the voices folder; "
            "BLT does not replace it. Remove or rename that folder first",
        )
    return target


def install_voicebank(
    source: Path, voices_dir: Path, say: Progress = lambda _text: None
) -> list[Installed]:
    """Copy the voicebank(s) in ``source`` (a folder or a .zip) into ``voices_dir``."""
    if not source.exists():
        raise VoiceInstallError("VOICE_SOURCE_MISSING", f"{source} does not exist")
    if source.is_file() and source.suffix.lower() != ".zip":
        raise VoiceInstallError(
            "VOICE_FORMAT",
            f"{source.name}: BLT adds a voicebank from a folder or a .zip file. Unpack other "
            "kinds (7z, rar) first and choose the folder",
        )
    voices_dir.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix=".blt-adding-", dir=voices_dir))
    try:
        if source.is_dir():
            if (
                source.resolve() == voices_dir.resolve()
                or voices_dir.resolve() in source.resolve().parents
            ):
                raise VoiceInstallError(
                    "VOICE_ALREADY_THERE", f"{source} is already inside the voices folder"
                )
            say(f"copying {source.name} …")
            unpacked = scratch / source.name
            shutil.copytree(source, unpacked)
            base = scratch  # a pack folder keeps its own name: Pack\Bank
            stem = source.name
        else:
            unpacked = scratch / "unpacked"
            unpacked.mkdir()
            _unpack(source, unpacked, say)
            base = unpacked
            stem = source.stem
        roots = bank_roots(unpacked)
        if not roots:
            raise VoiceInstallError(
                "VOICE_NOT_A_VOICEBANK",
                f"{source.name} holds no voicebank (a folder with a character.txt or an oto.ini "
                "and recordings). BLT cannot use a voice made another way",
            )
        planned: list[tuple[Path, tuple[str, ...]]] = []
        for root in roots:
            relative = root.relative_to(base).parts or (stem,)
            _free_name(voices_dir, relative)
            planned.append((root, relative))
        if len({r for _, r in planned}) != len(planned):
            raise VoiceInstallError("VOICE_DUPLICATE", f"{source.name} holds two banks of one name")
        done: list[Installed] = []
        for root, relative in planned:
            notes: list[str] = []
            if not _has(root, "character.txt"):
                (root / "character.txt").write_text(f"name={relative[-1]}\n", encoding="utf-8")
                notes.append("it had no character.txt, so a one-line one was added to the copy")
            kind = neural_kind(root)
            if kind is not None:
                notes.append(f"it is a {kind} voice, which BLT cannot sing with (UTAU-style only)")
            target = voices_dir.joinpath(*relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            name = join_singer_name(relative)
            say(f"adding {name} …")
            shutil.move(str(root), str(target))
            done.append(Installed(name, target, tuple(notes)))
        return done
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
