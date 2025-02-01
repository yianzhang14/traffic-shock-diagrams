import { CapacityEvent, UserInterface, dtPoint } from "../drawer_utils";
import { ShockwaveDrawer } from "../shockwave_drawer";

import { CapacityBottleneck } from "./base_augmenter";


export class TrafficLight extends CapacityBottleneck {
  private pos: number;
  private cycles: number[];
  private blockingStates: number[];
  private initState: number;
  private delay: number;

  constructor(
    pos: number,
    cycles: number[],
    blockingStates: number[],
    initState = 0,
    delay = 0
  ) {
    super(0);

    this.pos = pos;
    this.cycles = cycles;
    this.blockingStates = blockingStates;
    this.initState = initState;
    this.delay = delay;

    if (!(this.delay >= 0)) {
      throw new RangeError("Delay must be positive");
    }

    if (!(this.initState < this.cycles.length && this.initState >= 0)) {
      throw new RangeError("Initial state provided is invalid");
    }

    if (this.blockingStates.length !== this.cycles.length) {
      throw new RangeError("Length of blocking state/cycle arrays do not match");
    }
  }

  public init(drawer: ShockwaveDrawer) {
    let time = this.delay;
    let state = this.initState;

    while (time <= drawer.getSimulationTime()) {
      if (this.blockingStates[state]) {
        const start = new dtPoint(time, this.pos);
        const end = new dtPoint(time + this.cycles[state], this.pos);

        const cur = new UserInterface(start, 0, this, start, end);
        drawer.addUserInterface(cur);

        const startEvent = new CapacityEvent(start, cur, undefined, 0);
        drawer.addCapacityEvent(startEvent);

        const endEvent = new CapacityEvent(end, cur, 0);
        drawer.addCapacityEvent(endEvent);
      }

      time += this.cycles[state];
      state = (state + 1) % this.cycles.length;
    }
  }
}