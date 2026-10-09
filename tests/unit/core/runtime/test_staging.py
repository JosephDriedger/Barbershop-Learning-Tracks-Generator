import os
import time
from pathlib import Path

import pytest

from barbershop_tracks.core.runtime import (
    RuntimeLayout,
    StagingArea,
    StagingError,
    find_stale,
    publish,
    remove_staging,
)
from barbershop_tracks.core.runtime.process_identity import process_start_time
from barbershop_tracks.core.runtime.staging import (
    UNREADABLE_MARKER_GRACE_SECONDS,
    cleanup_stale,
    publish_directory,
)


def test_layout_separates_roles(tmp_path: Path) -> None:
    layout = RuntimeLayout.under(tmp_path / "bin", tmp_path / "data")
    roles = {
        layout.binaries,
        layout.runtime,
        layout.singers,
        layout.cache,
        layout.staging,
        layout.outputs,
    }
    assert len(roles) == 6
    assert layout.singers.parent == layout.data


def test_create_writes_marker_and_refuses_duplicates(tmp_path: Path) -> None:
    area = StagingArea.create(tmp_path, "job1", pid=42)
    assert area.path.name == ".staging-job1-42"
    assert (area.path / "staging.json").is_file()
    with pytest.raises(StagingError) as error:
        StagingArea.create(tmp_path, "job1", pid=42)
    assert error.value.code == "STAGING_EXISTS"


@pytest.mark.parametrize("name", ["", "a/b", "a\\b", ".hidden", "c:x"])
def test_bad_job_names(tmp_path: Path, name: str) -> None:
    with pytest.raises(StagingError) as error:
        StagingArea.create(tmp_path, name)
    assert error.value.code == "STAGING_JOB_NAME"


def test_stale_detection(tmp_path: Path) -> None:
    live = StagingArea.create(tmp_path, "a", pid=1)
    dead = StagingArea.create(tmp_path, "b", pid=2)
    broken = tmp_path / ".staging-c-3"
    broken.mkdir()
    (tmp_path / "outputs").mkdir()
    stale = find_stale(tmp_path, lambda m: m.pid == 1, now=time.time() + 10_000)
    assert stale == [dead.path, broken]
    assert live.path not in stale
    assert find_stale(tmp_path / "missing", lambda m: False) == []


def test_publish_is_atomic_and_drops_marker(tmp_path: Path) -> None:
    area = StagingArea.create(tmp_path / "staging", "j", pid=7)
    (area.path / "tenor.wav").write_bytes(b"x")
    target = tmp_path / "outputs" / "song"
    publish(area, target)
    assert [p.name for p in target.iterdir()] == ["tenor.wav"]
    assert not area.path.exists()


def test_publish_refuses_existing_destination(tmp_path: Path) -> None:
    area = StagingArea.create(tmp_path / "staging", "j", pid=7)
    target = tmp_path / "out"
    target.mkdir()
    with pytest.raises(StagingError) as error:
        publish(area, target)
    assert error.value.code == "PUBLISH_DESTINATION_EXISTS"
    assert area.path.exists()


def test_remove_only_staging_directories(tmp_path: Path) -> None:
    area = StagingArea.create(tmp_path, "j", pid=7)
    (area.path / "partial.wav").write_bytes(b"x")
    remove_staging(area.path)
    assert not area.path.exists()
    other = tmp_path / "outputs"
    other.mkdir()
    with pytest.raises(StagingError) as error:
        remove_staging(other)
    assert error.value.code == "STAGING_NOT_STAGING"


# --- ownership that survives pid reuse ---


def test_our_own_staging_directory_is_active_and_never_listed(tmp_path: Path) -> None:
    mine = StagingArea.create(tmp_path, "mine")
    assert mine.marker.pid == os.getpid()
    assert mine.marker.start_time == process_start_time(os.getpid())
    assert find_stale(tmp_path) == []
    assert cleanup_stale(tmp_path) == []
    assert mine.path.is_dir()


def test_a_recycled_pid_with_another_start_time_is_stale(tmp_path: Path) -> None:
    start = process_start_time(os.getpid())
    assert start is not None
    impostor = StagingArea.create(tmp_path, "old", pid=os.getpid(), start_time=start + 12345)
    genuine = StagingArea.create(tmp_path, "new", pid=os.getpid(), start_time=start)
    assert find_stale(tmp_path) == [impostor.path]
    assert genuine.path not in cleanup_stale(tmp_path)
    assert not impostor.path.exists()
    assert genuine.path.exists()


def test_a_pid_that_is_not_running_is_stale(tmp_path: Path) -> None:
    gone = StagingArea.create(tmp_path, "dead", pid=2_000_000_000, start_time=1)
    assert find_stale(tmp_path) == [gone.path]


def test_an_unreadable_marker_is_stale_only_after_the_grace_period(tmp_path: Path) -> None:
    fresh = tmp_path / ".staging-x-1"
    fresh.mkdir()
    assert find_stale(tmp_path) == []
    later = time.time() + UNREADABLE_MARKER_GRACE_SECONDS + 1
    assert find_stale(tmp_path, now=later) == [fresh]


def test_a_directory_being_created_is_never_taken_for_staging(tmp_path: Path) -> None:
    (tmp_path / ".creating-abc").mkdir()
    assert find_stale(tmp_path, now=time.time() + 10_000) == []


# --- publication keeps the previous result unless the new one is complete ---


def test_publish_directory_replaces_only_when_asked(tmp_path: Path) -> None:
    old = tmp_path / "outputs" / "song"
    old.mkdir(parents=True)
    (old / "old.wav").write_bytes(b"old")
    new = tmp_path / "staging" / "stems"
    new.mkdir(parents=True)
    (new / "new.wav").write_bytes(b"new")
    with pytest.raises(StagingError) as error:
        publish_directory(new, old)
    assert error.value.code == "PUBLISH_DESTINATION_EXISTS"
    assert (old / "old.wav").read_bytes() == b"old"
    publish_directory(new, old, replace=True)
    assert [p.name for p in old.iterdir()] == ["new.wav"]
    assert not new.exists()
    assert [p.name for p in old.parent.iterdir()] == ["song"]  # nothing left aside


def test_a_failed_replacement_restores_the_previous_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = tmp_path / "outputs" / "song"
    old.mkdir(parents=True)
    (old / "old.wav").write_bytes(b"old")
    new = tmp_path / "staging" / "stems"
    new.mkdir(parents=True)
    real_rename = Path.rename

    def flaky(self: Path, target: Path) -> Path:
        if self == new:
            raise OSError("disk full")
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", flaky)
    with pytest.raises(StagingError) as error:
        publish_directory(new, old, replace=True)
    assert error.value.code == "PUBLISH_FAILED"
    assert (old / "old.wav").read_bytes() == b"old"
