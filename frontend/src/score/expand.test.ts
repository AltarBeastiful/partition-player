/**
 * The score written out as it is played (plan 0009, step 3). The point of the whole module is one
 * property: the expanded page and the unrolled timeline are the same music. It is checked by reading
 * the expanded document back with `previewNotes` — which knows nothing of forms, passes or slices —
 * and comparing it note for note with the source read through the same reader and cut by the same
 * slices. Measure by measure on both sides, so that a tie the expansion had to break counts as the
 * two notes it becomes rather than as one.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { previewNotes } from "./alternatives";
import { expandScore, measureDurations, slicesOf } from "./expand";
import { children, parse, part, text, walk } from "./xml";
import { expandForm, passNames, sliceRanges, type Form, type Pass, type Under } from "../form";

const EPS = 1e-9;
const GROUND_TRUTH = readFileSync(resolve(process.cwd(), "../bench/samples/anton_yvan_boris_ground_truth.musicxml"), "utf8");
const anton = () => parse(GROUND_TRUTH);

/** The form saved with Anton in the app: the verse leaves measure 11 on beat 2, the chorus enters it there. */
const ANTON_FORM: Form = {
  sections: [{ name: "Verse", from: 0, to: 10, toOnset: 0.25 }, { name: "Chorus", from: 10, to: 18, fromOnset: 0.25 }],
  passes: Array.from({ length: 5 }, (_, i) => [{ section: 0, verse: i + 1 }, { section: 1, verse: null, times: 2 }]).flat(),
};

interface Sound { time: number; midi: number; length: number }

/** What the source sounds like over a pass list: its measures read one by one, cut by the slices. */
function fromSource(doc: XMLDocument, passes: Pass[]): { notes: Sound[]; lengths: number[] } {
  const durations = measureDurations(part(doc));
  const slices = sliceRanges(passes, durations, durations.length);
  const notes: Sound[] = [];
  const lengths: number[] = [];
  let time = 0;
  for (const s of slices) {
    const limit = s.cut ? s.to : Infinity;
    for (const n of previewNotes(doc, s.measure, s.measure).notes) {
      const end = n.time + n.length;
      if (end <= s.from + EPS || n.time >= s.to - EPS) continue;
      const start = Math.max(n.time, s.from);
      const stop = Math.min(end, limit);
      if (stop - start <= EPS) continue;
      notes.push({ time: time + start - s.from, midi: n.midi, length: stop - start });
    }
    lengths.push(s.to - s.from);
    time += s.to - s.from;
  }
  return { notes, lengths };
}

/** What the expanded document says, read the same way: one measure at a time, laid end to end. */
function fromExpanded(xml: string): { notes: Sound[]; lengths: number[] } {
  const doc = parse(xml);
  const count = children(part(doc), "measure").length;
  const notes: Sound[] = [];
  const lengths: number[] = [];
  let time = 0;
  for (let i = 0; i < count; i++) {
    const read = previewNotes(doc, i, i);
    for (const n of read.notes) notes.push({ time: time + n.time, midi: n.midi, length: n.length });
    lengths.push(read.lengths[0] ?? 0);
    time += read.lengths[0] ?? 0;
  }
  return { notes, lengths };
}

const order = (a: Sound, b: Sound) => a.time - b.time || a.midi - b.midi;

function expectSameMusic(doc: XMLDocument, passes: Pass[]): void {
  const { xml } = expandScore(doc, passes);
  const want = fromSource(doc, passes);
  const got = fromExpanded(xml);
  expect(got.lengths.length).toBe(want.lengths.length);
  got.lengths.forEach((l, i) => expect(Math.abs(l - want.lengths[i])).toBeLessThan(1e-9));
  expect(got.notes.length).toBe(want.notes.length);
  const a = [...want.notes].sort(order), b = [...got.notes].sort(order);
  a.forEach((n, i) => {
    expect(b[i].midi).toBe(n.midi);
    expect(Math.abs(b[i].time - n.time)).toBeLessThan(1e-9);
    expect(Math.abs(b[i].length - n.length)).toBeLessThan(1e-9);
  });
}

describe("the expanded page is what the player plays", () => {
  it("writes Anton's real form out note for note", () => {
    const doc = anton();
    expectSameMusic(doc, expandForm(ANTON_FORM, 19));
  });

  it("writes a plain page sung twice, a section cut on both sides, and a pass with times", () => {
    const doc = anton();
    const whole: Pass[] = [{ ranges: [{ from: 0, to: 18 }], verse: 1 }, { ranges: [{ from: 0, to: 18 }], verse: 2 }];
    expectSameMusic(doc, whole);
    const inside: Pass[] = [{ ranges: [{ from: 2, to: 5, fromOnset: 0.25, toOnset: 0.25 }], verse: null }];
    expectSameMusic(doc, inside);
    const times = expandForm({ sections: [{ name: "Chorus", from: 10, to: 12, fromOnset: 0.25 }], passes: [{ section: 0, verse: null, times: 3 }] }, 19);
    expect(times.length).toBe(3);
    expectSameMusic(doc, times);
  });

  it("agrees when a section is entered and left in the middle of the same measure", () => {
    const doc = anton();
    expectSameMusic(doc, [{ ranges: [{ from: 10, to: 10, fromOnset: 0.25 }], verse: null },
                          { ranges: [{ from: 10, to: 10, toOnset: 0.25 }], verse: 1 }]);
  });
});

describe("Anton, written out", () => {
  const passes = expandForm(ANTON_FORM, 19);
  const result = () => expandScore(anton(), passes, passNames(passes, ANTON_FORM, 19));

  it("turns 19 printed measures into 145, of which 15 are partial", () => {
    const e = result();
    expect(passes.length).toBe(15);
    expect(e.measures).toBe(145);
    expect(e.partial).toBe(15);
    expect(e.passes).toBe(15);
    expect(children(part(parse(e.xml)), "measure").length).toBe(145);
  });

  it("ends the verse with a one-beat measure and opens the chorus with a one-beat pickup under its chord", () => {
    const measures = children(part(parse(result().xml)), "measure");
    const verseEnd = measures[10];        // the eleventh measure of the first verse pass
    const chorusStart = measures[11];
    expect(verseEnd.getAttribute("implicit")).toBe("yes");
    expect(chorusStart.getAttribute("implicit")).toBe("yes");
    expect(children(verseEnd, "note").map((n) => text(n, "type"))).toEqual(["quarter"]);
    expect(verseEnd.getElementsByTagName("text")[0].textContent).toBe("relles.");
    expect(children(chorusStart, "note").map((n) => text(n, "type"))).toEqual(["eighth", "eighth"]);
    expect(chorusStart.getElementsByTagName("text")[0].textContent).toBe("An");
    // the Cm sits at the head of the printed measure, before the quarter the verse keeps: the chorus
    // is sung over it, so the chorus's own first measure has to say so
    const harmony = children(chorusStart, "harmony")[0];
    expect(harmony).toBeTruthy();
    expect(text(harmony.getElementsByTagName("root")[0] as Element, "root-step")).toBe("C");
    expect(text(harmony, "kind")).toBe("minor");
  });

  it("names every pass on the page and starts it on a new system", () => {
    const measures = children(part(parse(result().xml)), "measure");
    const marks = measures.flatMap((m) => Array.from(m.getElementsByTagName("rehearsal")).map((r) => r.textContent));
    expect(marks.slice(0, 4)).toEqual(["Verse 1", "Chorus", "Chorus", "Verse 2"]);
    expect(marks.length).toBe(15);
    expect(measures.filter((m) => children(m, "print").length > 0).length).toBe(14); // every pass but the first
  });

  it("writes the key, the time and the divisions once, not fifteen times", () => {
    const xml = result().xml;
    expect((xml.match(/<fifths>/g) ?? []).length).toBe(1);
    expect((xml.match(/<beats>/g) ?? []).length).toBe(1);
    expect((xml.match(/<divisions>/g) ?? []).length).toBe(1);
    expect((xml.match(/<clef>/g) ?? []).length).toBe(1);
  });

  it("is a document a reader can walk from end to end", () => {
    const doc = parse(result().xml);
    const measures = walk(part(doc));
    expect(measures.length).toBe(145);
    expect(measures.every((m) => m.divisions === 10080 && m.beats === 2 && m.beatType === 4)).toBe(true);
    expect(measures.map((m) => m.el.getAttribute("number"))).toEqual(measures.map((_, i) => String(i + 1)));
  });

  it("knows how long the expansion is without writing it", () => {
    expect(slicesOf(anton(), passes).length).toBe(145);
  });
});

// ---- the smaller rules, on documents small enough to read ------------------------------------------

const doc1 = (measures: string, divisions = 4, time = "2/4", fifths = 0) => parse(`<?xml version="1.0"?>
<score-partwise version="4.0"><part-list><score-part id="P1"><part-name>V</part-name></score-part></part-list>
<part id="P1">${measures.replace("{attrs}", `<attributes><divisions>${divisions}</divisions><key><fifths>${fifths}</fifths></key><time><beats>${time.split("/")[0]}</beats><beat-type>${time.split("/")[1]}</beat-type></time><clef><sign>G</sign><line>2</line></clef></attributes>`)}</part></score-partwise>`);

const note = (step: string, octave: number, dur: number, type: string, extra = "") =>
  `<note><pitch><step>${step}</step><octave>${octave}</octave></pitch><duration>${dur}</duration><voice>1</voice><type>${type}</type>${extra}</note>`;
const lyric = (n: number, word: string) => `<lyric name="${n}" number="${n}"><syllabic>single</syllabic><text>${word}</text></lyric>`;
const words = (m: Element) => Array.from(m.getElementsByTagName("lyric")).map((l) => `${l.getAttribute("number")}:${text(l, "text")}`);
const measuresOf = (xml: string) => children(part(parse(xml)), "measure");

describe("the words of the pass", () => {
  /** A page with two verses stacked under its first note and one word under its second. */
  const stacked = () => doc1(`<measure number="1">{attrs}${note("C", 4, 4, "quarter", lyric(1, "Lors") + lyric(2, "Un"))}${note("D", 4, 4, "quarter", lyric(1, "que"))}</measure>`);
  const pass = (verse: number | null): Pass[] => [{ ranges: [{ from: 0, to: 0 }], verse }];

  it("keeps the verse's own words and renumbers them to the row that prints", () => {
    const first = measuresOf(expandScore(stacked(), pass(1)).xml)[0];
    expect(words(first)).toEqual(["1:Lors", "1:que"]);
    const second = measuresOf(expandScore(stacked(), pass(2)).xml)[0];
    expect(words(second)).toEqual(["1:Un", "1:que"]);
  });

  it("keeps them all where the note has none of the verse asked for, and where the pass has no verse", () => {
    expect(words(measuresOf(expandScore(stacked(), pass(3)).xml)[0])).toEqual(["1:Lors", "2:Un", "1:que"]);
    expect(words(measuresOf(expandScore(stacked(), pass(null)).xml)[0])).toEqual(["1:Lors", "2:Un", "1:que"]);
  });
});

describe("the signs that told the old order", () => {
  const repeated = () => doc1(`<measure number="1">{attrs}<barline location="left"><bar-style>heavy-light</bar-style><repeat direction="forward"/></barline>${note("C", 4, 8, "half")}</measure>`
    + `<measure number="2">${note("D", 4, 8, "half")}<barline location="right"><ending number="1" type="start"/><bar-style>light-heavy</bar-style><repeat direction="backward"/></barline></measure>`);

  it("keeps the pickup of a page that starts on one (plan 0010)", () => {
    // 3/4: a one-quarter pickup the file marks, then two full measures, played twice
    const doc = doc1(`<measure number="0" implicit="yes">{attrs}${note("C", 4, 4, "quarter")}</measure>`
      + `<measure number="1">${note("D", 4, 12, "half")}</measure>`
      + `<measure number="2">${note("E", 4, 12, "half")}</measure>`);
    const ms = measuresOf(expandScore(doc, [{ ranges: [{ from: 0, to: 2 }], verse: 1 }, { ranges: [{ from: 0, to: 2 }], verse: 2 }]).xml);
    expect(ms.map((m) => m.getAttribute("implicit"))).toEqual(["yes", "no", "no", "yes", "no", "no"]);
  });

  it("takes the repeats and the endings off, since the order is written out", () => {
    const xml = expandScore(repeated(), [{ ranges: [{ from: 0, to: 1 }], verse: 1 }, { ranges: [{ from: 0, to: 1 }], verse: 2 }]).xml;
    expect(xml).not.toContain("<repeat");
    expect(xml).not.toContain("<ending");
    // and the double bar that closed the printed page closes this one, once, at the end
    const ms = measuresOf(xml);
    expect(ms.length).toBe(4);
    expect(ms.filter((m) => children(m, "barline").length > 0).map((m) => ms.indexOf(m))).toEqual([3]);
  });
});

describe("the attributes", () => {
  /** Two measures in C, then two in F, so a form that goes back has something to say again. */
  const keyChange = () => doc1(`<measure number="1">{attrs}${note("C", 4, 8, "half")}</measure>`
    + `<measure number="2">${note("D", 4, 8, "half")}</measure>`
    + `<measure number="3"><attributes><key><fifths>-1</fifths></key></attributes>${note("E", 4, 8, "half")}</measure>`
    + `<measure number="4">${note("F", 4, 8, "half")}</measure>`);

  it("re-emits a key only where it changes, and again when the form goes back under the old one", () => {
    const xml = expandScore(keyChange(), [{ ranges: [{ from: 2, to: 3 }], verse: null }, { ranges: [{ from: 0, to: 1 }], verse: null }, { ranges: [{ from: 2, to: 3 }], verse: null }]).xml;
    const fifths = measuresOf(xml).map((m) => Array.from(m.getElementsByTagName("fifths")).map((f) => f.textContent));
    expect(fifths).toEqual([["-1"], [], ["0"], [], ["-1"], []]);
  });
});

describe("a note the section cuts", () => {
  const long = () => doc1(`<measure number="1">{attrs}${note("C", 4, 16, "whole")}</measure>`, 4, "4/4");

  it("is written as the values that add up to what is played, tied", () => {
    const m = measuresOf(expandScore(long(), [{ ranges: [{ from: 0, to: 0, toOnset: 0.3125 }], verse: null }]).xml)[0];
    const notes = children(m, "note");
    expect(notes.map((n) => text(n, "type"))).toEqual(["quarter", "16th"]);           // 1.25 quarters
    expect(notes.map((n) => text(n, "duration"))).toEqual(["4", "1"]);
    expect(notes.map((n) => children(n, "tie").map((t) => t.getAttribute("type")).join(""))).toEqual(["start", "stop"]);
    expect(m.getAttribute("implicit")).toBe("yes");
  });
});

describe("a line that goes on playing underneath, written out (plan 0011, step 7)", () => {
  /** Two staves, four 4/4 measures: the top one a tune, the bottom one resting then answering. */
  const TWO_STAVES = `<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0"><part-list><score-part id="P1"><part-name>Piano</part-name></score-part></part-list>
<part id="P1">
${[["A", "4"], ["B", "4"], ["C", "5"], ["D", "5"]].map(([step, octave], i) => `  <measure number="${i + 1}">
    ${i === 0 ? '<attributes><divisions>1</divisions><key><fifths>0</fifths></key><time><beats>4</beats><beat-type>4</beat-type></time><staves>2</staves><clef number="1"><sign>G</sign><line>2</line></clef><clef number="2"><sign>G</sign><line>2</line></clef></attributes>' : ""}
    <note><pitch><step>${step}</step><octave>${octave}</octave></pitch><duration>4</duration><type>whole</type><staff>1</staff><lyric number="1"><syllabic>single</syllabic><text>la</text></lyric></note>
    <backup><duration>4</duration></backup>
    <note>${i < 2 ? "<rest/>" : "<pitch><step>F</step><octave>3</octave></pitch>"}<duration>4</duration><type>whole</type><staff>2</staff></note>
  </measure>`).join("\n")}
</part></score-partwise>`;

  const page = () => parse(TWO_STAVES);
  const whole: Pass[] = [{ ranges: [{ from: 0, to: 3 }], verse: null }];
  const flute: Under = { line: 0, from: 0, to: 1, startAt: 2, instrument: "flute" };

  it("writes nothing new, byte for byte, when no line goes on underneath", () => {
    const before = expandScore(page(), whole, passNames(whole, null, 4));
    const after = expandScore(page(), whole, passNames(whole, null, 4), []);
    expect(after.xml).toBe(before.xml);
    expect(after.unders).toBe(0);
    expect(children(parse(after.xml).documentElement, "part")).toHaveLength(1);
  });

  it("writes the loop as a part of its own, in step with the form", () => {
    const { xml, unders } = expandScore(page(), whole, passNames(whole, null, 4), [flute], ["Flute", "Voice"]);
    expect(unders).toBe(1);
    const doc = parse(xml);
    const parts = children(doc.documentElement, "part");
    expect(parts).toHaveLength(2);
    expect(text(children(children(doc.documentElement, "part-list")[0], "score-part")[1], "part-name")).toBe("Flute, going on");
    const loop = parts[1];
    const measures = children(loop, "measure");
    expect(measures).toHaveLength(4);                       // two of silence, then two tiles
    expect(children(measures[0], "note").every((n) => children(n, "rest").length === 1)).toBe(true);
    expect(children(measures[1], "note").every((n) => children(n, "rest").length === 1)).toBe(true);
    // the tiles are the top staff's own notes, back at the start of the loop
    const pitches = measures.slice(2).map((m) => children(m, "note").map((n) => text(n.querySelector("pitch")!, "step")));
    expect(pitches).toEqual([["A"], ["B"]]);
  });

  it("takes the line's own staff and leaves the words behind", () => {
    const lower: Under = { ...flute, line: 1 };
    const doc = parse(expandScore(page(), whole, passNames(whole, null, 4), [lower], ["Flute", "Voice"]).xml);
    const loop = children(doc.documentElement, "part")[1];
    const sounding = children(loop, "measure").slice(2).flatMap((m) => children(m, "note"));
    expect(sounding.every((n) => children(n, "lyric").length === 0)).toBe(true);
    expect(sounding.every((n) => children(n, "staff").length === 0)).toBe(true);
    expect(sounding.every((n) => children(n, "rest").length === 1)).toBe(true);  // the lower staff rests there
  });

  it("stops where the form stops, and says the last measure is not a bar of its own", () => {
    const long: Under = { line: 0, from: 0, to: 3, startAt: 2, instrument: "flute" };
    const doc = parse(expandScore(page(), whole, passNames(whole, null, 4), [long], ["Flute", "Voice"]).xml);
    const measures = children(children(doc.documentElement, "part")[1], "measure");
    expect(measures).toHaveLength(4);
    expect(measures[measures.length - 1].getAttribute("implicit")).toBe("no"); // the tile filled its measure
    expect(measures[measures.length - 1].querySelector("barline bar-style")?.textContent).toBe("light-heavy");
  });
});
