from typing import override

from sortedcontainers import SortedList

from ..drawer_utils import CapacityEvent, Interface, UserInterface, dtPoint
from .base_augmenter import TrafficAugmenter


class TrafficLight(TrafficAugmenter):
    """Specialization of augmenter for traffic lights. Traffic light augmenters cause capacity to
    drop to 0 for a specific period of time, followed by the release of that limitation.
    This occurs is a configurable cyclical manner.
    """

    id: int = 0

    def __init__(
        self,
        pos: float,
        cycles: tuple[float, ...],
        blocking_states: tuple[bool, ...],
        init_state: int = 0,
    ):
        """Traffic light constructor.

        Args:
            pos (float): the position at which the traffic light is located (meters)
            cycles (tuple[float, ...]): the times of each traffic light cycle
            blocking_states (tuple[bool, ...]): whether or not each cycle is blocking or not
            init_state (int, optional): initial state of the traffic light. Defaults to 0.

        Raises:
            ValueError: the state must be a valid index of cycle
            ValueError: each cycle of the traffic light must be defined to be blocking or not
        """
        self.pos = pos  # where the traffic light is
        self.cycles = cycles  # list of the delays of each of the cycles
        self.state = init_state  # initial state -- an index for self.cycles (will wrap around)
        self.blocking_states = (
            blocking_states  # list of whether each corresponding cycle is blocking or not
        )

        if not (self.state < len(self.cycles) and self.state >= 0):
            raise ValueError("The provided initial state is invalid.")

        if len(blocking_states) != len(cycles):
            raise ValueError("The lengths of the blocking states and cycles don't match")

        # generate an unique id
        self.id = TrafficLight.id
        TrafficLight.id += 1

    @override
    def init(self, simulation_time: float, events: SortedList, interfaces: list[Interface]):
        time = 0

        # continue adding capacity events to the event queue until we are out of time
        while time <= simulation_time:
            if self.blocking_states[self.state]:
                start = dtPoint(time, self.pos)
                end = dtPoint(time + self.cycles[self.state], self.pos)

                cur = UserInterface(start, 0, self, lower_bound=start, upper_bound=end)
                interfaces.append(cur)

                events.add(CapacityEvent(start, cur, posterior_capacity=0))
                events.add(CapacityEvent(end, cur, prior_capacity=0))

            time += self.cycles[self.state]
            self.state = (self.state + 1) % len(self.cycles)
