"""Derived timeline views built from source notes (never mutating them)."""

from barbershop_tracks.core.timeline.ties import TieMergeResult, merge_tied_notes

__all__ = ["TieMergeResult", "merge_tied_notes"]
