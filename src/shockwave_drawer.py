from __future__ import annotations

import collections
import copy
import dataclasses
from typing import TYPE_CHECKING, Any, Optional, cast

import matplotlib.cm as cm
import matplotlib.colors as mcolors
import matplotlib.patches as patches
import matplotlib.pyplot as plt
import networkx as nx  # type: ignore
import numpy as np
import plotly.graph_objects as go  # type: ignore
import seaborn as sns  # type: ignore
import shapely as shp  # type: ignore
from shapely.geometry import LineString, Polygon  # type: ignore
from shapely.ops import split  # type: ignore
from sortedcontainers import SortedList  # type: ignore

if TYPE_CHECKING:
    from src.augmenters.base_augmenter import CapacityBottleneck

from src.custom_types import (
    Axes,
    Color,
    Figure,
    FigureResult,
    GraphInterface,
    GraphLine,
    GraphPolygon,
)

from .drawer_utils import (
    PLOT_THRESHOLD_OFFSET,
    CapacityEvent,
    Event,
    EventType,
    Interface,
    IntersectionEvent,
    State,
    Trajectory,
    TruncationEvent,
    UserInterface,
    dtPoint,
    float_isclose,
)
from .fundamental_diagram import FundamentalDiagram

BLACK: Color = (0.0, 0.0, 0.0)
GREY: Color = (0.5, 0.5, 0.5)

EPS = 1e-2


class ShockwaveDrawer:
    """This encapsulates the main logic for creating a situation and determining
    the shockwave diagram for the created situation.
    """

    def __init__(
        self,
        diagram: FundamentalDiagram,
        augments: list[CapacityBottleneck],
    ):
        """Constructor for a ShockwaveDrawer.

        Args:
            diagram (FundamentalDiagram): the fundamental diagram under consideration
            simulation_time (float): how long to run the simulation for (seconds)
            augments (list[TrafficLight]): the things generating CapacityEvents that generate
            shockwaves

        Raises:
            ValueError: The density must be within the bounds of the provided fundamental diagram.
        """
        self.diagram = diagram

        # default state given the initial density
        self.default_state = self.diagram.get_initial_state()

        self.augments: list[CapacityBottleneck] = augments

    def _setup(self) -> None:
        """This function initializes all the data structures needed to run through the
        shockwave drawer. If already run through once, this resets all the data structures
        for a correct rerun."""
        # create the event queue -- want to process events in order of increasing time
        self.events: SortedList[Event] = SortedList()

        # interfaces created throughout the drawer lifetime
        self.interfaces: list[Interface] = []

        # use this to maintain the invariant that there should only be one event
        # at any given point -- this handles 3+ interface intersections
        self.intersections: dict[dtPoint, IntersectionEvent] = {}
        self.truncations: dict[dtPoint, TruncationEvent] = {}

        # these map UserInterfaces to the original prior/posterior capacities of a CapacityEvent
        # that was postponed due to being restricted to 0/0 prior/post capacity
        # self.latent_events: dict[UserInterface, tuple[float, float]] = dict()

        # initialize the augments -- add their events to the event queue
        for augment in self.augments:
            augment.init(self)

        if len(self.intersections) != 0:
            raise RuntimeError("had intersection between two user interfaces")

        self.colors: dict[tuple[State, State], Color] = dict()

        self.idx1 = 0

    def _save_state(self, **kwargs) -> None:
        print("------------------------------------")
        for key, value in kwargs.items():
            print(key, ":", value)
        print("------------------------------------")
        print("intersections", self.intersections)
        print("------------------------------------")
        print("interfaces", self.interfaces)
        print("------------------------------------")
        print("events", self.events)

        fig, ax = self.create_figure_plt(with_trajectories=True)
        fig.savefig("data/debug.png")

    def _add_interface(self, interface: Interface):
        """Private function to add an interface to the list of generated interfaces.
        Handles basic sanity checking (no duplicate interfaces) and generates IntersectionEvents
        as needed.

        TODO: somehow add hashing for interfaces to simply do set intersection for updating
        existing intersection events

        Args:
            interface (Interface): the interface to add
        """

        # only consider one intersection -- the one that is closest in time to it
        # breaks on vertical lines
        # min_intersect: dtPoint | None = None
        # min_interfaces: list[Interface] = []

        # min_truncation: dtPoint | None = None
        # min_truncation_interfaces: list[Interface] = []

        # find the interface that intersects the closest from the given interface
        for x in self.interfaces:
            # assert not x.equivalent_to(interface)  # basic sanity check -- should never happen

            # this fails if there is not a well-defined intersection
            # i.e., the intersection is either at a single point or doesn't exist
            # no multiple intersections (or infinite intersections)
            try:
                intersect = interface.intersection(x)
            except RuntimeError as e:
                self._save_state(intersection_assertion=(x, interface))
                raise e

            # ignore overlaps and non-intersecting interfaces
            if intersect is None or interface.has_endpoint(intersect):
                continue

            if x.is_user_generated():
                event: Event
                if intersect in self.truncations:
                    event = self.truncations[intersect]
                    if interface not in event.interfaces:
                        event.interfaces.append(interface)
                else:
                    event = TruncationEvent(intersect, cast(UserInterface, x), [interface])
                    self.truncations[intersect] = event

                    self.events.add(event)
            else:
                if intersect in self.intersections:
                    event = self.intersections[intersect]
                    if x not in event.interfaces:
                        event.interfaces.append(x)
                    if interface not in event.interfaces:
                        event.interfaces.append(interface)
                else:
                    event = IntersectionEvent(intersect, [interface, x])
                    self.intersections[intersect] = event

                    self.events.add(event)

        # # add the interface in question to the list since that is part of the  event
        # min_interfaces.append(interface)
        # min_truncation_interfaces.append(interface)

        # if min_truncation:
        #     assert isinstance(min_truncation_interfaces[0], UserInterface)
        #     truncation_event = TruncationEvent(
        #         min_truncation,
        #         min_truncation_interfaces[0],
        #         min_truncation_interfaces[1:],
        #     )
        #     self.events.add(truncation_event)

        # # if we have an interesct, generate an IntersectionEvent between these two interfaces
        # if min_intersect:
        #     # update an existing intersection event by adding it to the list of interfaces
        #     # can just do address comparison (no __eq__ overwriting) since we are only looking
        #     # at existing interfaces (i think -- should check)
        #     if min_intersect in self.intersections:
        #         event: IntersectionEvent | None = self.intersections.get(min_intersect)
        #         assert event is not None

        #         for interface in min_interfaces:
        #             if interface not in event.interfaces:
        #                 event.interfaces.append(interface)
        #     # create a brand new intersection event
        #     else:
        #         event = IntersectionEvent(min_intersect, min_interfaces)
        #         self.events.add(event)
        #         self.intersections[min_intersect] = event

        # add the interface to the list
        self.interfaces.append(interface)

    def _resolve_state(self, point: dtPoint, below: bool = True) -> State:
        """Private function to resolve the upstream and downstream state from a point.

        Reasoning: on the dt-plane, you can get the interface that pertains to an event by looking
        directly down from the event point (in the distance dimension) and taking the
        above state of the closest interface. Same idea for getting the above state

        OPTIMIZE: make this more efficient with segment trees
        TODO: figure out how to best handle cases where the resolved state is at an endpoint

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
            # ignore unhandled user-generated interfaces (& possibly filled-in
            # non-user-generated ones, but those do not exist)
            if interface.above is None:
                assert interface.is_user_generated()
                continue

            cur = interface.get_pos_at_time(point.time + EPS)

            if cur is None or float_isclose(point.position, cur):
                continue

            if res and float_isclose(scale * (point.position - cur), min_dist):
                if (below and interface.slope > res.slope) or (
                    not below and interface.slope < res.slope
                ):
                    res = interface
            elif scale * (point.position - cur) >= 0 and (
                scale * (point.position - cur) < min_dist
            ):
                res = interface

                min_dist = scale * (point.position - cur)

        # return the found state or default state if none found
        if res:
            assert res.above and res.below
            if below:
                return res.above
            return res.below

        return self.default_state

    def _get_states(self) -> set[State]:
        result = set()
        for interface in self.interfaces:
            if interface.has_valid_states():
                assert interface.above and interface.below
                result.add(interface.above)
                result.add(interface.below)

        return result

    def _handle_capacity_event(
        self, cur: CapacityEvent, above: Optional[State] = None, below: Optional[State] = None
    ) -> bool:
        """Private function for handling a capacity event. Determines what to do
        using the prior/posterior capacity (adjusted for the current state)
        and the fundamental diagram.

        Args:
            cur (CapacityEvent): The capacity event to handle
            above (State): the state above the point of the capacity event
            below (State): the state below the point of the capacity event
        """
        if cur.interface.get_pos_at_time(cur.point.time) is None:
            return False

        if not above:
            above = self._resolve_state(cur.point, below=False)
        if not below:
            below = self._resolve_state(cur.point, below=True)

        # get prior/posterior capacity
        prior_capacity = below.flow if cur.prior_capacity == -1 else cur.prior_capacity

        # terminate early if this event is no longer valid
        if prior_capacity != below.flow:
            return False

        posterior_capacity = (
            self.diagram.get_max_state().flow
            if cur.posterior_capacity == -1
            else cur.posterior_capacity
        )

        interface_slope = cur.interface.get_slope()

        # we are limited by the flow of the incoming state IF the state is queued
        if not self.diagram.state_is_queued(below):
            posterior_capacity = min(posterior_capacity, below.flow)

        # if we have an increase in capacity and there is not enough density (queuing)
        # to take advantage of that increase, do nothing -- no interface created
        # this applies to 0 into 0 since posterior and prior both 0
        print(prior_capacity, posterior_capacity, above, below)
        if (
            posterior_capacity > prior_capacity or float_isclose(posterior_capacity, prior_capacity)
        ) and (not self.diagram.state_is_queued(below) or above == below):
            # self.latent_events[cur.interface] = (cur.prior_capacity, cur.posterior_capacity)
            if not float_isclose(above.density, below.density):
                self._add_interface(
                    Interface(
                        cur.point,
                        self.diagram.get_interface_slope(above.density, below.density),
                        above,
                        below,
                        lower_bound=cur.point,
                    )
                )
            return False
        # we have an actual event with a decrease in capacity
        else:
            state_created = False

            # main interface of the event; direct result of the reduction in capacity
            main_interface_state = self.diagram.get_state_by_flow(posterior_capacity, left=False)

            # same logic as below, but unsure if this ever happens
            if main_interface_state != below:
                main_interface = Interface(
                    cur.point,
                    self.diagram.get_interface_slope(main_interface_state.density, below.density),
                    main_interface_state,
                    below,
                    lower_bound=cur.point,
                )

                print(main_interface)

                self._add_interface(main_interface)

                # this assumes that the interface are logically consistent -- for any time this
                # interface setting may occur, the result would be identical
                if float_isclose(main_interface.slope, interface_slope):
                    # this means it is exactly the current interface slope -- invalid
                    raise RuntimeError("An invalid interface was somehow created")

                assert main_interface.above and main_interface.below

                if cur.interface.endpoints[1] == cur.point:
                    if main_interface.slope < interface_slope:
                        cur.interface.set_below_state(main_interface.below)
                    elif main_interface.slope > interface_slope:
                        cur.interface.set_above_state(main_interface.above)
                else:
                    if main_interface.slope < interface_slope:
                        cur.interface.set_below_state(main_interface.above)
                    elif main_interface.slope > interface_slope:
                        cur.interface.set_above_state(main_interface.below)

                state_created |= True

            else:
                cur.interface.set_below_state(below)

            # the byproduct of the event -- for conservation of cars
            byproduct_interface_state = self.diagram.get_state_by_flow(
                posterior_capacity, left=True
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

                print(byproduct_interface)

                self._add_interface(byproduct_interface)

                if float_isclose(byproduct_interface.slope, interface_slope):
                    # this means it is exactly the current interface slope -- invalid
                    raise RuntimeError("An invalid interface was somehow created")

                assert byproduct_interface.below and byproduct_interface.above

                if cur.interface.endpoints[1] == cur.point:
                    if byproduct_interface.slope < interface_slope:
                        cur.interface.set_below_state(byproduct_interface.below)
                    elif byproduct_interface.slope > interface_slope:
                        cur.interface.set_above_state(byproduct_interface.above)
                else:
                    if byproduct_interface.slope < interface_slope:
                        cur.interface.set_below_state(byproduct_interface.above)
                    elif byproduct_interface.slope > interface_slope:
                        cur.interface.set_above_state(byproduct_interface.below)

                state_created |= True

            else:
                cur.interface.set_above_state(above)

            print(main_interface_state, byproduct_interface_state)

            return state_created

    def _handle_intersection_event(self, cur: IntersectionEvent, force: bool = False) -> bool:
        """Handles an intersection event. Determines behavior purely using
        the intersecting interfaces in question and basic dt-diagram
        resolutions.

        TODO: handle the assertion that the above/below states are not None for CapEvent interfaces

        Args:
            cur (IntersectionEvent): the IntersectionEvent to process
        """
        assert len(cur.interfaces) >= 2

        # remove the intersectionevent from the dictionary
        if not force:
            self.intersections.pop(cur.point)

        # resolve the actual interfaces at question -- during execution, may have invalidated some
        # so need to remove the interfaces that would not longer be cutoff here
        interfaces: list[Interface] = []

        for interface in cur.interfaces:
            assert force or not interface.is_user_generated()

            if interface.get_pos_at_time(cur.point.time) is None:
                continue
            interfaces.append(interface)

        # don't do anything if there is nothing else to do
        if len(interfaces) <= 1:
            return False

        # determine which state is above/below using interface slopes
        maxslope = float("-inf")
        above = None
        minslope = float("inf")
        below = None

        no_new_interface = False

        for interface in interfaces:
            if interface.slope > maxslope:
                maxslope = interface.slope
                below = interface.below

            if interface.slope < minslope:
                minslope = interface.slope
                above = interface.above

            # chop off the interface endpoints while iterating
            # assumes that it will always be in the future -- i.e., upper bound
            try:
                interface.add_cutoff(upper=cur.point)
            except Exception as _:
                print(interface, _)
                no_new_interface = True

        if no_new_interface:
            return False

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

            return True

        return False

    def _handle_truncation_event(self, cur: TruncationEvent) -> None:
        """Handles truncation events -- events involving intersection with an userinterface.
        The two main considerations are left-sided and right-sided truncations.

        Args:
            cur (TruncationEvent): the event to handle
        """

        self.truncations.pop(cur.point)

        interfaces: list[Interface] = []

        for interface in cur.interfaces:
            if interface.get_pos_at_time(cur.point.time) is None:
                continue
            interfaces.append(interface)

        if cur.user_interface.get_pos_at_time(cur.point.time) is None:
            return

        if len(interfaces) == 0:
            return

        for interface in interfaces:
            if interface == cur.user_interface:
                continue

            interface.add_cutoff(upper=cur.point)

        # if the current interface is a latent event, we process it as such
        if not cur.user_interface.has_valid_states():
            # extract prior/post capacity to inform the capacity event
            # prior_cap, post_cap = self.latent_events.pop(cur.user_interface)
            print("converting to capacity event")

            cur.user_interface.add_cutoff(lower=cur.point)

            # handle the capacity event using the information we have
            state_created = self._handle_capacity_event(
                CapacityEvent(
                    cur.point,
                    cur.user_interface,
                    prior_capacity=-1,
                    posterior_capacity=cur.user_interface.augment.bottleneck,
                ),
            )
        elif cur.user_interface.has_valid_states():
            print("handling right truncation event")

            # self.latent_events[cur.user_interface] = (-1, cur.user_interface.augment.bottleneck)
            new_interface = copy.deepcopy(cur.user_interface)
            self.interfaces.append(new_interface)
            cur.user_interface.add_cutoff(lower=cur.point)
            cur.user_interface.above = cur.user_interface.below = None

            state_created = self._handle_intersection_event(
                IntersectionEvent(cur.point, [new_interface] + cur.interfaces), force=True
            )

            if state_created:
                for interface in interfaces:
                    interface.add_cutoff(upper=cur.point)

                cur.user_interface.add_cutoff(upper=cur.point)

    def run(self, simulation_time: float, save_images=False) -> None:
        """Main function to generate the shockwave diagram given the inputs."""

        self.i = 0
        self.simulation_time = simulation_time

        # setup required data structures
        self._setup()

        # while there are more events to process
        while self.events:
            # get the first event (first event in time)
            time: float = self.events[0].point.time

            print(f"processing events at time {time}")

            pos_queue: SortedList[tuple[int, float, Event]] = SortedList()

            while self.events and float_isclose(self.events[0].point.time, time):
                x: Event = self.events.pop(0)

                match x.type:
                    case EventType.capacity:
                        pos_queue.add((3, x.point.position, x))
                    case EventType.intersection:
                        pos_queue.add((1, x.point.position, x))
                    case EventType.truncation:
                        x_trunc = cast(TruncationEvent, x)

                        if x_trunc.user_interface.has_valid_states():
                            pos_queue.add((1, x.point.position, x))
                        else:
                            pos_queue.add((2, x.point.position, x))

            while pos_queue:
                event: Event
                _, _, event = pos_queue.pop(0)

                # support disabling of events -- currently unused
                if event.disabled:
                    continue

                prev_num_interfaces = len(self.interfaces)

                print(f"processing {event}")

                # handle the vent based on its type
                match event.type:
                    case EventType.capacity:
                        self._handle_capacity_event(cast(CapacityEvent, event))
                    case EventType.intersection:
                        self._handle_intersection_event(cast(IntersectionEvent, event))
                    case EventType.truncation:
                        self._handle_truncation_event(cast(TruncationEvent, event))

                if save_images and len(self.interfaces) != prev_num_interfaces:
                    fig, ax = self.create_figure_plt(with_trajectories=True)
                    fig.savefig(f"data/{self.i}.png")

                    self.i += 1

    # plotting utilities vvv

    def _find_closest_intersection_traj(
        self, cur: Trajectory
    ) -> Optional[tuple[dtPoint, Interface]]:
        """This function is purely for generating trajectories. It finds the
        first intersection between a trajectory and generated interface to the right
        of the trajectory's left endpoint.

        Args:
            cur (Trajectory): the trajectory to query intersections for

        Returns:
            Optional[tuple[dtPoint, Interface]]: the intersection point and the interface
            the trajectory intersected with
        """
        min_intersect_time = float("inf")
        res: tuple[dtPoint, Interface] | None = None

        for interface in self.interfaces:
            # ignore interfaces without valid states -- these
            # weren't processed during the execution, meaning they don't
            # (shouldn't) do anything
            if not interface.has_valid_states():
                continue

            # ignore unhandled user-generated interfaces (& possibly filled-in
            # non-user-generated ones, but those do not exist)

            try:
                intersection = interface.intersection(cur)
            except RuntimeError:
                continue

            if intersection is None or cur.has_endpoint(intersection):
                continue

            if intersection.time < min_intersect_time:
                min_intersect_time = intersection.time
                res = (intersection, interface)

        return res

    def create_figure_plt(
        self,
        with_trajectories=False,
        num_trajectories: int = 100,
        with_polygons=False,
        max_time: Optional[float] = None,
        max_pos: Optional[float] = None,
    ) -> tuple[Figure, Axes]:
        """This function generates a matplotlib figure showing the fundamental digram,
        using the currently generated interfaces stored in self.interfaces.

        Trajectories can also be plotted, if specified.

        Args:
            with_trajectories (bool, optional): Whether or not to plot trajectories.
            Defaults to False.

        Returns:
            tuple[Figure, Axes]: the figure and axes of the generated image
        """

        fig, ax = plt.subplots(figsize=(20, 10))
        assert isinstance(ax, Axes)

        figure = self._create_figure(
            num_trajectories,
            with_trajectories,
            with_polygons,
            set_max_time=max_time,
            set_max_pos=max_pos,
        )

        normalizer = mcolors.TwoSlopeNorm(
            self.diagram.capacity_density, vmin=0, vmax=self.diagram.jam_density
        )

        state_color_space = sns.color_palette("Spectral_r", as_cmap=True)

        for graph_polygon in figure.polygons:
            ax.add_patch(
                patches.Polygon(
                    graph_polygon.polygon.exterior.coords,
                    closed=True,
                    color=state_color_space(normalizer(graph_polygon.state.density)),
                    alpha=0.5,
                )
            )
            ax.annotate(
                graph_polygon.label,
                dataclasses.astuple(graph_polygon.point),
                horizontalalignment="center",
                verticalalignment="center",
            )

        for user_interface in figure.user_interfaces:
            ax.plot(
                (user_interface.point1.time, user_interface.point2.time),
                (user_interface.point1.position, user_interface.point2.position),
                alpha=0.9,
                linestyle="dashed",
                c=user_interface.color,
            )

        for interface in figure.interfaces:
            ax.plot(
                (interface.point1.time, interface.point2.time),
                (interface.point1.position, interface.point2.position),
                c=interface.color,
                marker="o",
            )

        for trajectory in figure.trajectories:
            for line in trajectory:
                ax.plot(
                    (line.point1.time, line.point2.time),
                    (line.point1.position, line.point2.position),
                    c=line.color,
                    linewidth=0.5,
                    alpha=0.8,
                )

        scalarmappable = cm.ScalarMappable(norm=normalizer, cmap=state_color_space)
        scalarmappable.set_array([state.density for state in self._get_states()])

        cb = fig.colorbar(scalarmappable, ax=ax, label="Density scale")
        cb.set_alpha(0.5)

        ax.set_xbound(figure.min_time, figure.max_time)
        ax.set_ybound(figure.min_pos, figure.max_pos)

        ax.set_title("Shockwave Diagram")
        ax.set_xlabel("Time (seconds)")
        ax.set_ylabel("Position (meters)")

        plt.close(fig)

        return (fig, ax)

    def _create_figure(
        self,
        num_trajectories: int,
        with_trajectories: bool,
        with_polygons: bool,
        set_max_pos: Optional[float] = None,
        set_max_time: Optional[float] = None,
    ) -> FigureResult:
        color_space = sns.color_palette("tab20", len(self.interfaces))

        user_interfaces_out: list[GraphLine] = []
        interfaces_out: list[GraphInterface] = []
        trajectories_out: list[list[GraphLine]] = []
        polygons_out: list[GraphPolygon] = []

        max_pos: float = -1
        max_time: float = -1
        min_pos = float("inf")
        max_interface_pos: float = -1

        for interface in self.interfaces:
            p1 = interface.endpoints[0]

            max_time = max(max_time, p1.time)

            if interface.is_user_generated():
                max_interface_pos = max(
                    max_interface_pos,
                    interface.endpoints[0].position,
                    interface.endpoints[1].position,
                )

        max_interface_pos += 5 * PLOT_THRESHOLD_OFFSET
        max_time = max(max_time, self.simulation_time) + PLOT_THRESHOLD_OFFSET * 5

        if set_max_time:
            max_time = max(set_max_time, max_time)
        if set_max_pos:
            max_interface_pos = max(max_interface_pos, set_max_pos)
            max_pos = max(max_pos, set_max_pos)

        for interface in self.interfaces:
            if interface.is_user_generated():
                user_interfaces_out.append(
                    GraphLine(
                        cast(UserInterface, interface).original_lower_bound,
                        cast(UserInterface, interface).original_upper_bound,
                        BLACK,
                    )
                )
            # don't draw interfaces without valid states -- if they don't
            # have valid states, they weren't ever processed
            if not interface.has_valid_states():
                continue

            p1 = interface.endpoints[0]
            p2 = interface.endpoints[1]

            min_pos = min(min_pos, p1.position)

            if p2.time != float("inf"):
                min_pos = min(min_pos, p2.position)

            if p2.time == float("inf"):
                pos = interface.get_pos_at_time(max_time)
                assert pos is not None

                max_pos = max(max_pos, pos)
                p2 = dtPoint(
                    max_time,
                    pos,
                )

            color: Color = BLACK

            if not interface.is_user_generated():
                assert interface.above and interface.below
                tup: tuple[State, State] = (interface.above, interface.below)

                if tup in self.colors:
                    color = self.colors[tup]
                else:
                    color = color_space[self.idx1]
                    self.idx1 += 1
                    assert isinstance(color, tuple)
                    self.colors[tup] = color

            if p1 != p2:
                interfaces_out.append(
                    GraphInterface(p1, p2, color, interface.above, interface.below)
                )

        if with_trajectories:
            # gap = self.default_state.density
            slope = self.default_state.get_slope()

            for pos in np.linspace(
                -slope * max_time,
                max_pos,
                num_trajectories,
            ):
                cur_trajectories: list[GraphLine] = []

                try:
                    assert isinstance(pos, float)
                    cur = Trajectory(dtPoint(0, pos + 0.1), slope)

                    while True:
                        x = self._find_closest_intersection_traj(cur)
                        next_trajectory: Trajectory | None = None

                        if x is not None:
                            intersection, interface = x
                            assert interface.above

                            next_trajectory = Trajectory(
                                intersection, interface.above.get_slope(), lower_bound=intersection
                            )

                            # if we have a slope of inf (iff density of state is 0), just
                            # kill the trajectory -- this occurs if we have an trajectory intersect
                            # exactly at the point of an interface
                            if next_trajectory.slope == float("inf"):
                                break

                            cur.add_cutoff(upper=intersection)

                        p1 = cur.endpoints[0]
                        p2 = cur.endpoints[1]

                        if p2.time == float("inf"):
                            p2_pos = cur.get_pos_at_time(max_time + PLOT_THRESHOLD_OFFSET)
                            if p2_pos is None:
                                break
                            p2 = dtPoint(
                                max_time + PLOT_THRESHOLD_OFFSET,
                                p2_pos,
                            )

                        cur_trajectories.append(GraphLine(p1, p2, GREY))

                        if next_trajectory is not None:
                            cur = next_trajectory
                        else:
                            break
                except Exception as e:
                    print(e)

                trajectories_out.append(cur_trajectories)

        min_pos = min(min_pos, 0) - PLOT_THRESHOLD_OFFSET

        if with_polygons:
            try:
                polygons = self._resolve_polygons(max_time, max_pos, min_pos)
            except TimeoutError:
                return FigureResult(
                    max_interface_pos,
                    min_pos,
                    max_time,
                    -PLOT_THRESHOLD_OFFSET,
                    user_interfaces_out,
                    interfaces_out,
                    polygons_out,
                    trajectories_out,
                )

            line = LineString(
                [(-10 * PLOT_THRESHOLD_OFFSET, max_interface_pos), (max_time, max_interface_pos)]
            )

            full_polygon = shp.Polygon(
                [
                    (-PLOT_THRESHOLD_OFFSET, -PLOT_THRESHOLD_OFFSET),
                    (-PLOT_THRESHOLD_OFFSET, max_interface_pos),
                    (max_time, max_interface_pos),
                    (max_time, -PLOT_THRESHOLD_OFFSET),
                ]
            )

            for polygon in polygons:
                pieces = split(polygon, line)
                midpoint: shp.Point = polygon.representative_point()

                for geom in pieces.geoms:
                    piece_center: shp.Point = geom.representative_point()
                    if piece_center.y < midpoint.y:
                        midpoint = piece_center

                below = self._resolve_state(dtPoint(midpoint.x, midpoint.y))

                label = self.diagram.get_label_for_density(below.density)

                full_polygon = full_polygon.difference(polygon)

                polygons_out.append(
                    GraphPolygon(polygon, below, dtPoint(midpoint.x, midpoint.y), label)
                )

            full_polygon_point: shp.Point = full_polygon.representative_point()
            print(full_polygon_point)
            polygons_out.append(
                GraphPolygon(
                    full_polygon,
                    self.default_state,
                    dtPoint(full_polygon_point.x, full_polygon_point.y),
                    "A",
                )
            )

        return FigureResult(
            max_interface_pos,
            min_pos,
            max_time,
            -PLOT_THRESHOLD_OFFSET,
            user_interfaces_out,
            interfaces_out,
            polygons_out,
            trajectories_out,
        )

    def create_state_legend(self) -> tuple[Figure, Axes]:
        fig, ax = self.diagram.show()
        color_space = sns.color_palette("Spectral_r", as_cmap=True)

        for state in self._get_states():
            ax.scatter(
                state.density,
                state.flow,
                color=color_space(state.density / self.diagram.jam_density),
                s=50,
                alpha=1,
                zorder=2,
            )
            ax.annotate(
                self.diagram.get_label_for_density(state.density),
                xy=(state.density + 0.15, state.flow),
                horizontalalignment="center",
                verticalalignment="center",
            )

        plt.close(fig)

        return fig, ax

    def create_interface_legend(self) -> tuple[Figure, Axes]:
        """This function creates a helpful visual legend for what interfaces represent
        what state connection.

        NOTE: create_figure_x should be called before this or else everything will be black--
        the colors used reflect the ones generated in those functions

        Returns:
            tuple[Figure, Axes]: the legend
        """
        # note: this needs to be called after create_figure_x to generate the colors needed
        # otherwise it will be all black
        fig, ax = self.diagram.show()

        for interface in self.interfaces:
            if not interface.has_valid_states():
                continue

            assert interface.above and interface.below

            above, below = interface.above, interface.below
            ax.arrow(
                below.density,
                below.flow,
                (above.density - below.density),
                (above.flow - below.flow),
                color=self.colors.get((above, below), "black"),
                width=0.05,
                alpha=0.5,
            )

        plt.close(fig)

        return fig, ax

    def create_figure_px(self, with_trajectories=False, num_trajectories: int = 100) -> go.Figure:
        """This function generates a plotly figure showing the fundamental digram,
        using the currently generated interfaces stored in self.interfaces.

        Trajectories can also be plotted, if specified.

        Args:
            with_trajectories (bool, optional): Whether or not to plot trajectories.
            Defaults to False.

        Returns:
            tuple[Figure, Axes]: the figure and axes of the generated image
        """

        fig = go.Figure()
        fig.layout.hovermode = "closest"
        fig.layout.hoverdistance = -1  # ensures no "gaps" for selecting sparse data

        def line_plotter(
            p1: dtPoint,
            p2: dtPoint,
            dotted=False,
            color=None,
            alpha: Optional[float] = None,
            linewidth: Optional[float] = None,
            dashed=False,
        ):
            kwargs: dict[str, Any] = {}
            kwargs["line"] = {}

            if color:
                kwargs["line"]["color"] = color if isinstance(color, str) else f"rgb{color}"

            if alpha:
                kwargs["opacity"] = alpha

            kwargs["mode"] = "lines"
            if dotted:
                kwargs["mode"] = "markers+lines"

            if linewidth:
                kwargs["line"]["width"] = linewidth
            if dashed:
                kwargs["line"]["dash"] = "dash"

            fig.add_trace(
                go.Scatter(
                    x=(p1.time, p2.time),
                    y=(p1.position, p2.position),
                    hoverinfo="x+y",  # Show custom hover text
                    **kwargs,
                ),
            )

        def polygon_plotter():
            pass

        figure = self._create_figure(num_trajectories, with_trajectories, False)

        for user_interface in figure.user_interfaces:
            fig.add_trace(
                go.Scatter(
                    x=(user_interface.point1.time, user_interface.point2.time),
                    y=(user_interface.point1.position, user_interface.point2.position),
                    opacity=0.9,
                    line=dict(dash="dash", color="black"),
                    mode="lines",
                )
            )

        for interface in figure.interfaces:
            fig.add_trace(
                go.Scatter(
                    x=(interface.point1.time, interface.point2.time),
                    y=(interface.point1.position, interface.point2.position),
                    hoverinfo="x+y",
                    line=dict(
                        color=interface.color
                        if isinstance(interface.color, str)
                        else f"rgb{interface.color}"
                    ),
                    mode="markers+lines",
                )
            )

        for trajectory in figure.trajectories:
            for line in trajectory:
                fig.add_trace(
                    go.Scatter(
                        x=(line.point1.time, line.point2.time),
                        y=(line.point1.position, line.point2.position),
                        opacity=0.8,
                        line=dict(color=line.color, width=0.5),
                        mode="lines",
                    )
                )

        fig.update_layout(
            xaxis=dict(range=[figure.min_time, figure.max_time]),
            yaxis=dict(range=[figure.min_pos, figure.max_pos]),
            plot_bgcolor="white",
            autosize=False,
            width=1200,
            height=600,
        )

        return fig

    def _resolve_polygons(
        self,
        max_time: float,
        max_position: float,
        min_position: float,
        min_time: float = -PLOT_THRESHOLD_OFFSET,
    ) -> list[Polygon]:
        graph: collections.defaultdict[dtPoint, set[dtPoint]] = collections.defaultdict(
            lambda: set()
        )

        bottom_left = dtPoint(min_time, min_position)
        top_left = dtPoint(min_time, max_position)
        bottom_right = dtPoint(max_time, min_position)
        top_right = dtPoint(max_time, max_position)

        segments: SortedList[tuple[float, dtPoint]] = SortedList(key=lambda x: x[0])
        segments.add((min_position, bottom_right))
        segments.add((max_position, top_right))

        for interface in self.interfaces:
            if not interface.has_valid_states():
                continue

            x, y = interface.endpoints

            if y.time == float("inf"):
                y_pos = interface.get_pos_at_time(max_time)
                assert y_pos
                y = dtPoint(max_time, y_pos)

            if y != top_right and float_isclose(max_time, y.time):
                segments.add((y.position, y))

            graph[x].add(y)
            graph[y].add(x)

            for neighbor in graph[x]:
                graph[neighbor].add(x)

            for neighbor in graph[y]:
                graph[neighbor].add(y)

        graph[bottom_left].add(top_left)
        graph[bottom_left].add(bottom_right)
        graph[top_left].add(top_right)
        graph[top_left].add(bottom_left)
        graph[bottom_right].add(bottom_left)
        graph[top_right].add(top_left)

        for i in range(len(segments) - 1):
            _, below = segments[i]
            _, above = segments[i + 1]
            graph[below].add(above)
            graph[above].add(below)

        G = nx.Graph()

        for node, neighbors in graph.items():
            for neighbor in neighbors:
                G.add_edge(dataclasses.astuple(node), dataclasses.astuple(neighbor))

        cycles: list[list[tuple[float, float]]] = nx.minimum_cycle_basis(G)
        polygons: list[shp.Polygon] = []
        for cycle in cycles:
            polygon = Polygon([(x[0], x[1]) for x in cycle])

            if len(cycle) > 2 and not float_isclose(
                polygon.area, (max_time - min_time) * (max_position - min_position)
            ):
                polygons.append(polygon)

        return polygons
