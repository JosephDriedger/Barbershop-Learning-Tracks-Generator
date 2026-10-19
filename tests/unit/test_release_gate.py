"""The release gate refuses publication while anything required is unresolved."""

import copy
import json
import sys
from pathlib import Path
from typing import Any

import pytest

PACKAGING = Path(__file__).resolve().parents[2] / "packaging"
sys.path.insert(0, str(PACKAGING))

import release_gate as gate_module  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
INSTALLER = "a" * 64


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "subject.md").write_text("reviewed text", encoding="utf-8")
    (root / "docs" / "evidence.md").write_text("the review", encoding="utf-8")
    return root


def _item(kind: str = "review", **extra: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": "x",
        "title": "x",
        "kind": kind,
        "required": True,
        "subjects": ["docs/subject.md"],
        "signoff": None,
    }
    item.update(extra)
    return item


def _signed(root: Path, item: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    signoff: dict[str, Any] = {
        "by": "Ada Reviewer",
        "role": "licensing counsel",
        "date": "2026-11-02",
        "conclusion": "approved",
        "subjects": gate_module.subject_hashes(item, root),
        "evidence": ["docs/evidence.md"],
    }
    signoff.update(overrides)
    done = copy.deepcopy(item)
    done["signoff"] = signoff
    return done


def test_the_real_gate_file_is_well_formed_and_points_at_files_that_exist() -> None:
    gate = gate_module.load_gate()
    ids = [i["id"] for i in gate["items"]]
    assert len(ids) == len(set(ids))
    for item in gate["items"]:
        assert item["kind"] in gate_module.KINDS
        assert (REPO / item["packet"]).is_file(), item["id"]
        for subject in item["subjects"]:
            assert (REPO / subject).is_file(), f"{item['id']}: {subject}"
    required = {i["id"] for i in gate["items"] if i["required"]}
    assert {
        "qt-lgpl-review",
        "qt-source-published",
        "english-voicebank-acceptance",
        "clean-machine-verification",
        "code-signing-decision",
        "owner-release-approval",
        "source-history-licensing",
        "g2p-model-provenance",
        "ai-code-authorship",
        "native-dependencies-review",
    } <= required
    g2p = next(i for i in gate["items"] if i["id"] == "g2p-model-provenance")
    assert g2p["decision_field"] == "g2p_model"
    assert g2p["decision_values"] == ["excluded"]


def test_an_item_without_a_signoff_is_open(tmp_path: Path) -> None:
    assert gate_module.check_item(_item(), _repo(tmp_path)) == ["no sign-off recorded"]


def test_a_complete_signoff_closes_the_item(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    assert gate_module.check_item(_signed(root, _item()), root) == []


def test_a_signoff_survives_a_checkout_with_windows_line_endings(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    lf, crlf = bytes([10]), bytes([13, 10])
    (root / "docs" / "subject.md").write_bytes(b"line one" + lf + b"line two" + lf)
    item = _signed(root, _item())
    (root / "docs" / "subject.md").write_bytes(b"line one" + crlf + b"line two" + crlf)
    assert gate_module.check_item(item, root) == []


def test_changing_a_reviewed_file_reopens_the_item(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    item = _signed(root, _item())
    (root / "docs" / "subject.md").write_text("edited after the review", encoding="utf-8")
    problems = gate_module.check_item(item, root)
    assert any("changed since the sign-off" in p for p in problems)


@pytest.mark.parametrize(
    "name", ["Claude", "Claude Code", "github-actions", "CI", "release-bot", "AI assistant"]
)
def test_automation_and_assistants_cannot_sign(tmp_path: Path, name: str) -> None:
    root = _repo(tmp_path)
    problems = gate_module.check_item(_signed(root, _item(), by=name), root)
    assert any("must name a person" in p for p in problems)


@pytest.mark.parametrize(
    ("field", "value", "fragment"),
    [
        ("conclusion", "rejected", "conclusion"),
        ("conclusion", "open", "conclusion"),
        ("date", "next week", "date"),
        ("role", "", "role"),
        ("evidence", [], "no evidence"),
        ("evidence", ["docs/missing.md"], "does not exist"),
        ("conclusion", "approved-with-conditions", "conditions"),
    ],
)
def test_incomplete_signoffs_stay_open(
    tmp_path: Path, field: str, value: Any, fragment: str
) -> None:
    root = _repo(tmp_path)
    problems = gate_module.check_item(_signed(root, _item(), **{field: value}), root)
    assert any(fragment in p for p in problems), problems


def test_approved_with_written_conditions_is_accepted(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    item = _signed(
        root, _item(), conclusion="approved-with-conditions", conditions="re-review on change"
    )
    assert gate_module.check_item(item, root) == []


def test_acceptance_names_the_installer_and_it_must_be_the_one_released(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    assert any(
        "SHA-256 of the installer" in p
        for p in gate_module.check_item(_signed(root, _item("acceptance")), root)
    )
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "SHA256SUMS.txt").write_text(
        f"{'b' * 64} *BLT-Music-Generator-0.1.0-Setup.exe\n", encoding="utf-8"
    )
    item = _signed(root, _item("acceptance"), installer_sha256=INSTALLER)
    assert gate_module.check_item(item, root) == []
    assert any(
        "not the installer being released" in p
        for p in gate_module.check_item(item, root, artifacts)
    )
    (artifacts / "SHA256SUMS.txt").write_text(
        f"{INSTALLER} *BLT-Music-Generator-0.1.0-Setup.exe\n", encoding="utf-8"
    )
    assert gate_module.check_item(item, root, artifacts) == []


def test_a_publication_item_needs_the_url_of_the_published_asset(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    assert any(
        "URL" in p for p in gate_module.check_item(_signed(root, _item("publication")), root)
    )
    done = _signed(
        root, _item("publication"), evidence=["https://example.invalid/release/asset.zip"]
    )
    assert gate_module.check_item(done, root) == []


def _components(tmp_path: Path, status: str) -> Path:
    path = tmp_path / "components.json"
    path.write_text(
        json.dumps({"components": [{"id": "thing", "status": status}]}), encoding="utf-8"
    )
    return path


def test_every_signoff_valid_but_a_component_blocker_still_closes_the_gate(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    gate = {"items": [_signed(root, _item())]}
    assert gate_module.evaluate(gate, root, None, _components(tmp_path, "ok")) == {}
    assert "components.json" in gate_module.evaluate(
        gate, root, None, _components(tmp_path, "blocker")
    )


def test_not_required_items_do_not_close_the_gate(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    gate = {"items": [_item(required=False)]}
    assert gate_module.evaluate(gate, root, None, _components(tmp_path, "ok")) == {}


def test_the_gate_reads_no_ci_result(tmp_path: Path) -> None:
    """Nothing in evaluate() takes test results or a CI status, so green CI cannot open it."""
    import inspect

    parameters = set(inspect.signature(gate_module.evaluate).parameters)
    assert parameters == {"gate", "repo", "package_dir", "components"}
    root = _repo(tmp_path)
    gate = {"items": [_item()]}
    assert gate_module.evaluate(gate, root, None, _components(tmp_path, "ok")) == {
        "x": ["no sign-off recorded"]
    }


def test_a_release_build_must_be_clean_committed_and_blocker_free(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "SHA256SUMS.txt").write_text(
        f"{INSTALLER} *BLT-Music-Generator-0.1.0-Setup.exe\n", encoding="utf-8"
    )
    monkeypatch.setattr(gate_module, "git_head", lambda repo=None: "c" * 40)
    info = {
        "commit": "c" * 40,
        "uncommitted_changes": False,
        "release_blockers": [],
        "worldline_spline_free": True,
        "g2p_model": "excluded",
    }
    (artifacts / "release-info.json").write_text(json.dumps(info), encoding="utf-8")
    assert gate_module.package_problems(artifacts) == []
    info.update(
        uncommitted_changes=True,
        commit="d" * 40,
        release_blockers=["pyside6"],
        worldline_spline_free=False,
        g2p_model=None,
    )
    (artifacts / "release-info.json").write_text(json.dumps(info), encoding="utf-8")
    problems = " | ".join(gate_module.package_problems(artifacts))
    assert "uncommitted" in problems
    assert "not of the commit" in problems
    assert "blockers" in problems
    assert "no spline" in problems
    assert "model-free build" in problems
    info["g2p_model"] = "included"
    (artifacts / "release-info.json").write_text(json.dumps(info), encoding="utf-8")
    assert any("g2p model" in p for p in gate_module.package_problems(artifacts))


def test_sign_refuses_a_bot_and_records_a_person(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    gate_file = tmp_path / "gate.json"
    gate_file.write_text(
        json.dumps({"schema": "blt.release-gate/1", "items": [_item()]}), encoding="utf-8"
    )
    monkeypatch.setattr(gate_module, "GATE", gate_file)
    monkeypatch.setattr(gate_module, "REPO", root)
    base = ["sign", "x", "--role", "counsel", "--evidence", "docs/evidence.md"]
    with pytest.raises(SystemExit, match="cannot sign"):
        gate_module.main([*base, "--by", "Claude"])
    assert json.loads(gate_file.read_text(encoding="utf-8"))["items"][0]["signoff"] is None
    assert gate_module.main([*base, "--by", "Ada Reviewer"]) == 0
    saved = json.loads(gate_file.read_text(encoding="utf-8"))["items"][0]["signoff"]
    assert saved["by"] == "Ada Reviewer"
    assert saved["subjects"] == {
        "docs/subject.md": gate_module.text_sha256(root / "docs" / "subject.md")
    }


def _decision_item(**extra: Any) -> dict[str, Any]:
    return _item(decision_field="g2p_model", decision_values=["included", "excluded"], **extra)


def test_an_item_that_records_a_decision_needs_one_of_the_allowed_values(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    item = _decision_item()
    assert gate_module.check_item(_signed(root, item), root) == [
        "the sign-off must state g2p_model as one of ['included', 'excluded'], not None"
    ]
    assert gate_module.check_item(_signed(root, item, g2p_model="excluded"), root) == []
    assert gate_module.check_item(_signed(root, item, g2p_model="both"), root) != []


@pytest.mark.parametrize(("approved", "built", "ok"), [
    ("included", "included", True),
    ("excluded", "excluded", True),
    ("included", "excluded", False),
    ("excluded", "included", False),
])  # fmt: skip
def test_the_build_released_must_be_the_variant_the_reviewer_approved(
    tmp_path: Path, approved: str, built: str, ok: bool
) -> None:
    root = _repo(tmp_path)
    item = _signed(root, _decision_item(id="g2p"), g2p_model=approved)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "release-info.json").write_text(json.dumps({"g2p_model": built}), encoding="utf-8")
    problems = gate_module.decision_problems({"items": [item]}, artifacts)
    assert (problems == []) is ok
    if not ok:
        assert f"approved for g2p_model='{approved}'" in problems[0]


def test_signing_an_item_with_a_decision_records_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    gate_file = tmp_path / "gate.json"
    gate_file.write_text(
        json.dumps({"schema": "blt.release-gate/1", "items": [_decision_item()]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(gate_module, "GATE", gate_file)
    monkeypatch.setattr(gate_module, "REPO", root)
    base = [
        "sign",
        "x",
        "--by",
        "Ada Reviewer",
        "--role",
        "counsel",
        "--evidence",
        "docs/evidence.md",
    ]
    with pytest.raises(SystemExit, match="g2p_model"):
        gate_module.main(base)
    assert gate_module.main([*base, "--decision", "excluded"]) == 0
    saved = json.loads(gate_file.read_text(encoding="utf-8"))["items"][0]["signoff"]
    assert saved["g2p_model"] == "excluded"


def test_macos_build_records_are_held_to_the_same_rules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gate_module, "git_head", lambda repo=None: "c" * 40)
    info = {
        "architecture": "arm64",
        "commit": "c" * 40,
        "uncommitted_changes": False,
        "release_blockers": [],
        "worldline_spline_free": True,
        "g2p_model": "excluded",
        "disk_image": "BLT-Music-Generator-0.1.0-macos-arm64.dmg",
    }
    record = tmp_path / "release-info-macos-arm64.json"
    record.write_text(json.dumps(info), encoding="utf-8")
    # no checksum for the disk image yet
    assert any("no checksum" in p for p in gate_module.macos_package_problems(tmp_path))
    (tmp_path / "SHA256SUMS-macos-arm64.txt").write_text(
        f"{'b' * 64} *{info['disk_image']}\n", encoding="utf-8"
    )
    assert gate_module.macos_package_problems(tmp_path) == []
    info.update(uncommitted_changes=True, g2p_model="included", release_blockers=["pyside6"])
    record.write_text(json.dumps(info), encoding="utf-8")
    problems = " | ".join(gate_module.macos_package_problems(tmp_path))
    assert "uncommitted" in problems
    assert "model-free build" in problems
    assert "blockers" in problems
    assert all(p.startswith("release-info-macos-arm64.json") for p in problems.split(" | "))


def test_a_folder_without_macos_records_has_no_macos_problems(tmp_path: Path) -> None:
    assert gate_module.macos_package_problems(tmp_path) == []
