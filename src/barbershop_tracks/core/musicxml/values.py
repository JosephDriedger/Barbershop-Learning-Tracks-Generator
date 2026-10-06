"""Tiny helpers for reading MusicXML element text. Deliberately not an XML abstraction."""

import re
import xml.etree.ElementTree as ET
from fractions import Fraction

_DECIMAL = re.compile(r"[+-]?[0-9]+(?:\.[0-9]+)?")
_INTEGER = re.compile(r"[+-]?[0-9]+")


def child_text(element: ET.Element, tag: str) -> str | None:
    """Stripped text of the first ``tag`` child, or ``None`` if absent or empty."""
    child = element.find(tag)
    if child is None or child.text is None:
        return None
    text = child.text.strip()
    return text or None


def parse_decimal(text: str | None) -> Fraction | None:
    """Exact value of a plain decimal such as ``12`` or ``-0.5``; ``None`` if not one.

    Exponents, fractions (``1/2``) and special values are rejected, so there is never a
    float and never a surprising spelling.
    """
    if text is None or _DECIMAL.fullmatch(text.strip()) is None:
        return None
    return Fraction(text.strip())


def parse_int(text: str | None) -> int | None:
    """An integer in ASCII digits, or ``None``."""
    if text is None or _INTEGER.fullmatch(text.strip()) is None:
        return None
    return int(text.strip())
