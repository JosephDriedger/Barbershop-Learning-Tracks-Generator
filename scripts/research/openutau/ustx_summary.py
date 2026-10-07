"""Summarise an OpenUtau-saved ``.ustx`` into structured research facts (research only).

Descriptive, not a USTX model: no writer, normaliser, migration or production parser. Nothing here
says the format is stable. A key that is absent is reported as ``NOT_PRESENT`` (never a conventional
default, and distinct from a key whose value is null), because a missing field is itself evidence.
Unknown top-level keys are listed, not interpreted.

USTX is external, untrusted YAML: it is read with ``yaml.safe_load`` only, so Python/object tags are
rejected rather than constructed. PyYAML is a development dependency (``pip install -e ".[dev]"``),
not a runtime dependency of the application. ``summarize`` works on an already-parsed mapping.
"""

import importlib
from pathlib import Path
from typing import Any

NOT_PRESENT = "<not present>"
_KNOWN_TOP_LEVEL = frozenset(
    {
        "ustx_version",
        "resolution",
        "bpm",
        "beat_per_bar",
        "beat_unit",
        "tempos",
        "time_signatures",
        "expressions",
        "tracks",
        "voice_parts",
    }
)


class UstxReadError(Exception):
    """The file could not be read as safe YAML (controlled research-tool error, no traceback)."""


def load_yaml(path: Path) -> Any:
    try:
        yaml = importlib.import_module("yaml")
    except ModuleNotFoundError as error:
        raise UstxReadError(
            'PyYAML is not installed; install the development environment: pip install -e ".[dev]"'
        ) from error
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise UstxReadError(f"{path.name} is not safe, valid YAML: {error}") from error
    except (OSError, UnicodeDecodeError) as error:
        raise UstxReadError(f"cannot read {path.name}: {error}") from error


def _field(mapping: Any, key: str) -> Any:
    if not isinstance(mapping, dict) or key not in mapping:
        return NOT_PRESENT
    return mapping[key]


def _items(mapping: Any, key: str) -> Any:
    """A list under ``key``, ``NOT_PRESENT`` if the key is absent, or the odd value as found."""
    return _field(mapping, key)


def summarize(project: Any) -> dict[str, Any]:
    """Structured facts. Singer paths are reduced to their last component so that no
    machine-specific location is recorded (the *form* of the value is noted separately)."""
    tracks = _items(project, "tracks")
    if isinstance(tracks, list):
        tracks = [
            {
                "keys": sorted(track) if isinstance(track, dict) else NOT_PRESENT,
                "singer": _portable(_field(track, "singer")),
                "phonemizer": _field(track, "phonemizer"),
                "renderer_settings": _field(track, "renderer_settings"),
            }
            for track in tracks
        ]
    parts = _items(project, "voice_parts")
    if isinstance(parts, list):
        parts = [_part(part) for part in parts]
    expressions = _field(project, "expressions")
    top = sorted(project) if isinstance(project, dict) else []
    return {
        "top_level_keys": top,
        "unrecognized_top_level_keys": [k for k in top if k not in _KNOWN_TOP_LEVEL],
        "ustx_version": _field(project, "ustx_version"),
        "resolution": _field(project, "resolution"),
        "bpm": _field(project, "bpm"),
        "beat_per_bar": _field(project, "beat_per_bar"),
        "beat_unit": _field(project, "beat_unit"),
        "tempos": _items(project, "tempos"),
        "time_signatures": _items(project, "time_signatures"),
        "expressions": sorted(expressions) if isinstance(expressions, dict) else expressions,
        "tracks": tracks,
        "voice_parts": parts,
    }


def _part(part: Any) -> dict[str, Any]:
    notes = _field(part, "notes")
    return {
        "keys": sorted(part) if isinstance(part, dict) else NOT_PRESENT,
        "track_no": _field(part, "track_no"),
        "position": _field(part, "position"),
        "note_count": len(notes) if isinstance(notes, list) else NOT_PRESENT,
        "notes": [
            {
                "position": _field(n, "position"),
                "duration": _field(n, "duration"),
                "tone": _field(n, "tone"),
                "lyric": _field(n, "lyric"),
            }
            for n in (notes if isinstance(notes, list) else [])
        ],
    }


def _portable(value: Any) -> Any:
    """A singer value without a local path: the last path component, and what form it had."""
    if not isinstance(value, str) or value == NOT_PRESENT:
        return value
    if any(ch in value for ch in "\\/"):
        name = value.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
        return {"value": name, "form": "path (reduced to its last component)"}
    return {"value": value, "form": "identifier or display name"}
