"""The host-inventory check: what it accepts and, above all, what it refuses."""

import copy
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packaging"))

import verify_host_inventory as vhi  # noqa: E402
from barbershop_tracks.core.pipeline.config import (  # noqa: E402
    ENGLISH_PHONEMIZERS,
    REMOVED_PHONEMIZERS,
)

EXPECTED = json.loads((ROOT / "compliance" / "host-inventory.json").read_text(encoding="utf-8"))
REQUIRED = (*ENGLISH_PHONEMIZERS, vhi.DEFAULT_PHONEMIZER)


def host_report(*, model: bool = True) -> dict[str, Any]:
    """What ``blt-render-host --inventory`` would say for a host that matches the allow-list."""
    resources = copy.deepcopy(EXPECTED["resources"])
    for resource in resources:
        if resource["name"] == vhi.ENGLISH_PACK:
            if model:
                resource["zip_members"].append(dict(EXPECTED["g2p_model"], name=vhi.MODEL_MEMBER))
                resource["zip_members"].sort(key=lambda m: m["name"])
            resource["size"] = 1
            resource["sha256"] = "0" * 64
    return {
        "phonemizers": list(EXPECTED["phonemizers"]),
        "resources": resources,
        "g2p_model": "included" if model else "excluded",
    }


def problems(actual: dict[str, Any], g2p_model: str = "auto") -> list[str]:
    return vhi.compare(
        actual, EXPECTED, g2p_model=g2p_model, removed=REMOVED_PHONEMIZERS, required=REQUIRED
    )


def english_pack(report: dict[str, Any]) -> dict[str, Any]:
    return next(r for r in report["resources"] if r["name"] == vhi.ENGLISH_PACK)


def test_the_allow_list_describes_the_supported_engines() -> None:
    assert set(REQUIRED) <= set(EXPECTED["phonemizers"])
    assert not any(n.rsplit(".", 1)[-1] in REMOVED_PHONEMIZERS for n in EXPECTED["phonemizers"])
    names = {r["name"] for r in EXPECTED["resources"]}
    assert vhi.ENGLISH_PACK in names
    assert not any("plus" in n.lower() or "cpv" in n.lower() for n in names)


@pytest.mark.parametrize("model", [True, False])
def test_a_host_that_matches_is_accepted(model: bool) -> None:
    wanted = "included" if model else "excluded"
    assert problems(host_report(model=model), wanted) == []
    assert problems(host_report(model=model), "auto") == []


def test_a_removed_phonemizer_coming_back_is_refused() -> None:
    for class_name in REMOVED_PHONEMIZERS:
        report = host_report()
        report["phonemizers"].append(f"OpenUtau.Plugin.Builtin.{class_name}")
        found = problems(report)
        assert any("not on the allow-list" in p for p in found), class_name
        assert any("BLT removed" in p for p in found), class_name


def test_an_unlisted_phonemizer_is_refused_whatever_it_is_called() -> None:
    report = host_report()
    report["phonemizers"].append("Some.New.Phonemizer")
    assert problems(report) == ["phonemizer not on the allow-list: Some.New.Phonemizer"]


def test_a_missing_supported_phonemizer_is_refused() -> None:
    report = host_report()
    report["phonemizers"].remove("OpenUtau.Plugin.Builtin.ArpasingPhonemizer")
    found = problems(report)
    assert any("allow-list is missing" in p for p in found)
    assert any("BLT supports" in p for p in found)


def test_an_unlisted_embedded_resource_is_refused() -> None:
    report = host_report()
    report["resources"].append(
        {
            "assembly": "OpenUtau.Core",
            "set": "OpenUtau.Core.G2p.Data.Resources.resources",
            "name": "g2p-arpabet-plus",
            "size": 4327034,
            "sha256": "9fc73c72" + "0" * 56,
        }
    )
    assert problems(report) == [
        "embedded resource not on the allow-list: OpenUtau.Core: g2p-arpabet-plus"
    ]


def test_a_blanked_dictionary_that_gets_data_is_refused() -> None:
    report = host_report()
    german = next(r for r in report["resources"] if r["name"] == "g2p-de")
    german["size"] = 1887996
    german["sha256"] = "f" * 64
    assert problems(report) == ["embedded resource changed: OpenUtau.Core: g2p-de"]


def test_a_changed_english_dictionary_is_refused() -> None:
    report = host_report()
    members = english_pack(report)["zip_members"]
    next(m for m in members if m["name"] == "dict.txt")["sha256"] = "a" * 64
    assert any("dictionary files differ" in p for p in problems(report))


def test_an_extra_file_inside_the_english_pack_is_refused() -> None:
    report = host_report()
    english_pack(report)["zip_members"].append(
        {"name": "dict-plus.txt", "size": 1, "sha256": "b" * 64}
    )
    assert any("dictionary files differ" in p for p in problems(report))


def test_a_different_model_is_refused() -> None:
    report = host_report()
    model = next(m for m in english_pack(report)["zip_members"] if m["name"] == vhi.MODEL_MEMBER)
    model["sha256"] = "c" * 64
    assert any("not the reviewed model" in p for p in problems(report))


def test_the_model_is_refused_when_the_build_was_meant_to_exclude_it() -> None:
    assert any("meant to exclude" in p for p in problems(host_report(model=True), "excluded"))
    assert any("meant to include" in p for p in problems(host_report(model=False), "included"))


def test_a_report_that_disagrees_with_the_pack_is_refused() -> None:
    report = host_report(model=True)
    report["g2p_model"] = "excluded"
    assert any("reports g2p_model" in p for p in problems(report))


def test_the_native_runtime_must_match_the_model(tmp_path: Path) -> None:
    (tmp_path / "blt-host-build.json").write_text(json.dumps({"g2p_model": "included"}))
    assert vhi.file_problems(tmp_path, model_present=True) == [
        "the g2p model is present but onnxruntime.dll is not beside the host"
    ]
    (tmp_path / "onnxruntime.dll").write_bytes(b"x")
    assert vhi.file_problems(tmp_path, model_present=True) == []
    excluded = vhi.file_problems(tmp_path, model_present=False)
    assert any("still shipped" in p for p in excluded)
    assert any("blt-host-build.json says" in p for p in excluded)


def test_a_build_record_that_disagrees_is_refused(tmp_path: Path) -> None:
    (tmp_path / "blt-host-build.json").write_text(json.dumps({"g2p_model": "excluded"}))
    (tmp_path / "onnxruntime.dll").write_bytes(b"x")
    assert any("blt-host-build.json says" in p for p in vhi.file_problems(tmp_path, True))


def test_building_the_allow_list_requires_hosts_that_differ_only_by_the_model() -> None:
    with_model, without_model = host_report(model=True), host_report(model=False)
    with_model["openutau_commit"] = "a60ca58+blt-patched"
    built = vhi.build_expected(with_model, without_model)
    assert built["phonemizers"] == EXPECTED["phonemizers"]
    assert built["g2p_model"]["sha256"] == EXPECTED["g2p_model"]["sha256"]
    changed = copy.deepcopy(without_model)
    changed["phonemizers"].append("X.Y")
    with pytest.raises(SystemExit):
        vhi.build_expected(with_model, changed)
    other = copy.deepcopy(without_model)
    next(r for r in other["resources"] if r["name"] == "g2p-de")["size"] = 5
    with pytest.raises(SystemExit):
        vhi.build_expected(with_model, other)
