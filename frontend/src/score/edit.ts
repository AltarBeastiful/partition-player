/**
 * The editor's operations (ADR 0005, decision 4): pure functions on the MusicXML DOM. Each takes the
 * document and the key of the selected event, changes the document in place and returns the key to
 * select next (null when nothing sensible is left). An operation that does not apply throws an
 * EditError with a sentence for the user. Undo is the caller's business (a stack of serializations).
 */
import { filledQuarters } from "./check";
import { chordText, harmonyElement, parseChord, readHarmony, type ChordSpec } from "./chordText";
import {
  STEPS, child, children, find, insertOrdered, make, midiOf, part, removeChildren, setChild, text, walk,
  type Event, type EventKey, type MeasureInfo, type Pitch,
} from "./xml";

export class EditError extends Error {}

export type DurationType = "breve" | "whole" | "half" | "quarter" | "eighth" | "16th" | "32nd" | "64th";
export const TYPE_QUARTERS: Record<DurationType, number> = { breve: 8, whole: 4, half: 2, quarter: 1, eighth: 0.5, "16th": 0.25, "32nd": 0.125, "64th": 0.0625 };
export const TYPES: DurationType[] = ["whole", "half", "quarter", "eighth", "16th", "32nd"];

export function nominalQuarters(type: DurationType, dots: number): number {
  return TYPE_QUARTERS[type] * (2 - 1 / 2 ** dots);
}

/** The type and dots that write a length exactly, or null (five eighths has no single note value). */
export function typeFor(quarters: number): { type: DurationType; dots: number } | null {
  for (const type of Object.keys(TYPE_QUARTERS) as DurationType[]) {
    for (let dots = 0; dots <= 2; dots++) if (Math.abs(nominalQuarters(type, dots) - quarters) < 1e-9) return { type, dots };
  }
  return null;
}

/** Greedy split of a length into note values, longest first: 2.5 quarters -> half, eighth. */
export function splitQuarters(quarters: number): { type: DurationType; dots: number }[] {
  const out: { type: DurationType; dots: number }[] = [];
  let left = quarters;
  const values = (Object.keys(TYPE_QUARTERS) as DurationType[]).flatMap((type) => [1, 0].map((dots) => ({ type, dots, q: nominalQuarters(type, dots) })))
    .sort((a, b) => b.q - a.q);
  for (let guard = 0; left > 1e-9 && guard < 16; guard++) {
    const v = values.find((x) => x.q <= left + 1e-9);
    if (!v) break;
    out.push({ type: v.type, dots: v.dots });
    left -= v.q;
  }
  return out;
}

function gcd(a: number, b: number): number { return b ? gcd(b, a % b) : a; }
function lcm(a: number, b: number): number { return (a * b) / gcd(a, b); }

/** The smallest number of divisions per quarter that writes `quarters` as an integer. */
export function denominatorOf(quarters: number): number {
  for (let n = 1; n <= 3840; n++) if (Math.abs(quarters * n - Math.round(quarters * n)) < 1e-7) return n;
  throw new EditError("this length cannot be written");
}

/** Make every <divisions> of the part a multiple of `needed`, scaling all durations with it. */
export function ensureDivisions(partEl: Element, needed: number): void {
  const measures = children(partEl, "measure");
  if (measures.length === 0) return;
  if (!measures.some((m) => children(m, "attributes").some((a) => child(a, "divisions")))) {
    let attrs = child(measures[0], "attributes");
    if (!attrs) { attrs = make(partEl.ownerDocument, "attributes"); measures[0].insertBefore(attrs, measures[0].firstChild); }
    insertOrdered(attrs, make(partEl.ownerDocument, "divisions", "1"), ATTRIBUTES_ORDER);
  }
  let factor = 1;
  for (const m of measures) {
    for (const attrs of children(m, "attributes")) {
      const de = child(attrs, "divisions");
      if (!de) continue;
      const d = Number(de.textContent) || 1;
      const nd = lcm(d, needed);
      factor = nd / d;
      de.textContent = String(nd);
    }
    if (factor === 1) continue;
    for (const el of Array.from(m.children)) {
      if (el.tagName !== "note" && el.tagName !== "backup" && el.tagName !== "forward") continue;
      const du = child(el, "duration");
      if (du) du.textContent = String(Math.round(Number(du.textContent) * factor));
    }
  }
}

const ATTRIBUTES_ORDER = ["footnote", "level", "divisions", "key", "time", "staves", "part-symbol", "instruments", "clef", "staff-details", "transpose", "directive", "measure-style"];

// ---- context -------------------------------------------------------------------------------------

interface Ctx { doc: XMLDocument; partEl: Element; measures: MeasureInfo[]; m: MeasureInfo; ev: Event }

function ctx(doc: XMLDocument, key: EventKey): Ctx {
  const partEl = part(doc);
  const measures = walk(partEl);
  const ev = find(measures, key);
  if (!ev) throw new EditError("the selected note is not in the score any more");
  return { doc, partEl, measures, m: measures[key.measure], ev };
}

/** The notes sounding together with `ev`: the chord head and every note flagged <chord/> after it. */
export function chordGroup(events: Event[], ev: Event): Event[] {
  let head = ev.index;
  while (head > 0 && events[head].inChord) head--;
  const group = [events[head]];
  for (let i = head + 1; i < events.length && events[i].inChord; i++) group.push(events[i]);
  return group;
}

function tupletRatio(el: Element): number {
  const tm = child(el, "time-modification");
  if (!tm) return 1;
  const actual = Number(text(tm, "actual-notes", "1")) || 1;
  const normal = Number(text(tm, "normal-notes", "1")) || 1;
  return normal / actual;
}

function writeDuration(c: Ctx, el: Element, type: DurationType, dots: number): void {
  const quarters = nominalQuarters(type, dots) * tupletRatio(el);
  const needed = denominatorOf(quarters);
  ensureDivisions(c.partEl, needed);
  const divisions = walk(c.partEl)[c.m.index].divisions;
  setChild(c.doc, el, "duration", String(Math.round(quarters * divisions)));
  setChild(c.doc, el, "type", type);
  removeChildren(el, "dot");
  for (let i = 0; i < dots; i++) insertOrdered(el, make(c.doc, "dot"));
}

/** Type and dots of an event, derived from its duration when it has no <type> (a padding rest). */
export function typeOf(ev: Event): { type: DurationType; dots: number } | null {
  const t = text(ev.el, "type") as DurationType;
  if (t && t in TYPE_QUARTERS) return { type: t, dots: children(ev.el, "dot").length };
  return typeFor(ev.quarters / tupletRatio(ev.el));
}

// ---- pitch ---------------------------------------------------------------------------------------

const SHARPS = "FCGDAEB", FLATS = "BEADGCF";

/** The alteration the key signature gives a step: +1 for F in one sharp, -1 for B in one flat. */
export function keyAlter(step: string, fifths: number): number {
  if (fifths > 0) return SHARPS.slice(0, fifths).includes(step) ? 1 : 0;
  if (fifths < 0) return FLATS.slice(0, -fifths).includes(step) ? -1 : 0;
  return 0;
}

function writePitch(doc: XMLDocument, el: Element, p: Pitch): void {
  let pe = child(el, "pitch");
  if (!pe) { pe = make(doc, "pitch"); insertOrdered(el, pe); }
  setChild(doc, pe, "step", p.step, ["step", "alter", "octave"]);
  removeChildren(pe, "alter");
  if (p.alter) setChild(doc, pe, "alter", String(p.alter), ["step", "alter", "octave"]);
  setChild(doc, pe, "octave", String(p.octave), ["step", "alter", "octave"]);
  removeChildren(el, "accidental"); // the renderer derives the sign from the alteration and the key
}

/** Move the note a step up or down the staff. An accidental the print carried (one that differs from
 *  the key) travels with the note; a note that took its alteration from the key takes the new step's. */
export function stepPitch(doc: XMLDocument, key: EventKey, delta: number): EventKey {
  const c = ctx(doc, key);
  if (!c.ev.pitch || c.ev.isRest) throw new EditError("a rest has no pitch");
  const p = c.ev.pitch;
  const explicit = p.alter !== keyAlter(p.step, c.m.fifths);
  const idx = STEPS.indexOf(p.step) + delta;
  const step = STEPS[((idx % 7) + 7) % 7];
  const octave = p.octave + Math.floor(idx / 7);
  const np = { step, octave, alter: explicit ? p.alter : keyAlter(step, c.m.fifths) };
  writePitch(doc, c.ev.el, np);
  return { ...key, midi: midiOf(np) };
}

export function setAlter(doc: XMLDocument, key: EventKey, alter: number): EventKey {
  const c = ctx(doc, key);
  if (!c.ev.pitch || c.ev.isRest) throw new EditError("a rest has no pitch");
  const np = { ...c.ev.pitch, alter };
  writePitch(doc, c.ev.el, np);
  return { ...key, midi: midiOf(np) };
}

export function shiftOctave(doc: XMLDocument, key: EventKey, delta: number): EventKey {
  const c = ctx(doc, key);
  if (!c.ev.pitch || c.ev.isRest) throw new EditError("a rest has no pitch");
  const np = { ...c.ev.pitch, octave: c.ev.pitch.octave + delta };
  if (np.octave < 0 || np.octave > 9) throw new EditError("that octave is off the piano");
  writePitch(doc, c.ev.el, np);
  return { ...key, midi: midiOf(np) };
}

// ---- duration ------------------------------------------------------------------------------------

/** Set the note value of the selected event (and of the notes sounding with it). */
export function setDuration(doc: XMLDocument, key: EventKey, type: DurationType, dots: number): EventKey {
  const c = ctx(doc, key);
  if (c.ev.isGrace) throw new EditError("a grace note has no length");
  for (const e of chordGroup(c.m.events, c.ev)) writeDuration(c, e.el, type, dots);
  return key;
}

export function toggleDot(doc: XMLDocument, key: EventKey): EventKey {
  const c = ctx(doc, key);
  const t = typeOf(c.ev);
  if (!t) throw new EditError("this length has no single note value; set it first");
  return setDuration(doc, key, t.type, t.dots ? 0 : 1);
}

// ---- notes and rests -----------------------------------------------------------------------------

const STRIP_ON_REST = ["pitch", "tie", "accidental", "stem", "notehead", "notations", "lyric", "chord"];

export function toRest(doc: XMLDocument, key: EventKey): EventKey | null {
  const c = ctx(doc, key);
  if (c.ev.isRest) return key;
  const group = chordGroup(c.m.events, c.ev);
  if (group.length > 1) return deleteEvent(doc, key); // one note of a chord: the others go on sounding
  for (const tag of STRIP_ON_REST) removeChildren(c.ev.el, tag);
  insertOrdered(c.ev.el, make(doc, "rest"));
  untie(c.measures, c.ev);
  return { ...key, midi: null };
}

function clefDefault(measures: MeasureInfo[], measure: number, staff: number): Pitch {
  for (let i = measure; i >= 0; i--) {
    for (const attrs of children(measures[i].el, "attributes")) {
      for (const clef of children(attrs, "clef")) {
        const n = Number(clef.getAttribute("number") ?? "1") || 1;
        if (n !== staff) continue;
        const sign = text(clef, "sign", "G");
        return sign === "F" ? { step: "D", alter: 0, octave: 3 } : sign === "C" ? { step: "C", alter: 0, octave: 4 } : { step: "B", alter: 0, octave: 4 };
      }
    }
  }
  return { step: "B", alter: 0, octave: 4 };
}

/** A pitch for a new note: the nearest sounding note before it in the same staff, else after, else the clef's middle line. */
function neighbourPitch(measures: MeasureInfo[], measure: number, index: number, staff: number): Pitch {
  const all = measures.flatMap((m) => m.events.map((e) => ({ e, m: m.index })));
  const at = all.findIndex((x) => x.m === measure && x.e.index === index);
  for (let i = at - 1; i >= 0; i--) if (all[i].e.pitch && !all[i].e.isRest && all[i].e.key.staff === staff) return { ...all[i].e.pitch! };
  for (let i = at + 1; i < all.length; i++) if (all[i].e.pitch && !all[i].e.isRest && all[i].e.key.staff === staff) return { ...all[i].e.pitch! };
  return clefDefault(measures, measure, staff);
}

/** Make sure the event has a <type>; an untyped rest of an odd length is split into typed rests first. */
function ensureTyped(c: Ctx, ev: Event): Event {
  if (text(ev.el, "type")) return ev;
  const t = typeFor(ev.quarters / tupletRatio(ev.el));
  if (t) { writeDuration(c, ev.el, t.type, t.dots); return ev; }
  const pieces = splitQuarters(ev.quarters);
  if (pieces.length === 0) throw new EditError("this rest has no length");
  const parent = ev.el.parentElement!;
  let anchor: Element = ev.el;
  for (const piece of pieces.slice(1)) {
    const rest = ev.el.cloneNode(true) as Element;
    parent.insertBefore(rest, anchor.nextSibling);
    writeDuration(c, rest, piece.type, piece.dots);
    anchor = rest;
  }
  writeDuration(c, ev.el, pieces[0].type, pieces[0].dots);
  return ev;
}

export function toNote(doc: XMLDocument, key: EventKey): EventKey {
  const c = ctx(doc, key);
  if (!c.ev.isRest) return key;
  ensureTyped(c, c.ev);
  const el = c.ev.el;
  removeChildren(el, "rest");
  const p = neighbourPitch(c.measures, key.measure, c.ev.index, key.staff);
  writePitch(doc, el, p);
  el.removeAttribute("measure");
  return { ...key, midi: midiOf(p) };
}

/** Delete the event; a chord loses one note, a lone note leaves its beat to the neighbours. */
export function deleteEvent(doc: XMLDocument, key: EventKey): EventKey | null {
  const c = ctx(doc, key);
  const group = chordGroup(c.m.events, c.ev);
  const el = c.ev.el;
  untie(c.measures, c.ev);
  if (group.length > 1 && group[0] === c.ev) {
    const next = group[1].el;
    removeChildren(next, "chord");
    for (const lyric of children(el, "lyric")) insertOrdered(next, lyric); // the words stay on the beat
  }
  el.parentElement!.removeChild(el);
  const after = walk(c.partEl);
  const same = after[key.measure]?.events.filter((e) => e.key.staff === key.staff && e.key.voice === key.voice && !e.inChord) ?? [];
  const next = same.find((e) => e.key.onset >= key.onset - 1e-9) ?? same[same.length - 1];
  if (next) return next.key;
  const anyone = after[key.measure]?.events[0] ?? after[Math.max(0, key.measure - 1)]?.events[0];
  return anyone ? anyone.key : null;
}

/** A new note or rest of the selected event's length, before or after it. */
export function insertEvent(doc: XMLDocument, key: EventKey, where: "before" | "after", kind: "note" | "rest"): EventKey {
  const c = ctx(doc, key);
  const group = chordGroup(c.m.events, c.ev);
  const t = typeOf(c.ev) ?? { type: "quarter" as DurationType, dots: 0 };
  const el = make(doc, "note");
  if (kind === "rest") el.appendChild(make(doc, "rest"));
  el.appendChild(make(doc, "duration", "1"));
  el.appendChild(make(doc, "voice", String(key.voice)));
  el.appendChild(make(doc, "type", t.type));
  const tm = child(c.ev.el, "time-modification");
  if (tm) insertOrdered(el, tm.cloneNode(true) as Element);
  if (child(c.ev.el, "staff")) insertOrdered(el, make(doc, "staff", String(key.staff)));
  const anchor = where === "before" ? group[0].el : group[group.length - 1].el;
  anchor.parentElement!.insertBefore(el, where === "before" ? anchor : anchor.nextSibling);
  writeDuration(c, el, t.type, t.dots);
  let midi: number | null = null;
  if (kind === "note") {
    const p = c.ev.pitch && !c.ev.isRest ? { ...c.ev.pitch } : neighbourPitch(walk(c.partEl), key.measure, c.ev.index + (where === "after" ? group.length : 0), key.staff);
    writePitch(doc, el, p);
    midi = midiOf(p);
  }
  const after = walk(c.partEl)[key.measure].events.find((e) => e.el === el)!;
  return { ...after.key, midi };
}

// ---- ties ----------------------------------------------------------------------------------------

/** The next event in the same staff and voice, into the next measure when needed. */
export function nextInVoice(measures: MeasureInfo[], ev: Event): Event | null {
  const same = (e: Event) => e.key.staff === ev.key.staff && e.key.voice === ev.key.voice && !e.inChord && !e.isGrace;
  const m = measures[ev.key.measure];
  const later = m.events.filter((e) => same(e) && e.key.onset > ev.key.onset + 1e-9);
  if (later.length) return later[0];
  for (let i = ev.key.measure + 1; i < measures.length; i++) {
    const first = measures[i].events.find(same);
    if (first) return first;
  }
  return null;
}

export function prevInVoice(measures: MeasureInfo[], ev: Event): Event | null {
  const same = (e: Event) => e.key.staff === ev.key.staff && e.key.voice === ev.key.voice && !e.inChord && !e.isGrace;
  const m = measures[ev.key.measure];
  const earlier = m.events.filter((e) => same(e) && e.key.onset < ev.key.onset - 1e-9);
  if (earlier.length) return earlier[earlier.length - 1];
  for (let i = ev.key.measure - 1; i >= 0; i--) {
    const all = measures[i].events.filter(same);
    if (all.length) return all[all.length - 1];
  }
  return null;
}

export function tiedToNext(ev: Event): boolean {
  return children(ev.el, "tie").some((t) => t.getAttribute("type") === "start");
}

function setTie(doc: XMLDocument, el: Element, type: "start" | "stop", on: boolean): void {
  for (const t of children(el, "tie")) if (t.getAttribute("type") === type) el.removeChild(t);
  const notations = child(el, "notations");
  if (notations) for (const t of children(notations, "tied")) if (t.getAttribute("type") === type) notations.removeChild(t);
  if (!on) return;
  insertOrdered(el, make(doc, "tie", undefined, { type }));
  let n = child(el, "notations");
  if (!n) { n = make(doc, "notations"); insertOrdered(el, n); }
  n.appendChild(make(doc, "tied", undefined, { type }));
}

/** Drop the ties around an event that is deleted or becomes a rest. */
function untie(measures: MeasureInfo[], ev: Event): void {
  const doc = ev.el.ownerDocument;
  if (tiedToNext(ev)) { const n = nextInVoice(measures, ev); if (n) setTie(doc, n.el, "stop", false); }
  if (children(ev.el, "tie").some((t) => t.getAttribute("type") === "stop")) { const p = prevInVoice(measures, ev); if (p) setTie(doc, p.el, "start", false); }
}

/** Tie the note to the next one of the same pitch, or undo that tie. */
export function toggleTie(doc: XMLDocument, key: EventKey): EventKey {
  const c = ctx(doc, key);
  if (c.ev.isRest) throw new EditError("a rest cannot be tied");
  const next = nextInVoice(c.measures, c.ev);
  const on = !tiedToNext(c.ev);
  if (on) {
    if (!next || next.isRest) throw new EditError("there is no note after this one to tie to");
    if (next.key.midi !== c.ev.key.midi) throw new EditError("a tie joins two notes of the same pitch; change the next note first");
  }
  setTie(doc, c.ev.el, "start", on);
  if (next) setTie(doc, next.el, "stop", on);
  return key;
}

// ---- measures ------------------------------------------------------------------------------------

export function renumber(partEl: Element): void {
  children(partEl, "measure").forEach((m, i) => m.setAttribute("number", String(i + 1)));
}

function hasVoices(m: Element): boolean {
  return children(m, "backup").length > 0 || children(m, "forward").length > 0;
}

function measureCtx(doc: XMLDocument, index: number): { partEl: Element; measures: MeasureInfo[]; m: MeasureInfo } {
  const partEl = part(doc);
  const measures = walk(partEl);
  const m = measures[index];
  if (!m) throw new EditError("no such measure");
  return { partEl, measures, m };
}

/** Rests for the missing length, at the end of the measure. */
export function fillMeasure(doc: XMLDocument, index: number): EventKey | null {
  const { partEl, m } = measureCtx(doc, index);
  const expected = (m.beats * 4) / m.beatType;
  const gap = expected - filledQuarters(m.el, m.divisions);
  if (gap <= 1e-9) throw new EditError("the measure is not short");
  const last = [...m.events].reverse().find((e) => !e.isGrace);
  const voice = last ? String(last.key.voice) : "1";
  const staff = last && child(last.el, "staff") ? String(last.key.staff) : null;
  let anchor: Node | null = last ? last.el.nextSibling : null;
  const c: Ctx = { doc, partEl, measures: walk(partEl), m, ev: m.events[0] ?? ({} as Event) };
  let firstKey: EventKey | null = null;
  for (const piece of splitQuarters(gap)) {
    const rest = make(doc, "note");
    rest.appendChild(make(doc, "rest"));
    rest.appendChild(make(doc, "duration", "1"));
    rest.appendChild(make(doc, "voice", voice));
    rest.appendChild(make(doc, "type", piece.type));
    if (staff) rest.appendChild(make(doc, "staff", staff));
    if (anchor) m.el.insertBefore(rest, anchor); else m.el.appendChild(rest);
    anchor = rest.nextSibling;
    writeDuration(c, rest, piece.type, piece.dots);
    if (!firstKey) firstKey = walk(partEl)[index].events.find((e) => e.el === rest)!.key;
  }
  return firstKey;
}

/** Split the measure before the selected event; the rest of it becomes a new measure. */
export function splitMeasure(doc: XMLDocument, key: EventKey): EventKey {
  const c = ctx(doc, key);
  if (hasVoices(c.m.el)) throw new EditError("a measure with several voices cannot be split here");
  const head = chordGroup(c.m.events, c.ev)[0];
  if (head.key.onset < 1e-9) throw new EditError("select the first note of the new measure, not the first of this one");
  const fresh = make(doc, "measure");
  let start: Element = head.el;
  const prev = start.previousElementSibling;
  if (prev && prev.tagName === "harmony") start = prev; // the chord symbol on the split beat goes with it
  let node: Element | null = start;
  while (node) { const next: Element | null = node.nextElementSibling; fresh.appendChild(node); node = next; }
  const right = children(c.m.el, "barline").find((b) => b.getAttribute("location") === "right");
  if (right) fresh.appendChild(right);
  c.m.el.parentElement!.insertBefore(fresh, c.m.el.nextSibling);
  renumber(c.partEl);
  return { ...key, measure: key.measure + 1, onset: 0 };
}

export function mergeWithNext(doc: XMLDocument, index: number): void {
  const { partEl, measures, m } = measureCtx(doc, index);
  const next = measures[index + 1];
  if (!next) throw new EditError("this is the last measure");
  if (hasVoices(m.el) || hasVoices(next.el)) throw new EditError("measures with several voices cannot be merged here");
  for (const b of children(m.el, "barline")) if (b.getAttribute("location") === "right") m.el.removeChild(b);
  for (const el of Array.from(next.el.children)) {
    if (el.tagName === "barline" && el.getAttribute("location") === "left") continue;
    if (el.tagName === "attributes") { removeChildren(el, "divisions"); if (el.children.length === 0) continue; }
    m.el.appendChild(el);
  }
  next.el.parentElement!.removeChild(next.el);
  renumber(partEl);
}

export function insertMeasure(doc: XMLDocument, index: number, where: "before" | "after"): number {
  const { partEl, measures, m } = measureCtx(doc, index);
  const fresh = make(doc, "measure");
  const staves = Math.max(1, ...measures.flatMap((x) => x.events.map((e) => e.key.staff)));
  const expected = ((m.beats * 4) / m.beatType) * m.divisions;
  for (let s = 1; s <= staves; s++) {
    if (s > 1) { const b = make(doc, "backup"); b.appendChild(make(doc, "duration", String(expected))); fresh.appendChild(b); }
    const rest = make(doc, "note");
    rest.appendChild(make(doc, "rest", undefined, { measure: "yes" }));
    rest.appendChild(make(doc, "duration", String(expected)));
    rest.appendChild(make(doc, "voice", s === 1 ? "1" : "5"));
    if (staves > 1) rest.appendChild(make(doc, "staff", String(s)));
    fresh.appendChild(rest);
  }
  if (where === "before" && index === 0) {
    // the first measure carries the attributes: they move to the new first measure
    for (const attrs of children(m.el, "attributes")) fresh.insertBefore(attrs, fresh.firstChild);
    m.el.removeAttribute("implicit");
  }
  m.el.parentElement!.insertBefore(fresh, where === "before" ? m.el : m.el.nextSibling);
  renumber(partEl);
  return where === "before" ? index : index + 1;
}

export function deleteMeasure(doc: XMLDocument, index: number): number {
  const { partEl, measures, m } = measureCtx(doc, index);
  if (measures.length < 2) throw new EditError("the score needs at least one measure");
  const next = measures[index + 1];
  if (next) {
    const attrs = children(m.el, "attributes");
    for (const a of attrs.reverse()) next.el.insertBefore(a, next.el.firstChild);
  }
  m.el.parentElement!.removeChild(m.el);
  renumber(partEl);
  return Math.min(index, measures.length - 2);
}

// ---- attributes from a measure onward ------------------------------------------------------------

function attributesOf(doc: XMLDocument, m: Element): Element {
  let attrs = child(m, "attributes");
  if (!attrs) { attrs = make(doc, "attributes"); m.insertBefore(attrs, m.firstChild); }
  return attrs;
}

function setFromMeasure(doc: XMLDocument, index: number, tag: string, build: () => Element, matches: (el: Element) => boolean): void {
  const { partEl, measures } = measureCtx(doc, index);
  const attrs = attributesOf(doc, measures[index].el);
  for (const old of children(attrs, tag)) if (matches(old)) attrs.removeChild(old);
  insertOrdered(attrs, build(), ATTRIBUTES_ORDER);
  for (const m of measures.slice(index + 1)) {
    for (const a of children(m.el, "attributes")) for (const old of children(a, tag)) if (matches(old)) a.removeChild(old);
  }
  void partEl;
}

export function setTime(doc: XMLDocument, index: number, beats: number, beatType: number): void {
  if (!(beats >= 1 && beats <= 32) || ![1, 2, 4, 8, 16].includes(beatType)) throw new EditError("that is not a time signature");
  setFromMeasure(doc, index, "time", () => {
    const t = make(doc, "time");
    t.appendChild(make(doc, "beats", String(beats)));
    t.appendChild(make(doc, "beat-type", String(beatType)));
    return t;
  }, () => true);
}

export function setKey(doc: XMLDocument, index: number, fifths: number): void {
  if (!(fifths >= -7 && fifths <= 7)) throw new EditError("a key has at most seven sharps or flats");
  setFromMeasure(doc, index, "key", () => {
    const k = make(doc, "key");
    k.appendChild(make(doc, "fifths", String(fifths)));
    return k;
  }, () => true);
}

export function setClef(doc: XMLDocument, index: number, staff: number, sign: "G" | "F" | "C"): void {
  const line = sign === "G" ? 2 : sign === "F" ? 4 : 3;
  const staves = Math.max(1, ...walk(part(doc)).flatMap((x) => x.events.map((e) => e.key.staff)));
  setFromMeasure(doc, index, "clef", () => {
    const c = make(doc, "clef", undefined, staves > 1 ? { number: String(staff) } : undefined);
    c.appendChild(make(doc, "sign", sign));
    c.appendChild(make(doc, "line", String(line)));
    return c;
  }, (el) => (Number(el.getAttribute("number") ?? "1") || 1) === staff);
}

// ---- chord symbols -------------------------------------------------------------------------------

/** The <harmony> written at the event's onset in its measure, if any. */
export function harmonyAt(m: MeasureInfo, onset: number): Element | null {
  let pos = 0, found: Element | null = null;
  for (const el of Array.from(m.el.children)) {
    if (el.tagName === "harmony") { if (Math.abs(pos / m.divisions / 4 - onset) < 1e-9) found = el; }
    else if (el.tagName === "note") { if (!child(el, "chord") && !child(el, "grace")) pos += Number(text(el, "duration", "0")) || 0; }
    else if (el.tagName === "backup") pos -= Number(text(el, "duration", "0")) || 0;
    else if (el.tagName === "forward") pos += Number(text(el, "duration", "0")) || 0;
  }
  return found;
}

export function chordAt(doc: XMLDocument, key: EventKey): string {
  const c = ctx(doc, key);
  const h = harmonyAt(c.m, key.onset);
  const spec = h ? readHarmony(h) : null;
  return spec ? chordText(spec) : "";
}

/** Write the chord symbol typed for the selected beat; an empty text removes it. */
export function setChord(doc: XMLDocument, key: EventKey, input: string): ChordSpec | null {
  const c = ctx(doc, key);
  const existing = harmonyAt(c.m, key.onset);
  if (!input.trim()) { if (existing) existing.parentElement!.removeChild(existing); return null; }
  const spec = parseChord(input);
  if (!spec) throw new EditError(`"${input.trim()}" is not a chord symbol this app knows (C, Am7, F#dim, Bb/D…)`);
  const fresh = harmonyElement(doc, spec);
  if (existing) existing.parentElement!.replaceChild(fresh, existing);
  else { const head = chordGroup(c.m.events, c.ev)[0].el; head.parentElement!.insertBefore(fresh, head); }
  return spec;
}
