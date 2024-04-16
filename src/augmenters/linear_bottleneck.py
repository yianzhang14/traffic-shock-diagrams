from sortedcontainers import SortedList  # type: ignore
from typing_extensions import override

from ..drawer_utils import CapacityEvent, Interface, UserInterface, dtPoint
from .base_augmenter import TrafficAugmenter


class LineBottleneck(TrafficAugmenter):
    def __init__(self, start: dtPoint, end: dtPoint, bottleneck_capacity: float):
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
        self.start = start  # where the traffic light is
        self.end = end

        if bottleneck_capacity < 0:
            raise ValueError("Capacity must be positive")

        self.bottleneck_capacity = bottleneck_capacity

    @override
    def init(self, _simulation_time: float, events: SortedList, interfaces: list[Interface]):
        if self.start.time >= 0:
            cur = UserInterface(
                self.start,
                self.start.get_slope(self.end),
                self,
                lower_bound=self.start,
                upper_bound=self.end,
            )
            interfaces.append(cur)

            start_event = CapacityEvent(
                self.start, cur, posterior_capacity=self.bottleneck_capacity
            )
            events.add(start_event)

            end_event = CapacityEvent(self.end, cur, prior_capacity=self.bottleneck_capacity)
            events.add(end_event)


class HorizontalBottleneck(LineBottleneck):
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
        super().__init__(dtPoint(time_start, pos), dtPoint(time_end, pos), bottleneck_capacity)
