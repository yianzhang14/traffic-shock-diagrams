import * as fs from "fs";

import { HorizontalBottleneck, CapacityBottleneck, FundamentalDiagram, ShockwaveDrawer } from "./src/index";

// alternatively, look at getShockwave
const diagram = new FundamentalDiagram(3, 5.0, 1.0, 1.0);

const augments: CapacityBottleneck[] = [];
augments.push(new HorizontalBottleneck(30, 10, 20, 1.5));
// augments.push(new HorizontalBottleneck(30, 25, 40, 0));

const drawer = new ShockwaveDrawer(diagram, augments);

drawer.run(30);
fs.writeFile("output.json", JSON.stringify(drawer.generateFigure(100, true, false)), (err) => {console.error(err);});