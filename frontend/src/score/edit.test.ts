import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { checkMeasures, checkText, describe as describeLength } from "./check";
import { chordText, parseChord } from "./chordText";
import {
  EditError, chordAt, deleteEvent, fillMeasure, insertEvent, insertMeasure, keyAlter, mergeWithNext, setAlter, setChord,
  setDuration, setKey, setTime, shiftOctave, splitMeasure, splitQuarters, stepPitch, toNote, toRest, toggleDot, toggleTie, deleteMeasure,
} from "./edit";
import { find, parse, part, serialize, walk, type EventKey } from "./xml";

const GROUND_TRUTH = readFileSync(resolve(process.cwd(), "../bench/samples/anton_yvan_boris_ground_truth.musicxml"), "utf8");

const doc1 = (measures: string, divisions = 4, time = "3/4", fifths = 0) => parse(`<?xml version="1.0"?>
<score-partwise version="4.0"><part-list><score-part id="P1"><part-name>V</part-name></score-part></part-list>
<part id="P1">${measures.replace("{attrs}", `<attributes><divisions>${divisions}</divisions><key><fifths>${fifths}</fifths></key><time><beats>${time.split("/")[0]}</beats><beat-type>${time.split("/")[1]}</beat-type></time><clef><sign>G</sign><line>2</line></clef></attributes>`)}</part></score-partwise>`);

const note = (step: string, octave: number, dur: number, type: string, alter?: number, extra = "") =>
  `<note><pitch><step>${step}</step>${alter ? `<alter>${alter}</alter>` : ""}<octave>${octave}</octave></pitch><duration>${dur}</duration><voice>1</voice><type>${type}</type>${extra}</note>`;
const rest = (dur: number, type?: string) => `<note><rest/><duration>${dur}</duration><voice>1</voice>${type ? `<type>${type}</type>` : ""}</note>`;

function keyAt(doc: XMLDocument, measure: number, index: number): EventKey {
  return walk(part(doc))[measure].events[index].key;
}

describe("walk", () => {
  it("gives every event of the benchmark page a key and follows the attributes", () => {
    const doc = parse(GROUND_TRUTH);
    const ms = walk(part(doc));
    expect(ms.length).toBe(19);
    const events = ms.flatMap((m) => m.events);
    expect(events.filter((e) => !e.isRest).length).toBe(55);
    expect(events.filter((e) => e.isRest).length).toBe(15);
    expect(ms[0].fifths).toBe(-3);
    expect(ms[0].events[0].key).toEqual({ measure: 0, staff: 1, voice: 1, onset: 0, midi: 63 });
    expect(new Set(events.map((e) => JSON.stringify(e.key))).size).toBe(events.length);
    expect(serialize(doc)).toContain("<score-partwise");
  });
});

describe("check", () => {
  it("flags the measures that do not add up, like the Python check", () => {
    const doc = doc1(`<measure number="1">{attrs}${note("C", 4, 4, "quarter")}${note("G", 4, 4, "quarter")}${note("G", 4, 4, "quarter")}</measure>
      <measure number="2">${note("C", 4, 4, "quarter")}${note("D", 4, 2, "eighth")}</measure>
      <measure number="3">${note("C", 4, 8, "half")}${note("D", 4, 6, "quarter")}</measure>`);
    const checks = checkMeasures(walk(part(doc)));
    expect(checks.map((c) => c.status)).toEqual(["ok", "underfull", "overfull"]);
    expect(checkText(checks[1])).toBe("shorter than 3/4 by a dotted quarter");
    expect(checkText(checks[2])).toBe("longer than 3/4 by an eighth");
    expect(describeLength(2.5)).toBe("five eighths");
  });
});

describe("pitch", () => {
  it("steps within the key: F# in D major goes up to G natural, and B up crosses the octave", () => {
    const doc = doc1(`<measure number="1">{attrs}${note("F", 4, 4, "quarter", 1)}${note("B", 4, 4, "quarter")}${rest(4, "quarter")}</measure>`, 4, "3/4", 2);
    const k = stepPitch(doc, keyAt(doc, 0, 0), 1);
    expect(k.midi).toBe(67);
    const ev = find(walk(part(doc)), k)!;
    expect(ev.pitch).toEqual({ step: "G", alter: 0, octave: 4 });
    const k2 = stepPitch(doc, keyAt(doc, 0, 1), 1);
    expect(find(walk(part(doc)), k2)!.pitch).toEqual({ step: "C", alter: 1, octave: 5 }); // C# from the key of D
    expect(() => stepPitch(doc, keyAt(doc, 0, 2), 1)).toThrow(EditError);
  });
  it("carries an explicit accidental with the note, and sets or clears one", () => {
    const doc = doc1(`<measure number="1">{attrs}${note("B", 4, 4, "quarter", -1)}</measure>`, 4, "1/4", 0);
    const k = stepPitch(doc, keyAt(doc, 0, 0), -1);
    expect(find(walk(part(doc)), k)!.pitch).toEqual({ step: "A", alter: -1, octave: 4 });
    const k2 = setAlter(doc, k, 0);
    expect(find(walk(part(doc)), k2)!.pitch).toEqual({ step: "A", alter: 0, octave: 4 });
    expect(serialize(doc)).not.toContain("<alter>");
    const k3 = shiftOctave(doc, k2, 1);
    expect(k3.midi).toBe(81);
    expect(keyAlter("B", -2)).toBe(-1);
    expect(keyAlter("F", 1)).toBe(1);
    expect(keyAlter("E", 1)).toBe(0);
  });
});

describe("duration", () => {
  it("writes a thirty-second by raising the divisions of the whole part", () => {
    const doc = doc1(`<measure number="1">{attrs}${note("C", 4, 4, "quarter")}${note("D", 4, 4, "quarter")}${note("E", 4, 4, "quarter")}</measure>
      <measure number="2">${note("F", 4, 12, "half", 0, "<dot/>")}</measure>`);
    setDuration(doc, keyAt(doc, 0, 1), "32nd", 0);
    const ms = walk(part(doc));
    expect(ms[0].divisions).toBe(8);
    expect(ms[0].events.map((e) => e.duration)).toEqual([8, 1, 8]);
    expect(ms[1].events[0].duration).toBe(24);
    expect(checkMeasures(ms)[0].status).toBe("underfull");
    toggleDot(doc, keyAt(doc, 0, 0));
    expect(walk(part(doc))[0].events[0].quarters).toBe(1.5);
    expect(serialize(doc)).toContain("<dot/>");
  });
  it("splits an odd length into note values", () => {
    expect(splitQuarters(2.5).map((p) => `${p.type}${p.dots ? "." : ""}`)).toEqual(["half", "eighth"]);
    expect(splitQuarters(3.5).map((p) => `${p.type}${p.dots ? "." : ""}`)).toEqual(["half.", "eighth"]);
  });
});

describe("notes and rests", () => {
  it("turns a note into a rest and an untyped padding rest into a note with its neighbour's pitch", () => {
    const doc = doc1(`<measure number="1">{attrs}${note("E", 4, 4, "quarter", 0, '<lyric number="1"><syllabic>single</syllabic><text>la</text></lyric>')}${rest(8)}</measure>`);
    const k = toRest(doc, keyAt(doc, 0, 0))!;
    expect(k.midi).toBeNull();
    expect(serialize(doc)).not.toContain("<lyric");
    // the rest is now the second event; make it a note again: no note before, none after, so the clef's middle line
    const k2 = toNote(doc, keyAt(doc, 0, 1));
    const ev = find(walk(part(doc)), k2)!;
    expect(ev.pitch).toEqual({ step: "B", alter: 0, octave: 4 });
    expect(ev.el.querySelector("type")!.textContent).toBe("half");
    expect(checkMeasures(walk(part(doc)))[0].status).toBe("ok");
  });
  it("deletes, inserts, and keeps the words on the beat when a chord head goes", () => {
    const doc = doc1(`<measure number="1">{attrs}${note("C", 4, 4, "quarter", 0, '<lyric number="1"><syllabic>single</syllabic><text>do</text></lyric>')}<note><chord/><pitch><step>E</step><octave>4</octave></pitch><duration>4</duration><voice>1</voice><type>quarter</type></note>${note("G", 4, 8, "half")}</measure>`);
    const next = deleteEvent(doc, keyAt(doc, 0, 0))!;
    let ms = walk(part(doc));
    expect(ms[0].events.length).toBe(2);
    expect(ms[0].events[0].inChord).toBe(false);
    expect(ms[0].events[0].el.querySelector("lyric text")!.textContent).toBe("do");
    expect(next.midi).toBe(64);
    const k = insertEvent(doc, next, "after", "rest");
    ms = walk(part(doc));
    expect(ms[0].events.map((e) => (e.isRest ? "r" : e.key.midi))).toEqual([64, "r", 67]);
    expect(k.onset).toBe(0.25);
    expect(checkMeasures(ms)[0].status).toBe("overfull");
    expect(deleteEvent(doc, keyAt(doc, 0, 2))!.midi).toBeNull(); // the last event: the rest before it is selected
  });
});

describe("ties", () => {
  it("ties to the next note of the same pitch, across the bar line, and refuses otherwise", () => {
    const doc = doc1(`<measure number="1">{attrs}${note("D", 5, 12, "half", 0, "<dot/>")}</measure><measure number="2">${note("D", 5, 4, "quarter")}${note("E", 5, 8, "half")}</measure>`);
    toggleTie(doc, keyAt(doc, 0, 0));
    const xml = serialize(doc);
    expect(xml).toContain('<tie type="start"/>');
    expect(xml).toContain('<tied type="stop"/>');
    expect(() => toggleTie(doc, keyAt(doc, 1, 0))).toThrow(/same pitch/);
    toggleTie(doc, keyAt(doc, 0, 0));
    expect(serialize(doc)).not.toContain("<tie");
  });
});

describe("measures", () => {
  it("fills, splits, merges, inserts and deletes", () => {
    const doc = doc1(`<measure number="1">{attrs}${note("C", 4, 4, "quarter")}${note("D", 4, 4, "quarter")}</measure><measure number="2"><harmony><root><root-step>G</root-step></root><kind>major</kind></harmony>${note("E", 4, 4, "quarter")}${note("F", 4, 4, "quarter")}${note("G", 4, 4, "quarter")}<barline location="right"><bar-style>light-heavy</bar-style></barline></measure>`);
    const k = fillMeasure(doc, 0)!;
    expect(k.onset).toBe(0.5);
    expect(checkMeasures(walk(part(doc)))[0].status).toBe("ok");
    const k2 = splitMeasure(doc, keyAt(doc, 1, 1));
    let ms = walk(part(doc));
    expect(ms.length).toBe(3);
    expect(ms.map((m) => m.events.length)).toEqual([3, 1, 2]);
    expect(ms.map((m) => m.el.getAttribute("number"))).toEqual(["1", "2", "3"]);
    expect(k2).toEqual({ measure: 2, staff: 1, voice: 1, onset: 0, midi: 65 });
    expect(ms[2].el.querySelector("barline")).not.toBeNull();
    mergeWithNext(doc, 1);
    ms = walk(part(doc));
    expect(ms.length).toBe(2);
    expect(ms[1].events.map((e) => e.key.midi)).toEqual([64, 65, 67]);
    expect(ms[1].el.querySelector("harmony")).not.toBeNull();
    expect(insertMeasure(doc, 0, "before")).toBe(0);
    ms = walk(part(doc));
    expect(ms.length).toBe(3);
    expect(ms[0].el.querySelector("attributes")).not.toBeNull();
    expect(ms[0].events[0].isRest && ms[0].events[0].quarters === 3).toBe(true);
    expect(deleteMeasure(doc, 0)).toBe(0);
    ms = walk(part(doc));
    expect(ms.length).toBe(2);
    expect(ms[0].el.querySelector("attributes divisions")!.textContent).toBe("4");
  });
  it("sets a time signature or key from a measure on and drops later changes", () => {
    const doc = doc1(`<measure number="1">{attrs}${note("C", 4, 8, "half")}</measure><measure number="2"><attributes><time><beats>2</beats><beat-type>4</beat-type></time></attributes>${note("C", 4, 8, "half")}</measure><measure number="3">${note("C", 4, 8, "half")}</measure>`, 4, "3/4");
    setTime(doc, 0, 2, 4);
    let ms = walk(part(doc));
    expect(ms.map((m) => `${m.beats}/${m.beatType}`)).toEqual(["2/4", "2/4", "2/4"]);
    expect(checkMeasures(ms).map((c) => c.status)).toEqual(["ok", "ok", "ok"]);
    setKey(doc, 1, -3);
    ms = walk(part(doc));
    expect(ms.map((m) => m.fifths)).toEqual([0, -3, -3]);
    expect(() => setTime(doc, 0, 3, 5)).toThrow(EditError);
  });
});

describe("chord symbols", () => {
  it("parses and writes the grammar's chords and edits the one on a beat", () => {
    expect(chordText(parseChord("F#m7/A")!)).toBe("F#m7/A");
    expect(chordText(parseChord("Bb")!)).toBe("Bb");
    expect(chordText(parseChord("C7sus4")!)).toBe("C7sus4");
    expect(parseChord("H7")).toBeNull();
    expect(parseChord("Cm7b5")!.kind).toBe("half-diminished");
    const doc = doc1(`<measure number="1">{attrs}<harmony><root><root-step>C</root-step></root><kind>minor</kind></harmony>${note("C", 4, 4, "quarter")}${note("D", 4, 8, "half")}</measure>`);
    expect(chordAt(doc, keyAt(doc, 0, 0))).toBe("Cm");
    expect(chordAt(doc, keyAt(doc, 0, 1))).toBe("");
    setChord(doc, keyAt(doc, 0, 1), "G7/B");
    expect(chordAt(doc, keyAt(doc, 0, 1))).toBe("G7/B");
    setChord(doc, keyAt(doc, 0, 0), "");
    expect(chordAt(doc, keyAt(doc, 0, 0))).toBe("");
    expect(() => setChord(doc, keyAt(doc, 0, 0), "Xyz")).toThrow(EditError);
    expect(part(doc).querySelectorAll("harmony").length).toBe(1);
  });
});
