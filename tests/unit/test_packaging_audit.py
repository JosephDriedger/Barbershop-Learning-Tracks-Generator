"""The licence audit data and the tools that enforce it (components.json, inventory.py)."""

import hashlib
import json
import re
import sys
from pathlib import Path

import pytest

PACKAGING = Path(__file__).resolve().parents[2] / "packaging"
sys.path.insert(0, str(PACKAGING))

import inventory  # noqa: E402
import notices  # noqa: E402


def _components() -> list[dict[str, object]]:
    return inventory.load_components()


def test_component_ids_are_unique_and_complete() -> None:
    components = _components()
    ids = [str(c["id"]) for c in components]
    assert len(ids) == len(set(ids))
    for component in components:
        for key in ("name", "version", "license", "copyright", "source", "obligations", "status"):
            assert component.get(key), f"{component['id']}: {key} is empty"
        assert component["status"] in ("ok", "blocker")


def test_blockers_say_what_is_unresolved() -> None:
    blockers = [c for c in _components() if c["status"] == "blocker"]
    assert {"worldline", "pyside6", "g2p-arpabet-plus"} == {str(c["id"]) for c in blockers}
    for component in blockers:
        assert str(component["notes"]).strip() or str(component["obligations"]).strip()


def test_every_referenced_spdx_and_upstream_text_exists() -> None:
    for component in _components():
        for identifier in component["texts"]:  # type: ignore[attr-defined]
            assert (PACKAGING / "licenses" / f"{identifier}.txt").is_file(), identifier
        for extra in component["extra_texts"]:  # type: ignore[attr-defined]
            path = str(extra["path"])
            if path.startswith("packaging/"):
                assert (PACKAGING.parent / path).exists(), path


def test_lgpl_and_gpl_texts_are_shipped_with_the_qt_entries() -> None:
    by_id = {c["id"]: c for c in _components()}
    assert "LGPL-3.0-only" in by_id["pyside6"]["texts"]  # type: ignore[operator]
    assert "GPL-3.0-only" in by_id["pyside6"]["texts"]  # type: ignore[operator]
    assert (
        "FFmpeg"
        in json.loads((PACKAGING / "components.json").read_text("utf-8"))["external"][0]["name"]
    )


def test_generated_audit_tables_are_current() -> None:
    assert notices.update_audit(check=True) == 0


def test_glob_stars_stay_inside_one_path_segment() -> None:
    star = inventory.glob_regex("_internal/*.pyd")
    assert star.match("_internal/_ssl.pyd")
    assert not star.match("_internal/numpy/random/x.pyd")
    deep = inventory.glob_regex("_internal/numpy/**")
    assert deep.match("_internal/numpy/random/x.pyd")
    assert not deep.match("_internal/numpy.libs/x.dll")


def _component(identifier: str, *patterns: str, **extra: object) -> dict[str, object]:
    return {"id": identifier, "patterns": list(patterns), "status": "ok", **extra}


def test_classify_flags_unowned_stale_and_runtime_files(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    (dist / "host").mkdir(parents=True)
    (dist / "app.exe").write_bytes(b"x")
    (dist / "host" / "System.Runtime.dll").write_bytes(b"runtime")
    (dist / "host" / "Lib.dll").write_bytes(b"lib")
    (dist / "host" / "surprise.dll").write_bytes(b"new")
    components = [
        _component("app", "app.exe"),
        _component("runtime", match_runtime_pack=True),
        _component("lib", "host/Lib.dll"),
        _component("gone", "host/Removed.dll"),
    ]
    pack = {"System.Runtime.dll": hashlib.sha256(b"runtime").hexdigest()}
    result = inventory.classify(dist, components, pack)
    assert result["owners"]["host/System.Runtime.dll"] == "runtime"
    assert result["owners"]["host/Lib.dll"] == "lib"
    assert result["unowned"] == ["host/surprise.dll"]
    assert result["stale"] == ["gone"]


def test_a_runtime_pack_name_with_different_content_is_not_the_runtime(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    (dist / "host").mkdir(parents=True)
    (dist / "host" / "System.Text.Json.dll").write_bytes(b"nuget 9.0.2")
    components = [
        _component("runtime", match_runtime_pack=True),
        _component("json", "host/System.Text.Json.dll"),
    ]
    pack = {"System.Text.Json.dll": hashlib.sha256(b"runtime 8.0").hexdigest()}
    assert inventory.classify(dist, components, pack)["owners"] == {
        "host/System.Text.Json.dll": "json"
    }


def test_version_drift_is_reported(tmp_path: Path) -> None:
    deps = tmp_path / "deps.json"
    deps.write_text(json.dumps({"libraries": {"Foo/1.0.0": {}, "Bar/2.0.0": {}}}), encoding="utf-8")
    components = [
        {"id": "foo", "package": "Foo", "version": "1.0.0"},
        {"id": "bar", "package": "Bar", "version": "1.9.0"},
        {"id": "gone", "package": "Gone", "version": "1.0.0"},
    ]
    problems = inventory.version_problems(components, deps)
    assert len(problems) == 2
    assert any("bar" in p and "2.0.0" in p for p in problems)
    assert any("gone" in p for p in problems)


@pytest.mark.parametrize("version", [c["version"] for c in _components() if c.get("pypi")])
def test_audited_python_versions_look_like_versions(version: str) -> None:
    assert re.fullmatch(r"\d+(\.\d+)+", version)
