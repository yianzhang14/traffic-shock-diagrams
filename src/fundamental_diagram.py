from __future__ import annotations

from dataclasses import dataclass

import matplotlib.pyplot as plt
import numpy as np
from scipy import interpolate

from .custom_types import Axes, Figure
from .diagram_utils import State


class FundamentalDiagram:
    def __init__(self, freeflow_speed: float, jam_density: float, traffic_wave_speed: float):
        assert freeflow_speed >= 0 and jam_density >= 0 and traffic_wave_speed >= 0
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

    def get_interface_speed(self, d1: float, d2: float) -> float:
        state1 = self.get_state(d1)
        state2 = self.get_state(d2)

        return state1.get_interface_speed(state2)

    def get_jam_state(self) -> State:
        return State(self.jam_density, 0)

    def get_max_state(self) -> State:
        return State(self.capacity_density, self.capacity)

    def get_empty_state(self) -> State:
        return State(0, 0)
