"""The ``export`` command end to end: exit codes, machine-clean JSON, safety, determinism."""

import json
from pathlib import Path

import pytest

from barbershop_tracks.cli import main
from cli_scores import LINES, write_quartet

pytestmark = pytest.mark.usefixtures("no_network")

MANIFEST = "handoff-manifest.json"


def assign_args() -> list[str]:
    args: list[str] = []
    for role, line in LINES.items():
        args += ["--assign", f"{role.upper()}={line}"]
    return args


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def export(
    capsys: pytest.CaptureFixture[str], score: Path, out: Path, *extra: str
) -> tuple[int, str, str]:
    return run(capsys, "export", str(score), *assign_args(), "--out", str(out), *extra)


def tree(directory: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(directory.iterdir())}


# --- success ---


def test_an_export_writes_the_package_and_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    score = write_quartet(tmp_path)
    out = tmp_path / "out"
    code, text, err = export(capsys, score, out)
    assert code == 0
    assert err == ""
    package = out / "quartet.handoff"
    assert sorted(tree(package)) == sorted([MANIFEST, "OPENUTAU-STEPS.txt", "quartet.mid"])
    assert "Exported quartet.handoff" in text
    assert "lyrics: not exported" in text
    manifest = json.loads((package / MANIFEST).read_text())
    assert manifest["schema"] == "barbershop-tracks.handoff/1"
    assert manifest["lyrics"]["status"] == "not_exported"
    assert [r["line_id"] for r in manifest["roles"]] == list(LINES.values())
    assert manifest["source"]["display_name"] == "quartet.musicxml"


def test_the_package_name_defaults_to_the_score_and_can_be_chosen(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    score = write_quartet(tmp_path)
    assert export(capsys, score, tmp_path / "a", "--name", "My Song!")[0] == 0
    assert (tmp_path / "a" / "My_Song.handoff" / "My_Song.mid").is_file()


def test_the_midi_in_the_package_is_the_verified_export(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import hashlib

    score = write_quartet(tmp_path)
    export(capsys, score, tmp_path / "out")
    package = tmp_path / "out" / "quartet.handoff"
    manifest = json.loads((package / MANIFEST).read_text())
    assert (
        hashlib.sha256((package / "quartet.mid").read_bytes()).hexdigest()
        == (manifest["midi"]["sha256"])
    )
    assert manifest["source"]["sha256"] == hashlib.sha256(score.read_bytes()).hexdigest()


# --- machine-clean JSON ---


def test_json_stdout_is_exactly_one_document_on_success(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    score = write_quartet(tmp_path)
    code, out, err = export(capsys, score, tmp_path / "out", "--format", "json")
    assert code == 0
    assert err == ""
    data = json.loads(out)
    assert data["schema"] == "barbershop-tracks.export/1"
    assert data["status"] == "exported"
    assert data["package"]["directory"] == "quartet.handoff"
    assert data["package"]["replaced"] is False
    assert data["error"] is None
    assert data["readiness"]["ready"] is True


def test_json_stdout_is_exactly_one_document_when_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    score = write_quartet(tmp_path, tempo=False)
    out_dir = tmp_path / "out"
    code, out, _ = export(capsys, score, out_dir, "--format", "json")
    assert code == 1
    data = json.loads(out)
    assert data["status"] == "refused"
    assert data["package"] is None
    assert data["readiness"]["ready"] is False
    assert not out_dir.exists()  # nothing was written


# --- exit 1: the score cannot be exported ---


def test_a_not_ready_score_writes_nothing_and_exits_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    score = write_quartet(tmp_path)
    out_dir = tmp_path / "out"
    code, text, _ = run(capsys, "export", str(score), "--out", str(out_dir))  # nothing assigned
    assert code == 1
    assert "NOT READY" in text
    assert "Not exported" in text
    assert not out_dir.exists()


def test_strict_refuses_before_writing_an_advisory_score_that_a_plain_export_accepts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    score = write_quartet(tmp_path, lead_octave=7)  # far above the typical Lead range: advisory
    plain, _, _ = export(capsys, score, tmp_path / "plain")
    assert plain == 0
    assert (tmp_path / "plain" / "quartet.handoff").is_dir()
    code, out, _ = export(capsys, score, tmp_path / "strict", "--strict", "--format", "json")
    assert code == 1
    data = json.loads(out)
    assert data["status"] == "refused"
    assert data["readiness"]["outcome"] == {"strict": True, "passed": False}
    assert not (tmp_path / "strict").exists()  # refused before any side effect


def test_a_hand_edited_package_is_not_overwritten_by_the_cli(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    score = write_quartet(tmp_path)
    out_dir = tmp_path / "out"
    export(capsys, score, out_dir)
    steps = out_dir / "quartet.handoff" / "OPENUTAU-STEPS.txt"
    steps.write_text(steps.read_text() + " my notes")
    before = tree(out_dir / "quartet.handoff")
    code, out, err = export(capsys, score, out_dir, "--overwrite")
    assert (code, out) == (2, "")
    assert "error[HANDOFF_MODIFIED]" in err
    assert tree(out_dir / "quartet.handoff") == before
    assert sorted(p.name for p in out_dir.iterdir()) == ["quartet.handoff"]


# --- exit 2: invocation, input, filesystem ---


def test_a_missing_score_is_an_input_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = export(capsys, tmp_path / "nope.musicxml", tmp_path / "out")
    assert code == 2
    assert out == ""
    assert err.startswith("error")


def test_an_invalid_ppq_is_an_invocation_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    score = write_quartet(tmp_path)
    for ppq in ("0", "32768", "-5"):
        code, out, err = export(capsys, score, tmp_path / "out", "--ppq", ppq)
        assert code == 2
        assert out == ""
        assert "error[MIDI_PPQ_INVALID]" in err
    assert not (tmp_path / "out").exists()


def test_an_unusable_name_is_an_invocation_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    score = write_quartet(tmp_path)
    code, out, err = export(capsys, score, tmp_path / "out", "--name", "CON")
    assert code == 2
    assert out == ""
    assert "error[HANDOFF_NAME_INVALID]" in err


def test_an_existing_package_is_refused_without_overwrite(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    score = write_quartet(tmp_path)
    out_dir = tmp_path / "out"
    assert export(capsys, score, out_dir)[0] == 0
    before = tree(out_dir / "quartet.handoff")
    code, out, err = export(capsys, score, out_dir)
    assert (code, out) == (2, "")
    assert "error[HANDOFF_EXISTS]" in err
    assert tree(out_dir / "quartet.handoff") == before


def test_an_unrelated_directory_is_never_overwritten(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    score = write_quartet(tmp_path)
    target = tmp_path / "out" / "quartet.handoff"
    target.mkdir(parents=True)
    (target / "mine.txt").write_text("keep")
    code, out, err = export(capsys, score, tmp_path / "out", "--overwrite")
    assert (code, out) == (2, "")
    assert "error[HANDOFF_NOT_OURS]" in err
    assert (target / "mine.txt").read_text() == "keep"


def test_overwrite_replaces_our_own_package_and_leaves_nothing_behind(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    score = write_quartet(tmp_path)
    out_dir = tmp_path / "out"
    export(capsys, score, out_dir)
    code, out, _ = export(capsys, score, out_dir, "--overwrite", "--format", "json")
    assert code == 0
    assert json.loads(out)["package"]["replaced"] is True
    assert sorted(p.name for p in out_dir.iterdir()) == ["quartet.handoff"]  # no tmp/bak


# --- determinism ---


def test_two_exports_of_one_score_are_byte_identical(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    score = write_quartet(tmp_path)
    export(capsys, score, tmp_path / "one")
    export(capsys, score, tmp_path / "two")
    assert tree(tmp_path / "one" / "quartet.handoff") == tree(tmp_path / "two" / "quartet.handoff")


def test_the_manifest_carries_no_machine_specific_paths(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    score = write_quartet(tmp_path)
    export(capsys, score, tmp_path / "out")
    text = (tmp_path / "out" / "quartet.handoff" / MANIFEST).read_text()
    assert str(tmp_path) not in text
    assert tmp_path.name not in text


# --- the new target in `check` ---


def test_check_accepts_the_quartet_midi_target(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    score = write_quartet(tmp_path, lyric_part=None)  # no lyrics anywhere
    code, out, _ = run(
        capsys, "check", str(score), "--target", "quartet-midi", *assign_args(), "--format", "json"
    )
    assert code == 0
    data = json.loads(out)
    assert data["capability"]["name"] == "quartet-midi"
    assert data["ready"] is True
