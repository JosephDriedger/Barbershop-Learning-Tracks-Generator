"""Structured progress events.

Every event is a plain ``dict`` (JSON-serialisable) with an ``"event"`` key:

* ``stage``: ``{"event": "stage", "stage": <Stage>, "status": "started"|"finished", ...}``
* ``progress``: ``{"event": "progress", "stage": <Stage>, "completed": n, "total": m}``, only for
  stages where work can really be counted (13 mixes, 13 MP3 files); other stages report no number
* ``host``: the render host's own phase and progress messages, passed through unchanged in meaning
* ``warning``: something the user should know that did not stop the run
"""

from collections.abc import Callable
from enum import Enum
from typing import Any

EventHandler = Callable[[dict[str, Any]], None]


class Stage(Enum):
    SOURCE_LOADING = "source_loading"
    SCORE_ANALYSIS = "score_analysis"
    READINESS_VALIDATION = "readiness_validation"
    USTX_PREPARATION = "ustx_preparation"
    VOICEBANK_DISCOVERY = "voicebank_discovery"
    STEM_RENDERING = "stem_rendering"
    STEM_VALIDATION = "stem_validation"
    MIXING = "mixing"
    MP3_ENCODING = "mp3_encoding"
    PACKAGE_PUBLICATION = "package_publication"


STAGES: tuple[Stage, ...] = tuple(Stage)


def ignore(_event: dict[str, Any]) -> None:
    return None
