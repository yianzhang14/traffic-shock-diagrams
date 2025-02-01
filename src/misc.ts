import { polygon_t } from "./types";

const DEBUG = false;

export function debugLog(...args: unknown[]) {
  if (DEBUG) {
    console.log(...args);
  }
}

export function clip(val: number, lower: number, upper: number) {
  return Math.min(Math.max(val, lower), upper);
}

export function calculateArea(polygon: polygon_t): number {
  // shoelace formula
  const coordinates = polygon.geometry.coordinates[0]; // Extract the coordinates of the polygon
  let area = 0;
  const n = coordinates.length;

  // Shoelace formula calculation
  for (let i = 0; i < n - 1; i++) {
    const [x1, y1] = coordinates[i];
    const [x2, y2] = coordinates[i + 1];
    area += (x1 * y2) - (y1 * x2);
  }

  // Absolute value of the result divided by 2
  return Math.abs(area) / 2;
}