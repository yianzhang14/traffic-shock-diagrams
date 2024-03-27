from __future__ import annotations

import math

import matplotlib.pyplot as plt
import numpy as np
from scipy import interpolate

from .custom_types import Axes, Figure
from .diagram_utils import State


class FundamentalDiagram:
    def __init__(self, freeflow_speed: float, jam_density: float, traffic_wave_speed: float):
        assert freeflow_speed > 0 and jam_density > 0 and traffic_wave_speed > 0
        assert freeflow_speed > traffic_wave_speed

        self.freeflow_speed = freeflow_speed
        self.jam_density = jam_density
        self.trafficwave_speed = traffic_wave_speed

        # solve system of linear equations for the intersection
        self.capacity_density = (traffic_wave_speed * jam_density) / (
            traffic_wave_speed + freeflow_speed
        )
        self.capacity = self.capacity_density * freeflow_speed

        # this is the function of the fundamental diagram; x is density and y is capacity
        # assuming density is in vehicles per meter and capacity is in vehicles per second
        # i.e., assume speeds are in m/s and jam_density is veh/m
        self.func = interpolate.interp1d(
            [0, self.capacity_density, jam_density], [0, self.capacity, 0]
        )

    def show(self) -> tuple[Figure, Axes]:
        fig, ax = plt.subplots()
        ax: Axes

        x = np.linspace(0, self.jam_density, num=100)
        y = [self.func(x) for x in x]

        ax.plot(x, y)
        ax.set_title("Fundamental Diagram")
        ax.set_xlabel("Density (veh / m)")
        ax.set_ylabel("Capacity (veh / s)")

        return (fig, ax)

    def get_state(self, density: float) -> State:
        assert density >= 0 and density <= self.jam_density

        flow = self.func(density)

        return State(density, flow)

    def get_interface_slope(self, x: float | State, y: float | State) -> float:
        if isinstance(x, State) and isinstance(y, State):
            return x.get_interface_slope(y)
        elif isinstance(x, float) and isinstance(y, float):
            state1 = self.get_state(x)
            state2 = self.get_state(y)

            return state1.get_interface_slope(state2)

        raise RuntimeError("invalid arguments")

    def get_jam_state(self) -> State:
        return State(self.jam_density, 0)

    def get_max_state(self) -> State:
        return State(self.capacity_density, self.capacity)

    def get_empty_state(self) -> State:
        return State(0, 0)

    def get_state_by_flow(self, flow: float, prev_state: State, flip: bool = False) -> State:
        if math.isclose(flow, self.capacity):
            return self.get_max_state()

        left_density = flow / self.freeflow_speed
        # this is solving a linear equation -- specifically for the
        # right side of the fundamental diagram line
        right_density = (
            flow - self.capacity - self.trafficwave_speed * self.capacity_density
        ) / -self.trafficwave_speed

        # assumption: between two organic states, it is impossible for
        # the differential in flow/density to be in the same direction
        if not flip and (
            (flow > prev_state.flow and left_density > prev_state.density)
            or (flow < prev_state.flow and left_density < prev_state.density)
        ):
            return State(right_density, flow)

        return State(left_density, flow)

    def state_is_queued(self, state: State) -> bool:
        assert state.density >= 0 and state.density <= self.jam_density
        return state.density > self.capacity_density
