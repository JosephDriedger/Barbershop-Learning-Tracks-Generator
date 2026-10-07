"""Pure domain models.

No I/O, and no imports from Qt, ``ui``, ``workers``, ``core``, FFmpeg, OpenUtau or any
MusicXML parser code. Musical time is ``fractions.Fraction`` in quarter-note units.
"""

from barbershop_tracks.models.jobs import JobRequest, JobResult, JobStatus
from barbershop_tracks.models.lyric import (
    DEFAULT_VERSE,
    Lyric,
    LyricKind,
    LyricSegment,
    Melisma,
    Syllabic,
)
from barbershop_tracks.models.lyric_analysis import (
    AttackLyric,
    AttackRole,
    LineLyricAnalysis,
    LyricCoverage,
    LyricWord,
    MelismaBasis,
    MissingRun,
    SongLyricAnalysis,
    VerseChoice,
    WordSyllable,
)
from barbershop_tracks.models.mix import MixProfile, StemMix, TrackKind, TrackPlan
from barbershop_tracks.models.notation import ClefChange, SourceLine
from barbershop_tracks.models.note import Note
from barbershop_tracks.models.part import Part
from barbershop_tracks.models.performance import PerformanceNote
from barbershop_tracks.models.performed import (
    LocatedIssue,
    NoteOccurrence,
    PerformanceLocation,
    PerformancePlan,
    PerformedLine,
    PerformedMeterEvent,
    PerformedSong,
    PlayedMeasure,
    TransitionKind,
)
from barbershop_tracks.models.pitch import Pitch, Step
from barbershop_tracks.models.pitch_transform import IDENTITY_TRANSFORM, PitchTransform
from barbershop_tracks.models.song import Song, SourceMetadata
from barbershop_tracks.models.structure import MeasureSpan, RepeatKind, RepeatMark
from barbershop_tracks.models.timing import TempoChange, TimeSignature
from barbershop_tracks.models.validation import Severity, ValidationIssue, ValidationResult
from barbershop_tracks.models.voice import VoiceRole

__all__ = [
    "DEFAULT_VERSE",
    "IDENTITY_TRANSFORM",
    "AttackLyric",
    "AttackRole",
    "ClefChange",
    "JobRequest",
    "JobResult",
    "JobStatus",
    "LineLyricAnalysis",
    "LocatedIssue",
    "Lyric",
    "LyricCoverage",
    "LyricKind",
    "LyricSegment",
    "LyricWord",
    "MeasureSpan",
    "Melisma",
    "MelismaBasis",
    "MissingRun",
    "MixProfile",
    "Note",
    "NoteOccurrence",
    "Part",
    "PerformanceLocation",
    "PerformanceNote",
    "PerformancePlan",
    "PerformedLine",
    "PerformedMeterEvent",
    "PerformedSong",
    "Pitch",
    "PitchTransform",
    "PlayedMeasure",
    "RepeatKind",
    "RepeatMark",
    "Severity",
    "Song",
    "SongLyricAnalysis",
    "SourceLine",
    "SourceMetadata",
    "StemMix",
    "Step",
    "Syllabic",
    "TempoChange",
    "TimeSignature",
    "TrackKind",
    "TrackPlan",
    "TransitionKind",
    "ValidationIssue",
    "ValidationResult",
    "VerseChoice",
    "VoiceRole",
    "WordSyllable",
]
