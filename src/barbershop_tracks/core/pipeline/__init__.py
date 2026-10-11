"""The integrated generation pipeline: MusicXML to the 13-track learning package."""

from barbershop_tracks.core.pipeline.config import (
    DEFAULT_PHONEMIZER,
    DEFAULT_RENDERER,
    ResolvedConfig,
    config_path,
    discover_singers,
    load_config_file,
    resolve_config,
)
from barbershop_tracks.core.pipeline.coordinator import (
    EngineChoice,
    GenerateRequest,
    GenerateResult,
    Services,
    generate,
    package_dirname,
)
from barbershop_tracks.core.pipeline.errors import ErrorCategory, PipelineError
from barbershop_tracks.core.pipeline.events import STAGE_LABELS, STAGES, EventHandler, Stage
from barbershop_tracks.core.pipeline.lyric_files import (
    APPROVALS_SCHEMA,
    REVIEW_SCHEMA,
    approvals_document,
    read_approvals,
    render_review_text,
    review_report,
)
from barbershop_tracks.core.pipeline.preparation import Preparation, blocking_details, prepare

__all__ = [
    "APPROVALS_SCHEMA",
    "DEFAULT_PHONEMIZER",
    "DEFAULT_RENDERER",
    "REVIEW_SCHEMA",
    "STAGES",
    "STAGE_LABELS",
    "EngineChoice",
    "ErrorCategory",
    "EventHandler",
    "GenerateRequest",
    "GenerateResult",
    "PipelineError",
    "Preparation",
    "ResolvedConfig",
    "Services",
    "Stage",
    "approvals_document",
    "blocking_details",
    "config_path",
    "discover_singers",
    "generate",
    "load_config_file",
    "package_dirname",
    "prepare",
    "read_approvals",
    "render_review_text",
    "resolve_config",
    "review_report",
]
