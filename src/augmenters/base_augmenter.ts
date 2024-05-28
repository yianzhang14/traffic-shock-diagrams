import ShockwaveDrawer from "../shockwave_drawer";

/**
 * Base class of anything that would augment/affect traffic flow in the shockwave diagram.
 *
 * @abstract
 * @class TrafficAugmenter
 */
abstract class TrafficAugmenter {
    abstract init(drawer: ShockwaveDrawer): void;
}

/**
 * Specialization of traffic augmenter to augments that affect flow by altering capacity. Currently the only supported type of augment.
 *
 * @export
 * @abstract
 * @class CapacityBottleneck
 * @extends {TrafficAugmenter}
 */
export default abstract class CapacityBottleneck extends TrafficAugmenter {
    public bottleneck: number;

    /**
     * Creates an instance of CapacityBottleneck.
     * 
     * @param {number} bottleneck the bottleneck of this capacity bottleneck
     * @memberof CapacityBottleneck
     */
    constructor(bottleneck: number) {
        super();
        
        this.bottleneck = bottleneck;
    }
}