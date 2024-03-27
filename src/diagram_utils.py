from __future__ import annotations

import math
from abc import ABC
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
    intersection = 1
    capacity = 2


@dataclass
@total_ordering
class Event(ABC):
    point: dtPoint
    type: EventType

    def __eq__(self, other: Event) -> bool:
        return self.point == other.point

    def __lt__(self, other: Event) -> bool:
        return (self.point.time < other.point.time) or (
            self.point.position < other.point.position
        )  # tiebreaker


@dataclass
class IntersectionEvent(Event):
    interfaces: list[Interface]
    disabled: bool

    def __init__(self, point: dtPoint, interfaces: list[Interface], disabled: bool = False):
        super().__init__(point, EventType.intersection)

        self.interfaces = interfaces  # always make the acting interface the first one
        self.disabled = disabled


@dataclass
class CapacityEvent(Event):
    prior_capacity: float
    posterior_capacity: float
    interface: Interface

    def __init__(
        self,
        point: dtPoint,
        interface: Interface,
        prior_capacity: float = -1,
        posterior_capacity: float = -1,
    ):
        super().__init__(point, EventType.capacity)

        self.interface = interface

        # by default, we will make in_cap == -1 mean any capacity
        # out_cap == -1 will mean the max possible capacity after the event
        assert prior_capacity == -1 or prior_capacity >= 0
        assert posterior_capacity == -1 or posterior_capacity >= 0

        self.prior_capacity = prior_capacity
        self.posterior_capacity = posterior_capacity


@dataclass
class State:
    density: float
    flow: float

    id: int = field(default_factory=count().__next__, init=False)  # unique id

    def get_speed(self) -> float:
        return self.flow / self.density

    def get_interface_slope(self, other: State) -> float:
        return (self.flow - other.flow) / (self.density - other.density)


@total_ordering
class Interface:  # boundary between two states
    def __init__(
        self,
        point: dtPoint,
        slope: float,
        above: Optional[State],
        below: Optional[State],
        bounds: tuple[Optional[dtPoint], Optional[dtPoint]] = (None, None),
    ):
        self.point = point
        self.slope = slope

        # self.bounds: list[tuple[dtPoint, dtPoint]] = bounds  # limit 2, number of endpoints
        self.endpoints: list[dtPoint] = [
            bounds[0],
            bounds[1],
        ]  # lower, upper (with respect to time)

        self.above = above
        self.below = below

    def __str__(self) -> str:
        return f"Interface({self.point}, {self.slope})"

    def has_endpoint(self, point: dtPoint) -> bool:
        for endpoint in self.endpoints:
            if endpoint and endpoint == point:
                return True

        return False

    def intersection(self, other: Interface) -> Optional[dtPoint]:
        if math.isclose(self.slope, other.slope):
            return None

        # this is the formula for the intersection point (x)
        # of two lines in point-slope form
        time_of_intersection = (
            other.point.position
            - other.slope * other.point.time
            - self.point.position
            + self.slope * self.point.time
        ) / (self.slope - other.slope)

        # they intersect if there is a valid position at both times
        # for both interface definitions
        pos1 = self.get_pos_at_time(time_of_intersection)
        pos2 = other.get_pos_at_time(time_of_intersection)

        if not pos1 or not pos2:
            return None

        # this should be true by definition of intersection
        assert math.isclose(pos1, pos2)

        return dtPoint(time_of_intersection, pos1)

    def get_pos_at_time(self, time: float) -> Optional[float]:
        if (self.endpoints[1] and self.endpoints[1].time < time) or (
            self.endpoints[0] and self.endpoints[0].time > time
        ):
            return None

        return self.point.position + self.slope * (time - self.point.time)

    def add_cutoff(self, lower: Optional[dtPoint], upper: Optional[dtPoint]):
        # assert that this is a valid cutoff
        assert not lower or math.isclose(self.slope, self.point.get_slope(lower))  # along same line
        assert not upper or math.isclose(self.slope, self.point.get_slope(upper))  # along same line
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

    def equivalent_to(self, other: Interface) -> bool:
        if other.point == self.point:
            return math.isclose(other.slope, self.slope)

        if math.isclose(other.point.time, self.point.time):
            return math.isclose(other.point.position, self.point.position)

        return math.isclose(self.point.get_slope(other.point), other.slope) and math.isclose(
            other.slope, self.slope
        )

    def __eq__(self, other: Interface) -> bool:
        return self.point == other.point and self.slope == other.slope

    def __lt__(self, other: Interface) -> bool:
        return self.point < other.point and self.slope < other.slope
