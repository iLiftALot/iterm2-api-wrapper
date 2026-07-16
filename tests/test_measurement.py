from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from iterm2 import api_pb2, util

from iterm2_api_wrapper.api.it2measurement import CoordRange, Point


@dataclass(frozen=True)
class PointStub:
    x: int
    y: int


@dataclass(frozen=True)
class CoordRangeStub:
    start: PointStub
    end: PointStub


def point(x: int, y: int) -> PointStub:
    return PointStub(x=x, y=y)


def test_point_and_coord_range_convert_iterm_protobuf_coordinates() -> None:
    proto = api_pb2.GetPromptResponse().output_range
    proto.start.x = 1
    proto.start.y = 2
    proto.end.x = 3
    proto.end.y = 4

    converted_point = Point.from_coord_proto(proto.start)
    converted_range = CoordRange.from_proto(proto)

    assert isinstance(converted_point, util.Point)
    assert (converted_point.x, converted_point.y) == (1, 2)
    assert isinstance(converted_range, util.CoordRange)
    assert (converted_range.start.x, converted_range.start.y) == (1, 2)
    assert (converted_range.end.x, converted_range.end.y) == (3, 4)


def test_coord_range_accepts_range_like_and_start_end_point_like_objects() -> None:
    start = point(2, 3)
    end = point(4, 5)

    from_range = CoordRange(CoordRangeStub(start=start, end=end))
    from_points = CoordRange(start, end)
    from_factory = CoordRange.from_points(start, end)

    for coord_range in (from_range, from_points, from_factory):
        assert isinstance(coord_range.start, util.Point)
        assert isinstance(coord_range.end, util.Point)
        assert (coord_range.start.x, coord_range.start.y) == (2, 3)
        assert (coord_range.end.x, coord_range.end.y) == (4, 5)


def test_coord_range_rejects_invalid_construction_shapes() -> None:
    with pytest.raises(TypeError, match="range-like object"):
        CoordRange(object())  # pyright: ignore[reportArgumentType]

    with pytest.raises(TypeError, match="start and end point-like objects"):
        CoordRange(point(0, 0), object())  # pyright: ignore[reportArgumentType]

    with pytest.raises(TypeError, match="start and end point-like objects"):
        CoordRange(SimpleNamespace(x="0", y=0), point(1, 1))  # pyright: ignore[reportArgumentType]


def test_coord_range_geometry_and_half_open_clipping() -> None:
    coord_range = CoordRange(Point(2, 3), Point(4, 5))

    assert coord_range.total_lines == 3
    assert coord_range.is_empty is False
    assert coord_range.is_inverted is False
    assert coord_range.contains_point(point(2, 3)) is True
    assert coord_range.contains_point(point(0, 4)) is True
    assert coord_range.contains_point(point(4, 5)) is False
    assert CoordRange.point_key(point(8, 7)) == (7, 8)
    assert CoordRange.point_lt(point(9, 6), point(0, 7)) is True
    assert CoordRange.point_lte(point(9, 6), point(9, 6)) is True

    clipped = coord_range.clipped_before(point(1, 4))
    assert clipped is not coord_range
    assert (clipped.end.x, clipped.end.y) == (1, 4)
    assert coord_range.clipped_before(point(4, 5)) is coord_range

    empty = CoordRange(Point(0, 2), Point(0, 2))
    inverted = CoordRange(Point(3, 2), Point(0, 2))
    assert empty.is_empty is True
    assert empty.is_inverted is False
    assert inverted.is_empty is True
    assert inverted.is_inverted is True
