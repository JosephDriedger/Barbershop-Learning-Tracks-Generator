import io
from dataclasses import fields
from typing import IO, cast

import pytest

from barbershop_tracks.core.errors import ScoreResourceLimitError
from barbershop_tracks.core.musicxml.limits import (
    DEFAULT_LIMITS,
    MIB,
    LoaderLimits,
    describe_size,
    exceeds_ratio,
    read_limited,
)


def test_default_limits_use_binary_units() -> None:
    assert DEFAULT_LIMITS.max_score_bytes == 50 * 1024 * 1024
    assert DEFAULT_LIMITS.max_total_bytes == 50 * 1024 * 1024
    assert DEFAULT_LIMITS.max_compression_ratio == 100
    assert MIB == 1024 * 1024


def test_limits_are_named_and_configurable() -> None:
    names = {f.name for f in fields(LoaderLimits)}
    assert {"max_score_bytes", "max_total_bytes", "max_compression_ratio"} <= names
    custom = LoaderLimits(max_score_bytes=10, max_compression_ratio=5)
    assert custom.max_score_bytes == 10
    assert custom.max_compression_ratio == 5


@pytest.mark.parametrize("bad", [0, -1, True, 1.5])
def test_limits_reject_invalid_values(bad: object) -> None:
    with pytest.raises(ValueError, match="max_score_bytes"):
        LoaderLimits(max_score_bytes=bad)  # type: ignore[arg-type]


def test_describe_size() -> None:
    assert describe_size(50 * MIB) == "50 MiB"
    assert describe_size(1000) == "1000 bytes"
    assert describe_size(MIB + 1) == f"{MIB + 1} bytes"


@pytest.mark.parametrize(
    ("decompressed", "compressed", "expected"),
    [
        (100, 1, False),  # exactly 100:1 is allowed
        (101, 1, True),  # just above
        (10_000, 100, False),
        (10_001, 100, True),
        (5, 5, False),
        (1, 0, True),  # data from "zero" compressed bytes
        (0, 0, False),
    ],
)
def test_ratio_boundary_is_exact(decompressed: int, compressed: int, expected: bool) -> None:
    assert exceeds_ratio(decompressed, compressed, 100) is expected


def test_read_limited_exactly_at_limit_is_allowed() -> None:
    assert read_limited(io.BytesIO(b"x" * 10), 10, what="data", path=None) == b"x" * 10


def test_read_limited_one_byte_over_is_rejected() -> None:
    with pytest.raises(ScoreResourceLimitError, match="larger than the limit"):
        read_limited(io.BytesIO(b"x" * 11), 10, what="data", path=None)


def test_read_limited_stops_early_on_endless_streams() -> None:
    class Endless:
        reads = 0

        def read(self, size: int = -1) -> bytes:
            Endless.reads += 1
            return b"x" * size

    with pytest.raises(ScoreResourceLimitError):
        read_limited(cast(IO[bytes], Endless()), 100_000, what="data", path=None)
    assert Endless.reads < 50  # stopped after the limit instead of reading forever


def test_read_limited_empty_stream() -> None:
    assert read_limited(io.BytesIO(b""), 10, what="data", path=None) == b""
