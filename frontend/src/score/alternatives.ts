/**
 * The other readings of a note (plan 0005, decision 2). The engine's mistakes are few and measured: a
 * duration a step or two off the ladder, a pitch one or two steps away, another accidental, an octave,
 * a rest read as a note, an extra note. Every one of them is written here as a candidate edit — an
 * operation of `score/edit.ts` applied to a clone of the document — checked against the time signature
 * with `score/check.ts` and ranked, the readings that make the measure add up first. The module also
 * cuts a measure out of the score as a standalone MusicXML for the mini sheet (`excerpt`) and reads a
 * passage's notes for the ear (`previewNotes`). Nothing here touches the live document.
 */
import { checkMeasures, checkText, describe, filledQuarters } from "./check";
import {
  deleteEvent, insertEvent, nominalQuarters, setAlter, setDuration, shiftOctave, stepPitch, toNote, toRest,
  typeFor, typeOf, type DurationType,
} from "./edit";
import {
  child, children, find, insertOrdered, make, parse, part, serialize, walk,
  type Event, type EventKey, type MeasureInfo, type Pitch,
} from "./xml";

const EPS = 1e-9;
const ATTRIBUTES_ORDER = ["footnote", "level", "divisions", "key", "time", "staves", "part-symbol", "instruments", "clef",
  "staff-details", "transpose", "directive", "measure-style"];

// ---- the excerpt: one passage as a standalone score ----------------------------------------------

interface InForce { divisions: Element | null; key: Element | null; time: Element | null; staves: Element | null; clefs: Map<string, Element> }

/** The attributes in force at the start of measure `upto`: the latest of each seen from the first measure on. */
function inForce(partEl: Element, upto: number): InForce {
  const out: InForce = { divisions: null, key: null, time: null, staves: null, clefs: new Map() };
  for (const m of children(partEl, "measure").slice(0, upto + 1)) {
    for (const attrs of children(m, "attributes")) {
      const d = child(attrs, "divisions"); if (d) out.divisions = d;
      const k = child(attrs, "key"); if (k) out.key = k;
      const t = child(attrs, "time"); if (t) out.time = t;
      const s = child(attrs, "staves"); if (s) out.staves = s;
      for (const clef of children(attrs, "clef")) out.clefs.set(clef.getAttribute("number") ?? "1", clef);
    }
  }
  return out;
}

/** The page layout of the whole score means nothing to a one-measure sheet. */
function stripLayout(el: Element): void {
  for (const c of Array.from(el.children)) {
    if (c.tagName === "print") { el.removeChild(c); continue; }
    stripLayout(c);
  }
  el.removeAttribute("new-system");
  el.removeAttribute("new-page");
}

const STREAM = ["note", "backup", "forward", "harmony", "direction"];

/** Write the attributes in force into the first excerpted measure, completing one it already carries. */
function putAttributes(out: XMLDocument, measure: Element, f: InForce): void {
  let attrs: Element | null = null;
  for (const c of Array.from(measure.children)) {
    if (c.tagName === "attributes") { attrs = c; break; }
    if (STREAM.includes(c.tagName)) break;
  }
  if (!attrs) {
    attrs = make(out, "attributes");
    const anchor = Array.from(measure.children).find((c) => STREAM.includes(c.tagName)) ?? null;
    if (anchor) measure.insertBefore(attrs, anchor); else measure.appendChild(attrs);
  }
  const put = (el: Element | null) => {
    if (el && !child(attrs!, el.tagName)) insertOrdered(attrs!, out.importNode(el, true) as Element, ATTRIBUTES_ORDER);
  };
  put(f.divisions); put(f.key); put(f.time); put(f.staves);
  const have = new Set(children(attrs, "clef").map((c) => c.getAttribute("number") ?? "1"));
  for (const [number, clef] of f.clefs) {
    if (!have.has(number)) insertOrdered(attrs, out.importNode(clef, true) as Element, ATTRIBUTES_ORDER);
  }
}

/**
 * A standalone one-part MusicXML with measures [from, to] of part 0, the attributes in force at `from`
 * (divisions, key, time, clef(s)) written into the first excerpted measure.
 */
export function excerpt(doc: XMLDocument, from: number, to: number): string {
  const srcPart = part(doc);
  const srcMeasures = children(srcPart, "measure");
  const out = parse('<score-partwise version="4.0"><part-list/><part/></score-partwise>');
  const list = child(out.documentElement, "part-list")!;
  const outPart = child(out.documentElement, "part")!;
  const id = srcPart.getAttribute("id") || "P1";
  outPart.setAttribute("id", id);
  const srcList = child(doc.documentElement, "part-list");
  const scorePart = srcList ? children(srcList, "score-part").find((p) => p.getAttribute("id") === id) ?? children(srcList, "score-part")[0] : undefined;
  if (scorePart) {
    const clone = out.importNode(scorePart, true) as Element;
    clone.setAttribute("id", id);
    list.appendChild(clone);
  } else {
    const sp = make(out, "score-part", undefined, { id });
    sp.appendChild(make(out, "part-name", " "));
    list.appendChild(sp);
  }
  if (srcMeasures.length === 0) return serialize(out);
  const first = Math.max(0, Math.min(from, srcMeasures.length - 1));
  const last = Math.max(first, Math.min(to, srcMeasures.length - 1));
  for (let i = first; i <= last; i++) {
    const m = out.importNode(srcMeasures[i], true) as Element;
    m.setAttribute("number", String(i - first + 1));
    stripLayout(m);
    outPart.appendChild(m);
  }
  putAttributes(out, children(outPart, "measure")[0], inForce(srcPart, first));
  return serialize(out);
}

// ---- the passage for the ear ---------------------------------------------------------------------

export interface PreviewNote { time: number; midi: number; length: number } // whole notes from the start of the excerpt

function tieIs(ev: Event, type: "start" | "stop"): boolean {
  return children(ev.el, "tie").some((t) => t.getAttribute("type") === type);
}

/**
 * The sounding notes of measures [from, to] for the ear: onset in whole notes from the start of `from`
 * (measure lengths are the measures' actual filled length, so a short measure plays short), chord tones
 * at the same time, rests and grace notes skipped, a tie continuation extending the previous note.
 * Also returns the length of each measure in whole notes.
 */
export function previewNotes(doc: XMLDocument, from: number, to: number): { notes: PreviewNote[]; lengths: number[] } {
  const measures = walk(part(doc));
  const notes: PreviewNote[] = [];
  const lengths: number[] = [];
  const open = new Map<string, number>(); // staff/voice/pitch -> the note it goes on sounding
  let time = 0;
  for (let i = Math.max(0, from); i <= Math.min(to, measures.length - 1); i++) {
    const m = measures[i];
    const length = filledQuarters(m.el, m.divisions) / 4;
    for (const ev of m.events) {
      if (ev.isGrace || ev.isRest || ev.key.midi === null) continue;
      const id = `${ev.key.staff}/${ev.key.voice}/${ev.key.midi}`;
      const dur = ev.quarters / 4;
      const held = tieIs(ev, "stop") ? open.get(id) : undefined;
      if (held !== undefined) {
        notes[held].length += dur;
        if (!tieIs(ev, "start")) open.delete(id);
      } else {
        notes.push({ time: time + ev.key.onset, midi: ev.key.midi, length: dur });
        if (tieIs(ev, "start")) open.set(id, notes.length - 1);
      }
    }
    lengths.push(length);
    time += length;
  }
  return { notes, lengths };
}

// ---- the readings --------------------------------------------------------------------------------

export type ReadingKind = "duration" | "pitch" | "accidental" | "octave" | "rest" | "note" | "delete" | "split";

export interface Reading {
  id: string;
  kind: ReadingKind;
  label: string;
  apply: (doc: XMLDocument) => EventKey | null;
  key: EventKey | null;
  fixes: boolean;
  status: "ok" | "underfull" | "overfull" | "empty";
  note: string;
  weight: number;
  xml: string;
}

export interface Readings { current: { xml: string; status: Reading["status"]; note: string }; list: Reading[] }

/** whole, dotted half, half, dotted quarter, quarter, dotted eighth, eighth, dotted 16th, 16th, 32nd. */
const LADDER = [4, 3, 2, 1.5, 1, 0.75, 0.5, 0.375, 0.25, 0.125];

const WORD: Record<DurationType, string> = { breve: "breve", whole: "whole", half: "half", quarter: "quarter",
  eighth: "eighth", "16th": "16th", "32nd": "32nd", "64th": "64th" };
const PLURAL: Record<DurationType, string> = { breve: "breves", whole: "wholes", half: "halves", quarter: "quarters",
  eighth: "eighths", "16th": "16ths", "32nd": "32nds", "64th": "64ths" };

function valueWord(t: { type: DurationType; dots: number }): string {
  return (t.dots === 1 ? "dotted " : t.dots === 2 ? "double dotted " : "") + WORD[t.type];
}

/** The note name in the editor's words: F♯4, B♭3, "rest". */
function pitchName(p: Pitch | null): string {
  if (!p) return "rest";
  const acc = p.alter > 0 ? "♯".repeat(p.alter) : p.alter < 0 ? "♭".repeat(-p.alter) : "";
  return `${p.step}${acc}${p.octave}`;
}

/** "beat 2", "beat 2.5": where an event falls in its measure, as the toolbar says it. */
function beatOf(ev: Event, beatType: number): string {
  const b = ev.key.onset * beatType + 1;
  return Number.isInteger(b) ? `beat ${b}` : `beat ${Number(b.toFixed(2))}`;
}

interface Candidate {
  id: string;
  kind: ReadingKind;
  prefix: string;
  label: string | ((after: Event | null) => string);
  weight: number;
  distance: number;
  marks: boolean; // whether the key the operation returns names the changed event (a delete does not)
  op: (doc: XMLDocument) => EventKey | null;
}

/** The index of the rest the pipeline added at the end of the measure, if it is still there. */
function paddingAt(m: MeasureInfo, padGap: number): Event | null {
  if (!(padGap > EPS)) return null;
  const sounding = m.events.filter((e) => !e.isGrace);
  const last = sounding[sounding.length - 1];
  return last && last.isRest && Math.abs(last.quarters - padGap) < EPS ? last : null;
}

function article(word: string): string {
  return "aeiou".includes(word[0]) ? "an" : "a";
}

/**
 * The other readings of the event `key` names, ranked (plan 0005, decision 2). `padGap` is the length in
 * quarters of the rest the pipeline added at the end of this measure, if any. Never throws; a candidate
 * whose operation throws is dropped.
 */
export function readings(doc: XMLDocument, key: EventKey, opts: { padGap?: number } = {}): Readings {
  const nothing: Readings = { current: { xml: "", status: "empty", note: "" }, list: [] };
  let partEl: Element, measures: MeasureInfo[], m: MeasureInfo, ev: Event | null, current: Readings["current"];
  let check: ReturnType<typeof checkMeasures>[number];
  try {
    partEl = part(doc);
    measures = walk(partEl);
    if (!measures[key.measure]) return nothing;
    m = measures[key.measure];
    check = checkMeasures(measures)[key.measure];
    ev = find(measures, key);
    current = { xml: excerpt(doc, key.measure, key.measure), status: check.status, note: checkText(check) };
  } catch {
    return nothing;
  }
  if (!ev) return { current, list: [] };
  const here = ev;
  const padGap = opts.padGap ?? 0;
  const padding = paddingAt(m, padGap);
  const cands: Candidate[] = [];
  const at = (e: Event) => `m${key.measure}:e${e.index}`;
  const prefixOf = (e: Event) => (e === here ? "" : `${beatOf(e, m.beatType)}: `);

  // The changes that make the measure add up, on every event of the measure: ranked first.
  if (check.status === "underfull" || check.status === "overfull" || padding) {
    for (const e of m.events) {
      if (e.isGrace || e.inChord || (padding && e === padding)) continue;
      if (child(e.el, "time-modification")) continue; // a tuplet is not written with a plain note value
      const target = padding ? e.quarters + padGap : e.quarters - check.diff;
      if (target <= EPS || Math.abs(target - e.quarters) < EPS) continue;
      const t = typeFor(target);
      if (!t) continue;
      const was = typeOf(e);
      const paddingKey = padding ? padding.key : null;
      const target1 = t;
      cands.push({
        id: `duration:${target}:${padding ? "pad:" : ""}${at(e)}`, kind: "duration", prefix: prefixOf(e), weight: 2.5, distance: 0,
        marks: true, label: `${valueWord(t)} instead of ${was ? valueWord(was) : describe(e.quarters)}`,
        op: (d) => {
          if (paddingKey) deleteEvent(d, paddingKey);
          return setDuration(d, e.key, target1.type, target1.dots);
        },
      });
    }
    if (check.status === "overfull") {
      for (const e of m.events) {
        if (e.isGrace || e.inChord || Math.abs(e.quarters - check.diff) > EPS) continue;
        cands.push({ id: `delete:excess:${at(e)}`, kind: "delete", prefix: prefixOf(e), weight: 2, distance: 0, marks: false,
          label: "no note here", op: (d) => deleteEvent(d, e.key) });
      }
    }
  }

  // The duration ladder around the selected event.
  const written = here.isGrace ? null : typeOf(here);
  if (written) {
    const q0 = nominalQuarters(written.type, written.dots);
    let p = 0;
    for (let i = 1; i < LADDER.length; i++) if (Math.abs(LADDER[i] - q0) < Math.abs(LADDER[p] - q0)) p = i;
    for (const step of [-1, 1, -2, 2]) {
      const q = LADDER[p + step];
      if (q === undefined || Math.abs(q - q0) < EPS) continue;
      if (padding && Math.abs(q - (q0 + padGap)) < EPS) continue; // the fix above already reads it so, without the padding rest
      const t = typeFor(q);
      if (!t) continue;
      cands.push({ id: `duration:${q}:${at(here)}`, kind: "duration", prefix: "", weight: Math.abs(step) === 1 ? 3 : 2,
        distance: Math.abs(step), marks: true, label: `${valueWord(t)} instead of ${valueWord(written)}`,
        op: (d) => setDuration(d, key, t.type, t.dots) });
    }
  }

  // The pitch: a step or two away, another accidental, an octave.
  if (!here.isRest && here.pitch) {
    const was = pitchName(here.pitch);
    for (const [delta, weight] of [[1, 3], [-1, 3], [2, 2], [-2, 2]] as [number, number][]) {
      cands.push({ id: `pitch:${delta}:${at(here)}`, kind: "pitch", prefix: "", weight, distance: Math.abs(delta), marks: true,
        label: (after) => `${pitchName(after?.pitch ?? null)} instead of ${was}`, op: (d) => stepPitch(d, key, delta) });
    }
    for (const delta of [1, -1]) {
      cands.push({ id: `octave:${delta}:${at(here)}`, kind: "octave", prefix: "", weight: 1.5, distance: 1, marks: true,
        label: delta > 0 ? "an octave up" : "an octave down", op: (d) => shiftOctave(d, key, delta) });
    }
    for (const alter of [-1, 0, 1]) {
      if (alter === here.pitch.alter) continue;
      cands.push({ id: `accidental:${alter}:${at(here)}`, kind: "accidental", prefix: "", weight: 2, distance: 1, marks: true,
        label: (after) => `${pitchName(after?.pitch ?? null)} instead of ${was}`, op: (d) => setAlter(d, key, alter) });
    }
    cands.push({ id: `rest:${at(here)}`, kind: "rest", prefix: "", weight: 1.5, distance: 1, marks: true,
      label: "a rest instead of the note", op: (d) => toRest(d, key) });
  } else if (here.isRest) {
    cands.push({ id: `note:${at(here)}`, kind: "note", prefix: "", weight: 1.5, distance: 1, marks: true,
      label: "a note instead of the rest", op: (d) => toNote(d, key) });
  }

  cands.push({ id: `delete:${at(here)}`, kind: "delete", prefix: "", weight: 1, distance: 1, marks: false,
    label: "no note here", op: (d) => deleteEvent(d, key) });

  // One note read as two of half the value.
  if (written && !here.isRest && !here.isGrace) {
    const half = typeFor(nominalQuarters(written.type, written.dots) / 2);
    if (half && half.dots === 0) {
      cands.push({ id: `split:${at(here)}`, kind: "split", prefix: "", weight: 1, distance: 1, marks: true,
        label: `two ${PLURAL[half.type]} instead of ${article(WORD[written.type])} ${WORD[written.type]}`,
        op: (d) => { setDuration(d, key, half.type, 0); return insertEvent(d, key, "after", "note"); } });
    }
  }

  // Every candidate on a clone of the document: dropped when it throws or changes nothing, merged when
  // two of them write the same measure.
  const source = serialize(doc);
  const rows: { reading: Reading; distance: number }[] = [];
  const byXml = new Map<string, Reading>();
  for (const cand of cands) {
    let after: MeasureInfo[], xml: string, newKey: EventKey | null;
    try {
      const clone = parse(source);
      newKey = cand.op(clone);
      after = walk(part(clone));
      xml = excerpt(clone, key.measure, key.measure);
    } catch {
      continue;
    }
    if (xml === current.xml) continue;
    const already = byXml.get(xml);
    if (already) { already.weight = Math.max(already.weight, cand.weight); continue; }
    const ac = checkMeasures(after)[key.measure];
    if (!ac) continue;
    const fixes = ac.status === "ok" && (check.status !== "ok" || (!!padding && paddingAt(after[key.measure], padGap) === null));
    const note = ac.status === "ok" ? (fixes ? "measure adds up" : "")
      : ac.status === "empty" ? "empty measure"
      : `${check.status === ac.status ? "still" : "now"} ${checkText(ac)}`;
    const changed = newKey ? find(after, newKey) : null;
    const reading: Reading = {
      id: cand.id,
      kind: cand.kind,
      label: cand.prefix + (typeof cand.label === "string" ? cand.label : cand.label(changed)),
      apply: cand.op,
      key: cand.marks ? newKey : null,
      fixes,
      status: ac.status,
      note,
      weight: cand.weight,
      xml,
    };
    byXml.set(xml, reading);
    rows.push({ reading, distance: cand.distance });
  }
  rows.sort((a, b) => Number(b.reading.fixes) - Number(a.reading.fixes) || b.reading.weight - a.reading.weight || a.distance - b.distance);
  return { current, list: rows.map((r) => r.reading) };
}
