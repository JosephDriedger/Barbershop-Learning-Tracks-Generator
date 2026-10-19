"""Engine-neutral mixing of four vocal stems into the 13 learning tracks."""

from barbershop_tracks.core.mixing.audio import TailPolicy
from barbershop_tracks.core.mixing.errors import (
    MixCancelledError,
    MixClippingError,
    MixConfigurationError,
    MixDurationError,
    MixEncodingError,
    MixError,
    MixInputError,
    MixOutputError,
)
from barbershop_tracks.core.mixing.mp3 import FfmpegMp3Encoder, find_ffmpeg
from barbershop_tracks.core.mixing.package import (
    MANIFEST_NAME,
    AudioFormat,
    Mp3Encoder,
    PackagedFile,
    PackageResult,
    PackageSettings,
    PackageSource,
    build_learning_tracks,
    is_our_package,
    prelude_for,
    stems_from_render,
)
from barbershop_tracks.core.mixing.prelude import PreludeOptions, tonic_midi
from barbershop_tracks.core.mixing.specs import (
    DEFAULT_PROFILE,
    PRESETS,
    GainProfile,
    MixKind,
    MixSpec,
    profile_from_dict,
    standard_mix_specs,
)

__all__ = [
    "DEFAULT_PROFILE",
    "MANIFEST_NAME",
    "PRESETS",
    "AudioFormat",
    "FfmpegMp3Encoder",
    "GainProfile",
    "MixCancelledError",
    "MixClippingError",
    "MixConfigurationError",
    "MixDurationError",
    "MixEncodingError",
    "MixError",
    "MixInputError",
    "MixKind",
    "MixOutputError",
    "MixSpec",
    "Mp3Encoder",
    "PackageResult",
    "PackageSettings",
    "PackageSource",
    "PackagedFile",
    "PreludeOptions",
    "TailPolicy",
    "build_learning_tracks",
    "find_ffmpeg",
    "is_our_package",
    "prelude_for",
    "profile_from_dict",
    "standard_mix_specs",
    "stems_from_render",
    "tonic_midi",
]
