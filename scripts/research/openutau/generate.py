"""Generate the M6 research inputs into a git-ignored directory.

    python scripts/research/openutau/generate.py [--out research-output/openutau]

Part A: the real M5 handoff packages (built by the production code from tiny synthetic scores).
Part B: experimental MIDI files with lyric events (research inputs, not BLT output).
Also writes an expected-events JSON next to each input and an ``index.json`` listing hashes. Nothing
here drives OpenUtau, and nothing generated is ever committed.
"""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from catalog import BY_ID
from recipes_part_a import RECIPES, Recipe
from recipes_part_b import EXPERIMENTS, build_midi, expected_events
from research_common import DEFAULT_OUTPUT, INDEX_SCHEMA, blt_version, git_commit, sha256_hex

from barbershop_tracks.core.handoff import PreparedHandoff, prepare_handoff, write_package
from barbershop_tracks.core.midi import MidiPlan


def part_a_expected(plan: MidiPlan) -> list[dict[str, Any]]:
    """The expected event table of a Part A artifact, from the production code's MIDI plan."""
    events: list[dict[str, Any]] = []
    for record in plan.tempo:
        events.append(
            {
                "kind": "tempo",
                "tick": record.tick,
                "bpm_source": str(record.bpm),
                "us_per_quarter_exact": str(record.exact_us_per_quarter),
                "us_per_quarter_midi": record.encoded_us_per_quarter,
            }
        )
    for meter in plan.meter:
        if meter.written:
            events.append(
                {
                    "kind": "meter",
                    "tick": meter.tick,
                    "beats": meter.beats,
                    "beat_type": meter.beat_type,
                }
            )
    for track in plan.tracks:
        pending: dict[int, tuple[int, int]] = {}
        for event in track.events:
            if event.kind.name == "NOTE_ON":
                pending[event.data[0]] = (event.tick, event.data[1])
            elif event.kind.name == "NOTE_OFF":
                start, velocity = pending.pop(event.data[0])
                events.append(
                    {
                        "track": track.name,
                        "kind": "note",
                        "pitch": event.data[0],
                        "start_tick": start,
                        "end_tick": event.tick,
                        "velocity": velocity,
                    }
                )
    events.append({"kind": "end", "tick": plan.end_tick, "ppq": plan.ppq})
    events.sort(
        key=lambda e: (
            e["kind"] != "tempo",
            e["kind"] != "meter",
            e.get("track", ""),
            e.get("start_tick", e.get("tick", 0)),
        )
    )
    return events


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def generate_part_a(out: Path) -> list[dict[str, Any]]:
    index: list[dict[str, Any]] = []
    for recipe_id, make in sorted(RECIPES.items()):
        recipe: Recipe = make()
        preparation = prepare_handoff(
            recipe.parsed,
            recipe.assignments,
            name=recipe.artifact_id,
            source_name=f"{recipe.artifact_id}.synthetic",
            source_sha256=sha256_hex(recipe.artifact_id.encode("ascii")),
            ppq=recipe.ppq,
        )
        handoff: PreparedHandoff | None = preparation.handoff
        if handoff is None:
            raise SystemExit(
                f"recipe {recipe_id} is not exportable: {preparation.export_error or 'not ready'}"
            )
        folder = out / "A" / recipe_id
        folder.mkdir(parents=True, exist_ok=True)
        package = folder / handoff.dirname
        if package.exists():
            write_package(folder, handoff.dirname, handoff.files, overwrite=True)
        else:
            write_package(folder, handoff.dirname, handoff.files)
        _write_json(folder / f"{recipe_id}.expected.json", part_a_expected(handoff.midi.plan))
        index.append(
            {
                "part": "A",
                "recipe_id": recipe_id,
                "description": recipe.description,
                "midi": f"A/{recipe_id}/{handoff.dirname}/{recipe_id}.mid",
                "midi_sha256": handoff.manifest["midi"]["sha256"],
                "expected": f"A/{recipe_id}/{recipe_id}.expected.json",
            }
        )
    return index


def generate_part_b(out: Path) -> list[dict[str, Any]]:
    folder = out / "B"
    folder.mkdir(parents=True, exist_ok=True)
    index: list[dict[str, Any]] = []
    for experiment_id, experiment in sorted(EXPERIMENTS.items()):
        data = build_midi(experiment)
        (folder / f"{experiment_id}.mid").write_bytes(data)
        _write_json(folder / f"{experiment_id}.expected.json", expected_events(experiment))
        index.append(
            {
                "part": "B",
                "recipe_id": experiment_id,
                "description": experiment.description,
                "midi": f"B/{experiment_id}.mid",
                "midi_sha256": sha256_hex(data),
                "expected": f"B/{experiment_id}.expected.json",
            }
        )
    return index


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUTPUT, help="the git-ignored output directory"
    )
    args = parser.parse_args(argv)
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    entries = generate_part_a(out) + generate_part_b(out)
    experiments = sorted(BY_ID)
    _write_json(
        out / "index.json",
        {
            "schema": INDEX_SCHEMA,
            "blt_version": blt_version(),
            "blt_commit": git_commit(),
            "inputs": entries,
            "experiments": experiments,
        },
    )
    print(f"wrote {len(entries)} inputs for {len(experiments)} experiments to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
