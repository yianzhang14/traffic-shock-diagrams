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

ABS_TOL = 1e-4


def float_isclose(x: float, y: float) -> bool:
    return math.isclose(x, y, abs_tol=ABS_TOL)


@dataclass
class dtPoint:
    """
    This class represents a point on the time-position diagram.
    Generally, time is the x-axis, and position is the y-axis.

    Attributes:
        time (float): the time (x) of the point (seconds)
        poisition (float): the position (y) of the point (meters)
    """

    time: float
    position: float

    def __eq__(self, other: dtPoint):
        """Overload of the equality operator for points.
        Two points are equal if their time/position are equivalent up to floating point precision.

        Args:
            other (dtPoint): the point to compare with

        Returns:
            bool: whether or not the points are equal
        """
        # two points are equal if their time and position are equal, up to floating point error
        return float_isclose(self.time, other.time) and float_isclose(self.position, other.position)

    def get_slope(self, other: dtPoint) -> float:
        """Get the slope between two dtPoints, assuming position is y and time is x.
        Throws an error if the points have equivalent times, up to floating poitn precision.

        Args:
            other (dtPoint): the other point to get the slope between

        Returns:
            float: the slope between this point and the other
        """
        if float_isclose(self.time, other.time):
            raise ValueError("The two points have an invalid slope, as they share a time")

        return (self.position - other.position) / (self.time - other.time)

    def convert_to_shapely(self) -> shp.Point:
        """Converts a point to a shapely shp.Point object.

        Returns:
            shp.Point: the point in shp.Point form
        """
        return shp.Point(self.time, self.position)

    def __hash__(self) -> int:
        return hash((round(self.time, 5), round(self.position, 5)))


class EventType(Enum):
    """This enum encodes the possible types an event could be."""

    intersection = 1  # event where two interfaces interesect
    capacity = 2  # event where capacity changes (user-created typically)


@dataclass
@total_ordering
class Event(ABC):
    """The abstract base class for all events.

    Attributes:
        point (dtPoint): the point the event is taking place at
        type (EventType): the type of event it is
    """

    point: dtPoint
    type: EventType
    # priority to determine order to handle events; want intersection events to be processed first
    # to handle weird state resolutions
    priority: int

    def __eq__(self, other: Event) -> bool:
        """Overload of equality for events. Two events are equal if they have the same time.
        Only defined for comparison/sorting convenience.

        Args:
            other (Event): the event to compare with

        Returns:
            bool: whether or not the events are equal
        """
        return self.point == other.point and self.priority == other.priority

    def __lt__(self, other: Event) -> bool:
        """Overload of the less than operator for events. One event is less than another
        if the time of the former is less than that of the latter.

        Args:
            other (Event): the event to compare with

        Returns:
            bool: whether or not this event is less than the other
        """

        if self == other:
            return False

        if float_isclose(self.point.time, other.point.time):
            if self.priority == other.priority:
                return self.point.position < other.point.position

            return self.priority < other.priority

        return self.point.time < other.point.time


@dataclass
class IntersectionEvent(Event):
    """A specialization of event for intersection events."""

    interfaces: list[Interface]

    def __init__(self, point: dtPoint, interfaces: list[Interface]):
        """IntersectionEvent constructor.

        Args:
            point (dtPoint): the point this event occurs at
            interfaces (list[Interface]): the interfaces that are intersecting at this event
        """

        super().__init__(point, EventType.intersection, 1)

        self.interfaces = interfaces  # always make the acting interface the first one


@dataclass
class CapacityEvent(Event):
    """Specialization of Event for capacity events where capacity is changing.
    Prior & posterior capacity typically set by fiat upon user input.

    These are necessarily associated with some interface, by assumption.
    """

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
        """Constructor of a CapacityEvent.

        Args:
            point (dtPoint): The point the capacity event is located at.
            interface (Interface): The interface the capacity event was generated by.
            prior_capacity (float, optional): The capacity preceding the event (vehicles / second).
            Must be positive or -1. Defaults to -1.
            posterior_capacity (float, optional): the capacity following the event
            (vehicles / second). Must be positive or -1. Defaults to -1.
        """
        super().__init__(point, EventType.capacity, 2)

        self.interface = interface

        # by default, we will make in_cap == -1 mean any capacity
        # out_cap == -1 will mean the max possible capacity after the event
        if not (prior_capacity == -1 or prior_capacity >= 0):
            raise ValueError("Prior capacity not non-negative or -1.")

        if not (posterior_capacity == -1 or posterior_capacity >= 0):
            raise ValueError("Posterior capacity not non-negative or -1. ")

        self.prior_capacity = prior_capacity
        self.posterior_capacity = posterior_capacity


@dataclass
class State:
    """A class encapsulating the idea of a state, a section of the fundamental diagram with
    constant density and flow.

    Attributes:
        density (float): density of the state (vehicles / meter)
        flow (float): flow of the state (vehicles / second)
    """

    density: float
    flow: float

    id: int = field(default_factory=count().__next__, init=False)  # unique id

    def get_interface_slope(self, other: State) -> float:
        """Gets the slope between this state and another state. Used for determining the
        slope of an interface in the dt-space between these two states.

        Args:
            other (State): State to get the slope with

        Returns:
            float: slope between these two states (meters / second)
        """
        return (self.flow - other.flow) / (self.density - other.density)

    def __eq__(self, other) -> bool:
        """Overload of state equality. Two states are equal if they have the same density
        and flow values, up to floating point error.

        Args:
            other (other): state to compare with

        Returns:
            bool: whether or not they are equal
        """
        return float_isclose(self.density, other.density) and float_isclose(self.flow, other.flow)


class Interface:  # boundary between two states
    """This class encapsulates the idea of an interface in the dt-space, a linear boundary between
    two states. This linear boundary is fully defined by a point and a slope in the dt-space.

    The above/below states refer to the states directly above/below the interface in the typical
    dt-space orientation.

    The bounds define the endpoints. The first bound is the lower bound and the second is the
    upper bound in terms of the time-extent of the interface in dt-space.

    Not applicable to vertical interfaces.
    """

    def __init__(
        self,
        point: dtPoint,
        slope: float,
        above: Optional[State],
        below: Optional[State],
        bounds: tuple[Optional[dtPoint], Optional[dtPoint]] = (None, None),
    ):
        """Constructor of an Interface

        Args:
            point (dtPoint): a point that the interface lies on
            slope (float): the slope of the interface
            above (Optional[State]): the state above the interface, if any
            below (Optional[State]): the state below the interface, if any
            bounds (tuple[Optional[dtPoint], Optional[dtPoint]], optional): (left
            time bound, right time bound) of the interface, if any. Defaults to (None, None).
        """
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
        """Function to determine whether an interface contains a given point
        as an endpoint (bound).

        Args:
            point (dtPoint): point to check

        Returns:
            bool: whether or not the point is an endpoint of the interface
        """

        for endpoint in self.endpoints:
            if endpoint and endpoint == point:
                return True

        return False

    def intersection(self, other: Interface) -> Optional[dtPoint]:
        """Determines the point of intersection between this interface and another, if any.

        Args:
            other (Interface): interface to find an intersection with

        Returns:
            Optional[dtPoint]: the point of intersection, if it exists (None if it doesn't)
        """
        if float_isclose(self.slope, other.slope):
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
        assert float_isclose(pos1, pos2)

        return dtPoint(time_of_intersection, pos1)

    def get_pos_at_time(self, time: float) -> Optional[float]:
        """Gets the position of an the interface line/boundary at a given time, if it the
        interface is defined at the given time (time within the bounds of the interface).

        Args:
            time (float): time to query

        Returns:
            Optional[float]: the position of the interface at the time, if defined; None otherwise
        """
        if (self.endpoints[1] and self.endpoints[1].time < time) or (
            self.endpoints[0] and self.endpoints[0].time > time
        ):
            return None

        return self.point.position + self.slope * (time - self.point.time)

    def add_cutoff(self, lower: Optional[dtPoint], upper: Optional[dtPoint]):
        """Adds a cutoff to the interface. The points must be along the line defined by
        the interface.

        Args:
            lower (Optional[dtPoint]): the lower cutoff to add (w.r.t. time), if any
            upper (Optional[dtPoint]): the upper cutoff to add (w.r.t. time), if any
        """
        # error checking for for argument validity
        if not (not lower or float_isclose(self.slope, self.point.get_slope(lower))):
            raise ValueError(
                "The lower bound supplied is invalid--does not fall along the interface line."
            )

        if not (not upper or float_isclose(self.slope, self.point.get_slope(upper))):
            raise ValueError(
                "The upper bound supplied is invalid--does not fall along the interface line."
            )

        if not (lower is None or upper is None or (lower.time < upper.time)):
            raise ValueError(
                "The lower and upper bounds are not oriented correctly with respect to time."
            )

        # do nothing if there is nothing supplied
        if lower is None and upper is None:
            return

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
        """Determines whether this interface is functionally equivalent to the given interface.
        This occurs if the interfaces define the same.

        Args:
            other (Interface): interface to compare

        Returns:
            bool: whether or not the interfaces are functionally equivalent
        """
        # if the two interfaces are disjoint in terms of endpoints, they are not equivalent
        if (
            other.endpoints[1]
            and self.endpoints[0]
            and other.endpoints[1].time < self.endpoints[0].time
        ) or (
            self.endpoints[1]
            and other.endpoints[0]
            and self.endpoints[1].time < other.endpoints[0].time
        ):
            return False

        # if they share a point, they are equivalent if they share a slope
        if other.point == self.point:
            return float_isclose(other.slope, self.slope)

        # if they share a time (do this since getting slope is undefined), they are equivalent
        # if they share a position and a slope
        if float_isclose(other.point.time, self.point.time):
            return float_isclose(other.point.position, self.point.position) and float_isclose(
                self.slope, other.slope
            )

        return float_isclose(self.point.get_slope(other.point), other.slope) and float_isclose(
            other.slope, self.slope
        )
