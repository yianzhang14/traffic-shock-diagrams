const DEBUG = true;

export function debug_log(...args: unknown[]) {
  if (DEBUG) {
    console.log(...args);
  }
}

export function clip(val: number, lower: number, upper: number) {
  return Math.min(Math.max(val, lower), upper);
}