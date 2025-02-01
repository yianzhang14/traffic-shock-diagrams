import { CapacityEvent, UserInterface, dtPoint, floatIsClose } from "../drawer_utils";
import { ShockwaveDrawer } from "../shockwave_drawer";

import { CapacityBottleneck } from "./base_augmenter";


export class LineBottleneck extends CapacityBottleneck {
  private start: dtPoint;
  private end: dtPoint;

  constructor(start: dtPoint, end: dtPoint, bottleneckCapacity: number) {
    super(bottleneckCapacity);

    this.start = start;
    this.end = end;
  }

  public init(drawer: ShockwaveDrawer): void {
    if (floatIsClose(this.start.time, this.end.time)) {
      return;
    }

    if (this.start.time >= 0) {
      const cur: UserInterface = new UserInterface(
        this.start, this.start.getSlope(this.end), this, this.start, this.end
      );

      drawer.addUserInterface(cur);

      const startEvent = new CapacityEvent(
        this.start, cur, undefined, this.bottleneck
      );
      drawer.addCapacityEvent(startEvent);

      const endEvent = new CapacityEvent(
        this.end, cur, this.bottleneck
      );
      drawer.addCapacityEvent(endEvent);
    }
  }
}

export class HorizontalBottleneck extends LineBottleneck {
  constructor(pos: number, timeStart: number, timeEnd: number, bottleneckCapacity: number) {
    super(new dtPoint(timeStart, pos), new dtPoint(timeEnd, pos), bottleneckCapacity);
  }
}