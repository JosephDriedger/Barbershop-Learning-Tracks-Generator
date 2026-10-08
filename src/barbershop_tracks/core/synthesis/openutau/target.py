"""The OpenUtau release and USTX version this adapter is written for. Nothing else is assumed.

Compatibility with USTX 0.7 as written by OpenUtau 0.1.565 says nothing about any other release: a
different release needs its own tested target, not a different number here.
"""

import re
from dataclasses import dataclass


class UstxError(ValueError):
    """The plan cannot be written as a USTX for the requested target. ``code`` is stable."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class OpenUtauTarget:
    openutau_version: str
    ustx_version: str
    resolution: int  # project ticks per quarter note, as saved by the release
    renderers: frozenset[str]  # renderer names that release knows
    source_commit: str  # the exact source revision the behaviour was observed on


TARGET_0_1_565 = OpenUtauTarget(
    openutau_version="0.1.565",
    ustx_version="0.7",
    resolution=480,
    renderers=frozenset({"CLASSIC", "WORLDLINE-R", "ENUNU", "VOGEN", "DIFFSINGER", "VOICEVOX"}),
    source_commit="a60ca5830b9064556157245d4bf8f5920d93e5f8",
)
TARGETS: dict[str, OpenUtauTarget] = {TARGET_0_1_565.openutau_version: TARGET_0_1_565}


def target_for(openutau_version: str) -> OpenUtauTarget:
    """The tested target for a release, or ``USTX_TARGET_UNSUPPORTED``."""
    try:
        return TARGETS[openutau_version]
    except KeyError:
        known = ", ".join(sorted(TARGETS))
        raise UstxError(
            "USTX_TARGET_UNSUPPORTED",
            f"OpenUtau {openutau_version} has no tested USTX adapter (tested: {known})",
        ) from None


def read_ustx_version(text: str) -> str | None:
    """The ``ustx_version`` a project text declares, or ``None`` if it declares none."""
    match = re.search(r'^ustx_version:\s*"?([0-9][0-9.]*)"?\s*$', text, flags=re.MULTILINE)
    return match.group(1) if match else None


def require_ustx_version(text: str, target: OpenUtauTarget) -> None:
    found = read_ustx_version(text)
    if found != target.ustx_version:
        raise UstxError(
            "USTX_VERSION_MISMATCH",
            f"project declares ustx_version {found!r}; this adapter targets "
            f"{target.ustx_version!r} (OpenUtau {target.openutau_version})",
        )
