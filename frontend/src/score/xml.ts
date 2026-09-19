/**
 * The score as a MusicXML DOM (ADR 0005, decision 3). Everything the editor does is a function on
 * this document; the sheet is re-rendered from its serialization. This module is the reading side:
 * parsing, the walk that gives every event its position, and the key that names an event across
 * re-renders (measure, staff, voice, onset, pitch), the same key OSMD's graphical notes can be
 * mapped to.
 */

export interface Pitch { step: string; alter: number; octave: number }

/** Names one event of the document. `onset` is in whole notes from the start of the measure. */
export interface EventKey { measure: number; staff: number; voice: number; onset: number; midi: number | null }

export interface Event {
  el: Element;
  key: EventKey;
  index: number;          // position among the measure's <note> elements
  isRest: boolean;
  isGrace: boolean;
  inChord: boolean;       // carries <chord/>: sounds with the previous event
  duration: number;       // divisions
  quarters: number;       // actual length in quarters (0 for a grace note)
  pitch: Pitch | null;
}

export interface MeasureInfo { index: number; el: Element; divisions: number; beats: number; beatType: number; fifths: number; events: Event[] }

export const STEPS = ["C", "D", "E", "F", "G", "A", "B"];
const SEMITONES: Record<string, number> = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };

export function parse(text: string): XMLDocument {
  const doc = new DOMParser().parseFromString(text, "application/xml");
  const err = doc.getElementsByTagName("parsererror")[0];
  if (err) throw new Error("not well-formed XML: " + (err.textContent ?? "").slice(0, 200));
  if (doc.documentElement.tagName !== "score-partwise") throw new Error("expected score-partwise, got " + doc.documentElement.tagName);
  return doc;
}

export function serialize(doc: XMLDocument): string {
  const body = new XMLSerializer().serializeToString(doc.documentElement);
  return '<?xml version="1.0" encoding="UTF-8"?>\n' + body;
}

export function part(doc: XMLDocument, index = 0): Element {
  const parts = children(doc.documentElement, "part");
  if (parts.length === 0) throw new Error("no <part> in the document");
  return parts[Math.min(index, parts.length - 1)];
}

export function children(el: Element, tag: string): Element[] {
  return Array.from(el.children).filter((c) => c.tagName === tag);
}

export function child(el: Element, tag: string): Element | null {
  return children(el, tag)[0] ?? null;
}

export function text(el: Element | null, tag: string, fallback = ""): string {
  const c = el ? child(el, tag) : null;
  return (c?.textContent ?? fallback).trim();
}

export function midiOf(p: Pitch): number {
  return (p.octave + 1) * 12 + SEMITONES[p.step] + p.alter;
}

export function pitchOf(note: Element): Pitch | null {
  const p = child(note, "pitch");
  if (!p) return null;
  return { step: text(p, "step", "C"), alter: Number(text(p, "alter", "0")) || 0, octave: Number(text(p, "octave", "4")) };
}

/** Every measure of the part with the attributes in force and its events in stream order. */
export function walk(partEl: Element): MeasureInfo[] {
  let divisions = 1, beats = 4, beatType = 4, fifths = 0;
  const out: MeasureInfo[] = [];
  children(partEl, "measure").forEach((m, index) => {
    for (const attrs of children(m, "attributes")) {
      const d = text(attrs, "divisions"); if (d) divisions = Number(d) || divisions;
      const t = child(attrs, "time");
      if (t) { beats = Number(text(t, "beats", "4")); beatType = Number(text(t, "beat-type", "4")); }
      const k = child(attrs, "key");
      if (k) fifths = Number(text(k, "fifths", "0")) || 0;
    }
    out.push({ index, el: m, divisions, beats, beatType, fifths, events: events(m, index, divisions) });
  });
  return out;
}

/** The events of one measure with their onsets, following <backup> and <forward>. */
export function events(m: Element, measureIndex: number, divisions: number): Event[] {
  let pos = 0;         // divisions
  let lastOnset = 0;   // onset of the last non-chord note, for the notes flagged <chord/>
  const out: Event[] = [];
  let noteIndex = 0;
  for (const el of Array.from(m.children)) {
    if (el.tagName === "backup") pos -= Number(text(el, "duration", "0"));
    else if (el.tagName === "forward") pos += Number(text(el, "duration", "0"));
    else if (el.tagName === "note") {
      const isGrace = child(el, "grace") !== null;
      const inChord = child(el, "chord") !== null;
      const duration = isGrace ? 0 : Number(text(el, "duration", "0")) || 0;
      const onset = inChord ? lastOnset : pos;
      const pitch = pitchOf(el);
      const isRest = child(el, "rest") !== null;
      out.push({
        el, index: noteIndex++, isRest, isGrace, inChord, duration, quarters: duration / divisions, pitch,
        key: { measure: measureIndex, staff: Number(text(el, "staff", "1")) || 1, voice: Number(text(el, "voice", "1")) || 1,
               onset: onset / divisions / 4, midi: pitch && !isRest ? midiOf(pitch) : null },
      });
      if (!inChord && !isGrace) { lastOnset = pos; pos += duration; }
      else if (!inChord) lastOnset = pos;
    }
  }
  return out;
}

export function sameKey(a: EventKey, b: EventKey): boolean {
  return a.measure === b.measure && a.staff === b.staff && a.voice === b.voice && Math.abs(a.onset - b.onset) < 1e-6 && a.midi === b.midi;
}

/** The event of the document a key names, or null when it is gone (after a delete, a re-load). */
export function find(measures: MeasureInfo[], key: EventKey): Event | null {
  const m = measures[key.measure];
  if (!m) return null;
  return m.events.find((e) => sameKey(e.key, key)) ?? null;
}

/** The nearest event to a key in its measure: same voice and onset, else same onset, else the last. */
export function nearest(measures: MeasureInfo[], key: EventKey): Event | null {
  const m = measures[Math.min(key.measure, measures.length - 1)];
  if (!m || m.events.length === 0) return null;
  const exact = find(measures, key);
  if (exact) return exact;
  const voice = m.events.filter((e) => e.key.staff === key.staff && e.key.voice === key.voice && !e.inChord);
  const pool = voice.length ? voice : m.events.filter((e) => !e.inChord);
  let best = pool[0];
  for (const e of pool) if (Math.abs(e.key.onset - key.onset) < Math.abs(best.key.onset - key.onset)) best = e;
  return best ?? null;
}

/** MusicXML's order of a note's children, so an inserted child lands where a parser expects it. */
export const NOTE_ORDER = ["grace", "cue", "chord", "pitch", "unpitched", "rest", "duration", "tie", "instrument", "footnote", "level",
  "voice", "type", "dot", "accidental", "time-modification", "stem", "notehead", "notehead-text", "staff", "beam", "notations", "lyric", "play", "listen"];

export function insertOrdered(parent: Element, el: Element, order: string[] = NOTE_ORDER): void {
  const rank = order.indexOf(el.tagName);
  for (const c of Array.from(parent.children)) {
    const r = order.indexOf(c.tagName);
    if (r > rank) { parent.insertBefore(el, c); return; }
  }
  parent.appendChild(el);
}

export function make(doc: XMLDocument, tag: string, textContent?: string, attrs?: Record<string, string>): Element {
  const el = doc.createElementNS(null, tag);
  if (textContent !== undefined) el.textContent = textContent;
  if (attrs) for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  return el;
}

/** Set (or create) a single child element with the given text. */
export function setChild(doc: XMLDocument, parent: Element, tag: string, value: string, order: string[] = NOTE_ORDER): Element {
  let c = child(parent, tag);
  if (!c) { c = make(doc, tag); insertOrdered(parent, c, order); }
  c.textContent = value;
  return c;
}

export function removeChildren(parent: Element, tag: string): void {
  for (const c of children(parent, tag)) parent.removeChild(c);
}
