from sortedcontainers import SortedList

from ..diagram_utils import CapacityEvent, EventType, Interface, dtPoint
from ..fundamental_diagram import FundamentalDiagram
from .base_augmenter import TrafficAugmenter


class TrafficLight(TrafficAugmenter):
    id: int = 0

    def __init__(
        self,
        pos: float,
        cycles: tuple[float, ...],
        blocking_states: tuple[bool, ...],
        init_state: int = 0,
    ):
        self.pos = pos  # where the traffic light is
        self.cycles = cycles  # list of the delays of each of the cycles
        self.state = init_state  # initial state -- an index for self.cycles
        self.blocking_states = (
            blocking_states  # list of whether each corresponding cycle is blocking or not
        )

        assert self.state < len(self.cycles) and self.state >= 0
        assert len(blocking_states) == len(cycles)

        self.id = TrafficLight.id
        TrafficLight.id += 1

    def init(
        self,
        simulation_time: float,
        events: SortedList,
        interfaces: list[Interface],
        settings: FundamentalDiagram,
    ):
        time = 0

        while time <= simulation_time:
            if self.blocking_states[self.state]:
                start = dtPoint(time, self.pos)
                end = dtPoint(time + self.cycles[self.state], self.pos)

                cur = Interface(
                    start,
                    0,
                    bounds=[start, end],
                    above=settings.get_empty_state(),
                    below=settings.get_jam_state(),
                )
                interfaces.append(cur)

                events.add(CapacityEvent(start, cur, outflow=0))
                events.add(CapacityEvent(end, cur, inflow=0))

            time += self.cycles[self.state]
            self.state = (self.state + 1) % len(self.cycles)
