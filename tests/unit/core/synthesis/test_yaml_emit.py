import pytest

from barbershop_tracks.core.synthesis.openutau.yaml_emit import Flow, Quoted, emit, scalar


def test_plain_and_quoted_scalars() -> None:
    assert scalar("abc_1.x") == "abc_1.x"
    assert scalar("true") == '"true"'
    assert scalar("has space") == '"has space"'
    assert scalar("") == '""'
    assert scalar(Quoted("a")) == '"a"'
    assert scalar("é") == '"\\u00e9"'
    assert scalar(True) == "true"
    assert scalar(3) == "3"
    assert scalar(2.0) == "2"
    assert scalar(2.5) == "2.5"


def test_non_finite_and_unknown_types_refused() -> None:
    with pytest.raises(ValueError, match="non-finite"):
        scalar(float("nan"))
    with pytest.raises(TypeError):
        scalar(object())


def test_emit_shapes() -> None:
    text = emit({"a": 1, "e": [], "m": {}, "f": Flow([("x", 1), ("y", "io")]), "l": [{"k": 2}]})
    lines = text.splitlines()
    assert lines[0] == "a: 1"
    assert "e: []" in lines
    assert "m: {}" in lines
    assert "f: {x: 1, y: io}" in lines
    assert "\r" not in text
    assert all(line == line.rstrip() for line in lines)
    assert emit({"a": [1]}) == emit({"a": [1]})
