# from augmenters.base_augmenter import TrafficAugmenter
from sortedcontainers import SortedList

from .augmenters.traffic_light import TrafficLight
from .diagram_utils import (
    CapacityEvent,
    Event,
    EventType,
    Interface,
    IntersectionEvent,
    State,
    dtPoint,
)
from .fundamental_diagram import FundamentalDiagram

# from .state_handler import StateHandler


class ShockwaveDrawer:
    def __init__(
        self,
        diagram: FundamentalDiagram,
        simulation_time: float,
        augments: list[TrafficLight],
        init_density: float,
    ):
        self.diagram = diagram
        self.simulation_time = simulation_time

        self.events: SortedList[Event] = SortedList()

        assert init_density >= 0 and init_density <= self.diagram.jam_density

        self.default_state = self.diagram.get_state(init_density)
        self.interfaces: list[Interface] = []

        for augment in augments:
            augment.init(self.simulation_time, self.events, self.interfaces)

    def _add_interface(self, interface: Interface):
        # TODO: handle 2+ interface intersections (if they exist)
        print("adding interface", interface, interface.endpoints, interface.above, interface.below)

        # only consider one intersection -- the one that is closest in time to it
        # breaks on vertical lines
        min_intersect: dtPoint | None = None
        min_interface: Interface = None
        for x in self.interfaces:
            assert not x.equivalent_to(interface)
            intersect = interface.intersection(x)

            if intersect is None or interface.has_endpoint(intersect) or x.has_endpoint(intersect):
                continue
            elif not min_intersect or intersect.time < min_intersect.time:
                min_intersect = intersect
                min_interface = x

        if min_intersect:
            event = IntersectionEvent(min_intersect, [interface, min_interface])
            self.events.add(event)

        self.interfaces.append(interface)

    def _resolve_state(self, point: dtPoint, below: bool = True) -> State:
        # idea: on the dt-plane, you can get the interface that pertains to an event by looking
        # directly down from theevent point (in the distance dimension) and taking the
        # above state of the closest interface
        # same idea for getting the above state
        scale = 1 if below else -1
        res: State | None = None
        min_dist = float("inf")

        for interface in self.interfaces:
            if interface.has_endpoint(point):
                continue

            cur = interface.get_pos_at_time(point.time)

            if cur is None:
                continue

            if scale * (point.position - cur) >= 0 and scale * (point.position - cur) < min_dist:
                if below:
                    res = interface.above
                else:
                    res = interface.below

                min_dist = scale * (point.position - cur)

        return res or self.default_state

    def _handle_capacity_event(self, cur: CapacityEvent, above: State, below: State) -> None:
        prior_capacity = below.flow if cur.prior_capacity == -1 else cur.prior_capacity
        posterior_capacity = (
            self.diagram.get_max_state().flow
            if cur.posterior_capacity == -1
            else cur.posterior_capacity
        )
        # we are limited by the flow of the incoming state IF the state is queued
        if not self.diagram.state_is_queued(below):
            posterior_capacity = min(posterior_capacity, below.flow)

        # if we have an increase in capacity and there is not enough density (queuing)
        # to take advantage of that increase, do nothing -- no interface created
        if posterior_capacity >= prior_capacity and not self.diagram.state_is_queued(below):
            # TODO: do we need to store latent capactiy information?
            pass
        # we have an actual event with a decrease in capacity
        else:
            # main interface of the event; direct result of the reduction in capacity
            main_interface_state = self.diagram.get_state_by_flow(posterior_capacity, below)
            main_interface = Interface(
                cur.point,
                self.diagram.get_interface_slope(main_interface_state, below),
                main_interface_state,
                below,
                bounds=(cur.point, None),
            )

            # the byproduct of the event -- for conservation of cars
            byproduct_interface_state = self.diagram.get_state_by_flow(
                posterior_capacity, below, flip=True
            )

            print(above, byproduct_interface_state, below, main_interface_state, posterior_capacity)
            byproduct_interface = Interface(
                cur.point,
                self.diagram.get_interface_slope(above, byproduct_interface_state),
                above,
                byproduct_interface_state,
                bounds=(cur.point, None),
            )

            self._add_interface(main_interface)
            self._add_interface(byproduct_interface)

        # TODO: set the user interface above/below states

    def _handle_intersection_event(self, cur: IntersectionEvent) -> None:
        assert len(cur.interfaces) >= 2

        for interface in cur.interfaces:
            if interface.get_pos_at_time(cur.point.time) is None:
                return

        # determine which state is above/below using interface slopes
        maxslope = float("-inf")
        above = None
        minslope = float("inf")
        below = None

        for interface in cur.interfaces:
            if interface.slope > maxslope:
                maxslope = interface.slope
                below = interface.below

            if interface.slope < minslope:
                minslope = interface.slope
                above = interface.above

            # chop off the interface endpoints
            # assumes that it will always be in the future -- i.e., upper bound
            interface.add_cutoff(None, cur.point)

        assert above is not None and below is not None

        new_interface = Interface(
            cur.point,
            self.diagram.get_interface_slope(above, below),
            above,
            below,
            bounds=(cur.point, None),
        )

        self._add_interface(new_interface)

    def run(self):
        while self.events:
            cur: Event = self.events.pop(0)
            print(f"processing {cur}")
            above = self._resolve_state(cur.point, below=False)
            below = self._resolve_state(cur.point, below=True)

            match cur.type:
                case EventType.capacity:
                    self._handle_capacity_event(cur, above, below)
                case EventType.intersection:
                    self._handle_intersection_event(cur)
