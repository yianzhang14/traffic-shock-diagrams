import collections
from typing import Callable, Optional, cast

import matplotlib.pyplot as plt
import numpy as np
import plotly.graph_objects as go
import seaborn as sns
import shapely.geometry as shp
from matplotlib.patches import Polygon
from sortedcontainers import SortedList

from src.augmenters.base_augmenter import TrafficAugmenter
from src.custom_types import Axes, Figure

from .drawer_utils import (
    EPS,
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


class ShockwaveDrawer:
    """This encapsulates the main logic for creating a situation and determining
    the shockwave diagram for the created situation.
    """

    def __init__(
        self,
        diagram: FundamentalDiagram,
        simulation_time: float,
        augments: list[TrafficAugmenter],
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

        # default state given the initial density
        self.default_state = self.diagram.get_state(init_density)

        self.augments: list[TrafficAugmenter] = augments

    def _setup(self):
        """This function initializes all the data structures needed to run through the
        shockwave drawer. If already run through once, this resets all the data structures
        for a correct rerun."""
        # interfaces created throughout the drawer lifetime
        self.interfaces: list[Interface] = []

        # use this to maintain the invariant that there should only be one event
        # at any given point -- this handles 3+ interface intersections
        self.intersections: dict[dtPoint, IntersectionEvent] = {}

        # these map UserInterfaces to the original prior/posterior capacities of a CapacityEvent
        # that was postponed due to being restricted to 0/0 prior/post capacity
        self.latent_events: dict[UserInterface, tuple[float, float]] = {}

        # initialize the augments -- add their events to the event queue
        for augment in self.augments:
            augment.init(self.simulation_time, self.events, self.interfaces)

        self.colors: dict[tuple[State, State], np.ndarray] = dict()

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
        min_intersect: dtPoint | None = None
        min_interfaces: list[Interface] = []

        min_truncation: dtPoint | None = None
        min_truncation_interfaces: list[Interface] = []

        # find the interface that intersects the closest from the given interface
        for x in self.interfaces:
            assert not x.equivalent_to(interface)  # basic sanity check -- should never happen

            intersect = interface.intersection(x)

            # ignore overlaps and non-intersecting interfaces
            if intersect is None or interface.has_endpoint(intersect):
                continue

            if x.is_user_generated():
                if min_truncation and min_truncation == intersect:
                    min_truncation_interfaces.append(x)
                elif not min_truncation or intersect.time < min_truncation.time:
                    min_truncation = intersect
                    min_truncation_interfaces = [x]
            else:
                if min_intersect and min_intersect == intersect:
                    min_interfaces.append(x)
                elif not min_intersect or intersect.time < min_intersect.time:
                    min_intersect = intersect
                    min_interfaces = [x]

        # add the interface in question to the list since that is part of the  event
        min_interfaces.append(interface)
        min_truncation_interfaces.append(interface)

        if min_truncation:
            truncation_event = TruncationEvent(
                min_truncation, min_truncation_interfaces[0], min_truncation_interfaces[1:]
            )
            self.events.add(truncation_event)

            interface.truncation_event = truncation_event

        # if we have an interesct, generate an IntersectionEvent between these two interfaces
        if min_intersect:
            # update an existing intersection event by adding it to the list of interfaces
            # can just do address comparison (no __eq__ overwriting) since we are only looking
            # at existing interfaces (i think -- should check)
            if min_intersect in self.intersections:
                event: IntersectionEvent = self.intersections.get(min_intersect)

                for interface in min_interfaces:
                    if interface not in event.interfaces:
                        event.interfaces.append(interface)
            # create a brand new intersection event
            else:
                event = IntersectionEvent(min_intersect, min_interfaces)
                self.events.add(event)
                self.intersections[min_intersect] = event

        # add the interface to the list
        self.interfaces.append(interface)

    def _resolve_state(self, point: dtPoint, below: bool = True) -> State:
        """Private function to resolve the upstream and downstream state from a point.

        Reasoning: on the dt-plane, you can get the interface that pertains to an event by looking
        directly down from the event point (in the distance dimension) and taking the
        above state of the closest interface. Same idea for getting the above state

        OPTIMIZE: make this more efficient with segment trees
        TODO: handle user-generated interfaces more elegantly -- currently allow
        user-generated interfaces to be considered, as long as they have an above/below state

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

            if cur is None:
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
            if below:
                return res.above
            return res.below

        return self.default_state

    def _handle_capacity_event(self, cur: CapacityEvent) -> bool:
        """Private function for handling a capacity event. Determines what to do
        using the prior/posterior capacity (adjusted for the current state)
        and the fundamental diagram.

        Args:
            cur (CapacityEvent): The capacity event to handle
            above (State): the state above the point of the capacity event
            below (State): the state below the point of the capacity event
        """
        above = self._resolve_state(cur.point, below=False)
        below = self._resolve_state(cur.point, below=True)

        # fig, ax = self.create_figure_plt(with_trajectories=True)
        # fig.savefig(f"data/log_{self.i}.png")
        # self.i += 1

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

        # if we have an increase in capacity and there is not enough density (queuing)
        # to take advantage of that increase, do nothing -- no interface created
        # this applies to 0 into 0 since posterior and prior both 0
        if (
            posterior_capacity > prior_capacity or float_isclose(posterior_capacity, prior_capacity)
        ) and not self.diagram.state_is_queued(below):
            self.latent_events[cur.interface] = (cur.prior_capacity, cur.posterior_capacity)
            return False
        # we have an actual event with a decrease in capacity
        else:
            state_created = False

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

                interface_slope = cur.interface.get_slope()

                # this assumes that the interface are logically consistent -- for any time this
                # interface setting may occur, the result would be identical
                if float_isclose(main_interface.slope, interface_slope):
                    # this means it is exactly the current interface slope -- invalid
                    raise RuntimeError("An invalid interface was somehow created")
                if main_interface.slope < interface_slope:
                    cur.interface.below = main_interface.above
                elif main_interface.slope > interface_slope:
                    cur.interface.above = main_interface.below

                state_created |= True

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

                if float_isclose(byproduct_interface.slope, interface_slope):
                    # this means it is exactly the current interface slope -- invalid
                    raise RuntimeError("An invalid interface was somehow created")
                if byproduct_interface.slope < interface_slope:
                    cur.interface.below = byproduct_interface.above
                elif byproduct_interface.slope > interface_slope:
                    cur.interface.above = byproduct_interface.below

                state_created |= True

            return state_created

    def _handle_intersection_event(self, cur: IntersectionEvent) -> None:
        """Handles an intersection event. Determines behavior purely using
        the intersecting interfaces in question and basic dt-diagram
        resolutions.

        TODO: handle the assertion that the above/below states are not None for CapEvent interfaces

        Args:
            cur (IntersectionEvent): the IntersectionEvent to process
        """
        assert len(cur.interfaces) >= 2

        # remove the intersectionevent from the dictionary
        self.intersections.pop(cur.point)

        # resolve the actual interfaces at question -- during execution, may have invalidated some
        # so need to remove the interfaces that would not longer be cutoff here
        interfaces: list[Interface] = []

        truncation_events: list[TruncationEvent] = []

        for interface in cur.interfaces:
            assert not interface.is_user_generated()

            if interface.get_pos_at_time(cur.point.time) is None:
                continue
            interfaces.append(interface)

            if interface.truncation_event:
                truncation_events.append(interface.truncation_event)

        # don't do anything if there is nothing else to do
        if len(interfaces) <= 1:
            return

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

        for event in truncation_events:
            if event.right_truncated:
                below_state = self._resolve_state(cur.point)
                self._add_interface(
                    Interface(
                        cur.point,
                        below_state.get_slope(),
                        below,
                        below_state,
                        lower_bound=cur.point,
                        upper_bound=event.user_interface.original_upper_bound,
                    )
                )
                break

    def _handle_truncation_event(self, cur: TruncationEvent) -> None:
        interfaces: list[Interface] = []

        for interface in cur.interfaces:
            if interface.get_pos_at_time(cur.point.time) is None:
                continue
            interfaces.append(interface)

        if cur.user_interface.get_pos_at_time(cur.point.time) is None:
            return

        if len(interfaces) == 0:
            return

        # assumption: if we ever have an intersection with an user-generated interface,
        # this is because the user-generated interface started within an empty state
        # (the converse where the user-generated interface hit an empty state is impossible
        # since it would've made an interface below it that would hit the empty state instead)
        # in this case, we need some custom logic to handle things

        # if the current interface is a latent event, we process it as such
        if cur.user_interface in self.latent_events:
            if cur.user_interface.has_endpoint(cur.point):
                return
            # extract prior/post capacity to inform the capacity event
            prior_cap, post_cap = self.latent_events.pop(cur.user_interface)
            print("converting to capacity event")

            # handle the capacity event using the information we have
            state_created = self._handle_capacity_event(
                CapacityEvent(
                    cur.point,
                    cur.user_interface,
                    prior_capacity=prior_cap,
                    posterior_capacity=post_cap,
                )
            )

            # XXX: truncate everything accordingly -- this would only work for traffic lights
            # since this assumes that there is no need for an interface above the user-generated
            # interface -- i.e. this implies that the state above the user-generated interface
            # is empty
            if state_created:
                for interface in interfaces:
                    if interface == cur.user_interface:
                        continue

                    interface.add_cutoff(upper=cur.point)

                # optional: truncate the user-generated interface to actually
                # start where it is supposed to (where there is flow to manipulate)
                cur.user_interface.add_cutoff(lower=cur.point)
        elif cur.user_interface.has_valid_states():
            print("handling right truncation event")
            cur.user_interface.add_cutoff(upper=cur.point)
            cur.right_truncated = True
        else:
            for interface in interfaces:
                interface.add_cutoff(upper=cur.point)

    def run(self):
        """Main function to generate the shockwave diagram given the inputs."""

        self.i = 0

        # setup required data structures
        self._setup()

        # while there are more events to process
        while self.events:
            # get the first event (first event in time)
            cur: Event = self.events.pop(0)

            # support disabling of events -- currently unused
            if cur.disabled:
                continue

            print(f"processing {cur}")

            # handle the vent based on its type
            match cur.type:
                case EventType.capacity:
                    self._handle_capacity_event(cur)
                case EventType.intersection:
                    self._handle_intersection_event(cur)
                case EventType.truncation:
                    self._handle_truncation_event(cur)

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

            intersection = interface.intersection(cur)

            if intersection is None or cur.has_endpoint(intersection):
                continue

            if intersection.time < min_intersect_time:
                min_intersect_time = intersection.time
                res = (intersection, interface)

        return res

    def create_figure_plt(
        self, with_trajectories=False, num_trajectories: int = 100, with_polygons=False
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
        ax: Axes

        def line_plotter(
            p1: dtPoint,
            p2: dtPoint,
            dotted=False,
            color=None,
            alpha: Optional[float] = None,
            linewidth: Optional[float] = None,
            dashed=False,
        ):
            kwargs = {}
            if dotted:
                kwargs["marker"] = "o"
            if color:
                kwargs["c"] = color

            if alpha:
                kwargs["alpha"] = alpha
            if linewidth:
                kwargs["linewidth"] = linewidth
            if dashed:
                kwargs["linestyle"] = "dashed"

            ax.plot((p1.time, p2.time), (p1.position, p2.position), **kwargs)

        max_pos, max_time, min_pos = self._create_figure(
            line_plotter, num_trajectories, with_trajectories
        )

        ax.set_xbound(-PLOT_THRESHOLD_OFFSET, max_time)
        ax.set_ybound(min_pos - PLOT_THRESHOLD_OFFSET, max_pos)

        if with_polygons:
            polygons = self._resolve_polygons(max_time, max_pos, min_pos - PLOT_THRESHOLD_OFFSET)

            color_space = sns.color_palette("tab20", len(polygons))

            for i, polygon in enumerate(polygons):
                ax.add_patch(
                    Polygon(
                        polygon.exterior.coords,
                        closed=True,
                        alpha=0.2,
                        color=color_space[i],
                    )
                )

        plt.close(fig)

        return (fig, ax)

    def _create_figure(
        self, line_plotter: Callable, num_trajectories: int, with_trajectories: bool
    ) -> tuple[float, float, float]:
        color_space = sns.color_palette("tab20", int(len(self.interfaces) ** 0.5) + 10)
        idx = 0

        max_pos: float = -1
        max_time: float = -1
        min_pos = float("inf")

        for interface in self.interfaces:
            p1 = interface.endpoints[0]

            max_time = max(max_time, p1.time)

        max_time = max(max_time, self.simulation_time) + PLOT_THRESHOLD_OFFSET

        for interface in self.interfaces:
            # don't draw interfaces without valid states -- if they don't
            # have valid states, they weren't ever processed
            if not interface.has_valid_states():
                continue

            p1 = interface.endpoints[0]
            p2 = interface.endpoints[1]

            pos = interface.get_pos_at_time(max_time)

            min_pos = min(min_pos, p1.position)

            if p2.time != float("inf"):
                min_pos = min(min_pos, p2.position)

            if p2.time == float("inf"):
                max_pos = max(max_pos, pos)
                p2 = dtPoint(
                    max_time,
                    pos,
                )

            color = "black"

            if not interface.is_user_generated():
                tup: tuple[State, State] = (interface.above, interface.below)

                if tup in self.colors:
                    color = self.colors[tup]
                else:
                    color = color_space[idx]
                    idx += 1
                    self.colors[tup] = color

            if p1 != p2:
                line_plotter(p1, p2, dotted=True, color=color)

            if interface.is_user_generated():
                line_plotter(
                    cast(UserInterface, interface).original_lower_bound,
                    cast(UserInterface, interface).original_upper_bound,
                    alpha=0.9,
                    dotted=False,
                    dashed=True,
                    color="black",
                )

        try:
            if with_trajectories:
                # gap = self.default_state.density
                slope = self.default_state.get_slope()

                for pos in np.linspace(
                    -slope * max_time,
                    max_pos,
                    num_trajectories,
                ):
                    cur = Trajectory(dtPoint(0, pos + 0.1), slope)

                    while True:
                        x = self._find_closest_intersection_traj(cur)
                        next_trajectory: Trajectory | None = None

                        if x is not None:
                            intersection, interface = x
                            interface: Interface
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
                            p2 = dtPoint(
                                max_time + PLOT_THRESHOLD_OFFSET,
                                cur.get_pos_at_time(max_time + PLOT_THRESHOLD_OFFSET),
                            )

                        line_plotter(
                            p1,
                            p2,
                            dotted=False,
                            color="grey",
                            alpha=0.8,
                            linewidth=0.5,
                        )

                        if next_trajectory is not None:
                            cur = next_trajectory
                        else:
                            break
        except Exception as e:
            print(e)

        return max_pos, max_time, min(min_pos, 0) - PLOT_THRESHOLD_OFFSET

    def create_legend(self) -> tuple[Figure, Axes]:
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
            kwargs = {}
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

        max_pos, max_time, min_pos = self._create_figure(
            line_plotter, num_trajectories, with_trajectories
        )

        fig.update_layout(
            xaxis=dict(range=[0, max_time]),
            yaxis=dict(range=[min_pos - PLOT_THRESHOLD_OFFSET, max_pos]),
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
        min_time: float = 0,
    ) -> list[Polygon]:
        self.polygons = []

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
                y = dtPoint(max_time, interface.get_pos_at_time(max_time))

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

        polygons: list[shp.Polygon] = []

        seen: set[tuple[dtPoint, dtPoint]] = set()
        for point in graph.keys():
            if (
                float_isclose(point.time, min_time)
                or float_isclose(point.position, max_position)
                or float_isclose(point.position, min_position)
            ):
                continue
            stack: collections.deque[dtPoint] = collections.deque([point])

            cur = None
            for neighbor in graph[point]:
                if (point, neighbor) not in seen:
                    cur = neighbor
                    break

            if cur is None:
                continue

            while cur:
                stack.append(cur)

                prev_vec = np.array([cur.time - stack[-2].time, cur.position - stack[-2].position])

                max_angle: float = -1
                next_point: dtPoint | None = None

                for neighbor in graph[cur]:
                    vec = -1 * np.array(
                        [neighbor.time - cur.time, neighbor.position - cur.position]
                    )

                    if float_isclose(np.linalg.norm(prev_vec), 0) or float_isclose(
                        np.linalg.norm(vec), 0
                    ):
                        continue

                    expr = np.dot(prev_vec, vec) / np.linalg.norm(prev_vec) / np.linalg.norm(vec)
                    angle: float = np.degrees(np.arccos(np.clip(expr, -1, 1)))

                    sign: float = np.sign(prev_vec[0] * vec[1] - prev_vec[1] * vec[0])

                    if sign < 0:
                        angle = 360 - angle

                    if angle > max_angle:
                        max_angle = angle
                        next_point = neighbor

                if next_point == point:
                    break
                cur = next_point

            for i in range(len(stack) - 1):
                seen.add((stack[i], stack[i + 1]))
            seen.add((stack[-1], stack[0]))

            if len(stack) <= 2:
                continue
            polygon = shp.Polygon([(x.time, x.position) for x in stack])

            if not float_isclose(
                polygon.area, (max_time - min_time) * (max_position - min_position)
            ):
                polygons.append(polygon)

        return polygons
