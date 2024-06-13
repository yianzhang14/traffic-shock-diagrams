import { CapacityEvent, UserInterface, dtPoint, float_isclose } from "../drawer_utils";
import { ShockwaveDrawer }  from "../shockwave_drawer";
import { CapacityBottleneck } from "./base_augmenter";


export class LineBottleneck extends CapacityBottleneck {
  private start: dtPoint;
  private end: dtPoint;

  constructor(start: dtPoint, end: dtPoint, bottleneck_capacity: number) {
    super(bottleneck_capacity);
        
    this.start = start;
    this.end = end;
  }

  public init(drawer: ShockwaveDrawer): void {
    if (float_isclose(this.start.time, this.end.time)) {
      return;
    }

    if (this.start.time >= 0) {
      const cur: UserInterface = new UserInterface(
        this.start, this.start.getSlope(this.end), this, this.start, this.end
      );

      drawer.addUserInterface(cur);

      const start_event = new CapacityEvent(
        this.start, cur, undefined, this.bottleneck
      );
      drawer.addCapacityEvent(start_event);

      const end_event = new CapacityEvent(
        this.end, cur, this.bottleneck
      );
      drawer.addCapacityEvent(end_event);
    }
  }
}

export class HorizontalBottleneck extends LineBottleneck {
  constructor(pos: number, time_start: number, time_end: number, bottleneck_capacity: number) {
    super(new dtPoint(time_start, pos), new dtPoint(time_end, pos), bottleneck_capacity);
  }
}