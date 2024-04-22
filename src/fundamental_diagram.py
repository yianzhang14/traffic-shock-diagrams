from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from scipy import interpolate  # type: ignore

from src.custom_types import Axes, Figure
from src.drawer_utils import DIGIT_TOLERANCE, State, float_isclose


class FundamentalDiagram:
    """This class encapsulates a fundamental diagram. It basically serves as a setting file
    with useful helper functions for setting up/running through the shockwave drawer scenario.
    """

    def __init__(
        self,
        freeflow_speed: float,
        jam_density: float,
        traffic_wave_speed: float,
        init_density: float,
    ):
        """Constructor of a fundamental diagram.

        Args:
            freeflow_speed (float): speed at which uncongested traffic goes (meters / second)
            jam_density (float): maximum density cars can be at (cars / meter)
            traffic_wave_speed (float): speed at which shockwaves travel (?) (meters / second)

        Raises:
            ValueError: All speeds must be positive
            ValueError: Freeflow speed must be greater than traffic wave speed
        """
        if not (freeflow_speed > 0 and jam_density > 0 and traffic_wave_speed > 0):
            raise ValueError("All speeds must be positive.")

        if freeflow_speed <= traffic_wave_speed:
            raise ValueError("Freeflow speed must be greater than traffic wave speed.")

        if not (init_density >= 0 and init_density <= jam_density):
            raise ValueError(
                "The provided initial density is not valid for the provided fundamental diagram."
            )

        self.freeflow_speed = freeflow_speed
        self.jam_density = jam_density
        self.trafficwave_speed = traffic_wave_speed
        self.init_density = init_density

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
        """Shows the fundamental diagram in matplotlib.

        Returns:
            tuple[Figure, Axes]: the generated figure
        """

        fig, ax = plt.subplots()
        assert isinstance(ax, Axes)

        x = np.linspace(0, self.jam_density, num=100)
        y = [self.func(x) for x in x]

        ax.plot(x, y)
        ax.set_title("Fundamental Diagram")
        ax.set_xlabel("Density (veh / m)")
        ax.set_ylabel("Capacity (veh / s)")

        return (fig, ax)

    def get_initial_state(self) -> State:
        return self.get_state(self.init_density)

    def get_state(self, density: float) -> State:
        """Gets the state at a given density.

        Args:
            density (float): the density query

        Returns:
            State: the state at which the density is as given
        """
        if not (density >= 0 and density <= self.jam_density):
            raise ValueError("Density invalid -- not in the fundamental diagram")

        flow: float = self.func(density).item()

        return State(density, flow)

    def get_interface_slope(self, x: float, y: float) -> float:
        """Gets the slope between the two states associated with the given densities.

        Args:
            x (float): a density
            y (float): a density

        Returns:
            float: the slope between the two states associated with the given densities
        """

        if float_isclose(x, y):
            raise ValueError("The densities are equal -- slope not well-defined.")

        state1 = self.get_state(x)
        state2 = self.get_state(y)

        return state1.get_interface_slope(state2)

    def get_jam_state(self) -> State:
        """Returns the jam state (nothing moving and congested) of the fundamental diagram.

        Returns:
            State: the state corresponding to the jam state
        """
        return State(self.jam_density, 0)

    def get_max_state(self) -> State:
        """Returns the maximal state (max flow) of the fundamental diagram.

        Returns:
            State: the state corresponding to the maximal state
        """
        return State(self.capacity_density, self.capacity)

    def get_empty_state(self) -> State:
        """Returns the empty state (nothing moving and no cars) of the fundamental diagram.

        Returns:
            State: the state corresponding to the empty state
        """
        return State(0, 0)

    def get_state_by_flow(self, flow: float, left: bool = True) -> State:
        """Finds the states associated with a given flow and, by default, returns the valid one.
        The valid state is defined as the one that would have a negative slope with the previous
        state.

        Can get the corresponding invalid state with flip=False.

        Args:
            flow (float): the flow query (cars / second)
            prev_state (State): the previous state (used to determine validity)
            flip (bool, optional): whether or not to return the invalid state. Defaults to False.

        Returns:
            State: the desired state associated with a given flow
        """

        # if we want the max flow, return the max state
        if float_isclose(flow, self.capacity):
            return self.get_max_state()

        left_density = flow / self.freeflow_speed
        # this is solving a linear equation -- specifically for the
        # right side of the fundamental diagram line
        right_density = (
            flow - self.capacity - self.trafficwave_speed * self.capacity_density
        ) / -self.trafficwave_speed

        if left:
            return State(left_density, flow)
        else:
            return State(right_density, flow)

        # # assumption: between two organic states, it is impossible for
        # # the differential in flow/density to be in the same direction
        # if not flip and (
        #     (flow > prev_state.flow and left_density > prev_state.density)
        #     or (flow < prev_state.flow and left_density < prev_state.density)
        # ):
        #     return State(right_density, flow)

        # return State(left_density, flow)

    def state_is_queued(self, state: State) -> bool:
        """Determines whether a state is queued--has density greater than the capacity density.

        Args:
            state (State): the query state

        Raises:
            ValueError: state density must be within bounds of the diagram

        Returns:
            bool: whether or not the state is queued
        """

        if not (state.density >= 0 and state.density <= self.jam_density):
            raise ValueError("Density of the provided state is invalid")

        return state.density > self.capacity_density and not float_isclose(
            state.density, self.capacity_density
        )

    def get_label_for_density(self, density: float) -> str:
        if float_isclose(density, 0):
            return "E"
        elif float_isclose(density, self.init_density):
            return "A"
        elif float_isclose(density, self.capacity_density):
            return "M"
        elif float_isclose(density, self.jam_density):
            return "J"

        normalized_density = density / self.jam_density
        n = hash(round(normalized_density, DIGIT_TOLERANCE)) % 703

        result = []
        while n > 0:
            n -= 1  # Subtract 1 to account for the offset
            quotient, remainder = divmod(n, 26)
            result.append(chr(65 + remainder))
            n = quotient

        return "".join(result)
