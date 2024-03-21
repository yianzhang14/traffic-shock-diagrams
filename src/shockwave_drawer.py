# from augmenters.base_augmenter import TrafficAugmenter
from augmenters.traffic_light import TrafficLight
from sortedcontainers import SortedList

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

    def _add_interface(self, interface: Interface):
        # TODO: handle 2+ interface intersections (if they exist)
        for x in self.interfaces:
            assert x != interface

            intersect = interface.intersection(x)

            if intersect is None:
                continue
            else:
                self.events.add(IntersectionEvent(intersect, [x, interface]))

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
            cur = interface.get_pos_at_time(point.time)
            if scale * (point.position - cur) >= 0 and scale * (point.position - cur) < min_dist:
                if below:
                    res = interface.above
                else:
                    res = interface.below

                min_dist = scale * (point.position - cur)

        return res or self.default_state

    def _handle_capacity_event(self, cur: CapacityEvent, above: State, below: State) -> None:
        # flow can spontaneously go down
        # TODO: determine if we need an inflow in a capacity event --
        # is not really determined by the event but by prior conditions
        # it is encapsulated by the below state essentially
        inflow = below.flow if cur.inflow == -1 else cur.inflow  # noqa: F841

        outflow = self.diagram.get_max_state().flow if cur.outflow == -1 else cur.outflow
        # TODO: adjust the outflow for the maximum permissible flow
        outflow = min(
            outflow, float("inf")
        )  # possibly above.flow with consideration for default state?

        # TODO: make this orientation-independent (instead of below_*, make names more meaningful)
        # TODO: do we actually need this conditional? it is currently just the same
        # need conditional here to preserve the above/below orientation of interfaces
        # essentially when flow goes up, cars must group
        # downwards and vice versa for the conservation of cars
        if outflow < cur.outflow:
            # the stuff below it (going into the event)
            event_below_state = self.diagram.get_state_by_flow(outflow, below)
            below_interface = Interface(
                cur.point,
                self.diagram.get_interface_slope(event_below_state, below),
                event_below_state,
                below,
                bounds=(cur.point, None),
            )

            # the stuff above it (going out of the event)
            # empty state is kinda a byproduct of everything --
            # not a pure result of capacity changes
            event_above_state = self.diagram.get_state_by_flow(outflow, below, flip=True)
            above_interface = Interface(
                cur.point,
                self.diagram.get_interface_slope(above, event_above_state),
                above,
                event_above_state,
                bounds=(cur.point, None),
            )

        elif outflow > cur.outflow:
            # the stuff below it (going into the event)
            event_below_state = self.diagram.get_state_by_flow(outflow, below)
            below_interface = Interface(
                cur.point,
                self.diagram.get_interface_slope(event_below_state, above),
                event_below_state,
                below,
                bounds=(cur.point, None),
            )

            # the stuff above it (going out of the event)
            # empty state is kinda a byproduct of everything --
            # not a pure result of capacity changes
            # TODO: currently, there is no ambiguity in getting state by flow for traffic lights
            # will only go to maximal, which is the only point that maps to exactly one density
            # may have to swap the flips
            event_above_state = self.diagram.get_state_by_flow(outflow, below, flip=True)
            above_interface = Interface(
                cur.point,
                self.diagram.get_interface_slope(above, event_above_state),
                above,
                event_above_state,
                bounds=(cur.point, None),
            )
        else:  # math.isclose(outflow, cur.outflow)
            raise RuntimeError("this capacity event doesn't change")

        self._add_interface(below_interface)
        self._add_interface(above_interface)

    def _handle_intersection_event(
        self, cur: IntersectionEvent, above: State, below: State
    ) -> None:
        # chop off the interface endpoints
        # assumes that it will always be in the future -- i.e., upper bound
        for interface in cur.interfaces:
            interface.add_cutoff(None, cur.point)

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
            above = self._resolve_state(cur.point, below=False)
            below = self._resolve_state(cur.point, below=True)

            match cur.type:
                case EventType.capacity:
                    self._handle_capacity_event(cur, above, below)
                    break
                case EventType.intersection:
                    self._handle_intersection_event(cur, above, below)
                    break
