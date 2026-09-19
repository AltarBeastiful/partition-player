/**
 * The live measure check (ADR 0005, decision 1): a measure shorter or longer than its time signature
 * is a doubt. Same rules as the Python `postprocess.inspect` (the longest voice, following backup
 * and forward, grace notes and chord tones not counted), so the flags on the screen and the saved
 * statistics agree.
 */
import { children, text, type MeasureInfo } from "./xml";

export type Status = "ok" | "underfull" | "overfull" | "empty";
export interface MeasureCheck { index: number; status: Status; expected: number; filled: number; time: string; diff: number }

/** Length of the longest voice in quarters, like `_measure_filled`. */
export function filledQuarters(m: Element, divisions: number): number {
  let pos = 0, end = 0;
  for (const el of Array.from(m.children)) {
    if (el.tagName === "note") {
      if (children(el, "grace").length) continue;
      const d = Number(text(el, "duration", "0")) || 0;
      if (!children(el, "chord").length) pos += d;
      end = Math.max(end, pos);
    } else if (el.tagName === "backup") pos -= Number(text(el, "duration", "0")) || 0;
    else if (el.tagName === "forward") { pos += Number(text(el, "duration", "0")) || 0; end = Math.max(end, pos); }
  }
  return end / divisions;
}

export function checkMeasures(measures: MeasureInfo[]): MeasureCheck[] {
  return measures.map((m) => {
    const expected = (m.beats * 4) / m.beatType;
    const filled = filledQuarters(m.el, m.divisions);
    const diff = filled - expected;
    const status: Status = filled === 0 ? "empty" : Math.abs(diff) < 1e-9 ? "ok" : diff < 0 ? "underfull" : "overfull";
    return { index: m.index, status, expected, filled, time: `${m.beats}/${m.beatType}`, diff };
  });
}

const NAMES: [number, string][] = [[4, "a whole note"], [3, "a dotted half"], [2, "a half note"], [1.5, "a dotted quarter"], [1, "a quarter"],
  [0.75, "a dotted eighth"], [0.5, "an eighth"], [0.25, "a sixteenth"], [0.125, "a thirty-second"]];
const WORDS = ["", "", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"];

/** A length in words: "a dotted quarter", "five eighths", "2.3 quarters". Same as the Python `describe`. */
export function describe(quarters: number): string {
  for (const [q, name] of NAMES) if (Math.abs(q - quarters) < 1e-9) return name;
  for (const [unit, name] of [[1, "quarters"], [0.5, "eighths"], [0.25, "sixteenths"]] as [number, string][]) {
    const n = quarters / unit;
    if (Math.abs(n - Math.round(n)) < 1e-9 && n >= 2 && n <= 12) return `${WORDS[Math.round(n)]} ${name}`;
  }
  return `${Number(quarters.toFixed(4))} quarters`;
}

export function checkText(c: MeasureCheck): string {
  if (c.status === "underfull") return `shorter than ${c.time} by ${describe(-c.diff)}`;
  if (c.status === "overfull") return `longer than ${c.time} by ${describe(c.diff)}`;
  if (c.status === "empty") return "empty measure";
  return "";
}
