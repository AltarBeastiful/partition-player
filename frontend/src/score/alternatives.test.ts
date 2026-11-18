import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { excerpt, previewNotes, readings } from "./alternatives";
import { checkMeasures } from "./check";
import { parse, part, serialize, walk, type EventKey } from "./xml";

const GROUND_TRUTH = readFileSync(resolve(process.cwd(), "../bench/samples/anton_yvan_boris_ground_truth.musicxml"), "utf8");

const doc1 = (measures: string, divisions = 4, time = "3/4", fifths = 0) => parse(`<?xml version="1.0"?>
<score-partwise version="4.0"><part-list><score-part id="P1"><part-name>V</part-name></score-part></part-list>
<part id="P1">${measures.replace("{attrs}", `<attributes><divisions>${divisions}</divisions><key><fifths>${fifths}</fifths></key><time><beats>${time.split("/")[0]}</beats><beat-type>${time.split("/")[1]}</beat-type></time><clef><sign>G</sign><line>2</line></clef></attributes>`)}</part></score-partwise>`);

const note = (step: string, octave: number, dur: number, type: string, alter?: number, extra = "") =>
  `<note><pitch><step>${step}</step>${alter ? `<alter>${alter}</alter>` : ""}<octave>${octave}</octave></pitch><duration>${dur}</duration><voice>1</voice><type>${type}</type>${extra}</note>`;
const rest = (dur: number, type?: string) => `<note><rest/><duration>${dur}</duration><voice>1</voice>${type ? `<type>${type}</type>` : ""}</note>`;
const chordNote = (step: string, octave: number, dur: number, type: string) =>
  `<note><chord/><pitch><step>${step}</step><octave>${octave}</octave></pitch><duration>${dur}</duration><voice>1</voice><type>${type}</type></note>`;
const grace = (step: string, octave: number, type: string) =>
  `<note><grace/><pitch><step>${step}</step><octave>${octave}</octave></pitch><voice>1</voice><type>${type}</type></note>`;

function keyAt(doc: XMLDocument, measure: number, index: number): EventKey {
  return walk(part(doc))[measure].events[index].key;
}

const notes = (xml: string) => (xml.match(/<note[ >]/g) ?? []).length;

/** A 3/4 measure the pipeline padded: quarter, quarter, eighth and an untyped eighth rest at the end. */
const padded = () => doc1(`<measure number="1">{attrs}${note("C", 4, 4, "quarter")}${note("D", 4, 4, "quarter")}${note("E", 4, 2, "eighth")}${rest(2)}</measure>`);

describe("readings of a padded measure", () => {
  it("offers the length the padding hides, on every note of the measure, first", () => {
    const doc = padded();
    const r = readings(doc, keyAt(doc, 0, 0), { padGap: 0.5 });
    expect(r.current.status).toBe("ok");

    const fix = r.list.find((x) => x.label === "dotted quarter instead of quarter" && x.fixes)!;
    expect(fix).toBeTruthy();
    expect(notes(fix.xml)).toBe(3);
    expect(fix.status).toBe("ok");
    expect(fix.note).toBe("measure adds up");
    expect(checkMeasures(walk(part(parse(fix.xml))))[0].status).toBe("ok");
    expect(fix.key!.midi).toBe(60);

    const second = r.list.find((x) => x.label === "beat 2: dotted quarter instead of quarter")!;
    expect(second).toBeTruthy();
    expect(second.fixes).toBe(true);
    expect(notes(second.xml)).toBe(3);

    const last = r.list.map((x) => x.fixes).lastIndexOf(true);
    const firstOther = r.list.findIndex((x) => !x.fixes);
    expect(last).toBeGreaterThan(-1);
    expect(last).toBeLessThan(firstOther);

    const longer = r.list.find((x) => x.label === "half instead of quarter")!;
    expect(longer.fixes).toBe(false);
    expect(longer.note).toContain("longer than 3/4");
  });
});

describe("readings of an overfull measure", () => {
  it("shortens the note that is too long, or drops it", () => {
    const doc = doc1(`<measure number="1">{attrs}${note("C", 4, 16, "whole")}</measure>`);
    const r = readings(doc, keyAt(doc, 0, 0));
    expect(r.current.status).toBe("overfull");
    expect(r.current.note).toBe("longer than 3/4 by a quarter");

    const fix = r.list.find((x) => x.label === "dotted half instead of whole")!;
    expect(fix.fixes).toBe(true);
    expect(fix.note).toBe("measure adds up");
    expect(r.list[0].fixes).toBe(true);

    const gone = r.list.find((x) => x.kind === "delete")!;
    expect(gone.label).toBe("no note here");
    expect(gone.key).toBe(null);
    expect(notes(gone.xml)).toBe(0);
  });
});

describe("readings of a pitch", () => {
  const doc = () => doc1(`<measure number="1">{attrs}${note("F", 4, 4, "quarter")}${note("G", 4, 4, "quarter")}${rest(4, "quarter")}</measure>`);

  it("names the steps, the accidentals and the octave as the toolbar does", () => {
    const d = doc();
    const r = readings(d, keyAt(d, 0, 0));
    const by = (label: string) => r.list.find((x) => x.label === label);
    expect(by("G4 instead of F4")!.key!.midi).toBe(67);
    expect(by("E4 instead of F4")!.key!.midi).toBe(64);
    expect(by("A4 instead of F4")!.key!.midi).toBe(69);
    expect(by("D4 instead of F4")!.key!.midi).toBe(62);
    expect(by("F♯4 instead of F4")!.key!.midi).toBe(66);
    expect(by("an octave up")!.key!.midi).toBe(77);
    expect(by("an octave down")!.key!.midi).toBe(53);
    expect(by("a rest instead of the note")).toBeTruthy();
    expect(by("two eighths instead of a quarter")!.kind).toBe("split");
    expect(r.list.filter((x) => x.kind === "accidental").map((x) => x.label).sort())
      .toEqual(["F♭4 instead of F4", "F♯4 instead of F4"]);
  });

  it("gives a rest no pitch, only a note", () => {
    const d = doc();
    const r = readings(d, keyAt(d, 0, 2));
    expect(r.list.some((x) => x.kind === "pitch" || x.kind === "octave" || x.kind === "accidental")).toBe(false);
    expect(r.list.some((x) => x.kind === "split")).toBe(false);
    expect(r.list.some((x) => x.label === "a note instead of the rest")).toBe(true);
  });
});

describe("readings of a grace note", () => {
  it("has no length to read otherwise", () => {
    const doc = doc1(`<measure number="1">{attrs}${grace("D", 5, "eighth")}${note("C", 4, 4, "quarter")}${note("D", 4, 4, "quarter")}${note("E", 4, 4, "quarter")}</measure>`);
    const r = readings(doc, keyAt(doc, 0, 0));
    expect(r.list.some((x) => x.kind === "duration" || x.kind === "split")).toBe(false);
    expect(r.list.length).toBeGreaterThan(0);
    expect(r.list.some((x) => x.kind === "pitch")).toBe(true);
  });
});

describe("the readings are distinct and reproducible", () => {
  it("writes a different measure each, and the same one its apply writes", () => {
    const doc = padded();
    const r = readings(doc, keyAt(doc, 0, 0), { padGap: 0.5 });
    const xmls = r.list.map((x) => x.xml);
    expect(xmls.length).toBeGreaterThan(5);
    expect(new Set(xmls).size).toBe(xmls.length);
    expect(xmls.every((x) => x !== r.current.xml)).toBe(true);
    const source = serialize(doc);
    for (const reading of r.list) {
      const fresh = parse(source);
      reading.apply(fresh);
      expect(excerpt(fresh, 0, 0)).toBe(reading.xml);
    }
  });
});

describe("excerpt", () => {
  it("carries the attributes in force into a measure taken on its own", () => {
    const doc = parse(GROUND_TRUTH);
    const one = excerpt(doc, 1, 1);
    expect(one).toContain("<divisions>");
    expect(one).toContain("<fifths>-3</fifths>");
    expect(one).toContain("<beats>");
    expect(one).toContain("<clef>");
    expect((one.match(/<measure[ >]/g) ?? []).length).toBe(1);
    const back = parse(one);
    expect(walk(part(back)).length).toBe(1);
    expect(walk(part(back))[0].fifths).toBe(-3);
    const two = excerpt(doc, 0, 1);
    expect((two.match(/<measure[ >]/g) ?? []).length).toBe(2);
    expect(walk(part(parse(two))).length).toBe(2);
  });
});

describe("previewNotes", () => {
  it("sounds a chord together, a tie once, and a short measure short", () => {
    const doc = doc1(`<measure number="1">{attrs}${note("C", 4, 4, "quarter")}${chordNote("E", 4, 4, "quarter")}${note("G", 4, 4, "quarter", undefined, '<tie type="start"/>')}${rest(4, "quarter")}</measure>
      <measure number="2">${note("G", 4, 4, "quarter", undefined, '<tie type="stop"/>')}${rest(4, "quarter")}</measure>`);
    const { notes: played, lengths } = previewNotes(doc, 0, 1);
    expect(lengths).toEqual([0.75, 0.5]);
    expect(played.length).toBe(3);
    expect(played[0]).toEqual({ time: 0, midi: 60, length: 0.25 });
    expect(played[1]).toEqual({ time: 0, midi: 64, length: 0.25 });
    expect(played[2]).toEqual({ time: 0.25, midi: 67, length: 0.5 });
  });
});
