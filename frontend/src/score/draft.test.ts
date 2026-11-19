/**
 * The model draft as the sheet shows it (plan 0016, step 6): the corrected score is the read score
 * with the ticked changes written in, change by change, and nothing else. Run on the Anton ground
 * truth, whose first measures carry "Lors-que nous é- / tions en-core en-" under 4 notes each.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import type { ModelChange } from "../api";
import { changeLine, correctedXml, lyricAt, markKeys } from "./draft";
import { parse, part, walk } from "./xml";

const GROUND_TRUTH = readFileSync(resolve(process.cwd(), "../bench/samples/anton_yvan_boris_ground_truth.musicxml"), "utf8");
const span = { staff: 0, from: 0, to: 3 };
const change = (id: string, measure: number, onset: number, old: ModelChange["old"], now: ModelChange["new"], extra: Partial<ModelChange> = {}): ModelChange =>
  ({ id, span, verse: 1, measure, onset, old, new: now, ticked: true, conflict: false, ...extra });

const CHANGES: ModelChange[] = [
  change("c1", 0, 0, { text: "Lors", syllabic: "begin" }, { text: "Lorsque", syllabic: "single" }),
  change("c2", 1, 0, { text: "tions", syllabic: "end" }, { text: "tion", syllabic: "end" }),
  change("c3", 2, 2, { text: "le", syllabic: "single" }, null),
  change("c4", 2, 0, null, { text: "fans", syllabic: "end" }, { verse: 2 }),
];

const all = () => new Set(CHANGES.map((c) => c.id));

describe("the corrected score", () => {
  it("writes a ticked change over the old syllable", () => {
    const doc = parse(correctedXml(GROUND_TRUTH, CHANGES, all()));
    expect(lyricAt(doc, 0, 0, 0, 1)).toEqual({ text: "Lorsque", syllabic: "single" });
    expect(lyricAt(doc, 0, 1, 0, 1)).toEqual({ text: "tion", syllabic: "end" });
  });

  it("clears a syllable the model took away", () => {
    const doc = parse(correctedXml(GROUND_TRUTH, CHANGES, all()));
    expect(lyricAt(doc, 0, 2, 2, 1)).toBeNull();
  });

  it("adds a second verse under a note that had none, leaving verse 1 there", () => {
    const doc = parse(correctedXml(GROUND_TRUTH, CHANGES, all()));
    expect(lyricAt(doc, 0, 2, 0, 2)).toEqual({ text: "fans", syllabic: "end" });
    expect(lyricAt(doc, 0, 2, 0, 1)).toEqual({ text: "fants", syllabic: "end" });
  });

  it("leaves an unticked change as read", () => {
    const doc = parse(correctedXml(GROUND_TRUTH, CHANGES, new Set(["c2"])));
    expect(lyricAt(doc, 0, 0, 0, 1)).toEqual({ text: "Lors", syllabic: "begin" });
    expect(lyricAt(doc, 0, 1, 0, 1)).toEqual({ text: "tion", syllabic: "end" });
    expect(lyricAt(doc, 0, 2, 2, 1)).toEqual({ text: "le", syllabic: "single" });
  });

  it("is the read score itself when nothing is ticked", () => {
    expect(correctedXml(GROUND_TRUTH, CHANGES, new Set())).toBe(GROUND_TRUTH);
  });

  it("touches no note, only lyrics", () => {
    const notes = (xml: string) => walk(part(parse(xml))).flatMap((m) => m.events.map((e) => [e.key.measure, e.key.onset, e.key.midi]));
    expect(notes(correctedXml(GROUND_TRUTH, CHANGES, all()))).toEqual(notes(GROUND_TRUTH));
  });
});

describe("the change list", () => {
  it("says the old value of a changed syllable", () => {
    expect(changeLine(CHANGES[0])).toBe('bar 1, verse 1: "Lors" becomes "Lorsque"');
  });
  it("says a syllable that goes and one that is new", () => {
    expect(changeLine(CHANGES[2])).toBe('bar 3, verse 1: "le" is taken away');
    expect(changeLine(CHANGES[3])).toBe('bar 3, verse 2: new "fans"');
  });
});

describe("where the marks go", () => {
  it("names the sounding note of each change, by onset rank", () => {
    const measures = walk(part(parse(GROUND_TRUTH)));
    const keys = markKeys(measures, CHANGES);
    expect(keys.map((k) => k.measure)).toEqual([0, 1, 2, 2]);
    expect(keys[2].onset).toBeGreaterThan(keys[3].onset);
  });
});
