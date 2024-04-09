from typing import override

from sortedcontainers import SortedList

from ..drawer_utils import CapacityEvent, Interface, UserInterface, dtPoint
from .base_augmenter import TrafficAugmenter


class TimedBottleneck(TrafficAugmenter):
    """Specialization of augmenter for traffic lights. Traffic light augmenters cause capacity to
    drop to 0 for a specific period of time, followed by the release of that limitation.
    This occurs is a configurable cyclical manner.
    """

    def __init__(self, pos: float, time_start: float, time_end: float, bottleneck_capacity: float):
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

        self.time_start = time_start
        self.time_end = time_end

        if bottleneck_capacity < 0:
            raise ValueError("Capacity must be positive")

        self.bottleneck_capacity = bottleneck_capacity

    @override
    def init(self, simulation_time: float, events: SortedList, interfaces: list[Interface]):
        if self.time_start >= 0 and self.time_end <= simulation_time:
            start = dtPoint(self.time_start, self.pos)
            end = dtPoint(self.time_end, self.pos)

            cur = UserInterface(start, 0, self, lower_bound=start, upper_bound=end)
            interfaces.append(cur)

            start_event = CapacityEvent(start, cur, posterior_capacity=self.bottleneck_capacity)
            events.add(start_event)

            end_event = CapacityEvent(end, cur, prior_capacity=self.bottleneck_capacity)
            events.add(end_event)
