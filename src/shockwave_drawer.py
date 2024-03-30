# from augmenters.base_augmenter import TrafficAugmenter
import matplotlib.pyplot as plt
from sortedcontainers import SortedList

from src.custom_types import Axes

from .augmenters.traffic_light import TrafficLight
from .drawer_utils import (
    CapacityEvent,
    Event,
    EventType,
    Interface,
    IntersectionEvent,
    State,
    dtPoint,
    float_isclose,
)
from .fundamental_diagram import FundamentalDiagram

# from .state_handler import StateHandler


class ShockwaveDrawer:
    """This encapsulates the main logic for creating a situation and determining
    the shockwave diagram for the created situation.
    """

    def __init__(
        self,
        diagram: FundamentalDiagram,
        simulation_time: float,
        augments: list[TrafficLight],
        init_density: float,
    ):
        """Constructor for a ShockwaveDrawer.

        Args:
            diagram (FundamentalDiagram): the fundamental diagram under consideration
            simulation_time (float): how long to run the simulation for (seconds)
            augments (list[TrafficLight]): the things generating CapacityEvents that generate
            shockwaves
            init_density (float): The default density that cars are in at time 0

        Raises:
            ValueError: The density must be within the bounds of the provided fundamental diagram.
        """
        self.diagram = diagram
        self.simulation_time = simulation_time

        # create the event queue -- want to process events in order of increasing time
        self.events: SortedList[Event] = SortedList()

        if not (init_density >= 0 and init_density <= self.diagram.jam_density):
            raise ValueError(
                "The provided initial density is not valid for the provided fundamental diagram."
            )

        self.default_state = self.diagram.get_state(init_density)
        self.interfaces: list[Interface] = []

        # initialize the augments -- add their events to the event queue
        for augment in augments:
            augment.init(self.simulation_time, self.events, self.interfaces)

    def _add_interface(self, interface: Interface):
        """Private function to add an interface to the list of generated interfaces.
        Handles basic sanity checking (no duplicate interfaces) and generates IntersectionEvents
        as needed.

        TODO: try kdTrees for faster intersection resolution

        Args:
            interface (Interface): the interface to add
        """

        # only consider one intersection -- the one that is closest in time to it
        # breaks on vertical lines
        min_intersect: dtPoint | None = None
        min_interfaces: list[Interface] = []

        # find the interface that intersects the closest from the given interface
        for x in self.interfaces:
            assert not x.equivalent_to(interface)  # basic sanity check -- should never happen

            intersect = interface.intersection(x)

            # ignore overlaps and non-intersecting interfaces
            if intersect is None or interface.has_endpoint(intersect):
                continue
            elif min_intersect and min_intersect == intersect:
                min_interfaces.append(x)
            elif not min_intersect or intersect.time < min_intersect.time:
                min_intersect = intersect
                min_interfaces = [x]

        min_interfaces.append(interface)

        # if we have an interesct, generate an IntersectionEvent between these two interfaces
        if min_intersect:
            event = IntersectionEvent(min_intersect, min_interfaces)
            self.events.add(event)

        # add the interface to the list
        self.interfaces.append(interface)

    def _resolve_state(self, point: dtPoint, below: bool = True) -> State:
        """Private function to resolve the upstream and downstream state from a point.

        Idea: on the dt-plane, you can get the interface that pertains to an event by looking
        directly down from the event point (in the distance dimension) and taking the
        above state of the closest interface. Same idea for getting the above state

        TODO: make this more efficient by indexing interfaces by position

        Args:
            point (dtPoint): the point to resolve the state for
            below (bool, optional): whether you want to below state or not. Defaults to True.

        Returns:
            State: The state below/above the point, default state if no state found.
        """

        scale = 1 if below else -1
        res: Interface | None = None
        min_dist = float("inf")

        # find the closest interface below/above the point and its relevant state
        for interface in self.interfaces:
            # ignore overlapping interfaces
            if interface.has_endpoint(point):
                continue

            cur = interface.get_pos_at_time(point.time)

            if cur is None or float_isclose(point.position - cur, 0):
                continue

            if scale * (point.position - cur) >= 0 and scale * (point.position - cur) < min_dist:
                res = interface

                min_dist = scale * (point.position - cur)

        # return the found state or default state if none found
        if res:
            # TODO: make this more robust
            if res.above is None:
                return self.default_state
            if below:
                return res.above
            return res.below

        return self.default_state

    def _handle_capacity_event(self, cur: CapacityEvent) -> None:
        """Private function for handling a capacity event. Determines what to do
        using the prior/posterior capacity (adjusted for the current state)
        and the fundamental diagram.

        TODO: determine whether we need to store latent capacity information (see the `pass` below)
        TODO: set the event interface above/below states at the end (don't really need to)

        Args:
            cur (CapacityEvent): The capacity event to handle
            above (State): the state above the point of the capacity event
            below (State): the state below the point of the capacity event
        """
        above = self._resolve_state(cur.point, below=False)
        below = self._resolve_state(cur.point, below=True)

        # get prior/posterior capacity
        prior_capacity = below.flow if cur.prior_capacity == -1 else cur.prior_capacity
        posterior_capacity = (
            self.diagram.get_max_state().flow
            if cur.posterior_capacity == -1
            else cur.posterior_capacity
        )

        # we are limited by the flow of the incoming state IF the state is queued
        if not self.diagram.state_is_queued(below):
            posterior_capacity = min(posterior_capacity, below.flow)

        print(above, below, prior_capacity, posterior_capacity)

        # if we have an increase in capacity and there is not enough density (queuing)
        # to take advantage of that increase, do nothing -- no interface created
        if posterior_capacity >= prior_capacity and not self.diagram.state_is_queued(below):
            pass
        # we have an actual event with a decrease in capacity
        else:
            # main interface of the event; direct result of the reduction in capacity
            main_interface_state = self.diagram.get_state_by_flow(posterior_capacity, below)

            # same logic as below, but unsure if this ever happens
            if main_interface_state != below:
                main_interface = Interface(
                    cur.point,
                    self.diagram.get_interface_slope(main_interface_state.density, below.density),
                    main_interface_state,
                    below,
                    lower_bound=cur.point,
                )

                self._add_interface(main_interface)

            # the byproduct of the event -- for conservation of cars
            byproduct_interface_state = self.diagram.get_state_by_flow(
                posterior_capacity, below, flip=True
            )

            # if we don't have a state difference here, there is no interface created
            # consider a traffic light with empty state already above
            if byproduct_interface_state != above:
                byproduct_interface = Interface(
                    cur.point,
                    self.diagram.get_interface_slope(
                        above.density, byproduct_interface_state.density
                    ),
                    above,
                    byproduct_interface_state,
                    lower_bound=cur.point,
                )

                self._add_interface(byproduct_interface)

    def _handle_intersection_event(self, cur: IntersectionEvent) -> None:
        """Handles an intersection event. Determines behavior purely using
        the intersecting interfaces in question and basic dt-diagram
        resolutions.

        TODO: is an event valid if it just cuts off one of the interfaces? Currently
        only valid if it cuts off all the interfaces in question.
        TODO: handle the assertion that the above/below states are not None for CapEvent interfaces

        Args:
            cur (IntersectionEvent): the IntersectionEvent to process
        """
        assert len(cur.interfaces) >= 2

        # determine if this event is still valid -- i.e., it would actually
        # cutoff the interfaces
        for interface in cur.interfaces:
            if interface.get_pos_at_time(cur.point.time) is None:
                return

        # determine which state is above/below using interface slopes
        maxslope = float("-inf")
        above = None
        minslope = float("inf")
        below = None

        no_new_interface = False

        for interface in cur.interfaces:
            if interface.slope > maxslope:
                maxslope = interface.slope
                below = interface.below

            if interface.slope < minslope:
                minslope = interface.slope
                above = interface.above

            # chop off the interface endpoints while iterating
            # assumes that it will always be in the future -- i.e., upper bound
            try:
                interface.add_cutoff(None, cur.point)
            except Exception as _:
                print(interface, _)
                no_new_interface = True

        if no_new_interface:
            return

        # this basically checks that above/below are not None -- may break on
        # intersection with user-inputted interfaces since
        # we currently don't fill in any CapacityEvent interfaces
        assert above is not None and below is not None

        # don't create new interface if there is no actual change in state
        # see three intersection for an example
        if above != below:
            # creat the new interface using the found above/below states
            # goes outwards from this current point to higher times
            new_interface = Interface(
                cur.point,
                self.diagram.get_interface_slope(above.density, below.density),
                above,
                below,
                lower_bound=cur.point,
            )

            self._add_interface(new_interface)

    def run(self):
        """Main function to generate the shockwave diagram given the inputs."""

        self.figures = []

        self.update_figure()

        # while there are more events to process
        while self.events:
            # get the first event (first event in time)
            cur: Event = self.events.pop(0)
            print(f"processing {cur}")
            prev = len(self.interfaces)

            # handle the vent based on its type
            match cur.type:
                case EventType.capacity:
                    self._handle_capacity_event(cur)
                case EventType.intersection:
                    # scan forward for a potentially more complete intersection event
                    # that includes all the interfaces intersecting there -- needed for correct
                    # above/below resolution of the new interface
                    x: IntersectionEvent
                    for x in self.events:
                        if float_isclose(x.point.time, cur.point.time):
                            if (
                                float_isclose(x.point.position, cur.point.position)
                                and type(x) == type(cur)
                                and len(x.interfaces) > len(cur.interfaces)
                            ):
                                cur = x
                        else:
                            break

                    self._handle_intersection_event(cur)

            if prev != len(self.interfaces):
                self.update_figure()

    def update_figure(self):
        fig, ax = plt.subplots(figsize=(20, 10))
        ax: Axes

        for interface in self.interfaces:
            p1 = interface.endpoints[0]
            p2 = interface.endpoints[1]

            if p1 is None:
                p1 = dtPoint(0, interface.get_pos_at_time(0))
            if p2 is None:
                p2 = dtPoint(
                    self.simulation_time + 5, interface.get_pos_at_time(self.simulation_time + 5)
                )

            if p1 != p2:
                ax.plot((p1.time, p2.time), (p1.position, p2.position), marker="o")

        self.figures.append((fig, ax))
        plt.close(fig)
