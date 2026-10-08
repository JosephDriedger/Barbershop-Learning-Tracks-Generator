"""The structured observation format: templates, validation and expected-vs-observed comparison."""

import json
import re
from pathlib import Path
from typing import Any

from catalog import BY_ID, Experiment
from research_common import (
    AUTOMATION_CLASSIFICATIONS,
    CLASSIFICATIONS,
    EVIDENCE_METHODS,
    PARTS,
    SCHEMA,
    blt_version,
    git_commit,
)

_REQUIRED = (
    "schema",
    "experiment_id",
    "part",
    "environment",
    "input",
    "expected",
    "observed",
    "classification",
    "classification_note",
    "details",
    "evidence_method",
    "requires",
    "notes",
)
_ENVIRONMENT = (
    "openutau_version",
    "openutau_build",
    "platform",
    "import_method",
    "relevant_settings",
    "blt_version",
    "blt_commit",
)
# a drive-letter path, a UNC path, or a home directory: never recorded in observations
_PATH = re.compile(
    r"(?<![A-Za-z0-9])[A-Za-z]:[\\/](?![\\/])|\\\\[A-Za-z0-9_.-]+\\|(?:^|[\s\"'(])/(?:Users|home)/"
)


def template(
    experiment: Experiment, expected_events: list[dict[str, Any]], *, input_sha256: str | None
) -> dict[str, Any]:
    """An empty observation for ``experiment``: expected filled in, the rest to be recorded."""
    automation = experiment.experiment_id == "C07_AUTOMATION"
    return {
        "schema": SCHEMA,
        "experiment_id": experiment.experiment_id,
        "part": experiment.part,
        "environment": {
            "openutau_version": "",
            "openutau_build": "",
            "platform": "",
            "import_method": "",
            "relevant_settings": {},
            "blt_version": blt_version(),
            "blt_commit": git_commit(),
        },
        "input": {
            "description": experiment.title,
            "recipe_id": experiment.input_id,
            "artifact_sha256": input_sha256,
        },
        "expected": {"summary": experiment.criteria, "events": expected_events},
        "observed": {"summary": "", "events": []},
        "classification": "UNKNOWN",
        "classification_note": "",
        "details": {},
        "evidence_method": "ui_numeric" if not automation else "documentation",
        "requires": {
            "voicebank": experiment.requires_voicebank,
            "manual_openutau": experiment.requires_manual_openutau,
        },
        "notes": "",
    }


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


def staleness(data: Any, current_sha256: str | None) -> str | None:
    """Why an observation no longer applies to the *current* generated input, or ``None``.

    An observation is bound to the exact input it was recorded against: same experiment id but a
    different generated-input hash means the recipe changed and the observation is stale.
    """
    if current_sha256 is None:
        return None
    recorded = data.get("input", {}).get("artifact_sha256") if isinstance(data, dict) else None
    if recorded is None:
        return "the observation is not bound to a generated input hash"
    if recorded != current_sha256:
        return (
            f"stale: it was recorded against input {str(recorded)[:12]} but the experiment now "
            f"generates {current_sha256[:12]}"
        )
    return None


def validate(
    data: Any, *, allow_template: bool = False, current_input_sha256: str | None = None
) -> list[str]:
    """Problems with an observation (an empty list means it is acceptable to commit).

    ``current_input_sha256`` is the hash of the input the experiment generates today (Part A/B);
    when given, the observation must be bound to exactly that input.
    """
    if not isinstance(data, dict):
        return ["an observation must be a JSON object"]
    problems = [f"missing field {name}" for name in _REQUIRED if name not in data]
    if problems:
        return problems
    stale = staleness(data, current_input_sha256)
    if stale:
        problems.append(stale)
    if data["schema"] != SCHEMA:
        problems.append(f"schema must be {SCHEMA}")
    experiment = BY_ID.get(data["experiment_id"])
    if experiment is None:
        problems.append(f"unknown experiment_id {data['experiment_id']!r}")
    elif experiment.part != data["part"]:
        problems.append(f"part must be {experiment.part} for {experiment.experiment_id}")
    if data["part"] not in PARTS:
        problems.append("part must be A, B or C")
    allowed = CLASSIFICATIONS + (AUTOMATION_CLASSIFICATIONS if data["part"] == "C" else ())
    if data["classification"] not in allowed:
        problems.append(f"classification must be one of {', '.join(allowed)}")
    if data["evidence_method"] not in EVIDENCE_METHODS:
        problems.append(f"evidence_method must be one of {', '.join(EVIDENCE_METHODS)}")
    environment = data["environment"]
    if not isinstance(environment, dict):
        problems.append("environment must be an object")
    else:
        problems += [
            f"missing environment.{name}" for name in _ENVIRONMENT if name not in environment
        ]
        if not allow_template:
            for name in ("openutau_version", "platform", "import_method"):
                if not environment.get(name):
                    problems.append(f"environment.{name} must be recorded")
    if not allow_template:
        if data["classification"] == "UNKNOWN" and not data["classification_note"]:
            problems.append("an UNKNOWN classification needs a classification_note saying why")
        if not data["observed"].get("events") and not data["observed"].get("summary"):
            problems.append("nothing observed")
        if data["evidence_method"] == "ui_visual" and data["classification"] == "MATCH":
            problems.append("ui_visual evidence alone cannot support a MATCH")
    for text in _strings(data):
        if _PATH.search(text):
            problems.append(f"a local path appears in the observation: {text[:40]!r}")
            break
    for key in ("user", "username", "timestamp", "date"):
        if key in data or (isinstance(environment, dict) and key in environment):
            problems.append(f"{key} must not be recorded")
    return problems


def compare_events(expected: list[dict[str, Any]], observed: list[dict[str, Any]]) -> list[str]:
    """Exact differences between expected and observed event tables (order-insensitive match by
    position in the list; both are written in the same deterministic order)."""
    differences: list[str] = []
    if len(expected) != len(observed):
        differences.append(f"expected {len(expected)} events, observed {len(observed)}")
    for index, (want, got) in enumerate(zip(expected, observed, strict=False)):
        for key in sorted(set(want) | set(got)):
            if want.get(key) != got.get(key):
                differences.append(
                    f"event {index} {key}: expected {want.get(key)!r}, observed {got.get(key)!r}"
                )
    return differences


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dumps(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=True) + "\n"
