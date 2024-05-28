import { MinPriorityQueue, HashMap, PriorityQueue } from "data-structure-typed";
import CapacityBottleneck from "./augmenters/base_augmenter";
import { State, Event, DiagramInterface, dtPoint, IntersectionEvent, TruncationEvent, UserInterface, float_isclose, CapacityEvent, FixedTimeComparable, compareFixedTimeComparable, EventType, Trajectory } from "./drawer_utils";
import FundamentalDiagram from "./fundamental_diagram";
import assert from "assert";

const EPS: number = 1e-4;

/**
 * This class encapsulates all the logic needed to create the shockwave diagram given a fundmental diagram settings object and a list of augments to consider.
 *
 * @export
 * @class ShockwaveDrawer
 */
export default class ShockwaveDrawer {
    private diagram: FundamentalDiagram;
    private default_state: State;
    private augments: CapacityBottleneck[];

    private events: MinPriorityQueue<Event> = new MinPriorityQueue(undefined, {"comparator": Event.compareTo});
    private interfaces: DiagramInterface[] = [];
    
    private intersections: HashMap<dtPoint, IntersectionEvent> = new HashMap(undefined, {"hashFn": dtPoint.hash});
    private truncations: HashMap<dtPoint, TruncationEvent> = new HashMap(undefined, {"hashFn": dtPoint.hash});


    /**
     * Creates an instance of ShockwaveDrawer.
     * 
     * @param {FundamentalDiagram} diagram fundamental diagram to act as the backbone "settings" for the drawer
     * @param {CapacityBottleneck[]} augments list of augments to consider
     * @memberof ShockwaveDrawer
     */
    constructor(diagram: FundamentalDiagram, augments: CapacityBottleneck[]) {
        this.diagram = diagram;
        this.default_state = this.diagram.getInitialState();
        this.augments = augments;
    }

    /**
     * Sets up all the data structures needed to run through the shockwave drawer. If already run through once, this resets all data structures for a re-entrant rerun.
     *
     * @private
     * @memberof ShockwaveDrawer
     */
    private setup(): void {
        // clear everything
        this.events.clear();
        this.interfaces = [];

        this.intersections.clear();
        this.truncations.clear();

        // initialize capacity events
        for (const augment of this.augments) {
            augment.init(this);
        }

        // check for potential user interface intersections (which are not supported)
        if (this.intersections.size != 0) {
            throw new EvalError("Had intersection between two user interfaces");
        }
    }

    /**
     * Adds an interface to the rolling list of interfaces. Handles intersections with other interfaces accordingly by creating new events/updating existing events.
     *
     * @private
     * @param {DiagramInterface} diagram_interface interface to add
     * @memberof ShockwaveDrawer
     */
    private addInterface(diagram_interface: DiagramInterface): void {
        // iterate over the interfaces
        for (const x of this.interfaces) {
            // compute the intersection
            let intersect: dtPoint | undefined;
            try {
                intersect = diagram_interface.intersection(x);
            } catch (err) {
                console.error(err);
                throw err;
            }

            // if no intersection or the intersection is trivial, skip
            if (intersect === undefined || diagram_interface.hasEndpoint(intersect)) {
                continue;
            }

            // if the intersected interface is user generated, we have a truncation event
            if (x.isUserGenerated()) {
                // either update an existing truncation event or create a new one
                let event: TruncationEvent | undefined = this.truncations.get(intersect);
                
                if (event === undefined) {
                    event = new TruncationEvent(intersect, x as UserInterface, [diagram_interface]);

                    this.truncations.set(intersect, event);
                    this.events.add(event);
                } else {
                    if (!event.interfaces.includes(diagram_interface)) {
                        event.interfaces.push(diagram_interface);
                    }
                }
            // otherwise, we have an intersection event
            } else {
                // either update an existing intersection event or create a new one
                let event: IntersectionEvent | undefined = this.intersections.get(intersect);

                if (event === undefined) {
                    event = new IntersectionEvent(intersect, [diagram_interface, x]);

                    this.intersections.set(intersect, event);
                    this.events.add(event);
                } else {
                    if (!event.interfaces.includes(x)) {
                        event.interfaces.push(x);
                    }
                    if (!event.interfaces.includes(diagram_interface)) {
                        event.interfaces.push(diagram_interface);
                    }
                }
            }
        }

        this.interfaces.push(diagram_interface);
    }

    /**
     * Helper function for determining the downstream/upstream (by position) state of a given point. Resolves these states by considering interfaces. Finds either the closest downstream/upstream interface, or returns the default state if there is none.
     *
     * @private
     * @param {dtPoint} point point to resolve state for
     * @param {boolean} [below=true] whether or not to get the upstream state
     * @return {State} resultant state
     * @memberof ShockwaveDrawer
     */
    private resolveState(point: dtPoint, below: boolean = true): State {
        const scale = below ? 1 : -1;
        let res: DiagramInterface | undefined = undefined;
        let min_dist: number = Infinity;

        for (const diagram_interface of this.interfaces) {
            if (diagram_interface.above === undefined) {
                console.assert(diagram_interface.isUserGenerated(), "have non-user-generated interface with an undefined above/below state");
                continue;
            }

            const cur: number | undefined = diagram_interface.getPosAtTime(point.time + EPS);

            if (cur === undefined || float_isclose(point.position, cur)) {
                continue;
            }

            if (res !== undefined && float_isclose(scale * (point.position - cur), min_dist)) {
                if ((below && diagram_interface.slope > res.slope) || (!below && diagram_interface.slope < res.slope)) {
                    res = diagram_interface;
                } else if ((scale * (point.position - cur) >= 0 && (scale * (point.position - cur) < min_dist))) {
                    res = diagram_interface;
                    min_dist = scale * (point.position - cur);
                }
            }
        }

        if (res !== undefined) {
            if (below) {
                return res.above!;
            }

            return res.below!;
        }

        return this.default_state;
    }

    /**
     * Returns all unique states found throughout the shockwave drawer. 
     *
     * @private
     * @return {State[]} list of unique states
     * @memberof ShockwaveDrawer
     */
    private getStates(): State[] {
        const states: HashMap<State, undefined> = new HashMap(undefined, {"hashFn": State.hash});

        for (const diagram_interface of this.interfaces) {
            if (diagram_interface.hasValidStates()) {
                states.set(diagram_interface.above!, undefined);
                states.set(diagram_interface.below!, undefined);
            }
        }

        const res: State[] = [];
        for (const state of states.keys()) {
            res.push(state);
        }

        return res;
    }

    /**
     * Handles the processing of a capacity event, an event at which a change in capacity occurs in the time-space diagram. Determines behavior using the prior/posterior capacity defined by the event and the fundamental diagram.
     *
     * @private
     * @param {CapacityEvent} cur event to handle
     * @return {boolean} whether or not a new state was created
     * @memberof ShockwaveDrawer
     */
    private handleCapacityEvent(cur: CapacityEvent): boolean {
        // if event no longer needs to be handled, don't
        if (cur.user_interface.getPosAtTime(cur.point.time) === undefined) {
            return false;
        }

        // state resolution & determination of the prior and posterior capacity
        const above: State = this.resolveState(cur.point, false);
        const below: State = this.resolveState(cur.point, true);

        const prior_capacity = cur.prior_capacity === -1 ? below.flow : cur.prior_capacity;

        // this occurs if the first event of the capacity event (the drop) did not happen
        if (prior_capacity !== below.flow) {
            return false;
        }

        let posterior_capacity = cur.posterior_capacity === -1 ? this.diagram.getMaxState().flow : cur.posterior_capacity;
        const interface_slope = cur.user_interface.getSlope();

        // posterior capacity is limited by incoming flow IF the state is queued
        if (!this.diagram.stateIsQueued(below)) {
            posterior_capacity = Math.min(posterior_capacity, below.flow);
        }

        // if we have an increase in capacity and there is not enough density (queueing) to take advantage of that, only add an interface if it is trivial
        if ((posterior_capacity > prior_capacity || float_isclose(posterior_capacity, prior_capacity)) && (!this.diagram.stateIsQueued(below) || above.equalTo(below))) {
            if (!float_isclose(above.density, below.density)) {
                this.addInterface(new DiagramInterface(
                    cur.point,
                    this.diagram.getInterfaceSlope(above.density, below.density),
                    above,
                    below,
                    cur.point
                ));
            }

            return false;
        // have a canonical capacity event with a meaningful change in capacity
        } else {
            let state_created = false;

            // main interface of event; right side result of capacity change (according to fundamental diagram)
            const main_interface_state: State = this.diagram.getStateByFlow(posterior_capacity, false);

            // if the interface state is nontrivial, process it
            if (!main_interface_state.equalTo(below)) {
                const main_interface = new DiagramInterface(
                    cur.point,
                    this.diagram.getInterfaceSlope(main_interface_state.density, below.density),
                    main_interface_state,
                    below,
                    cur.point
                );

                this.addInterface(main_interface);

                if (float_isclose(main_interface.slope, interface_slope)) {
                    throw new EvalError("An invalid interface was somehow created--duplicated the original interface");
                }

                assert(main_interface.above !== undefined);
                assert(main_interface.below !== undefined);

                // update states -- enforces that these set states are logically consistent (any time we set an interface, the result would be identical)
                if (cur.user_interface.upper_bound.equalTo(cur.point)) {
                    if (main_interface.slope < interface_slope) {
                        cur.user_interface.setBelowState(main_interface.below);
                    } else if (main_interface.slope > interface_slope) {
                        cur.user_interface.setAboveState(main_interface.above);
                    }
                } else {
                    if (main_interface.slope < interface_slope) {
                        cur.user_interface.setBelowState(main_interface.above);
                    } else if (main_interface.slope > interface_slope) {
                        cur.user_interface.setAboveState(main_interface.below);
                    }
                }

                state_created ||= true;
            } else {
                // otherwise, there is no interface and simply pass through states
                cur.user_interface.setBelowState(below);
            }

            // byproduct state -- to conserve cars on the left side of the fundamental diagram
            const byproduct_interface_state = this.diagram.getStateByFlow(posterior_capacity, true);

            // same logic as with the main state
            if (!byproduct_interface_state.equalTo(above)) {
                const byproduct_interface = new DiagramInterface(
                    cur.point,
                    this.diagram.getInterfaceSlope(above.density, byproduct_interface_state.density),
                    above,
                    byproduct_interface_state,
                    cur.point
                );

                if (float_isclose(byproduct_interface.slope, interface_slope)) {
                    throw new EvalError("An invalid interface was somehow created -- duplicated existing interface");
                }

                assert(byproduct_interface.above);
                assert(byproduct_interface.below);

                if (cur.user_interface.upper_bound.equalTo(cur.point)) {
                    if (byproduct_interface.slope < interface_slope) {
                        cur.user_interface.setBelowState(byproduct_interface.below);
                    } else if (byproduct_interface.slope > interface_slope) {
                        cur.user_interface.setAboveState(byproduct_interface.above);
                    }
                } else {
                    if (byproduct_interface.slope < interface_slope) {
                        cur.user_interface.setBelowState(byproduct_interface.above);
                    } else if (byproduct_interface.slope > interface_slope) {
                        cur.user_interface.setAboveState(byproduct_interface.below);
                    }
                }

                 state_created ||= true;
            } else {
                cur.user_interface.setAboveState(above);
            }

            return state_created;
        }
    }

    /**
     * Handles an intersection event, in which any number of interfaces that are not user generated intersect, potentially creating a new outgoing interface while limiting the extents of the component interfaces.
     *
     * @private
     * @param {IntersectionEvent} cur event to handle
     * @param {boolean} [force=false] whether or not to force an intersection event (ignore checking for consistency)
     * @return {boolean} whether or not a new interface was created
     * @memberof ShockwaveDrawer
     */
    private handleIntersectionEvent(cur: IntersectionEvent, force: boolean = false): boolean {
        console.assert(cur.interfaces.length >= 2, "number of interfaces in an intersection event msut necessarily be greater than or equal to 2");

        // check whether or not this event is registered in the intersectionevent log
        if (!force && !this.intersections.delete(cur.point)) {
            throw new EvalError("Had an intersection event that was recorded in the intersection dictionary");
        }

        // gather all valid interfaces at this point
        const interfaces: DiagramInterface[] = [];

        for (const diagram_interface of cur.interfaces) {
            if (diagram_interface.getPosAtTime(cur.point.time) === undefined) {
                continue;
            }

            interfaces.push(diagram_interface);
        }

        // if there is only one valid interface, there is nothing to do
        if (interfaces.length <= 1) {
            return false;
        }

        // determine among the interfaces the above and below state of the new offshooting interface using slope logic
        let max_slope: number = -1 * Infinity;
        let above: State | undefined;
        let min_slope: number = Infinity;
        let below: State | undefined;

        let no_new_interface: boolean = false;

        for (const diagram_interface of interfaces) {
            console.assert(!diagram_interface.isUserGenerated(), "interface being processed in intersection event does not is user generated, which is invalid");
            
            if (diagram_interface.slope > max_slope) {
                max_slope = diagram_interface.slope;
                below = diagram_interface.below;
            }

            if (diagram_interface.slope < min_slope) {
                min_slope = diagram_interface.slope;
                above = diagram_interface.above;
            }

            try {
                diagram_interface.addCutoff(undefined, cur.point);
            } catch (err) {
                console.error(`Had error adding cutoff. May be intended. ${diagram_interface}, ${err}`);
                no_new_interface = true;
            }
        }

        if (no_new_interface) {
            return false;
        }

        if (above === undefined || below === undefined) {
            throw new EvalError("above/below must not be undefined when resolved in an intersection event");
        }

        // create a new interface if it would be non-trivial
        if (above !== below) {
            const new_interface = new DiagramInterface(
                cur.point,
                this.diagram.getInterfaceSlope(above?.density, below.density),
                above,
                below,
                cur.point
            );

            this.addInterface(new_interface);

            return true;
        }

        return false;
    }

    /**
     * Handles a truncation event, in which any number of non-user-generated interfaces intersect with a single user-generated interface. Either handles it by converting the event to a new capacity event by fiat or by creating a new intersectionevent organically.
     *
     * @private
     * @param {TruncationEvent} cur
     * @memberof ShockwaveDrawer
     */
    private handleTruncationEvent(cur: TruncationEvent): void {
        // check for whether or not a truncation event is recorded for this point
        if (!this.truncations.delete(cur.point)) {
            throw new EvalError("There was a truncation event that wasn't recorded in the trunction event dictionary/log");
        }

        // check if the user interface is still defined here
        if (cur.user_interface.getPosAtTime(cur.point.time) === undefined) {
            // if it isn't, return early
            // don't need to convert to intersectionevent since one already exists since addInterface handles this already
            return;
        }

        // gather all valid interfaces that are defined at the event's point & cutoff the component interfaces
        const interfaces: DiagramInterface[] = [];

        for (const diagram_interface of cur.interfaces) {
            if (diagram_interface.getPosAtTime(cur.point.time) === undefined) {
                continue;
            }

            interfaces.push(diagram_interface);
            diagram_interface.addCutoff(undefined, cur.point);
        }

        // if the user interface has not already been processed (it doesn't have valid states), create a new capacity event for when it "starts"
        if (!cur.user_interface.hasValidStates()) {
            console.log("converting to capacity event")

            this.handleCapacityEvent(
                new CapacityEvent(
                    cur.point,
                    cur.user_interface,
                    -1,
                    cur.user_interface.augment.bottleneck
                )
            );
        // otherwise, try to handle it as an intersection event
        } else {
            console.log("handling right truncation event");

            // create a new interface to represent that this user interface is being split into two "components"
            // the newly-created interface is the old one but with a right-side cutoff
            // the previously-existing interface is nulled out with a left-side cutoff
            const new_interface: UserInterface = cur.user_interface.clone();
            this.interfaces.push(new_interface);
            cur.user_interface.addCutoff(cur.point);
            cur.user_interface.above = cur.user_interface.below = undefined;

            // process resulting intersectionevent & cutoff user-interface if a new state is created in its place
            const state_created = this.handleIntersectionEvent(
                new IntersectionEvent(cur.point, [new_interface as DiagramInterface].concat(cur.interfaces)), true
            );

            if (state_created) {
                cur.user_interface.addCutoff(undefined, cur.point);
            }
        }
    }

    public run(simulation_time: number): void {
        this.setup();

        while (this.events.size != 0) {
            const time: number = this.events.peek()!.point.time;

            const pos_queue: PriorityQueue<FixedTimeComparable> = new PriorityQueue(undefined, {"comparator": compareFixedTimeComparable});

            while (this.events.size != 0) {
                const x: Event = this.events.poll()!;

                let priority: number = -1;

                switch(x.type) {
                    case EventType.capacity: {
                        priority = 3;
                        break;
                    }
                    case EventType.intersection: {
                        priority = 1;
                        break;
                    }
                    case EventType.truncation: {
                        if ((x as TruncationEvent).user_interface.hasValidStates()) {
                            priority = 1;
                        } else {
                            priority = 2;
                        }
                    }
                }

                pos_queue.add({"event": x, "priority": priority, "position": x.point.position});
            }

            while (pos_queue.size != 0) {
                const cur = pos_queue.poll()!;
                const event = cur.event;

                if (event.disabled) {
                    continue;
                }

                console.log(`processing ${event}`);

                switch (event.type) {
                    case EventType.capacity: {
                        this.handleCapacityEvent(event as CapacityEvent);
                        break;
                    }
                    case EventType.intersection: {
                        this.handleIntersectionEvent(event as IntersectionEvent);
                        break;
                    }
                    case EventType.truncation: {
                        this.handleTruncationEvent(event as TruncationEvent);
                        break;
                    }
                }
            }
        }
    }

    private findClosestIntersectionPoint(cur: Trajectory):  {
        const min_intersect_time: number = Infinity;
        res = 
    }


}