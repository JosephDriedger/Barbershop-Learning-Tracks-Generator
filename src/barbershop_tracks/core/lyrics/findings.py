"""A finding produced by an analysis state machine, located by performed-attack index."""

from typing import NamedTuple

from barbershop_tracks.models import Severity


class Finding(NamedTuple):
    code: str
    severity: Severity
    message: str
    attack_index: int


def error(code: str, message: str, attack_index: int) -> Finding:
    return Finding(code, Severity.ERROR, message, attack_index)


def warning(code: str, message: str, attack_index: int) -> Finding:
    return Finding(code, Severity.WARNING, message, attack_index)
