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


def test_layout_separates_roles(tmp_path: Path) -> None:
    layout = RuntimeLayout.under(tmp_path / "bin", tmp_path / "data")
    roles = {layout.binaries, layout.singers, layout.cache, layout.staging, layout.outputs}
    assert len(roles) == 5
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
    stale = find_stale(tmp_path, lambda pid: pid == 1)
    assert stale == [dead.path, broken]
    assert live.path not in stale
    assert find_stale(tmp_path / "missing", lambda pid: False) == []


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
