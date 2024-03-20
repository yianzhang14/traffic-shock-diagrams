from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from functools import total_ordering
from itertools import count
from typing import Optional

import shapely as shp

# from .fundamental_diagram import FundamentalDiagram


@dataclass
class dtPoint:
    time: float
    position: float

    def unpack(self) -> tuple[float, float]:
        return (self.time, self.position)

    def __eq__(self, other: dtPoint):
        return math.isclose(self.time, other.time) and math.isclose(self.position, other.position)

    def get_slope(self, other: dtPoint) -> float:
        assert not math.isclose(self.time, other.time)

        return (self.position - other.position) / (self.time - other.time)

    def convert_to_shapely(self) -> shp.Point:
        return shp.Point(self.time, self.position)


class EventType(Enum):
    user: 1
    generated: 2


@dataclass
@total_ordering
class Event:
    # a (hardcoded) event is a change in capacity; need to know incoming and outcoming (step up or a step down)
    # idea: abstract events even more to be literal changes in capacity (for hardcoded); a traffic light would have two
    # for the generated ones, they are intersections between interfaces -- cut things off and will generate a new one
    # if there wasn't a new one, then there would not be an intersection
    point: dtPoint
    type: EventType
    interfaces: Optional[list[Interface]] = []  # can you have more than 2 intersecting?

    def __eq__(self, other: Event) -> bool:
        return self.point == other.point

    def __lt__(self, other: Event) -> bool:
        return (self.point.time < other.point.time) or (
            self.point.position < other.point.position
        )  # tiebreaker


@dataclass
class State:
    density: float
    flow: float

    id: int = field(default_factory=count().__next__, init=False)  # unique id

    def get_speed(self) -> float:
        return self.flow / self.density

    def get_interface_speed(self, other: State) -> float:
        return (self.flow - other.flow) / (self.density - other.density)


class Interface:  # boundary between two states
    def __init__(
        self,
        point: dtPoint,
        slope: float,
        above: State = None,
        below: State = None,
        bounds: tuple[dtPoint, dtPoint] = [],
    ):
        self.point = point
        self.slope = slope

        self.above = above
        self.below = below

        # self.bounds: list[tuple[dtPoint, dtPoint]] = bounds  # limit 2, number of endpoints
        self.endpoints: list[dtPoint] = [None, None]  # lower, upper (with respect to time)

    def get_pos_at_time(self, time: float) -> Optional[float]:
        if (self.endpoints[1] and self.endpoints[1].time < time) or (
            self.endpoints[0] and self.endpoints[0].time > time
        ):
            return None

        return self.point.position + self.slope * (time - self.point.time)

    def add_cutoff(self, lower: Optional[dtPoint], upper: Optional[dtPoint]):
        # assert that this is a valid cutoff
        assert math.isclose(self.slope, self.point.get_slope(lower))  # along same line
        assert math.isclose(self.slope, self.point.get_slope(upper))  # along same line
        assert not (lower is None and upper is None)  # don't accept redundant cutoffs
        assert (
            lower is None or upper is None or (lower.time < upper.time)
        )  # have lower and upper be oriented correctly

        # update point to always be within the points
        if lower is None:
            self.point = upper
        else:
            self.point = lower

        # update the endpoint bounds
        if lower is not None:
            if self.endpoints[0] is None:
                self.endpoints[0] = lower
            elif self.endpoints[0].time < lower.time:
                self.endpoints[0] = lower

        if upper is not None:
            if self.endpoints[1] is None:
                self.endpoints[1] = upper
            elif self.endpoints[1].time > upper.time:
                self.endpoints[1] = upper

    def __eq__(self, other: Interface) -> bool:
        if other.point == self.point:
            return math.isclose(other.slope, self.slope)

        return self.point.get_slope(other.point) == other.slope and other.slope == self.slope
