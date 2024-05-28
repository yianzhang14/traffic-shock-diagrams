import { UserInterface, dtPoint, float_isclose } from "../drawer_utils";
import ShockwaveDrawer from "../shockwave_drawer";
import CapacityBottleneck from "./base_augmenter";


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
            const cur: UserInterface = new UserInterface(this.start, this.start.getSlope(this.end), this, this.start, this.end);
        }
    }
}