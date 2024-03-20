# from augmenters.base_augmenter import TrafficAugmenter
from augmenters.traffic_light import TrafficLight
from sortedcontainers import SortedList

from .diagram_utils import Event, EventType, Interface, State, dtPoint
from .fundamental_diagram import FundamentalDiagram

# from .state_handler import StateHandler


class ShockwaveDrawer:
    def __init__(
        self,
        diagram: FundamentalDiagram,
        simulation_time: float,
        augments: list[TrafficLight],
        init_density: float,
        init_flow: float,
    ):
        self.diagram = diagram
        self.simulation_time = simulation_time

        self.events: SortedList[Event] = SortedList()
        self.default_state = State(init_density, init_flow)
        # self.states = StateHandler(simulation_time, self.simulation_time *
        #   self.diagram.freeflow_speed, init_density, init_flow)
        self.interfaces: list[Interface] = []

        for augment in augments:
            augment.init(self.simulation_time, self.events, self.interfaces, self.diagram)

    def resolve_state(self, point: dtPoint, below: bool = True) -> State:
        # idea: on the dt-plane, you can get the interface that pertains to an event by looking
        # directly down from theevent point (in the distance dimension) and taking the
        # above state of the closest interface
        # same idea for getting the above state
        scale = 1 if below else -1
        res: State | None = None
        min_dist = float("inf")

        for interface in self.interfaces:
            cur = interface.get_pos_at_time(point.time)
            if scale * (point.position - cur) >= 0 and scale * (point.position - cur) < min_dist:
                if below:
                    res = interface.above
                else:
                    res = interface.below

                min_dist = scale * (point.position - cur)

        return res or self.default_state

    def run(self):
        while self.events:
            cur: Event = self.events.pop(0)
            above = self.resolve_state(cur.point, below=False)
            below = self.resolve_state(cur.point, below=True)

            if cur.type == EventType.user:
                assert (
                    len(cur.interfaces) == 1
                )  # if we assume augmenters always have an interface, this must be true
                interface = cur.interfaces[0]
