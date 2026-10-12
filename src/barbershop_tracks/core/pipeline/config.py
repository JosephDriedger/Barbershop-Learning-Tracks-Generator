"""Where BLT finds the things it needs, and how a user changes that.

Precedence for every setting, highest first:

1. an explicit command-line option (``overrides``);
2. an environment variable (``BLT_SINGERS_DIR``, ``BLT_FFMPEG``, ``BLT_HOST_DIR``, ``DOTNET_ROOT``,
   ``BLT_DATA_DIR``, ``BLT_OUTPUT_DIR``);
3. the user's config file (``%LOCALAPPDATA%\\BarbershopLearningTracks\\config.json``, or the file
   named by ``BLT_CONFIG``);
4. discovery, only where it cannot be ambiguous: ``ffmpeg`` on ``PATH``, the platform data
   directories, the host next to the application (or in a development checkout), and the standard
   OpenUtau ``Singers`` folder in Documents when it exists.

The voicebank itself is never discovered: ``--singer`` (or ``singer`` in the config file) names it
explicitly and is checked against what is installed. Every resolved value records where it came
from, so ``barbershop-tracks config`` can say exactly why BLT is using it.
"""

import json
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import platformdirs

from barbershop_tracks.core.mixing import (
    DEFAULT_PROFILE,
    PRESETS,
    GainProfile,
    find_ffmpeg,
    profile_from_dict,
)
from barbershop_tracks.core.mixing.errors import MixConfigurationError
from barbershop_tracks.core.pipeline.errors import ErrorCategory, PipelineError
from barbershop_tracks.core.runtime import RuntimeLayout
from barbershop_tracks.core.runtime.layout import APP_NAME

DEFAULT_PHONEMIZER = "OpenUtau.Core.DefaultPhonemizer"
DEFAULT_RENDERER = "WORLDLINE-R"
# The renderers the shipped render host can run. The packaged host leaves out the ONNX runtime that
# the neural renderers (ENUNU, VOGEN, DIFFSINGER, VOICEVOX) need.
SHIPPED_RENDERERS = ("WORLDLINE-R", "CLASSIC")

_KEYS = (
    "singers_dir",
    "ffmpeg",
    "host_dir",
    "dotnet_root",
    "data_dir",
    "output_dir",
    "singer",
    "phonemizer",
    "renderer",
    "gain_profile",
)
_ENVIRONMENT = {
    "singers_dir": "BLT_SINGERS_DIR",
    "ffmpeg": "BLT_FFMPEG",
    "host_dir": "BLT_HOST_DIR",
    "dotnet_root": "DOTNET_ROOT",
    "data_dir": "BLT_DATA_DIR",
    "output_dir": "BLT_OUTPUT_DIR",
}


def config_path(environ: Mapping[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    if env.get("BLT_CONFIG"):
        return Path(env["BLT_CONFIG"])
    return Path(platformdirs.user_config_dir(APP_NAME, appauthor=False)) / "config.json"


def load_config_file(path: Path) -> dict[str, str]:
    """The settings in a config file; a missing file is simply empty, a bad one is an error."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except OSError as error:
        raise PipelineError(
            ErrorCategory.CONFIGURATION, "CONFIG_UNREADABLE", f"cannot read {path}: {error}"
        ) from error
    try:
        data = json.loads(text)
    except ValueError as error:
        raise PipelineError(
            ErrorCategory.CONFIGURATION, "CONFIG_INVALID", f"{path} is not valid JSON: {error}"
        ) from error
    if not isinstance(data, dict):
        raise PipelineError(
            ErrorCategory.CONFIGURATION, "CONFIG_INVALID", f"{path} must be an object"
        )
    unknown = sorted(set(data) - set(_KEYS))
    if unknown:
        raise PipelineError(
            ErrorCategory.CONFIGURATION,
            "CONFIG_UNKNOWN_KEY",
            f"{path} has unknown setting(s) {unknown}; known: {list(_KEYS)}",
        )
    for key, value in data.items():
        if not isinstance(value, str) or not value.strip():
            raise PipelineError(
                ErrorCategory.CONFIGURATION,
                "CONFIG_INVALID",
                f"{path}: {key} must be a non-empty string",
            )
    return {key: str(value) for key, value in data.items()}


@dataclass(frozen=True, slots=True)
class ResolvedConfig:
    layout: RuntimeLayout
    singers_dir: Path | None
    ffmpeg: Path | None
    host_binaries: Path | None
    dotnet_root: Path | None
    output_dir: Path | None
    singer: str | None
    phonemizer: str
    renderer: str
    gain_profile: GainProfile
    sources: Mapping[str, str] = field(default_factory=dict)

    def host_environment(self) -> dict[str, str]:
        """Extra environment for the render host (the .NET runtime location, when configured)."""
        return {"DOTNET_ROOT": str(self.dotnet_root)} if self.dotnet_root is not None else {}


def _development_host() -> Path | None:
    """The host build of a source checkout, so developers need no configuration."""
    root = Path(__file__).resolve().parents[4]
    candidate = root / "research-output" / "host" / "build"
    return candidate if (root / "host" / "build.ps1").is_file() and candidate.is_dir() else None


def _installed_host() -> Path | None:
    candidate = Path(sys.executable).resolve().parent / "host"
    return candidate if candidate.is_dir() else None


def resolve_config(
    file_values: Mapping[str, str],
    *,
    overrides: Mapping[str, str | None] | None = None,
    environ: Mapping[str, str] | None = None,
    profile_file: Path | None = None,
) -> ResolvedConfig:
    env = os.environ if environ is None else environ
    given = {k: v for k, v in (overrides or {}).items() if v}
    values: dict[str, str] = {}
    sources: dict[str, str] = {}
    for key in _KEYS:
        if key in given:
            values[key], sources[key] = given[key], "command line"
        elif key in _ENVIRONMENT and env.get(_ENVIRONMENT[key]):
            values[key], sources[key] = env[_ENVIRONMENT[key]], f"environment {_ENVIRONMENT[key]}"
        elif key in file_values:
            values[key], sources[key] = file_values[key], "config file"

    def path_of(key: str, discovered: Path | None, how: str) -> Path | None:
        if key in values:
            return Path(values[key])
        if discovered is not None:
            sources[key] = f"discovered: {how}"
        return discovered

    documents = Path(platformdirs.user_documents_dir()) / "OpenUtau" / "Singers"
    singers = path_of("singers_dir", documents if documents.is_dir() else None, "OpenUtau default")
    ffmpeg = path_of("ffmpeg", find_ffmpeg(), "PATH")
    if "ffmpeg" in values:  # an explicit choice is never second-guessed
        ffmpeg = Path(values["ffmpeg"])
    host = path_of("host_dir", _installed_host() or _development_host(), "next to the application")
    dotnet = path_of("dotnet_root", None, "")
    data = (
        Path(values["data_dir"])
        if "data_dir" in values
        else Path(platformdirs.user_data_dir(APP_NAME, appauthor=False))
    )
    sources.setdefault("data_dir", "default user data directory")
    cache = Path(platformdirs.user_cache_dir(APP_NAME, appauthor=False))
    layout = RuntimeLayout.under(host.parent if host else Path.cwd(), data, cache)
    output = Path(values["output_dir"]) if "output_dir" in values else None
    return ResolvedConfig(
        layout=layout,
        singers_dir=singers,
        ffmpeg=ffmpeg,
        host_binaries=host,
        dotnet_root=dotnet,
        output_dir=output,
        singer=values.get("singer"),
        phonemizer=values.get("phonemizer", DEFAULT_PHONEMIZER),
        renderer=values.get("renderer", DEFAULT_RENDERER),
        gain_profile=_profile(values.get("gain_profile"), profile_file),
        sources=sources,
    )


def _profile(name: str | None, file: Path | None) -> GainProfile:
    if file is not None:
        try:
            raw: Any = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise PipelineError(
                ErrorCategory.CONFIGURATION, "GAIN_PROFILE_FILE", f"cannot read {file}: {error}"
            ) from error
        try:
            return profile_from_dict(raw)
        except MixConfigurationError as error:
            raise PipelineError(
                ErrorCategory.CONFIGURATION, error.code, f"{file}: {error.message}"
            ) from error
    if name is None:
        return DEFAULT_PROFILE
    if name not in PRESETS:
        raise PipelineError(
            ErrorCategory.CONFIGURATION,
            "GAIN_PROFILE_UNKNOWN",
            f"unknown gain profile {name!r}; presets: {sorted(PRESETS)}",
        )
    return PRESETS[name]


def discover_singers(singers_dir: Path, *, depth: int = 3) -> set[str]:
    """Names of folders that look like voicebanks (they hold character.txt/yaml or an oto.ini).

    A folder with a character file is a voicebank *root*: what lies below it (the pitch sets A3, C4,
    ... or the breaths of a multi-pitch bank, each with its own oto.ini) belongs to that one
    voicebank and is not listed as further voices.
    """
    found: set[str] = set()

    def walk(folder: Path, remaining: int) -> None:
        try:
            children = [c for c in folder.iterdir() if c.is_dir()]
        except OSError:
            return
        for child in children:
            if any((child / m).is_file() for m in ("character.txt", "character.yaml")):
                found.add(child.name)
                continue  # a voicebank root: its subfolders are its own parts
            if (child / "oto.ini").is_file():
                found.add(child.name)
            if remaining > 1:
                walk(child, remaining - 1)

    walk(singers_dir, depth)
    return found
