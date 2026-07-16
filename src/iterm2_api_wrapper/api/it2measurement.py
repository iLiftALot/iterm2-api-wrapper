from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, TypeGuard, overload

from iterm2 import util


if TYPE_CHECKING:
    from iterm2.api_pb2 import Global___Coord, Global___CoordRange


class PointLike(Protocol):
    @property
    def x(self) -> int: ...
    @property
    def y(self) -> int: ...


class CoordRangeLike(Protocol):
    @property
    def start(self) -> PointLike: ...
    @property
    def end(self) -> PointLike: ...


class Point(util.Point):
    def __init__(self, x: int, y: int):
        super().__init__(x, y)

    @staticmethod
    def from_coord_proto(proto: Global___Coord):
        return Point(proto.x, proto.y)


def _point_from(point: PointLike) -> util.Point:
    if isinstance(point, util.Point):
        return point

    return Point(point.x, point.y)


def _is_point_like(value: object) -> TypeGuard[PointLike]:
    return isinstance(getattr(value, "x", None), int) and isinstance(getattr(value, "y", None), int)


def _is_coord_range_like(value: object) -> TypeGuard[CoordRangeLike]:
    return _is_point_like(getattr(value, "start", None)) and _is_point_like(getattr(value, "end", None))


class CoordRange(util.CoordRange):
    @overload
    def __init__(self, range: CoordRangeLike, /) -> None: ...
    @overload
    def __init__(self, start: PointLike, end: PointLike, /) -> None: ...

    def __init__(self, range_or_start: CoordRangeLike | PointLike, end: PointLike | None = None, /) -> None:
        if end is None:
            if not _is_coord_range_like(range_or_start):
                raise TypeError("CoordRange() expected a range-like object or start/end point-like objects")

            start_point = _point_from(range_or_start.start)
            end_point = _point_from(range_or_start.end)
        else:
            if not _is_point_like(range_or_start) or not _is_point_like(end):
                raise TypeError("CoordRange() expected start and end point-like objects")

            start_point = _point_from(range_or_start)
            end_point = _point_from(end)

        super().__init__(start_point, end_point)

    @staticmethod
    def from_proto(proto: Global___CoordRange) -> CoordRange:
        return CoordRange(proto)

    @property
    def total_lines(self) -> int:
        """Return the number of screen rows covered by an iTerm2 coordinate range."""
        start, end = self.start, self.end
        return (end.y - start.y) + (1 if end.x > 0 else 0)

    @property
    def is_inverted(self) -> bool:
        """Return True when a coordinate range ends before it starts."""
        start, end = self.start, self.end
        return end.y < start.y or (end.y == start.y and end.x < start.x)

    @property
    def is_empty(self) -> bool:
        """Return True when this range contains no screen rows."""
        return self.total_lines <= 0

    @classmethod
    def from_points(cls, start: PointLike, end: PointLike) -> CoordRange:
        return cls(start, end)

    @staticmethod
    def point_key(point: PointLike) -> tuple[int, int]:
        """Return a sortable key for an iTerm2 :class:`Point`."""
        return (int(point.y), int(point.x))

    @classmethod
    def point_lt(cls, left: PointLike, right: PointLike) -> bool:
        """Return True when `left` is before `right`."""
        return cls.point_key(left) < cls.point_key(right)

    @classmethod
    def point_lte(cls, left: PointLike, right: PointLike) -> bool:
        """Return True when `left` is before or equal to `right`."""
        return cls.point_key(left) <= cls.point_key(right)

    def contains_point(self, point: PointLike) -> bool:
        """Return True when :class:`Point` is inside this half-open coordinate range."""
        return self.point_lte(self.start, point) and self.point_lt(point, self.end)

    def clipped_before(self, point: PointLike) -> CoordRange:
        """Return this range clipped to end before :class:`Point` when :class:`Point` is inside it."""
        if not self.contains_point(point):
            return self

        return type(self).from_points(self.start, point)
