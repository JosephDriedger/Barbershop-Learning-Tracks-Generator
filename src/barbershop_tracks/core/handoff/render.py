"""Pure rendering of an ``export`` outcome (text and one JSON document). No I/O."""

import json
from pathlib import Path
from typing import Any

from barbershop_tracks.core.handoff.package import Preparation
from barbershop_tracks.core.readiness.render import render_text, report_to_dict

EXPORT_SCHEMA = "barbershop-tracks.export/1"

EXPORTED, REFUSED = "exported", "refused"


def export_to_dict(
    preparation: Preparation, *, path: Path | None, strict: bool, replaced: bool = False
) -> dict[str, Any]:
    """``status`` is ``exported`` or ``refused`` (the score is not exportable; nothing written)."""
    handoff = preparation.handoff
    error = preparation.export_error
    package: dict[str, Any] | None = None
    if handoff is not None:
        package = {
            "directory": handoff.dirname,
            "path": None if path is None else str(path),
            "replaced": replaced,
            "files": handoff.manifest["files"],
            "midi_sha256": handoff.manifest["midi"]["sha256"],
        }
    return {
        "schema": EXPORT_SCHEMA,
        "status": EXPORTED if handoff is not None else REFUSED,
        "package": package,
        "warnings": [] if handoff is None else handoff.manifest["warnings"],
        "error": None if error is None else {"code": error.code, "message": error.message},
        "readiness": report_to_dict(preparation.report, strict=strict),
    }


def render_export_json(
    preparation: Preparation, *, path: Path | None, strict: bool, replaced: bool = False
) -> str:
    data = export_to_dict(preparation, path=path, strict=strict, replaced=replaced)
    return json.dumps(data, indent=2) + "\n"


def render_export_text(
    preparation: Preparation, *, path: Path | None, strict: bool, replaced: bool = False
) -> str:
    handoff = preparation.handoff
    if handoff is None:
        out = [render_text(preparation.report, strict=strict).rstrip("\n")]
        error = preparation.export_error
        if error is not None:
            out.append(f"Not exported: {error.code}: {error.message}")
        else:
            out.append("Not exported: the score is not ready for the quartet MIDI handoff.")
        return "\n".join(out) + "\n"
    note = " (replaced the previous package)" if replaced else ""
    out = [f"Exported {handoff.dirname}{note}"]
    if path is not None:
        out.append(f"  at {path}")
    for entry in handoff.manifest["files"]:
        out.append(f"  {entry['name']}  {entry['bytes']} bytes  sha256 {entry['sha256'][:12]}")
    for warning in handoff.manifest["warnings"]:
        out.append(f"  warning {warning['code']}: {warning['message']}")
    out.append("  lyrics: not exported (see the manifest)")
    return "\n".join(out) + "\n"
