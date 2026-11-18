/**
 * The live measure check (ADR 0005, decision 1): a measure shorter or longer than its time signature
 * is a doubt. Same rules as the Python `postprocess.inspect` (the longest voice, following backup
 * and forward, grace notes and chord tones not counted), so the flags on the screen and the saved
 * statistics agree.
 */
import { children, text, type MeasureInfo } from "./xml";

export type Status = "ok" | "underfull" | "overfull" | "empty";
/** `upbeat` is a short measure that is meant to be short (plan 0010): it is not a doubt. */
export interface MeasureCheck { index: number; status: Status; expected: number; filled: number; time: string; diff: number; upbeat: boolean }

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

/**
 * The short measures that are an upbeat and not a mistake (plan 0010), by index. The same two shapes
 * as the Python `upbeats`: a first measure the document marks `implicit="yes"`, which is how
 * MusicXML writes a pickup, and a short measure completed exactly by a short neighbour — or, for the
 * page's first and last measures, by each other — which is one bar written in two pieces, the way a
 * songbook writes a section that begins mid-bar.
 *
 * Safe here because this check never sees raw engine output: a recognized page has been padded
 * before anyone looks at it (`postprocess`), so a short measure is either an authored upbeat or an
 * edit made a moment ago.
 */
function upbeats(lengths: { filled: number; expected: number }[], implicitFirst: boolean): Set<number> {
  const n = lengths.length;
  const short = (i: number) => i >= 0 && i < n && lengths[i].filled > 0 && lengths[i].filled < lengths[i].expected;
  const out = new Set<number>();
  for (let i = 0; i < n; i++) {
    if (!short(i)) continue;
    if (i === 0 && implicitFirst) { out.add(i); continue; }
    const ends = [...(i === 0 ? [n - 1] : []), ...(i === n - 1 ? [0] : [])];
    for (const j of [i - 1, i + 1, ...ends]) {
      if (j === i || !short(j)) continue;
      if (Math.abs(lengths[i].filled + lengths[j].filled - lengths[i].expected) < 1e-9) { out.add(i); break; }
    }
  }
  return out;
}

export function checkMeasures(measures: MeasureInfo[]): MeasureCheck[] {
  const lengths = measures.map((m) => ({ filled: filledQuarters(m.el, m.divisions), expected: (m.beats * 4) / m.beatType }));
  const excused = upbeats(lengths, measures[0]?.el.getAttribute("implicit") === "yes");
  return measures.map((m, i) => {
    const { filled, expected } = lengths[i];
    const diff = filled - expected;
    const status: Status = filled === 0 ? "empty" : Math.abs(diff) < 1e-9 ? "ok" : diff < 0 ? "underfull" : "overfull";
    return { index: m.index, status, expected, filled, time: `${m.beats}/${m.beatType}`, diff, upbeat: excused.has(i) };
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
