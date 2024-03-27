from __future__ import annotations

import shapely as shp
from shapely.geometry import Polygon

# from .diagram_utils import Event, EventType, Interface, State, dtPoint
from .diagram_utils import State, dtPoint

"""
    shapely implementation of state resolution; currently deprecated
"""

raise NotImplementedError("Deprecated in favor of direct state resolution.")


class ShapedState:
    def __init__(self, state: State, polygon: Polygon):
        self.state = state
        self.polygon = polygon


class StateHandler:
    def __init__(
        self, simulation_time: float, max_dist: float, init_density: float, init_flow: float
    ):
        raise NotImplementedError("not implemented")
        self.simulation_time = simulation_time
        self.max_dist = max_dist

        # idea: to determine what polygon something is in, iterate from the back (more up to date)
        # the base (start) that everything should be in is just the initial conditions
        # need to make sure only one state of each thing is in here at a time
        self.states: list[ShapedState] = [
            ShapedState(
                State(init_density, init_flow),
                shp.Polygon(
                    (
                        (
                            0,
                            -self.max_dist,
                        ),  # we allow max_dist to go negative to account for off-border interfaces (i think this is the limit of how low it can go)  # noqa: E501
                        (self.simulation_time, -self.max_dist),
                        (self.simulation_time, self.max_dist),
                        (0, self.max_dist),
                        (0, -self.max_dist),
                    )
                ),
            )
        ]

        self.mapper: dict[int, int] = dict()
        self.mapper[self.states[0].id] = 0

    def resolve_point(self, point: dtPoint) -> State:
        for i in range(len(self.states) - 1, -1, -1):
            if self.states[i].polygon.contains(point.convert_to_shapely()):
                return self.states[i]

        assert False  # should never get here
