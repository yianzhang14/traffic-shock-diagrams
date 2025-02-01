import { State, floatIsClose } from "./drawer_utils";


export class FundamentalDiagram {
  public freeflowSpeed: number;
  public jamDensity: number;
  public trafficWaveSpeed: number;
  public initDensity: number;

  public capacityDensity: number;
  public capacity: number;

  /**
     * Creates an instance of FundamentalDiagram. Fully determined by the parameters listed here.
     * 
     * @param {number} freeflowSpeed absval of slope of LHS of fundamental diagram
     * @param {number} jamDensity at what point the RHS of the fundamental diagram has 0 flow
     * @param {number} trafficWaveSpeed absval of the slope of the RHS of the fundamental diagram (translated into a negative slope)
     * @param {number} initDensity initial density of the situation
     * @memberof FundamentalDiagram
     */
  constructor(
    freeflowSpeed: number, jamDensity: number, trafficWaveSpeed: number, initDensity: number
  ) {
    if (!(freeflowSpeed > 0 && jamDensity > 0 && trafficWaveSpeed > 0)) {
      throw new RangeError("All inputs/speeds must be positive");
    }

    if (freeflowSpeed <= trafficWaveSpeed) {
      throw new RangeError("Freeflow speed must be greater than traffic wave speed");
    }

    if (!this.densityIsValid(initDensity)) {
      throw new RangeError("The provided initial density is not valid for the described fundamnetal diagram--does not fall within the range of possible densities");
    }


    this.freeflowSpeed = freeflowSpeed;
    this.jamDensity = jamDensity;
    this.trafficWaveSpeed = trafficWaveSpeed;
    this.initDensity = initDensity;

    // solve a system of linear equations to get the peak/intersection
    // between the freeflow and traffic wave portions of the fundmental diagram
    this.capacityDensity = (
      trafficWaveSpeed * jamDensity
    ) / (trafficWaveSpeed + freeflowSpeed);

    // if (initDensity > this.capacityDensity) {
    //   throw new RangeError("The initial density should be non-queued for now");
    // }

    this.capacity = this.capacityDensity * freeflowSpeed;
  }

  public densityIsValid(density: number): boolean {
    return (
      !(density > 0 && density < this.jamDensity)
      && !floatIsClose(density, this.jamDensity)
      && !floatIsClose(density, 0)
    );
  }

  /**
     * Helper function for interpolating the fundamental diagram equation for flow given a density. Essentially utilizes the piecewise definition of the fundamental diagram.
     *
     * @private
     * @param {number} density density to query
     * @return {number} the flow associated with that density
     * @memberof FundamentalDiagram
     */
  private interpolateFlow(density: number): number {
    if (!this.densityIsValid(density)) {
      throw new RangeError("Density invalid -- not possible in the fundamental diagram");
    }

    if (floatIsClose(density, this.capacityDensity)) {
      return this.capacity;
    } else if (floatIsClose(density, 0)) {
      return 0;
    } else if (density < this.capacityDensity) {
      return this.freeflowSpeed * density;
    } else {
      return this.capacity - this.trafficWaveSpeed * (density - this.capacityDensity);
    }

  }

  /**
     * Gets the state associated with a given density. Essentially a wrapper around interpolateFlow.
     *
     * @param {number} density density to query
     * @return {State} the resultant state
     * @memberof FundamentalDiagram
     */
  public getState(density: number): State {
    const flow: number = this.interpolateFlow(density);

    return new State(density, flow);
  }

  /**
     * Gets the state associated with this.initDensity.
     *
     * @return {State} the resultant state
     * @memberof FundamentalDiagram
     */
  public getInitialState(): State {
    return this.getState(this.initDensity);
  }

  /**
     * Computes the slope between two densities on the fundamental diagram--i.e., the slope of the line that would connect two given densities.
     *
     * @param {number} x density 1
     * @param {number} y density 2
     * @return {number} the slope
     * @memberof FundamentalDiagram
     */
  public getInterfaceSlope(x: number, y: number): number {
    if (floatIsClose(x, y)) {
      throw new RangeError("The densities are equal -- slope not well-defined.");
    }

    const state1: State = this.getState(x);
    const state2: State = this.getState(y);

    return state1.getInterfaceSlope(state2);
  }

  /**
     * Returns the state that would be the jam state--where the fundmental diagram's RHS reaches flow 0.
     *
     * @return {State} the jam state
     * @memberof FundamentalDiagram
     */
  public getJamState(): State {
    return new State(this.jamDensity, 0);
  }

  /**
     * Retuns the state that would be the maximal flow state--where the flow is maximal.
     *
     * @return {State} the maximal flow state
     * @memberof FundamentalDiagram
     */
  public getMaxState(): State {
    return new State(this.capacityDensity, this.capacity);
  }

  /**
     * Returns the state that would be the empty state--where both flow and density are 0.
     *
     * @return {State} the empty state
     * @memberof FundamentalDiagram
     */
  public getEmptyState(): State {
    return new State(0, 0);
  }

  /**
     * Somewhat similar to an inverse version of interpolateFlow. Given a flow, resolves the (up to) two points that have that flow, and returns the corresponding one depeneding on the value of the left parameter.
     *
     * @param {number} flow flow to query
     * @param {boolean} [left=false] whether or not to return the LHS's state
     * @return {State} the desired state 
     * @memberof FundamentalDiagram
     */
  public getStateByFlow(flow: number, left = false): State {
    // if we want the max flow, return the max state -- there is only one option here
    if (floatIsClose(flow, this.capacity)) {
      return this.getMaxState();
    }

    // solving a linear equation
    const leftDensity: number = flow / this.freeflowSpeed;
    const rightDensity = (
      flow - this.capacity - this.trafficWaveSpeed * this.capacityDensity
    ) / (-1 * this.trafficWaveSpeed);

    if (left) {
      return new State(leftDensity, flow);
    } else {
      return new State(rightDensity, flow);
    }
  }

  /**
     * Determines whether a state is queued--i.e., it is on the RHS of the fundmental diagram, excluding the maximal state.
     *
     * @param {State} state state to
     * @return {boolean} whether or not the state is queued
     * @memberof FundamentalDiagram
     */
  public stateIsQueued(state: State): boolean {
    if (!this.densityIsValid(state.density)) {
      throw new RangeError("density of the provided state is invalid");
    }

    return (
      state.density > this.capacityDensity && !floatIsClose(state.density, this.capacityDensity)
    );
  }
}