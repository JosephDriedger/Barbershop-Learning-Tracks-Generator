"""Unattended rendering: plan in, validated stems out."""

from barbershop_tracks.core.rendering.backend import (
    OpenUtauRenderBackend,
    RenderResult,
    RenderSettings,
)
from barbershop_tracks.core.rendering.cancel import CancelToken
from barbershop_tracks.core.rendering.errors import (
    OutputValidationError,
    ProjectValidationError,
    RenderCancelledError,
    RenderConfigurationError,
    RenderError,
    RenderTimeoutError,
    SynthesisError,
)
from barbershop_tracks.core.rendering.stems import StemPolicy, StemReport

__all__ = [
    "CancelToken",
    "OpenUtauRenderBackend",
    "OutputValidationError",
    "ProjectValidationError",
    "RenderCancelledError",
    "RenderConfigurationError",
    "RenderError",
    "RenderResult",
    "RenderSettings",
    "RenderTimeoutError",
    "StemPolicy",
    "StemReport",
    "SynthesisError",
]
