from __future__ import annotations
from iterm2 import util
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from iterm2 import Point


class CoordRange(util.CoordRange):
    def __init__(self, range: util.CoordRange) -> None:
        super().__init__(range.start, range.end)

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
    def from_points(cls, start: Point, end: Point) -> CoordRange:
        obj = cls.__new__(cls)
        util.CoordRange.__init__(obj, start, end)
        return obj

    @staticmethod
    def point_key(point: Point) -> tuple[int, int]:
        """Return a sortable key for an iTerm2 :class:`Point`."""
        return (int(point.y), int(point.x))

    @classmethod
    def point_lt(cls, left: Point, right: Point) -> bool:
        """Return True when `left` is before `right`."""
        return cls.point_key(left) < cls.point_key(right)

    @classmethod
    def point_lte(cls, left: Point, right: Point) -> bool:
        """Return True when `left` is before or equal to `right`."""
        return cls.point_key(left) <= cls.point_key(right)

    def contains_point(self, point: Point) -> bool:
        """Return True when :class:`Point` is inside this half-open coordinate range."""
        return self.point_lte(self.start, point) and self.point_lt(point, self.end)

    def clipped_before(self, point: Point) -> CoordRange:
        """Return this range clipped to end before :class:`point` when :class:`point` is inside it."""
        if not self.contains_point(point):
            return self

        return type(self).from_points(self.start, point)
