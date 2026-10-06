"""Qt-independent request/result structures exchanged between pipeline and UI worker."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from types import MappingProxyType

from barbershop_tracks.models.mix import MixProfile
from barbershop_tracks.models.validation import ValidationResult
from barbershop_tracks.models.voice import VoiceRole


class JobStatus(Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    AWAITING_STEMS = "awaiting_stems"  # bundle written; waiting for the user's rendered stems


@dataclass(frozen=True, slots=True, kw_only=True)
class JobRequest:
    """Everything needed to run one job.

    ``role_assignments`` maps a source part id to its voice role and is supplied
    explicitly by the caller. ``stem_paths`` is used by stem-based backends.
    ``backend`` is a backend identifier string, not a class reference.
    """

    musicxml_path: Path
    output_dir: Path
    role_assignments: Mapping[str, VoiceRole] = field(default_factory=dict)
    mix_profile: MixProfile = field(default_factory=MixProfile)
    backend: str = "manual_openutau"
    stem_paths: Mapping[VoiceRole, Path] = field(default_factory=dict)
    work_dir: Path | None = None

    def __post_init__(self) -> None:
        if not self.backend:
            raise ValueError("backend must not be empty")
        for part_id, role in self.role_assignments.items():
            if not part_id:
                raise ValueError("role_assignments keys must be non-empty part ids")
            if not isinstance(role, VoiceRole):
                raise TypeError("role_assignments values must be VoiceRole values")
        for role in self.stem_paths:
            if not isinstance(role, VoiceRole):
                raise TypeError("stem_paths keys must be VoiceRole values")
        object.__setattr__(self, "role_assignments", MappingProxyType(dict(self.role_assignments)))
        object.__setattr__(self, "stem_paths", MappingProxyType(dict(self.stem_paths)))


@dataclass(frozen=True, slots=True, kw_only=True)
class JobResult:
    """The outcome of a job. A COMPLETED job cannot carry validation errors."""

    status: JobStatus
    validation: ValidationResult = field(default_factory=ValidationResult)
    output_files: tuple[Path, ...] = ()
    error_message: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "output_files", tuple(self.output_files))
        if self.status is JobStatus.COMPLETED and self.validation.has_errors:
            raise ValueError("a completed job cannot have validation errors")
        if self.status is JobStatus.FAILED and not self.error_message:
            raise ValueError("a failed job needs an error message")

    @property
    def succeeded(self) -> bool:
        return self.status is JobStatus.COMPLETED
