"""Per-user preferences (QSettings). Ordinary choices only.

Never stored: staging paths, lyric approvals, role assignments (they belong to one score), or
anything about a previous score's content. A stored voice that is no longer installed is kept as
a preference but shown as missing by the window; stored values that do not make sense fall back to
the defaults instead of breaking startup.
"""

from pathlib import Path
from typing import Any

from PySide6.QtCore import QByteArray, QSettings

from barbershop_tracks.models import VoiceRole

FORMATS = ("wav", "mp3", "both")
PRESETS = ("default", "strong-focus", "gentle-focus", "custom")
ORGANIZATION = "BarbershopLearningTracks"
APPLICATION = "BLT Music Generator"


class _Pref:
    """A typed setting: reads fall back to ``default`` when the stored value is unusable."""

    def __init__(
        self,
        key: str,
        default: Any,
        kind: type,
        allowed: tuple[Any, ...] | None = None,
        low: float | None = None,
        high: float | None = None,
    ) -> None:
        self.key, self.default, self.kind = key, default, kind
        self.allowed, self.low, self.high = allowed, low, high

    def __get__(self, owner: "Preferences | None", cls: type | None = None) -> Any:
        if owner is None:
            return self
        raw = owner.raw(self.key, self.default)
        try:
            if self.kind is bool:
                value: Any = raw if isinstance(raw, bool) else str(raw).lower() == "true"
            elif self.kind is QByteArray:
                return raw if isinstance(raw, QByteArray) else QByteArray()
            else:
                value = self.kind(raw)
        except (TypeError, ValueError):
            return self.default
        if self.allowed is not None and value not in self.allowed:
            return self.default
        if self.low is not None and self.high is not None and isinstance(value, int | float):
            return type(value)(min(self.high, max(self.low, value)))
        return value

    def __set__(self, owner: "Preferences", value: Any) -> None:
        owner.store(self.key, value)


class Preferences:
    last_score_dir = _Pref("paths/last_score_dir", "", str)
    output_dir = _Pref("paths/output_dir", "", str)
    singers_dir = _Pref("paths/singers_dir", "", str)
    ffmpeg_path = _Pref("paths/ffmpeg", "", str)
    host_dir = _Pref("paths/host_dir", "", str)
    dotnet_root = _Pref("paths/dotnet_root", "", str)
    audio_format = _Pref("output/format", "wav", str, FORMATS)
    gain_preset = _Pref("output/gain_preset", "default", str, PRESETS)
    custom_focus = _Pref("output/custom_focus", 0.5, float)
    custom_others = _Pref("output/custom_others", 0.15, float)
    mp3_quality = _Pref("output/mp3_quality", 2, int, None, 0, 9)
    keep_stems = _Pref("output/keep_stems", False, bool)
    keep_project = _Pref("output/keep_project", False, bool)
    phonemizer = _Pref("engine/phonemizer", "", str)
    renderer = _Pref("engine/renderer", "", str)
    timeout_minutes = _Pref("engine/timeout_minutes", 15, int, None, 1, 240)
    geometry = _Pref("window/geometry", QByteArray(), QByteArray)
    splitter = _Pref("window/splitter", QByteArray(), QByteArray)

    def __init__(self, settings: QSettings) -> None:
        self._s = settings

    @classmethod
    def native(cls) -> "Preferences":
        return cls(QSettings(ORGANIZATION, APPLICATION))

    @classmethod
    def at(cls, path: Path) -> "Preferences":
        """An INI file (used by tests and portable setups)."""
        return cls(QSettings(str(path), QSettings.Format.IniFormat))

    def raw(self, key: str, default: Any) -> Any:
        return self._s.value(key, default)

    def store(self, key: str, value: Any) -> None:
        self._s.setValue(key, value)

    def singer(self, role: VoiceRole) -> str:
        value = self._s.value(f"voices/{role.value}", "")
        return value if isinstance(value, str) else ""

    def set_singer(self, role: VoiceRole, singer: str) -> None:
        self._s.setValue(f"voices/{role.value}", singer)

    def sync(self) -> None:
        self._s.sync()
