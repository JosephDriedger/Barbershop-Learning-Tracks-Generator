"""The M6 research tooling: generators are deterministic and exportable, the observation format is
strict, and nothing generated can be committed. (The tooling itself lives in
scripts/research/openutau/ and is not production code.)"""

import io
import json
import subprocess
from copy import deepcopy
from itertools import pairwise
from pathlib import Path
from typing import Any

import generate
import mido
import observe
import pytest
from catalog import BY_ID, CATALOG
from observations import compare_events, template, validate
from recipes_part_a import RECIPES
from recipes_part_b import EXPERIMENTS, build_midi, expected_events
from research_common import SCHEMA
from ustx_summary import NOT_PRESENT, UstxReadError, load_yaml, summarize

from barbershop_tracks.core.handoff import prepare_handoff

ROOT = Path(__file__).resolve().parents[2]


def prepared(recipe_id: str):  # type: ignore[no-untyped-def]
    recipe = RECIPES[recipe_id]()
    result = prepare_handoff(
        recipe.parsed,
        recipe.assignments,
        name=recipe.artifact_id,
        source_name="x",
        source_sha256="0" * 64,
        ppq=recipe.ppq,
    )
    assert result.handoff is not None, result.export_error
    return result.handoff


# --- the catalog ---


def test_experiment_ids_are_unique_and_every_input_exists() -> None:
    ids = [e.experiment_id for e in CATALOG]
    assert len(ids) == len(set(ids))
    for e in CATALOG:
        assert e.part == e.experiment_id[0]
        if e.part == "A":
            assert e.input_id in RECIPES, e.experiment_id
        elif e.part == "B":
            assert e.input_id in EXPERIMENTS, e.experiment_id
        else:
            assert e.input_id is None
        assert e.steps
        assert e.observe
        assert e.criteria


def test_every_planned_experiment_is_in_the_catalog() -> None:
    planned = [f"A{n:02d}" for n in range(1, 16)] + [f"B0{n}" for n in range(1, 10)]
    planned += [f"C0{n}" for n in range(1, 8)]
    for prefix in planned:
        assert any(i.startswith(prefix + "_") for i in BY_ID), prefix


def test_only_the_synthesis_experiments_require_a_voicebank() -> None:
    needs = {e.experiment_id for e in CATALOG if e.requires_voicebank}
    assert {"A13_SINGER", "A14_PHONEMIZER", "A15_RENDER_WORKFLOW"} <= needs
    assert not {e for e in needs if e.startswith("B")}
    assert (
        not {e.experiment_id for e in CATALOG if e.part == "A" and e.experiment_id < "A13"} & needs
    )


# --- Part A: real M5 packages from tiny synthetic scores ---


@pytest.mark.parametrize("recipe_id", sorted(RECIPES))
def test_every_part_a_recipe_exports_with_the_production_code_deterministically(
    recipe_id: str,
) -> None:
    first, second = prepared(recipe_id), prepared(recipe_id)
    assert first.files == second.files
    assert first.manifest["lyrics"]["status"] == "not_exported"


def test_the_baseline_voices_have_distinct_note_counts() -> None:
    counts = {r["role"]: r["attacks"] for r in prepared("baseline").manifest["roles"]}
    assert counts == {"tenor": 8, "lead": 7, "baritone": 6, "bass": 5}


def test_the_transposed_line_expects_its_sounding_pitches() -> None:
    notes = [
        e
        for e in generate.part_a_expected(prepared("pitches").midi.plan)
        if e.get("track") == "Baritone"
    ]
    assert [n["pitch"] for n in notes] == [48, 50, 52, 53]  # written 60.. sounds an octave lower


def test_the_tempo_recipe_contains_a_rounded_tempo() -> None:
    plan = prepared("tempo").midi.plan
    assert [t.encoded_us_per_quarter for t in plan.tempo] == [600000, 500000, 666667]
    assert plan.tempo[2].error_us_per_quarter != 0


def test_the_pickup_and_repeat_recipes_are_performed_timelines() -> None:
    assert prepared("pickup").midi.plan.end_position == 9  # 1 + 4 + 4
    assert prepared("repeats").midi.plan.end_position == 20  # bars 1-2 twice, then bar 3


def test_the_grid_recipe_lands_on_the_documented_ticks() -> None:
    lead = [
        (e["start_tick"], e["end_tick"])
        for e in generate.part_a_expected(prepared("grid").midi.plan)
        if e.get("track") == "Lead"
    ]
    assert (1920, 2200) in lead  # 7/12 of a quarter is 280 ticks
    assert (2400, 2430) in lead  # 1/16: 30 ticks
    assert (2430, 2475) in lead  # 3/32 at an odd tick: 45 ticks
    assert (1120, 1280) in lead  # a triplet eighth: 160 ticks
    assert (1440, 1536) in lead  # a quintuplet slot: 96 ticks


def test_the_ppq_960_discriminator_is_real_production_output_at_ppq_960() -> None:
    handoff = prepared("grid_ppq960")
    assert handoff.manifest["midi"]["ppq"] == 960
    lead = [
        (e["start_tick"], e["end_tick"])
        for e in generate.part_a_expected(handoff.midi.plan)
        if e.get("track") == "Lead"
    ]
    assert (0, 960) in lead  # a quarter note is tick 960, not 480
    assert (1920, 2240) in lead  # a triplet eighth: 320 ticks
    assert (2880, 2895) in lead  # 1/64 of a quarter: 15 ticks (7.5 at PPQ 480)
    assert (2895, 2940) in lead  # starts at the odd tick 2895, 45 ticks long
    assert (3840, 4400) in lead  # 7/12 of a quarter: 560 ticks
    assert BY_ID["A06_TIMING_GRID_PPQ960"].input_id == "grid_ppq960"
    assert BY_ID["A06_TIMING_GRID"].input_id == "grid"  # the original input is unchanged


def test_adjacent_notes_share_a_tick() -> None:
    notes = [
        e
        for e in generate.part_a_expected(prepared("adjacent").midi.plan)
        if e.get("track") == "Lead"
    ]
    assert all(a["end_tick"] == b["start_tick"] for a, b in pairwise(notes))


# --- Part B: experimental MIDI, not production output ---


def read_lyrics(data: bytes, track_name: str) -> list[tuple[int, str]]:
    mid = mido.MidiFile(file=io.BytesIO(data))
    for track in mid.tracks:
        if track[0].name == track_name:
            tick, out = 0, []
            for message in track:
                tick += message.time
                if message.type == "lyrics":
                    out.append((tick, message.text))
            return out
    raise AssertionError(track_name)


@pytest.mark.parametrize("experiment_id", sorted(EXPERIMENTS))
def test_part_b_midi_is_deterministic_and_matches_its_expected_table(experiment_id: str) -> None:
    experiment = EXPERIMENTS[experiment_id]
    data = build_midi(experiment)
    assert data == build_midi(experiment)
    for track in experiment.tracks:
        sent = [(n.start, n.lyric) for n in track.notes if n.lyric is not None]
        assert read_lyrics(data, track.name) == sent
    table = expected_events(experiment)
    assert len(table) == sum(len(t.notes) for t in experiment.tracks)


def test_the_continuation_experiments_send_the_literal_tokens() -> None:
    def lyrics(experiment_id: str) -> list[str]:
        data = build_midi(EXPERIMENTS[experiment_id])
        return [t for _, t in read_lyrics(data, "Lead")]

    assert lyrics("B03_PLUS") == ["la", "+", "+"]
    assert lyrics("B04_PLUS_TILDE") == ["la", "+~", "+~"]
    assert lyrics("B05_MELISMA_MIXED") == ["won", "+", "+~"]
    assert lyrics("B05_MELISMA_HYPHEN") == ["won", "-", "-"]


def test_a_note_without_a_lyric_gets_no_lyric_event_at_all() -> None:
    sent = read_lyrics(build_midi(EXPERIMENTS["B02_MISSING_LYRIC"]), "Lead")
    assert [t for _, t in sent] == ["la", "la"]
    assert sum(1 for t in EXPERIMENTS["B02_MISSING_LYRIC"].tracks[0].notes if t.lyric is None) == 2


def test_one_source_track_leaves_the_other_tracks_lyric_free() -> None:
    data = build_midi(EXPERIMENTS["B08_ONE_SOURCE_TRACK"])
    assert read_lyrics(data, "Lead")
    for name in ("Tenor", "Baritone", "Bass"):
        assert read_lyrics(data, name) == []


# --- generation and the Git exclusion ---


def test_generate_writes_inputs_expected_tables_and_an_index(tmp_path: Path) -> None:
    assert generate.main(["--out", str(tmp_path)]) == 0
    index = json.loads((tmp_path / "index.json").read_text())
    assert len(index["inputs"]) == len(RECIPES) + len(EXPERIMENTS)
    for entry in index["inputs"]:
        assert (tmp_path / entry["midi"]).is_file()
        assert (tmp_path / entry["expected"]).is_file()
    again = tmp_path / "again"
    generate.main(["--out", str(again)])
    first = {(e["recipe_id"], e["midi_sha256"]) for e in index["inputs"]}
    second = {
        (e["recipe_id"], e["midi_sha256"])
        for e in json.loads((again / "index.json").read_text())["inputs"]
    }
    assert first == second  # deterministic hashes


def test_generated_output_is_ignored_by_git() -> None:
    done = subprocess.run(
        ["git", "check-ignore", "-q", "research-output/openutau/B/B01_SYLLABLES.mid"],
        cwd=ROOT,
        check=False,
    )
    assert done.returncode == 0


# --- observations ---


def valid_observation() -> dict[str, Any]:
    data = template(BY_ID["A07_TEMPO"], [{"kind": "tempo", "tick": 0}], input_sha256="0" * 64)
    data["environment"].update(
        openutau_version="0.0.0-test", platform="test-os", import_method="File > Open"
    )
    data["observed"] = {"summary": "tempo imported", "events": [{"kind": "tempo", "tick": 0}]}
    data["classification"] = "MATCH"
    return data


def test_a_template_is_valid_only_as_a_template() -> None:
    data = template(BY_ID["A01_FILE_ACCEPTANCE"], [], input_sha256=None)
    assert data["schema"] == SCHEMA
    assert validate(data, allow_template=True) == []
    assert validate(data)  # not committable until recorded


def test_a_recorded_observation_validates() -> None:
    assert validate(valid_observation()) == []


@pytest.mark.parametrize(
    ("mutation", "fragment"),
    [
        (lambda d: d.update(classification="PASS"), "classification must be"),
        (lambda d: d.update(evidence_method="vibes"), "evidence_method"),
        (lambda d: d.update(experiment_id="A99_NOPE"), "unknown experiment_id"),
        (lambda d: d.update(part="B"), "part must be A"),
        (lambda d: d.update(evidence_method="ui_visual"), "ui_visual evidence alone"),
        (lambda d: d["environment"].update(openutau_version=""), "openutau_version must be"),
        (lambda d: d.update(notes="see C:\\Users\\someone\\project.ustx"), "local path"),
        (lambda d: d.update(notes="/home/someone/x"), "local path"),
        (lambda d: d.update(timestamp="2026-01-01"), "must not be recorded"),
        (lambda d: d["environment"].update(user="someone"), "must not be recorded"),
        (lambda d: d.pop("expected"), "missing field expected"),
    ],
)
def test_the_validator_rejects_what_must_not_be_committed(mutation: Any, fragment: str) -> None:
    data = deepcopy(valid_observation())
    mutation(data)
    assert any(fragment in problem for problem in validate(data)), validate(data)


def test_unknown_needs_a_reason_and_automation_classes_are_part_c_only() -> None:
    unknown = valid_observation()
    unknown["classification"] = "UNKNOWN"
    assert any("classification_note" in p for p in validate(unknown))
    unknown["classification_note"] = "could not read the numeric value"
    assert validate(unknown) == []
    automation = template(BY_ID["C07_AUTOMATION"], [], input_sha256=None)
    automation["environment"].update(openutau_version="x", platform="y", import_method="z")
    automation["observed"]["summary"] = "no documented headless mode found"
    automation["classification"] = "NOT_FOUND"
    automation["evidence_method"] = "documentation"
    assert validate(automation) == []
    bad = valid_observation()
    bad["classification"] = "NOT_FOUND"
    assert validate(bad)


def test_compare_reports_exact_differences() -> None:
    expected = [{"pitch": 60, "start_tick": 0}, {"pitch": 62, "start_tick": 480}]
    assert compare_events(expected, deepcopy(expected)) == []
    diffs = compare_events(
        expected, [{"pitch": 60, "start_tick": 0}, {"pitch": 62, "start_tick": 481}]
    )
    assert diffs == ["event 1 start_tick: expected 480, observed 481"]
    assert "expected 2 events, observed 1" in compare_events(expected, expected[:1])[0]


def test_the_template_command_fills_in_the_expected_events(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "t.json"
    assert observe.main(["template", "B03_PLUS", "--out", str(target)]) == 0
    data = json.loads(target.read_text())
    assert [e["lyric"] for e in data["expected"]["events"]] == ["la", "+", "+"]
    assert data["input"]["artifact_sha256"]
    assert observe.main(["validate", str(target), "--allow-template"]) == 0
    assert observe.main(["validate", str(target)]) == 1
    assert observe.main(["template", "NOPE"]) == 2


# --- the USTX summariser (pure; research only) ---


def test_the_ustx_summary_is_defensive_and_records_no_local_paths() -> None:
    project = {
        "ustx_version": "0.6",
        "resolution": 480,
        "tracks": [{"singer": "C:\\Users\\someone\\Singers\\Demo", "phonemizer": "X"}],
        "voice_parts": [
            {
                "track_no": 0,
                "position": 0,
                "notes": [{"position": 0, "duration": 480, "tone": 60, "lyric": "la"}],
            }
        ],
    }
    summary = summarize(project)
    assert summary["resolution"] == 480
    assert summary["tracks"][0]["singer"] == {
        "value": "Demo",
        "form": "path (reduced to its last component)",
    }
    assert "Users" not in json.dumps(summary)
    assert summary["voice_parts"][0]["notes"][0]["lyric"] == "la"
    assert summarize({})["tracks"] == NOT_PRESENT  # absent is reported, never a default
    assert summarize(None)["ustx_version"] == NOT_PRESENT


def test_an_absent_key_is_distinct_from_a_null_value_and_unknown_keys_are_listed() -> None:
    summary = summarize({"ustx_version": None, "mystery": 1, "tracks": [{"singer": None}]})
    assert summary["ustx_version"] is None  # present, null
    assert summary["resolution"] == NOT_PRESENT  # absent
    assert summary["unrecognized_top_level_keys"] == ["mystery"]
    assert summary["tracks"][0]["phonemizer"] == NOT_PRESENT


def test_ustx_yaml_is_loaded_safely(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    good = tmp_path / "good.ustx"
    good.write_text("ustx_version: 0.6\nresolution: 480\n", encoding="utf-8")
    assert load_yaml(good) == {"ustx_version": 0.6, "resolution": 480}
    # external input: Python/object tags must be rejected, never constructed
    unsafe = tmp_path / "unsafe.ustx"
    unsafe.write_text('x: !!python/object/apply:builtins.print ["constructed"]\n', encoding="utf-8")
    with pytest.raises(UstxReadError):
        load_yaml(unsafe)
    assert "constructed" not in capsys.readouterr().out


def test_malformed_yaml_is_a_controlled_error_not_a_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    broken = tmp_path / "broken.ustx"
    broken.write_text("a: [unclosed\n", encoding="utf-8")
    with pytest.raises(UstxReadError):
        load_yaml(broken)
    assert observe.main(["ustx-summary", str(broken)]) == 2
    assert "error:" in capsys.readouterr().err
    assert observe.main(["ustx-summary", str(tmp_path / "missing.ustx")]) == 2


def test_pyyaml_is_a_development_dependency_only() -> None:
    import tomllib

    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dev = config["project"]["optional-dependencies"]["dev"]
    assert any(d.lower().startswith("pyyaml") for d in dev)
    assert not any(d.lower().startswith("pyyaml") for d in config["project"]["dependencies"])


# --- observations are bound to the exact input they were recorded against ---


def test_an_observation_goes_stale_when_the_generated_input_changes() -> None:
    data = valid_observation()
    digest = data["input"]["artifact_sha256"]
    assert validate(data, current_input_sha256=digest) == []
    assert any("stale" in p for p in validate(data, current_input_sha256="f" * 64))
    data["input"]["artifact_sha256"] = None
    assert any("not bound" in p for p in validate(data, current_input_sha256=digest))


def test_the_validate_and_compare_commands_detect_a_stale_observation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "o.json"
    observe.main(["template", "B03_PLUS", "--out", str(target)])
    data = json.loads(target.read_text())
    data["environment"].update(openutau_version="0", platform="p", import_method="m")
    data["observed"] = {"summary": "seen", "events": data["expected"]["events"]}
    data["classification"] = "MATCH"
    target.write_text(json.dumps(data))
    assert observe.main(["validate", str(target)]) == 0
    assert observe.main(["compare", str(target)]) == 0
    data["input"]["artifact_sha256"] = "0" * 64  # as if the recipe had changed since
    target.write_text(json.dumps(data))
    capsys.readouterr()
    assert observe.main(["validate", str(target)]) == 1
    assert "stale" in capsys.readouterr().err
    assert observe.main(["compare", str(target)]) == 1
    assert "stale" in capsys.readouterr().err


def test_a_missing_git_is_recorded_as_not_recorded_not_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import research_common

    def no_git(*args: object, **kwargs: object) -> None:
        raise OSError("git not found")

    monkeypatch.setattr(subprocess, "run", no_git)  # the same module object research_common uses
    assert research_common.git_commit() is None
    data = template(BY_ID["A01_FILE_ACCEPTANCE"], [], input_sha256=None)
    assert data["environment"]["blt_commit"] is None
    assert validate(data, allow_template=True) == []


def test_path_rejection_is_conservative_about_ordinary_prose() -> None:
    data = valid_observation()
    data["notes"] = "imported via File/Open; 4/4 and 6/8; the +/- tokens; lyric 'and/or'"
    assert validate(data) == []


def test_each_part_b_input_is_one_experiment_and_the_melisma_variants_are_distinct() -> None:
    b_inputs = [e.input_id for e in CATALOG if e.part == "B"]
    assert len(b_inputs) == len(set(b_inputs))  # one experiment id, one exact input
    assert {e.experiment_id for e in CATALOG if e.experiment_id.startswith("B05")} == {
        "B05_MELISMA_PLUS",
        "B05_MELISMA_PLUS_TILDE",
        "B05_MELISMA_MIXED",
        "B05_MELISMA_HYPHEN",
    }


def test_the_tempo_expectation_keeps_source_exact_and_encoded_apart() -> None:
    plan = prepared("tempo").midi.plan
    tempos = [e for e in generate.part_a_expected(plan) if e["kind"] == "tempo"]
    rounded = tempos[2]
    assert rounded["bpm_source"] == "90"
    assert rounded["us_per_quarter_exact"] == "2000000/3"
    assert rounded["us_per_quarter_midi"] == 666667


def test_every_committed_observation_validates_and_is_bound_to_the_current_input() -> None:
    folder = ROOT / "tests" / "fixtures" / "openutau" / "observations"
    files = sorted(folder.glob("*.json"))
    assert files, "no committed observations"
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["experiment_id"] == path.stem
        problems = validate(data, current_input_sha256=observe._current_hash(data))
        assert problems == [], (path.name, problems)


def test_a_url_is_not_mistaken_for_a_local_path_but_real_paths_still_are() -> None:
    data = valid_observation()
    data["notes"] = "source https://labs.example.org/ALYS/DB and ftp://host/x"
    assert validate(data) == []
    for leak in ("C:\\Users\\me\\x", "D:/work/x", "\\\\server\\share\\x", "see /home/me/x"):
        data["notes"] = leak
        assert any("local path" in p for p in validate(data)), leak
