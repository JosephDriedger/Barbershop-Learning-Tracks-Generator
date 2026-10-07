"""The ``check`` and ``lines`` commands end to end, on synthetic quartet scores."""

import json
from pathlib import Path

import pytest

from barbershop_tracks.cli import main
from cli_scores import LINES, quartet_xml, write_quartet

pytestmark = pytest.mark.usefixtures("no_network")

GOLDEN = Path(__file__).resolve().parents[1] / "fixtures" / "cli"


def assign_args(**overrides: str) -> list[str]:
    args: list[str] = []
    for role, line in LINES.items():
        args += ["--assign", f"{role.upper()}={overrides.get(role, line)}"]
    return args


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def check_json(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, dict]:  # type: ignore[type-arg]
    code, out, _ = run(capsys, "check", *argv, "--format", "json")
    return code, json.loads(out)


def finding_codes(data: dict) -> list[str]:  # type: ignore[type-arg]
    return [f["code"] for f in data["findings"]]


# --- exit codes: 0 ready, 1 not ready, 2 usage / input / load failure ---


def test_a_ready_score_exits_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write_quartet(tmp_path)
    code, out, err = run(capsys, "check", str(path), *assign_args())
    assert code == 0
    assert "Readiness for quartet-vocal: READY" in out
    assert err == ""


def test_a_score_that_is_not_ready_exits_one_with_a_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_quartet(tmp_path)
    code, out, _ = run(capsys, "check", str(path))  # nothing assigned
    assert code == 1
    assert "NOT READY" in out
    assert "ROLE_MISSING" in out


def test_strict_makes_advisory_findings_not_ready(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_quartet(tmp_path)  # ready, with advisory lyric-less lines
    assert run(capsys, "check", str(path), *assign_args())[0] == 0
    code, data = check_json(capsys, str(path), *assign_args(), "--strict")
    assert code == 1
    assert data["ready"] is True  # readiness itself is unchanged ...
    assert data["outcome"] == {"strict": True, "passed": False}  # ... the invocation fails


def test_strict_passes_when_there_is_nothing_advisory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_quartet(tmp_path, lyric_part=None)
    args = ["--target", "test-tone", "--strict"]
    code, data = check_json(capsys, str(path), *args)
    assert code == 0
    assert data["counts"]["advisory"] == 0


def test_a_missing_file_is_an_input_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = run(capsys, "check", str(tmp_path / "nope.musicxml"))
    assert code == 2
    assert out == ""
    assert err.startswith("error:")


def test_an_unsupported_extension_and_malformed_xml_are_load_failures(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text = tmp_path / "score.txt"
    text.write_text("hello", encoding="utf-8")
    assert run(capsys, "check", str(text))[0] == 2
    bad = tmp_path / "bad.musicxml"
    bad.write_text("<score-partwise", encoding="utf-8")
    assert run(capsys, "check", str(bad))[0] == 2
    assert run(capsys, "lines", str(bad))[0] == 2


def test_a_loaded_score_with_errors_is_a_report_not_a_load_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    jump = (
        "<direction><direction-type><words>D.C.</words></direction-type>"
        '<sound dacapo="yes"/></direction><note>'
    )
    xml = quartet_xml().replace("<note>", jump, 1)
    path = tmp_path / "jump.musicxml"
    path.write_text(xml, encoding="utf-8")
    code, data = check_json(capsys, str(path), *assign_args())
    assert code == 1
    assert "UNSUPPORTED_JUMP" in finding_codes(data)
    assert data["ready"] is False


@pytest.mark.parametrize(
    "bad",
    [
        ["--assign", "banana"],
        ["--assign", "ALTO=P1/s1/v1"],
        ["--assign", "TENOR="],
        ["--ignore", ""],
        ["--target", "karaoke"],
    ],
)
def test_syntax_errors_are_usage_errors_exit_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], bad: list[str]
) -> None:
    path = write_quartet(tmp_path)
    with pytest.raises(SystemExit) as exc:
        main(["check", str(path), *bad])
    assert exc.value.code == 2
    assert "usage" in capsys.readouterr().err.lower()


def test_no_command_prints_help_and_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "check" in capsys.readouterr().out


# --- semantically invalid assignments are findings, exit one ---


def test_an_unknown_line_is_a_readiness_finding_not_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_quartet(tmp_path)
    code, data = check_json(capsys, str(path), *assign_args(tenor="P99/s1/v7"))
    assert code == 1
    assert "ROLE_LINE_UNKNOWN" in finding_codes(data)


def test_a_role_given_twice_and_a_line_given_two_roles_are_findings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_quartet(tmp_path)
    args = [*assign_args(), "--assign", f"TENOR={LINES['lead']}"]
    code, data = check_json(capsys, str(path), *args)
    assert code == 1
    assert {"ROLE_DUPLICATE", "LINE_ASSIGNED_TWICE"} <= set(finding_codes(data))


def test_roles_are_case_insensitive_but_lines_are_exact(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_quartet(tmp_path)
    lower = [a.replace("TENOR", "tenor") for a in assign_args()]
    assert run(capsys, "check", str(path), *lower)[0] == 0
    code, data = check_json(capsys, str(path), *assign_args(tenor="p1/S1/V1"))  # no fuzzy match
    assert code == 1
    assert "ROLE_LINE_UNKNOWN" in finding_codes(data)


# --- what the checks find ---


def test_a_missing_tempo_blocks(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write_quartet(tmp_path, tempo=False)
    code, data = check_json(capsys, str(path), *assign_args())
    assert code == 1
    assert "TEMPO_MISSING" in finding_codes(data)


def test_a_chord_blocks_the_quartet(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write_quartet(tmp_path, chord_in=2)
    code, data = check_json(capsys, str(path), *assign_args())
    assert code == 1
    assert "LINE_SIMULTANEOUS_NOTES" in finding_codes(data)


def test_partial_lyrics_on_the_only_lyric_line_block(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_quartet(tmp_path, partial_lyrics=True)
    code, data = check_json(capsys, str(path), *assign_args())
    assert code == 1
    assert "LYRIC_SOURCE_INCOMPLETE" in finding_codes(data)


def test_no_lyrics_at_all_blocks_vocal_but_not_test_tone(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_quartet(tmp_path, lyric_part=None)
    assert check_json(capsys, str(path), *assign_args())[0] == 1
    code, data = check_json(capsys, str(path), "--target", "test-tone", *assign_args())
    assert code == 0
    assert data["capability"]["name"] == "test-tone"


def test_ignoring_a_line_is_recorded_not_silent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_quartet(tmp_path, lyric_part=None)
    args = [
        "--target",
        "test-tone",
        "--assign",
        f"TENOR={LINES['tenor']}",
        "--ignore",
        LINES["bass"],
    ]
    code, data = check_json(capsys, str(path), *args)
    assert code == 0
    ignored = [f for f in data["findings"] if f["code"] == "LINE_IGNORED"]
    assert [f["line_id"] for f in ignored] == [LINES["bass"]]
    assert ignored[0]["disposition"] == "info"
    assert [line["ignored"] for line in data["lines"]] == [False, False, False, True]


def test_an_unknown_ignored_line_is_a_finding(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_quartet(tmp_path)
    code, data = check_json(capsys, str(path), *assign_args(), "--ignore", "P9/s1/v1")
    assert code == 1
    assert "IGNORED_LINE_UNKNOWN" in finding_codes(data)


def test_the_verse_option_is_passed_to_the_lyric_analysis(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_quartet(tmp_path)
    code, data = check_json(capsys, str(path), *assign_args(), "--verse", "7")
    assert "LYRIC_VERSE_NOT_FOUND" in finding_codes(data)
    assert code == 1


# --- the JSON contract ---


def test_json_keeps_source_severity_and_readiness_disposition_apart(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # a lyric-domain ERROR: blocking for the vocal capability, info for test-tone
    from xml_builders import lyric_xml, syl, text

    begin = lyric_xml(syl("begin"), text("ba"))
    marked = quartet_xml(lyric_part=None).replace("</note>", begin + "</note>", 1)
    broken = tmp_path / "unclosed.musicxml"
    broken.write_text(marked, encoding="utf-8")
    _, vocal = check_json(capsys, str(broken), *assign_args())
    _, tone = check_json(capsys, str(broken), "--target", "test-tone")
    unclosed_vocal = next(f for f in vocal["findings"] if f["code"] == "LYRIC_WORD_UNCLOSED")
    unclosed_tone = next(f for f in tone["findings"] if f["code"] == "LYRIC_WORD_UNCLOSED")
    assert unclosed_vocal["severity"] == unclosed_tone["severity"] == "error"
    assert unclosed_vocal["disposition"] == "blocking"
    assert unclosed_tone["disposition"] == "info"
    assert unclosed_vocal["location"]["number"] == 1


def test_json_schema_fields(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write_quartet(tmp_path)
    _, data = check_json(capsys, str(path), *assign_args())
    assert list(data) == [
        "schema",
        "capability",
        "ready",
        "clean",
        "outcome",
        "counts",
        "performed_length",
        "lines",
        "findings",
    ]
    assert data["schema"] == "barbershop-tracks.readiness/1"
    assert data["performed_length"] == "8"
    finding = data["findings"][0]
    assert list(finding) == [
        "disposition",
        "severity",
        "code",
        "origin",
        "role",
        "line_id",
        "measure",
        "beat",
        "location",
        "superseded_by",
        "message",
    ]


def test_output_is_deterministic(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write_quartet(tmp_path)
    first = run(capsys, "check", str(path), *assign_args(), "--format", "json")
    second = run(capsys, "check", str(path), *assign_args(), "--format", "json")
    assert first == second


@pytest.mark.parametrize(
    ("golden", "argv"),
    [
        ("quartet_ready.check.json", ["check", "{p}", *assign_args(), "--format", "json"]),
        ("quartet_unassigned.check.json", ["check", "{p}", "--format", "json"]),
        ("quartet_ready.check.txt", ["check", "{p}", *assign_args()]),
        ("quartet.lines.json", ["lines", "{p}", "--format", "json"]),
        ("quartet.lines.txt", ["lines", "{p}"]),
    ],
)
def test_golden_snapshots(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], golden: str, argv: list[str]
) -> None:
    path = write_quartet(tmp_path)
    _, out, _ = run(capsys, *[str(path) if a == "{p}" else a for a in argv])
    assert out == (GOLDEN / golden).read_text(encoding="utf-8")


# --- lines ---


def test_lines_lists_identifiers_with_unconfirmed_name_suggestions(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_quartet(tmp_path)
    code, out, _ = run(capsys, "lines", str(path), "--format", "json")
    data = json.loads(out)
    assert code == 0
    assert [line["line_id"] for line in data["lines"]] == list(LINES.values())
    assert [line["suggestion"]["role"] for line in data["lines"]] == [
        "tenor",
        "lead",
        "baritone",
        "bass",
    ]
    assert {line["suggestion"]["basis"] for line in data["lines"]} == {"name"}
    assert {line["suggestion"]["confirmed"] for line in data["lines"]} == {False}
    assert [line["has_lyrics"] for line in data["lines"]] == [False, True, False, False]


def test_unnamed_lines_get_a_flagged_order_guess(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_quartet(tmp_path, names=False)
    _, out, _ = run(capsys, "lines", str(path), "--format", "json")
    suggestions = [line["suggestion"] for line in json.loads(out)["lines"]]
    assert {s["basis"] for s in suggestions} == {"order"}
    assert all(not s["confirmed"] for s in suggestions)


def test_lines_never_assigns_anything(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write_quartet(tmp_path)
    assert run(capsys, "lines", str(path))[0] == 0
    _, data = check_json(capsys, str(path))  # a later check still has no assignments
    assert [line["role"] for line in data["lines"]] == [None, None, None, None]


def test_lines_notes_that_a_score_has_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    jump = (
        "<direction><direction-type><words>x</words></direction-type>"
        '<sound dacapo="yes"/></direction><note>'
    )
    path = tmp_path / "jump.musicxml"
    path.write_text(quartet_xml().replace("<note>", jump, 1), encoding="utf-8")
    code, out, _ = run(capsys, "lines", str(path))
    assert code == 0
    assert "error(s)" in out


# --- machine-clean JSON: stdout is exactly one document, diagnostics stay on stderr ---


def test_json_stdout_is_exactly_one_document_when_not_ready(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_quartet(tmp_path, tempo=False)
    code, out, _ = run(capsys, "check", str(path), *assign_args(), "--format", "json")
    assert code == 1
    data = json.loads(out)  # the whole of stdout parses: no heading, prose or traceback
    assert out.lstrip().startswith("{")
    assert out.rstrip().endswith("}")
    assert data["ready"] is False
    assert data["outcome"]["passed"] is False


def test_json_stdout_is_clean_when_ready(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_quartet(tmp_path)
    code, out, err = run(capsys, "check", str(path), *assign_args(), "--format", "json")
    assert code == 0
    assert json.loads(out)["ready"] is True
    assert err == ""


def test_load_failure_with_json_format_emits_no_fake_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = run(capsys, "check", str(tmp_path / "nope.musicxml"), "--format", "json")
    assert code == 2
    assert out == ""
    assert err != ""
