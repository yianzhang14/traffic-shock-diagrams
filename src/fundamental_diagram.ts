import { State, float_isclose } from "./drawer_utils";


export default class FundamentalDiagram {
    public freeflow_speed: number;
    public jam_density: number;
    public traffic_wave_speed: number;
    public init_density: number;

    public capacity_density: number;
    public capacity: number;

    /**
     * Creates an instance of FundamentalDiagram. Fully determined by the parameters listed here.
     * 
     * @param {number} freeflow_speed absval of slope of LHS of fundamental diagram
     * @param {number} jam_density at what point the RHS of the fundamental diagram has 0 flow
     * @param {number} traffic_wave_speed absval of the slope of the RHS of the fundamental diagram (translated into a negative slope)
     * @param {number} init_density initial density of the situation
     * @memberof FundamentalDiagram
     */
    constructor(freeflow_speed: number, jam_density: number, traffic_wave_speed: number, init_density: number) {
        if (!(freeflow_speed > 0 && jam_density > 0 && traffic_wave_speed > 0)) {
            throw new RangeError("All inputs/speeds must be positive");
        }

        if (freeflow_speed <= traffic_wave_speed) {
            throw new RangeError("Freeflow speed must be greater than traffic wave speed");
        }

        if (!(init_density >= 0 && init_density <= jam_density)) {
            throw new RangeError("The provided initial density is not valid for the described fundamnetal diagram--does not fall within the range of possible densities");
        }
        
        this.freeflow_speed = freeflow_speed;
        this.jam_density = jam_density;
        this.traffic_wave_speed = traffic_wave_speed;
        this.init_density = init_density;

        // solve a system of linear equations to get the peak/intersection
        // between the freeflow and traffic wave portions of the fundmental diagram
        this.capacity_density = (traffic_wave_speed * jam_density) / (traffic_wave_speed + freeflow_speed)
        this.capacity = this.capacity_density * freeflow_speed;
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
        if (!(density >= 0 && density <= this.jam_density)) {
            throw new RangeError("Density invalid -- not possible in the fundamental diagram");
        }

        if (float_isclose(density, this.capacity_density)) {
            return this.capacity;
        } else if (density < this.capacity_density) {
            return this.freeflow_speed * density;
        } else {
            return this.capacity - this.traffic_wave_speed * density;
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
     * Gets the state associated with this.init_density.
     *
     * @return {State} the resultant state
     * @memberof FundamentalDiagram
     */
    public getInitialState(): State {
        return this.getState(this.init_density);
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
        if (float_isclose(x, y)) {
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
        return new State(this.jam_density, 0);
    }

    /**
     * Retuns the state that would be the maximal flow state--where the flow is maximal.
     *
     * @return {State} the maximal flow state
     * @memberof FundamentalDiagram
     */
    public getMaxState(): State {
        return new State(this.capacity_density, this.capacity);
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
    public getStateByFlow(flow: number, left: boolean=false): State {
        // if we want the max flow, return the max state -- there is only one option here
        if (float_isclose(flow, this.capacity)) {
            return this.getMaxState();
        }

        // solving a linear equation
        const left_density: number = flow / this.freeflow_speed;
        const right_density = (flow - this.capacity - this.traffic_wave_speed * this.capacity_density) / (-1 * this.traffic_wave_speed);

        if (left) {
            return new State(left_density, flow);
        } else {
            return new State(right_density, flow);
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
        if (!(state.density >= 0 && state.density <= this.jam_density)) {
            throw new RangeError("density of the provided state is invalid");
        }

        return state.density > this.capacity && !float_isclose(state.density, this.capacity_density);
    }
}