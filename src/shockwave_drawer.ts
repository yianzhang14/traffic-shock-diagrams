import * as turf from "@turf/turf";
import { acos, dot, norm, pi, sign, } from "mathjs";
import polylabel from "polylabel";
import { Dictionary, Set, PriorityQueue, DefaultDictionary } from "typescript-collections";

import { CapacityBottleneck } from "./augmenters/base_augmenter";
import {
  State,
  Event,
  DiagramInterface,
  dtPoint,
  IntersectionEvent,
  TruncationEvent,
  UserInterface,
  floatIsClose,
  CapacityEvent,
  FixedTimeComparable,
  compareFixedTimeComparable,
  EventType,
  Trajectory,
} from "./drawer_utils";
import { FundamentalDiagram } from "./fundamental_diagram";
import { calculateArea, clip, debugLog } from "./misc";
import { polygon_t, Viewport } from "./types";
import { FigureResult, GraphInterface, GraphLine, GraphPolygon, GraphTrajectory, Pair } from "./types";

const EPS = 1e-4;
const PlotThresholdOffset = 1;

/**
 * This class encapsulates all the logic needed to create the shockwave diagram given a fundmental diagram settings object and a list of augments to consider.
 *
 * @export
 * @class ShockwaveDrawer
 */
export class ShockwaveDrawer {
  private diagram: FundamentalDiagram;
  private defaultState: State;
  private augments: CapacityBottleneck[] = [];

  private events = new PriorityQueue<Event>(Event.compareTo);
  private interfaces: DiagramInterface[] = [];

  private intersections = new Dictionary<dtPoint, IntersectionEvent>();
  private truncations = new Dictionary<dtPoint, TruncationEvent>();

  private simulationTime: number | undefined;


  /**
 * Creates an instance of ShockwaveDrawer.
 * 
 * @param {FundamentalDiagram} diagram fundamental diagram to act as the backbone "settings" for the drawer
 * @param {CapacityBottleneck[]} augments list of augments to consider
 * @memberof ShockwaveDrawer
 */
  constructor(diagram: FundamentalDiagram) {
    this.diagram = diagram;
    this.defaultState = this.diagram.getInitialState();
  }

  /**
 * Sets up all the data structures needed to run through the shockwave drawer. If already run through once, this resets all data structures for a re-entrant rerun.
 *
 * @private
 * @memberof ShockwaveDrawer
 */
  private setup(augments: CapacityBottleneck[]): void {
    this.augments = augments;

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
    if (this.intersections.size() !== 0) {
      throw new EvalError("Had intersection between two user interfaces");
    }
  }

  public addUserInterface(diagramInterface: UserInterface): void {
    if (!diagramInterface.isUserGenerated()) {
      throw new TypeError("Can only add user interfaces");
    }

    this.addInterface(diagramInterface);
  }

  public addCapacityEvent(event: CapacityEvent): void {
    if (!(event.type === EventType.capacity)) {
      throw new TypeError("Can only add capacity events");
    }

    this.events.add(event);
  }

  /**
 * Adds an interface to the rolling list of interfaces. Handles intersections with other interfaces accordingly by creating new events/updating existing events.
 *
 * @private
 * @param {DiagramInterface} diagramInterface interface to add
 * @memberof ShockwaveDrawer
 */
  private addInterface(diagramInterface: DiagramInterface): void {
    // iterate over the interfaces
    for (const x of this.interfaces) {
      // compute the intersection
      let intersect: dtPoint | undefined;
      try {
        intersect = diagramInterface.intersection(x);
      } catch (err) {
        console.error(err);
        throw err;
      }

      // if no intersection or the intersection is trivial, skip
      if (intersect === undefined || diagramInterface.hasEndpoint(intersect)) {
        continue;
      }

      // if the intersected interface is user generated, we have a truncation event
      if (x.isUserGenerated()) {
        // either update an existing truncation event or create a new one
        let event: TruncationEvent | undefined = this.truncations.getValue(intersect);

        if (event === undefined) {
          event = new TruncationEvent(intersect, x as UserInterface, [diagramInterface]);

          this.truncations.setValue(intersect, event);
          this.events.add(event);
        } else {
          if (!event.interfaces.includes(diagramInterface)) {
            event.interfaces.push(diagramInterface);
          }
        }
        // otherwise, we have an intersection event
      } else {
        // either update an existing intersection event or create a new one
        let event: IntersectionEvent | undefined = this.intersections.getValue(intersect);

        if (event === undefined) {
          event = new IntersectionEvent(intersect, [diagramInterface, x]);

          this.intersections.setValue(intersect, event);
          this.events.add(event);
        } else {
          if (!event.interfaces.includes(x)) {
            event.interfaces.push(x);
          }
          if (!event.interfaces.includes(diagramInterface)) {
            event.interfaces.push(diagramInterface);
          }
        }
      }
    }

    this.interfaces.push(diagramInterface);
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
  private resolveState(point: dtPoint, below = true): State {
    const scale = below ? 1 : -1;
    let res: DiagramInterface | undefined;
    let minDist = Infinity;

    for (const diagramInterface of this.interfaces) {
      if (diagramInterface.above === undefined) {
        console.assert(diagramInterface.isUserGenerated(), "have non-user-generated interface with an undefined above/below state");
        continue;
      }

      const cur: number | undefined = diagramInterface.getPosAtTime(point.time + EPS);

      if (cur === undefined || floatIsClose(point.position, cur)) {
        continue;
      }

      if (res !== undefined && floatIsClose(scale * (point.position - cur), minDist)) {
        if (
          (below && diagramInterface.slope > res.slope)
          || (!below && diagramInterface.slope < res.slope)
        ) {
          res = diagramInterface;
        }
      } else if (
        (scale * (point.position - cur) >= 0
          && (scale * (point.position - cur) < minDist))
      ) {
        res = diagramInterface;
        minDist = scale * (point.position - cur);
      }
    }

    if (res !== undefined) {
      if (below) {
        return res.above!;
      }

      return res.below!;
    }

    return this.defaultState;
  }

  /**
 * Returns all unique states found throughout the shockwave drawer. 
 *
 * @private
 * @return {State[]} list of unique states
 * @memberof ShockwaveDrawer
 */
  private getStates(): State[] {
    const states = new Set<State>();

    for (const diagramInterface of this.interfaces) {
      if (diagramInterface.hasValidStates()) {
        states.add(diagramInterface.above!);
        states.add(diagramInterface.below!);
      }
    }

    const res: State[] = states.toArray();

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
    if (cur.userInterface.getPosAtTime(cur.point.time) === undefined) {
      return false;
    }

    // state resolution & determination of the prior and posterior capacity
    const above: State = this.resolveState(cur.point, false);
    const below: State = this.resolveState(cur.point, true);

    const priorCapacity = cur.priorCapacity === -1 ? below.flow : cur.priorCapacity;

    // this occurs if the first event of the capacity event (the drop) did not happen
    if (priorCapacity !== below.flow) {
      return false;
    }

    let posteriorCapacity = (
      cur.posteriorCapacity === -1
        ? this.diagram.getMaxState().flow
        : cur.posteriorCapacity
    );
    const interfaceSlope = cur.userInterface.getSlope();

    // posterior capacity is limited by incoming flow IF the state is queued
    if (!this.diagram.stateIsQueued(below)) {
      posteriorCapacity = Math.min(posteriorCapacity, below.flow);
    }

    // if we have an increase in capacity and there is not enough density (queueing) to take advantage of that, only add an interface if it is trivial
    if (
      (posteriorCapacity > priorCapacity || floatIsClose(posteriorCapacity, priorCapacity))
      && (!this.diagram.stateIsQueued(below) || above.equalTo(below))
    ) {
      if (!floatIsClose(above.density, below.density)) {
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
      let stateCreated = false;

      // main interface of event; right side result of capacity change (according to fundamental diagram)
      const mainInterfaceState: State = this.diagram.getStateByFlow(posteriorCapacity, false);

      // if the interface state is nontrivial, process it
      if (!mainInterfaceState.equalTo(below)) {
        const mainInterface = new DiagramInterface(
          cur.point,
          this.diagram.getInterfaceSlope(mainInterfaceState.density, below.density),
          mainInterfaceState,
          below,
          cur.point
        );

        this.addInterface(mainInterface);

        if (floatIsClose(mainInterface.slope, interfaceSlope)) {
          throw new EvalError("An invalid interface was somehow created--duplicated the original interface");
        }

        if (mainInterface.above === undefined || mainInterface.below === undefined) {
          throw new TypeError("Main interface should have a well-defined above/below interface");
        }

        // update states -- enforces that these set states are logically consistent (any time we set an interface, the result would be identical)
        if (cur.userInterface.upperBound.equalTo(cur.point)) {
          if (mainInterface.slope < interfaceSlope) {
            cur.userInterface.setBelowState(mainInterface.below);
          } else if (mainInterface.slope > interfaceSlope) {
            cur.userInterface.setAboveState(mainInterface.above);
          }
        } else {
          if (mainInterface.slope < interfaceSlope) {
            cur.userInterface.setBelowState(mainInterface.above);
          } else if (mainInterface.slope > interfaceSlope) {
            cur.userInterface.setAboveState(mainInterface.below);
          }
        }

        stateCreated ||= true;
      } else {
        // otherwise, there is no interface and simply pass through states
        cur.userInterface.setBelowState(below);
      }

      // byproduct state -- to conserve cars on the left side of the fundamental diagram
      const byproductInterfaceState = this.diagram.getStateByFlow(posteriorCapacity, true);

      // same logic as with the main state
      if (!byproductInterfaceState.equalTo(above)) {
        const byproductInterface = new DiagramInterface(
          cur.point,
          this.diagram.getInterfaceSlope(above.density, byproductInterfaceState.density),
          above,
          byproductInterfaceState,
          cur.point
        );

        this.addInterface(byproductInterface);

        if (floatIsClose(byproductInterface.slope, interfaceSlope)) {
          throw new EvalError("An invalid interface was somehow created -- duplicated existing interface");
        }

        if (byproductInterface.above === undefined || byproductInterface.below === undefined) {
          throw new TypeError("Byproduct interface above/below states should be well-defined");
        }

        if (cur.userInterface.upperBound.equalTo(cur.point)) {
          if (byproductInterface.slope < interfaceSlope) {
            cur.userInterface.setBelowState(byproductInterface.below);
          } else if (byproductInterface.slope > interfaceSlope) {
            cur.userInterface.setAboveState(byproductInterface.above);
          }
        } else {
          if (byproductInterface.slope < interfaceSlope) {
            cur.userInterface.setBelowState(byproductInterface.above);
          } else if (byproductInterface.slope > interfaceSlope) {
            cur.userInterface.setAboveState(byproductInterface.below);
          }
        }

        stateCreated ||= true;
      } else {
        cur.userInterface.setAboveState(above);
      }

      return stateCreated;
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
  private handleIntersectionEvent(cur: IntersectionEvent, force = false): boolean {
    console.assert(cur.interfaces.length >= 2, "number of interfaces in an intersection event msut necessarily be greater than or equal to 2");

    // check whether or not this event is registered in the intersectionevent log
    if (!force && !this.intersections.remove(cur.point)) {
      throw new EvalError("Had an intersection event that was recorded in the intersection dictionary");
    }

    // gather all valid interfaces at this point
    const interfaces: DiagramInterface[] = [];

    for (const diagramInterface of cur.interfaces) {
      if (diagramInterface.getPosAtTime(cur.point.time) === undefined) {
        continue;
      }

      interfaces.push(diagramInterface);
    }

    // if there is only one valid interface, there is nothing to do
    if (interfaces.length <= 1) {
      return false;
    }

    // determine among the interfaces the above and below state of the new offshooting interface using slope logic
    let maxSlope: number = -1 * Infinity;
    let above: State | undefined;
    let minSlope = Infinity;
    let below: State | undefined;

    let noNewInterface = false;

    for (const diagramInterface of interfaces) {
      console.assert(!diagramInterface.isUserGenerated(), "interface being processed in intersection event does not is user generated, which is invalid");

      if (diagramInterface.slope > maxSlope) {
        maxSlope = diagramInterface.slope;
        below = diagramInterface.below;
      }

      if (diagramInterface.slope < minSlope) {
        minSlope = diagramInterface.slope;
        above = diagramInterface.above;
      }

      try {
        diagramInterface.addCutoff(undefined, cur.point);
      } catch (err) {
        console.error("Had error adding cutoff. May be intended.", err);
        noNewInterface = true;
      }
    }

    if (noNewInterface) {
      return false;
    }

    if (above === undefined || below === undefined) {
      throw new EvalError("above/below must not be undefined when resolved in an intersection event");
    }

    // create a new interface if it would be non-trivial
    if (above !== below) {
      const newInterface = new DiagramInterface(
        cur.point,
        this.diagram.getInterfaceSlope(above?.density, below.density),
        above,
        below,
        cur.point
      );

      this.addInterface(newInterface);

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
    if (!this.truncations.remove(cur.point)) {
      throw new EvalError("There was a truncation event that wasn't recorded in the trunction event dictionary/log");
    }

    // check if the user interface is still defined here
    if (cur.userInterface.getPosAtTime(cur.point.time) === undefined) {
      // if it isn't, return early
      // don't need to convert to intersectionevent since one already exists since addInterface handles this already
      return;
    }

    // gather all valid interfaces that are defined at the event's point & cutoff the component interfaces
    const interfaces: DiagramInterface[] = [];

    for (const diagramInterface of cur.interfaces) {
      if (diagramInterface.getPosAtTime(cur.point.time) === undefined) {
        continue;
      }

      interfaces.push(diagramInterface);
    }

    if (interfaces.length === 0) {
      return;
    }

    for (const diagramInterface of interfaces) {
      if (diagramInterface.equivalentTo(cur.userInterface)) {
        continue;
      }

      diagramInterface.addCutoff(undefined, cur.point);
    }

    // if the user interface has not already been processed (it doesn't have valid states), create a new capacity event for when it "starts"
    if (!cur.userInterface.hasValidStates()) {
      debugLog("converting to capacity event");

      cur.userInterface.addCutoff(cur.point);

      this.handleCapacityEvent(
        new CapacityEvent(
          cur.point,
          cur.userInterface,
          -1,
          cur.userInterface.augment.bottleneck
        )
      );
      // otherwise, try to handle it as an intersection event
    } else {
      debugLog("handling right truncation event");

      // create a new interface to represent that this user interface is being split into two "components"
      // the newly-created interface is the old one but with a right-side cutoff
      // the previously-existing interface is nulled out with a left-side cutoff
      const newInterface: UserInterface = cur.userInterface.clone();
      this.interfaces.push(newInterface);
      cur.userInterface.addCutoff(cur.point);
      cur.userInterface.above = cur.userInterface.below = undefined;

      // process resulting intersectionevent & cutoff user-interface if a new state is created in its place
      const stateCreated = this.handleIntersectionEvent(
        new IntersectionEvent(
          cur.point,
          [newInterface as DiagramInterface].concat(cur.interfaces)),
        true
      );

      if (stateCreated) {
        for (const diagramInterface of interfaces) {
          diagramInterface.addCutoff(undefined, cur.point);
        }

        cur.userInterface.addCutoff(undefined, cur.point);
      }
    }
  }

  public run(simulationTime: number, augments: CapacityBottleneck[]): void {
    this.setup(augments);

    this.simulationTime = simulationTime;

    while (this.events.size() !== 0) {
      const time: number = this.events.peek()!.point.time;

      const posQueue = new PriorityQueue<FixedTimeComparable>(compareFixedTimeComparable);

      while (this.events.size() !== 0 && floatIsClose(this.events.peek()!.point.time, time)) {
        const x: Event | undefined = this.events.dequeue();

        if (x === undefined) {
          break;
        }

        let priority = -1;

        switch (x.type) {
          case EventType.capacity: {
            priority = 3;
            break;
          }
          case EventType.intersection: {
            priority = 1;
            break;
          }
          case EventType.truncation: {
            if ((x as TruncationEvent).userInterface.hasValidStates()) {
              priority = 1;
            } else {
              priority = 2;
            }
          }
        }

        posQueue.add({ "event": x, "priority": priority, "position": x.point.position });
      }

      while (posQueue.size() !== 0) {
        const cur = posQueue.dequeue()!;
        const event = cur.event;

        if (event.disabled) {
          continue;
        }

        debugLog("processing event", event.point, event.type);

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

  private findClosestIntersectionPoint_trajectory(
    cur: Trajectory
  ): [dtPoint, DiagramInterface] | undefined {
    let minIntersectTime = Infinity;
    let result: [dtPoint, DiagramInterface] | undefined;

    for (const diagramInterface of this.interfaces) {
      if (!diagramInterface.hasValidStates()) {
        continue;
      }

      let intersection: dtPoint | undefined;
      try {
        intersection = diagramInterface.intersection(cur);
      } catch (err) {
        continue;
      }

      if (intersection === undefined || cur.hasEndpoint(intersection)) {
        continue;
      }

      if (intersection.time < minIntersectTime) {
        minIntersectTime = intersection.time;
        result = [intersection, diagramInterface];
      }
    }

    return result;
  }

  /**
* Generates a figure after the drawer has run, creating interfaces & states partitioning the timespace diagram.
* 
* Can generate with trajectories (and a number of trajectories), which scale according to the initial density. 
* Can also generate with polygon, which overlay the partitioned areas.
* 
* Can also specify the viewport---defined by max/min position and max/min time. If not specified, will scale according
* to the geometries generated (assuming only positive times).
* 
* @param numTrajectories 
* @param withTrajectories 
* @param withPolygons 
* @param viewport 
* @returns 
*/

  public generateFigure(
    numTrajectories: number,
    withTrajectories: boolean,
    withPolygons: boolean,
    viewport?: Viewport
  ): FigureResult {
    const userInterfacesOut: GraphLine[] = [];
    const interfacesOut: GraphInterface[] = [];
    const trajectoriesOut: GraphTrajectory[] = [];
    const polygonsOut: GraphPolygon[] = [];

    let maxPos = -1;
    let maxTime = -1;
    let minPos = Infinity;
    // let minTime = Infinity;

    for (const diagramInterface of this.interfaces) {
      const p1: dtPoint = diagramInterface.lowerBound;

      maxTime = Math.max(maxTime, p1.time);
    }

    maxTime = Math.max(maxTime, this.simulationTime!) + PlotThresholdOffset;

    if (viewport !== undefined) {
      maxTime = Math.max(maxTime, viewport.maxTime);
      maxPos = Math.max(maxPos, viewport.maxPos);
    }

    for (const diagramInterface of this.interfaces) {
      if (diagramInterface.isUserGenerated()) {
        userInterfacesOut.push({
          point1: (diagramInterface as UserInterface).originalLowerBound,
          point2: (diagramInterface as UserInterface).originalUpperBound
        });
      }

      if (!diagramInterface.hasValidStates()) {
        continue;
      }

      const p1 = diagramInterface.lowerBound;
      let p2 = diagramInterface.upperBound;

      minPos = Math.min(minPos, p1.position);

      if (p2.time !== Infinity) {
        minPos = Math.min(minPos, p1.position);
      }

      if (p2.time === Infinity) {
        const pos = diagramInterface.getPosAtTime(maxTime);

        if (pos === undefined) {
          throw new TypeError("Diagram interface should be defined at max time");
        }

        maxPos = Math.max(maxPos, pos);
        p2 = new dtPoint(maxTime, pos);
      }

      if (!p1.equalTo(p2)) {
        interfacesOut.push({
          above: diagramInterface.above,
          below: diagramInterface.below,
          point1: p1,
          point2: p2
        });
      }
    }

    minPos = Math.min(minPos, -1 * PlotThresholdOffset);

    const defaultViewport: Viewport = {
      maxTime: Math.max(maxTime, viewport?.maxTime ?? -1 * Infinity),
      minTime: Math.min(-1 * PlotThresholdOffset, (viewport?.minTime ?? Infinity)),
      maxPos: Math.max(maxPos, viewport?.maxPos ?? -1 * Infinity),
      minPos: Math.min(minPos, (viewport?.minPos ?? Infinity))
    };

    if (viewport === undefined) {
      viewport = defaultViewport;
    }

    if (withTrajectories && this.diagram.initDensity !== 0) {
      const slope = this.defaultState.getSlope();

      const step = (
        (viewport.maxPos + slope * viewport.maxTime) / numTrajectories
      );
      for (let pos =
        Math.floor(-1 * slope * viewport.maxTime);
        pos <= viewport.maxPos;
        pos += step / this.diagram.initDensity
      ) {
        const curTrajectories: GraphLine[] = [];
        try {
          let cur = new Trajectory(new dtPoint(0, pos), slope);

          while (true) {  // eslint-disable-line no-constant-condition
            const x = this.findClosestIntersectionPoint_trajectory(cur);
            let nextTrajectory: Trajectory | undefined;

            if (x !== undefined) {
              const intersection = x[0];
              const intersectingInterface = x[1];

              if (intersectingInterface.above === undefined) {
                throw new TypeError("Intersecting interface above state should not be undefined");
              }

              nextTrajectory = new Trajectory(
                intersection, intersectingInterface.above.getSlope(), intersection
              );

              if (nextTrajectory.slope === Infinity) {
                break;
              }

              cur.addCutoff(undefined, intersection);
            }

            const p1 = cur.lowerBound;
            let p2 = cur.upperBound;

            if (p2.time === Infinity) {
              const p2Pos = cur.getPosAtTime(maxTime + PlotThresholdOffset);

              if (p2Pos === undefined) {
                break;
              }

              p2 = new dtPoint(maxTime + PlotThresholdOffset, p2Pos,);
            }

            curTrajectories.push({
              point1: p1,
              point2: p2
            });

            if (nextTrajectory !== undefined) {
              cur = nextTrajectory;
            } else {
              break;
            }
          }
        } catch (err) {
          console.error(err);
        }

        if (curTrajectories.length >= 1) {
          const cleanedTraj: GraphTrajectory = [
            curTrajectories[0].point1, curTrajectories[0].point2
          ];

          for (let i = 1; i < curTrajectories.length; i++) {
            cleanedTraj.push(curTrajectories[i].point2);
          }

          trajectoriesOut.push(cleanedTraj);
        }
      }
    }

    if (withPolygons) {
      const polygons = this.resolvePolygons(
        defaultViewport, viewport
      );

      for (const polygon of polygons) {
        const midpoint = polylabel(polygon.geometry.coordinates);
        const midpointDt = new dtPoint(midpoint[0], midpoint[1]);

        const below = this.resolveState(midpointDt, true);

        polygonsOut.push({
          points: polygon.geometry.coordinates[0].map(([x, y]) => new dtPoint(x, y)),
          state: below,
          point: midpointDt,
        });
      }
    }

    return {
      viewport,
      userInterfaces: userInterfacesOut,
      interfaces: interfacesOut,
      polygons: polygonsOut,
      trajectories: trajectoriesOut,
      states: this.getStates()
    };
  }

  private resolvePolygons(
    fullViewport: Viewport,
    setViewport?: Viewport
  ): polygon_t[] {
    const graph = new DefaultDictionary<dtPoint, Set<dtPoint>>(
      () => { return new Set<dtPoint>(); }
    );

    const bottomLeft = new dtPoint(fullViewport.minTime, fullViewport.minPos);
    const topLeft = new dtPoint(fullViewport.minTime, fullViewport.maxPos);
    const bottomRight = new dtPoint(fullViewport.maxTime, fullViewport.minPos);
    const topRight = new dtPoint(fullViewport.maxTime, fullViewport.maxPos);

    const segments: [number, dtPoint][] = [];
    segments.push([fullViewport.minPos, bottomRight]);
    segments.push([fullViewport.maxPos, topRight]);

    for (const diagramInterface of this.interfaces) {
      if (!diagramInterface.hasValidStates()) {
        continue;
      }

      const x = diagramInterface.lowerBound;
      let y = diagramInterface.upperBound;

      if (y.time === Infinity) {
        const yPos = diagramInterface.getPosAtTime(fullViewport.maxTime);

        if (yPos === undefined) {
          throw new TypeError("Polygon y pos should not be undefined");
        }

        y = new dtPoint(fullViewport.maxTime, yPos);
      }

      if (!y.equalTo(topRight) && floatIsClose(fullViewport.maxTime, y.time)) {
        segments.push([y.position, y]);
      }

      graph.getValue(x).add(y);
      graph.getValue(y).add(x);

      for (const neighbor of graph.getValue(x).toArray()) {
        graph.getValue(neighbor).add(x);
      }

      for (const neighbor of graph.getValue(y).toArray()) {
        graph.getValue(neighbor).add(y);
      }
    }

    graph.getValue(bottomLeft).add(topLeft);
    graph.getValue(bottomLeft).add(bottomRight);
    graph.getValue(topLeft).add(topRight);
    graph.getValue(topLeft).add(bottomLeft);
    graph.getValue(bottomRight).add(bottomLeft);
    graph.getValue(topRight).add(topLeft);

    segments.sort((a, b) => { return a[0] - b[0]; });

    for (let i = 0; i < segments.length - 1; i++) {
      const below = segments[i][1];
      const above = segments[i + 1][1];

      graph.getValue(below).add(above);
      graph.getValue(above).add(below);
    }

    if (setViewport === undefined) {
      setViewport = fullViewport;
    }

    const polygons: polygon_t[] = [];
    const fullPolygon: polygon_t = turf.polygon(
      [[
        [setViewport.minTime, setViewport.minPos],
        [setViewport.minTime, setViewport.maxPos],
        [setViewport.maxTime, setViewport.maxPos],
        [setViewport.maxTime, setViewport.minPos],
        [setViewport.minTime, setViewport.minPos],
      ]]
    );

    const seen = new Set<Pair<dtPoint>>;

    for (let i = 0; i < 2; i++) {
      for (const point of graph.keys()) {
        const stack: dtPoint[] = [];
        stack.push(point);

        let cur: dtPoint | null = null;
        for (const neighbor of graph.getValue(point).toArray()) {
          if (!seen.contains(new Pair(point, neighbor))) {
            cur = neighbor;
            break;
          }
        }

        if (cur === null) {
          continue;
        }

        let stop = false;
        let iterations = 0;

        while (cur !== null) {
          stack.push(cur);
          const n = stack.length;

          const prevVec = [cur.time - stack[n - 2].time, cur.position - stack[n - 2].position];

          let maxAngle = -1;
          let nextPoint: dtPoint | null = null;

          for (const neighbor of graph.getValue(cur).toArray()) {
            const vec = [cur.time - neighbor.time, cur.position - neighbor.position];

            if (floatIsClose(norm(prevVec) as number, 0)
              || floatIsClose(norm(vec) as number, 0)
            ) {
              continue;
            }

            const expr = dot(prevVec, vec) / (norm(prevVec) as number) / (norm(vec) as number);
            let angle = (acos(clip(expr, -1, 1)) as number) * 180 / pi;

            const detSign = sign(prevVec[0] * vec[1] - prevVec[1] * vec[0]);

            if (detSign < 0) {
              angle = 360 - angle;
            }

            if (angle > maxAngle) {
              maxAngle = angle;
              nextPoint = neighbor;
            }
          }

          if (nextPoint === null || nextPoint.equalTo(point)) {
            break;
          }

          cur = nextPoint;

          iterations++;

          if (iterations === graph.size() * 2) {
            stop = true;
            break;
          }
        }

        if (stop) {
          break;
        }

        for (let i = 0; i < stack.length - 1; i++) {
          seen.add(new Pair<dtPoint>(stack[i], stack[i + 1]));
        }
        seen.add(new Pair<dtPoint>(stack[stack.length - 1], stack[0]));

        if (stack.length <= 2) {
          continue;
        }

        const points = stack.map((x) => x.toArray());
        points.push([stack[0].time, stack[0].position]);
        const poly = turf.polygon([points]);

        polygons.push(poly);
      }
    }

    const out: polygon_t[] = [];

    for (const polygon of polygons) {
      const intersect = turf.intersect(turf.featureCollection([polygon, fullPolygon]));

      if (intersect?.geometry === undefined) {
        continue;
      } else if (intersect.geometry.type === "Polygon") {
        out.push(intersect as polygon_t);
      } else if (intersect.geometry.type === "MultiPolygon") {
        intersect.geometry.coordinates.forEach(subPolygon => {
          out.push(turf.polygon(subPolygon));
        });
      }
    }

    if (out.length > 1) {
      for (let i = 0; i < out.length; i++) {
        if (floatIsClose(calculateArea(out[i]), calculateArea(fullPolygon))) {
          out.splice(i, 1);
          break;
        }
      }
    }

    return out;
  }

  public getSimulationTime(): number {
    return this.simulationTime ?? -1;
  }

  public getInterfaces(): DiagramInterface[] {
    return this.interfaces;
  }


}