"""The Microsoft Visual C++ runtime BLT does not ship: detection and the missing-runtime message."""

import pytest

from barbershop_tracks.core.runtime.vcruntime import REQUIRED, RuntimeStatus, runtime_status


def test_a_runtime_at_or_above_the_requirement_is_fine() -> None:
    assert RuntimeStatus(REQUIRED).ok
    assert RuntimeStatus((14, 51, 36247)).ok
    assert RuntimeStatus((15, 0, 1)).ok


def test_an_older_or_missing_runtime_is_not_and_says_what_is_needed() -> None:
    assert not RuntimeStatus((14, 40, 33810)).ok
    assert not RuntimeStatus((14, 44, 35210)).ok
    assert "too old" in RuntimeStatus((14, 40, 33810)).text
    assert "14.44.35211" in RuntimeStatus(None).text
    assert "not installed" in RuntimeStatus(None).text


def test_this_machine_reports_a_runtime_or_none_without_raising() -> None:
    status = runtime_status()
    assert status.installed is None or len(status.installed) == 3


def test_off_windows_the_check_does_not_apply(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.platform", "linux")
    assert runtime_status().ok
