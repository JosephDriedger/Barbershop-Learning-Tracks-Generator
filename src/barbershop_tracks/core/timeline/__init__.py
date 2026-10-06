"""Derived timeline views built from source notes (never mutating them)."""

from barbershop_tracks.core.timeline.expand import perform_song
from barbershop_tracks.core.timeline.repeats import PlanResult, plan_performance
from barbershop_tracks.core.timeline.ties import TieMergeResult, merge_tied_notes

__all__ = ["PlanResult", "TieMergeResult", "merge_tied_notes", "perform_song", "plan_performance"]
