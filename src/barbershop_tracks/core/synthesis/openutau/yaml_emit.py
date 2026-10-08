"""A tiny deterministic YAML emitter for exactly the shapes a USTX needs.

Ordered mappings, lists, flow mappings and scalars; fixed key order, LF newlines, no trailing
spaces.
Strings are bare only when plainly safe, otherwise JSON-quoted (which YAML accepts). It is not a
general serializer and refuses anything it does not know.
"""

import json
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

_PLAIN = re.compile(r"^[A-Za-z][A-Za-z0-9_.\-]*$")
_RESERVED = frozenset({"true", "false", "null", "yes", "no", "on", "off", "y", "n", "~"})


class Quoted(str):
    """A string that is always written JSON-quoted (used for lyrics, whatever they contain)."""

    __slots__ = ()


class Flow:
    """A mapping written on one line: ``{x: -40, y: 0, shape: io}``."""

    __slots__ = ("items",)

    def __init__(self, items: Sequence[tuple[str, Any]]) -> None:
        self.items = tuple(items)


def scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("a non-finite number cannot be written")
        return str(int(value)) if value == int(value) and abs(value) < 1e15 else repr(value)
    if isinstance(value, str):
        if isinstance(value, Quoted):
            return json.dumps(str(value), ensure_ascii=True)
        if _PLAIN.match(value) and value.lower() not in _RESERVED:
            return value
        return json.dumps(value, ensure_ascii=True)
    raise TypeError(f"cannot write {type(value).__name__}")


def _flow(flow: Flow) -> str:
    return "{" + ", ".join(f"{k}: {scalar(v)}" for k, v in flow.items) + "}"


def _entry(key: str, value: Any, indent: int, prefix: str, out: list[str]) -> None:
    if isinstance(value, Flow):
        out.append(f"{prefix}{key}: {_flow(value)}")
    elif isinstance(value, Mapping):
        if not value:
            out.append(f"{prefix}{key}: {{}}")
        else:
            out.append(f"{prefix}{key}:")
            _mapping(value, indent + 2, out)
    elif isinstance(value, list):
        if not value:
            out.append(f"{prefix}{key}: []")
        else:
            out.append(f"{prefix}{key}:")
            for item in value:
                _item(item, indent, out)
    else:
        out.append(f"{prefix}{key}: {scalar(value)}")


def _mapping(
    mapping: Mapping[str, Any], indent: int, out: list[str], lead: str | None = None
) -> None:
    pad = " " * indent
    for position, (key, value) in enumerate(mapping.items()):
        prefix = lead if (position == 0 and lead is not None) else pad
        _entry(key, value, indent, prefix, out)


def _item(item: Any, indent: int, out: list[str]) -> None:
    pad = " " * indent
    if isinstance(item, Flow):
        out.append(f"{pad}- {_flow(item)}")
    elif isinstance(item, Mapping):
        if not item:
            out.append(f"{pad}- {{}}")
        else:
            _mapping(item, indent + 2, out, lead=f"{pad}- ")
    else:
        out.append(f"{pad}- {scalar(item)}")


def emit(mapping: Mapping[str, Any]) -> str:
    """The mapping as block YAML (top-level keys at column zero)."""
    out: list[str] = []
    _mapping(mapping, 0, out)
    return "\n".join(out) + "\n"
