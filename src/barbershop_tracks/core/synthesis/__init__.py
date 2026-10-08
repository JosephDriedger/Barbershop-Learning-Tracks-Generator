"""Engine-neutral synthesis: what is sung, by whom, exactly (no engine concepts here).

The OpenUtau-specific serializer lives in ``synthesis.openutau``; nothing here imports it.
"""

from barbershop_tracks.core.synthesis.build import build_synthesis_plan, sounding_midi_pitch
from barbershop_tracks.core.synthesis.errors import PlanNotReadyError, SynthesisPlanError
from barbershop_tracks.core.synthesis.plan import (
    VOICE_ORDER,
    LyricApproval,
    LyricProposal,
    LyricProvenance,
    LyricState,
    MeterPoint,
    NoteLyric,
    OutputRequirements,
    PlannedNote,
    ReviewItem,
    ReviewReason,
    SourceIdentity,
    SynthesisPlan,
    TempoPoint,
    VoiceEngineRef,
    VoicePlan,
    engine_refs_from,
)

__all__ = [
    "VOICE_ORDER",
    "LyricApproval",
    "LyricProposal",
    "LyricProvenance",
    "LyricState",
    "MeterPoint",
    "NoteLyric",
    "OutputRequirements",
    "PlanNotReadyError",
    "PlannedNote",
    "ReviewItem",
    "ReviewReason",
    "SourceIdentity",
    "SynthesisPlan",
    "SynthesisPlanError",
    "TempoPoint",
    "VoiceEngineRef",
    "VoicePlan",
    "build_synthesis_plan",
    "engine_refs_from",
    "sounding_midi_pitch",
]
