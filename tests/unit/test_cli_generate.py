"""The ``generate`` and ``config`` commands up to (not including) the render host."""

import json
from pathlib import Path

import pytest

from barbershop_tracks.cli import main
from cli_scores import LINES, quartet_xml, write_quartet


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("BLT_SINGERS_DIR", "BLT_FFMPEG", "BLT_HOST_DIR", "DOTNET_ROOT", "BLT_OUTPUT_DIR"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("BLT_CONFIG", str(tmp_path / "no-config.json"))
    monkeypatch.setenv("BLT_DATA_DIR", str(tmp_path / "data"))


def assigns() -> list[str]:
    args = []
    for role in ("tenor", "lead", "baritone", "bass"):
        args += ["--assign", f"{role.upper()}={LINES[role]}"]
    return args


def singers(tmp_path: Path) -> Path:
    folder = tmp_path / "singers"
    (folder / "my-singer").mkdir(parents=True, exist_ok=True)
    (folder / "my-singer" / "character.txt").write_text("name=x", encoding="utf-8")
    return folder


def generate(tmp_path: Path, score: Path, *extra: str) -> list[str]:
    return [
        "generate",
        str(score),
        "--out",
        str(tmp_path / "out"),
        "--singers-dir",
        str(singers(tmp_path)),
        "--host-dir",
        str(tmp_path),
        "--singer",
        "my-singer",
        *assigns(),
        *extra,
    ]


def test_help_lists_the_command_and_its_options(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stop:
        main(["generate", "--help"])
    assert stop.value.code == 0
    text = capsys.readouterr().out
    for option in (
        "--assign",
        "--singer",
        "--audio-format",
        "--replace",
        "--approve-lyrics",
        "--progress",
        "--ffmpeg",
        "--gain-profile",
        "--keep-stems",
    ):
        assert option in text
    with pytest.raises(SystemExit):
        main(["--help"])
    assert "generate" in capsys.readouterr().out


def test_without_a_voice_mapping_the_command_says_how_to_make_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    score = write_quartet(tmp_path, all_lyrics=True)
    code = main(["generate", str(score), "--out", str(tmp_path / "out"), "--singer", "x"])
    assert code == 2
    err = capsys.readouterr().err
    assert "NO_VOICE_MAPPING" in err
    assert "lines" in err


def test_without_an_output_folder_it_asks_for_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    score = write_quartet(tmp_path, all_lyrics=True)
    assert main(["generate", str(score), "--singer", "x", *assigns()]) == 2
    assert "NO_OUTPUT" in capsys.readouterr().err


def test_a_bad_assignment_and_a_bad_singer_are_usage_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    score = write_quartet(tmp_path, all_lyrics=True)
    assert main(generate(tmp_path, score, "--assign", "SOPRANO=P1/s1/v1")) == 2
    assert "BAD_ASSIGN" in capsys.readouterr().err
    with pytest.raises(SystemExit) as stop:
        main(["generate", str(score), "--singer", "nobody="])
    assert stop.value.code == 2


def test_a_score_missing_its_tempo_exits_1_and_lists_the_findings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    score = write_quartet(tmp_path, all_lyrics=True, tempo=False)
    assert main(generate(tmp_path, score)) == 1
    err = capsys.readouterr().err
    assert "SOURCE_NOT_READY" in err
    assert "TEMPO" in err
    assert not (tmp_path / "out").exists()


def test_a_missing_score_file_exits_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(generate(tmp_path, tmp_path / "nope.musicxml")) == 1
    assert "error[" in capsys.readouterr().err


def test_an_uninstalled_singer_exits_2_and_names_what_is_installed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    score = write_quartet(tmp_path, all_lyrics=True)
    args = generate(tmp_path, score)
    args[args.index("--singer") + 1] = "ghost"
    assert main(args) == 2
    err = capsys.readouterr().err
    assert "SINGER_NOT_FOUND" in err
    assert "my-singer" in err


def test_no_singer_at_all_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    score = write_quartet(tmp_path, all_lyrics=True)
    args = generate(tmp_path, score)
    del args[args.index("--singer") : args.index("--singer") + 2]
    assert main(args) == 2
    assert "SINGER_NOT_CHOSEN" in capsys.readouterr().err


def test_mp3_without_ffmpeg_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    score = write_quartet(tmp_path, all_lyrics=True)
    assert main(generate(tmp_path, score, "--audio-format", "mp3")) == 2
    assert "FFMPEG_NOT_CONFIGURED" in capsys.readouterr().err


# --- lyric review ---


def test_missing_harmony_lyrics_exit_6_and_write_a_review_and_a_template(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    score = write_quartet(tmp_path)  # only the Lead has words
    assert main(generate(tmp_path, score)) == 6
    err = capsys.readouterr().err
    assert "LYRICS_NEED_REVIEW" in err
    assert "tenor: 8" in err
    assert "lead" not in err.split("have no decided lyric")[1].split(":")[0]
    review = json.loads(
        (tmp_path / "out" / "quartet_learning_tracks.lyric-review.json").read_text()
    )
    assert review["schema"] == "blt.lyric-review/1"
    assert len(review["items"]) == 24
    template = json.loads(
        (
            tmp_path / "out" / "quartet_learning_tracks.lyric-review.approvals-template.json"
        ).read_text()
    )
    assert template["schema"] == "blt.lyric-approvals/1"
    assert template["source_sha256"] == review["source"]["sha256"]
    assert all(a["text"] is None for a in template["approvals"])


def test_the_review_report_can_be_sent_to_a_chosen_file(tmp_path: Path) -> None:
    score = write_quartet(tmp_path)
    where = tmp_path / "review" / "r.json"
    assert main(generate(tmp_path, score, "--review-report", str(where))) == 6
    assert json.loads(where.read_text())["ready"] is False
    assert (tmp_path / "review" / "r.approvals-template.json").is_file()


def test_a_review_never_overwrites_a_file_that_is_not_ours(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    score = write_quartet(tmp_path)
    mine = tmp_path / "mine.json"
    mine.write_text('{"keep": true}', encoding="utf-8")
    assert main(generate(tmp_path, score, "--review-report", str(mine))) == 6
    assert json.loads(mine.read_text()) == {"keep": True}
    assert "not overwritten" in capsys.readouterr().err


def test_json_progress_reports_the_review_as_an_error_event(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    score = write_quartet(tmp_path)
    assert main(generate(tmp_path, score, "--progress", "json")) == 6
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert events[-1]["event"] == "error"
    assert events[-1]["category"] == "review"
    assert events[-1]["details"]["review"]["items"]
    assert events[0] == {"event": "stage", "stage": "source_loading", "status": "started"}


def test_approvals_for_another_score_are_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    score = write_quartet(tmp_path)
    approvals = tmp_path / "a.json"
    approvals.write_text(
        json.dumps(
            {"schema": "blt.lyric-approvals/1", "source_sha256": "00" * 32, "approvals": []}
        ),
        encoding="utf-8",
    )
    assert main(generate(tmp_path, score, "--approve-lyrics", str(approvals))) == 2
    assert "APPROVALS_WRONG_SCORE" in capsys.readouterr().err


def test_approving_every_note_gets_past_the_review(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    score = write_quartet(tmp_path)
    main(generate(tmp_path, score))
    template = tmp_path / "out" / "quartet_learning_tracks.lyric-review.approvals-template.json"
    document = json.loads(template.read_text())
    for entry in document["approvals"]:
        entry["text"], entry["approved_by"] = "la", "tester"
    filled = tmp_path / "filled.json"
    filled.write_text(json.dumps(document), encoding="utf-8")
    capsys.readouterr()
    code = main(generate(tmp_path, score, "--approve-lyrics", str(filled)))
    err = capsys.readouterr().err
    assert "LYRICS_NEED_REVIEW" not in err  # the lyrics are decided; it fails later, at the host
    assert code in {2, 3}  # no render host exists in this unit test


# --- config ---


def test_config_shows_values_sources_and_what_is_found(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = singers(tmp_path)
    assert main(["config", "--singers-dir", str(folder), "--format", "json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["singers_dir"]["singers"] == ["my-singer"]
    assert report["singers_dir"]["source"] == "command line"
    assert report["defaults"]["singer"] is None
    assert main(["config", "--singers-dir", str(folder)]) == 0
    assert "my-singer" in capsys.readouterr().out


def test_config_reads_the_config_file_and_reports_a_bad_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "c.json"
    path.write_text(json.dumps({"singer": "from-file"}), encoding="utf-8")
    assert main(["config", "--config", str(path), "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["defaults"]["singer"] == "from-file"
    path.write_text("{oops", encoding="utf-8")
    assert main(["config", "--config", str(path)]) == 2
    assert "CONFIG_INVALID" in capsys.readouterr().err


def test_unused_builders_are_importable() -> None:
    assert quartet_xml(all_lyrics=True).startswith("<")


def test_voices_lists_and_adds_a_voicebank(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    voices = tmp_path / "voices"
    source = tmp_path / "from" / "nice-voice"
    source.mkdir(parents=True)
    (source / "character.txt").write_text("name=n", encoding="utf-8")
    assert main(["voices", "list", "--singers-dir", str(voices)]) == 0
    assert "(no voices yet)" in capsys.readouterr().out
    assert main(["voices", "add", str(source), "--singers-dir", str(voices)]) == 0
    assert "Added nice-voice" in capsys.readouterr().out
    assert main(["voices", "list", "--singers-dir", str(voices)]) == 0
    assert "nice-voice" in capsys.readouterr().out
    assert main(["voices", "add", str(source), "--singers-dir", str(voices)]) == 2
    assert "VOICE_EXISTS" in capsys.readouterr().err
