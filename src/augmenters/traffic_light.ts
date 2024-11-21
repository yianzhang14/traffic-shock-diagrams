import { CapacityEvent, UserInterface, dtPoint } from "../drawer_utils";
import { ShockwaveDrawer } from "../shockwave_drawer";

import { CapacityBottleneck } from "./base_augmenter";


export class TrafficLight extends CapacityBottleneck {
  private pos: number;
  private cycles: number[];
  private blocking_states: number[];
  private init_state: number;
  private delay: number;

  constructor(
    pos: number, 
    cycles: number[], 
    blocking_states: number[], 
    init_state = 0, 
    delay = 0
  ) {
    super(0);

    this.pos = pos;
    this.cycles = cycles;
    this.blocking_states = blocking_states;
    this.init_state = init_state;
    this.delay = delay;

    if (!(this.delay >= 0)) {
      throw new RangeError("Delay must be positive");
    }

    if (!(this.init_state < this.cycles.length && this.init_state >= 0)) {
      throw new RangeError("Initial state provided is invalid");
    }

    if (this.blocking_states.length !== this.cycles.length) {
      throw new RangeError("Length of blocking state/cycle arrays do not match");
    }
  }

  public init(drawer: ShockwaveDrawer) {
    let time = this.delay;
    let state = this.init_state;

    while (time <= drawer.getSimulationTime()) {
      if (this.blocking_states[state]) {
        const start = new dtPoint(time, this.pos);
        const end = new dtPoint(time + this.cycles[state], this.pos);

        const cur = new UserInterface(start, 0, this, start, end);
        drawer.addUserInterface(cur);

        const start_event = new CapacityEvent(start, cur, undefined, 0);
        drawer.addCapacityEvent(start_event);

        const end_event = new CapacityEvent(end, cur, 0);
        drawer.addCapacityEvent(end_event);
      }

      time += this.cycles[state];
      state = (state + 1) % this.cycles.length;
    }
  }
}