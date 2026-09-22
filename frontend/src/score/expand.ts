/**
 * The score as it is played (plan 0009): the form written out, one measure element per slice of the
 * timeline, so the file that leaves the app is sung in the order the app sings it — verse 1, chorus,
 * chorus, verse 2… — with the words of each verse under its own notes and no repeat sign left to obey.
 *
 * Nothing here invents arithmetic. The slices come from `sliceRanges` (`form.ts`), the very function
 * the player lays its sound on, so the page and the sound leave and enter a measure on the same beat
 * (decision 2). What this module adds is the notation of a slice: a measure entered or left on a beat
 * of its own is written as a short measure, `implicit="yes"`, holding exactly what is played in it
 * (decision 3); a note the section cuts is renotated, tied where one value will not write it; the
 * chord in force is re-emitted where a pass begins under it; the words of the pass are picked by the
 * rule the dimming layer uses and renumbered to the one row that prints (decision 4); repeats and
 * endings come off, since the order is now written out, and each pass opens a system with its name
 * on it (decision 5); the attributes in force are re-emitted only where they change (decision 6).
 *
 * A measure's length here is what it holds — `filledQuarters`, the length `previewNotes` reads back —
 * not what its time signature asks for. The player measures a measure with OSMD instead, and the two
 * differ only on a measure that does not add up, where what the page holds is the thing to write.
 */
import { inForce, type InForce } from "./alternatives";
import { filledQuarters } from "./check";
import { nominalQuarters, renumber, splitQuarters, typeFor, type DurationType } from "./edit";
import { child, children, insertOrdered, make, parse, part, removeChildren, serialize, setChild, text } from "./xml";
import { sliceRanges, type Pass, type Slice } from "../form";

const EPS = 1e-9;
const FINAL_STYLES = ["light-heavy", "heavy-light", "heavy-heavy"];
const ATTRIBUTES_ORDER = ["footnote", "level", "divisions", "key", "time", "staves", "part-symbol", "instruments", "clef",
  "staff-details", "transpose", "directive", "measure-style"];

export interface Expansion {
  xml: string;
  measures: number;   // measure elements written
  partial: number;    // of which entered or left on a beat of their own
  passes: number;
}

/** The divisions per quarter in force at each measure of the part. */
function divisionsByMeasure(partEl: Element): number[] {
  let divisions = 1;
  return children(partEl, "measure").map((m) => {
    for (const attrs of children(m, "attributes")) {
      const d = text(attrs, "divisions");
      if (d) divisions = Number(d) || divisions;
    }
    return divisions;
  });
}

/** The length of every measure of the part in whole notes, as what it holds (not as its time asks). */
export function measureDurations(partEl: Element): number[] {
  const divisions = divisionsByMeasure(partEl);
  return children(partEl, "measure").map((m, i) => filledQuarters(m, divisions[i]) / 4);
}

/**
 * The slices a pass list makes of this document, in playing order. Cheap — no note is touched — so
 * the page can say how long the expansion is before anyone asks for it (decision 8).
 */
export function slicesOf(doc: XMLDocument, passes: Pass[]): Slice[] {
  const partEl = part(doc);
  const durations = measureDurations(partEl);
  return sliceRanges(passes, durations, durations.length);
}

// ---- reading one source measure ------------------------------------------------------------------

/** One element of a measure's stream with its onset in divisions; a chord is gathered on its head. */
interface Item { el: Element; group: Element[]; onset: number; duration: number; grace: boolean; kind: string }

function items(m: Element): Item[] {
  const out: Item[] = [];
  let pos = 0;
  let head: Item | null = null;
  for (const el of Array.from(m.children)) {
    const dur = Number(text(el, "duration", "0")) || 0;
    if (el.tagName === "backup") { pos -= dur; head = null; continue; }
    if (el.tagName === "forward") { pos += dur; head = null; continue; }
    if (el.tagName !== "note") { out.push({ el, group: [el], onset: pos, duration: 0, grace: false, kind: el.tagName }); continue; }
    const grace = child(el, "grace") !== null;
    const inChord = child(el, "chord") !== null;
    if (inChord) { if (head) head.group.push(el); continue; } // sounds with the note before it, and takes its fate
    const item: Item = { el, group: [el], onset: pos, duration: grace ? 0 : dur, grace, kind: "note" };
    out.push(item);
    head = item;
    if (!grace) pos += item.duration;
  }
  return out;
}

// ---- writing one slice ---------------------------------------------------------------------------

function setValue(out: XMLDocument, note: Element, durDiv: number, value: { type: DurationType; dots: number } | null): void {
  setChild(out, note, "duration", String(Math.round(durDiv)));
  removeChildren(note, "dot");
  if (value) {
    setChild(out, note, "type", value.type);
    for (let i = 0; i < value.dots; i++) insertOrdered(note, make(out, "dot"));
  } else removeChildren(note, "type");
}

function dropTie(note: Element, type: "start" | "stop"): void {
  for (const t of children(note, "tie")) if (t.getAttribute("type") === type) note.removeChild(t);
  const n = child(note, "notations");
  if (!n) return;
  for (const t of children(n, "tied")) if (t.getAttribute("type") === type) n.removeChild(t);
}

function addTie(out: XMLDocument, note: Element, type: "start" | "stop"): void {
  if (child(note, "rest")) return;
  dropTie(note, type);
  insertOrdered(note, make(out, "tie", undefined, { type }));
  let n = child(note, "notations");
  if (!n) { n = make(out, "notations"); insertOrdered(note, n); }
  n.appendChild(make(out, "tied", undefined, { type }));
}

/** The words of the pass: verse `n` where the note stacks several, renumbered to the row that prints. */
function keepVerse(note: Element, verse: number | null): void {
  const all = children(note, "lyric");
  if (all.length === 0) return;
  const numberOf = (l: Element) => parseInt(l.getAttribute("number") ?? "1", 10);
  if (verse !== null && all.length > 1) {
    const mine = all.filter((l) => numberOf(l) === verse);
    if (mine.length > 0) for (const l of all) if (!mine.includes(l)) note.removeChild(l);
  }
  const left = children(note, "lyric");
  if (left.length === 1) { left[0].setAttribute("number", "1"); left[0].removeAttribute("name"); }
}

/** A note whose written value changed: its beam, its tuplet and its slur no longer describe it. */
function renotated(note: Element): void {
  removeChildren(note, "beam");
  removeChildren(note, "time-modification");
  const n = child(note, "notations");
  if (!n) return;
  for (const c of Array.from(n.children)) if (c.tagName === "tuplet" || c.tagName === "slur") n.removeChild(c);
}

/** A length in divisions as one note value, or as tied values; by its duration alone when neither writes it. */
function valuesFor(lengthDiv: number, divisions: number): { div: number; value: { type: DurationType; dots: number } | null }[] {
  const quarters = lengthDiv / divisions;
  const one = typeFor(quarters);
  if (one) return [{ div: lengthDiv, value: one }];
  const pieces = splitQuarters(quarters);
  const total = pieces.reduce((s, p) => s + nominalQuarters(p.type, p.dots), 0);
  if (pieces.length > 0 && Math.abs(total - quarters) < 1e-9) {
    return pieces.map((p) => ({ div: nominalQuarters(p.type, p.dots) * divisions, value: p }));
  }
  return [{ div: lengthDiv, value: null }];  // written by its duration alone, as the pipeline's padding rests are
}

/**
 * One slice of one source measure, as a measure element of the expanded score. Positions are in the
 * measure's own divisions; `cut` is whether the section is left at `toDiv`, the only case where a note
 * ringing past the edge is shortened rather than left to ring.
 *
 * `<backup>` and `<forward>` are not copied but written again from the onsets, since dropping the
 * notes before an upbeat moves every voice after them.
 */
function writeSlice(out: XMLDocument, src: Element, divisions: number, fromDiv: number, toDiv: number, cut: boolean, verse: number | null): Element {
  const m = make(out, "measure");
  const limit = cut ? toDiv : Infinity;
  const partial = fromDiv > EPS || cut;
  let outPos = 0;
  const place = (onset: number) => {
    const want = Math.max(0, onset - fromDiv);
    if (Math.abs(want - outPos) < EPS) return;
    const el = make(out, want > outPos ? "forward" : "backup");
    el.appendChild(make(out, "duration", String(Math.round(Math.abs(want - outPos)))));
    m.appendChild(el);
    outPos = want;
  };
  for (const it of items(src)) {
    if (it.kind !== "note") {
      if (it.kind === "print") continue;                                   // the printed page's layout is not this one's
      if (it.kind === "barline") {
        // The order is written out, so repeats and endings come off; and the double bar that closed
        // the printed page would otherwise close the page fifteen times over, so it is left to the
        // end of the expansion (the caller puts it back on the last measure).
        if (child(it.el, "repeat") || child(it.el, "ending")) continue;
        if (FINAL_STYLES.includes(text(it.el, "bar-style"))) continue;
        m.appendChild(out.importNode(it.el, true) as Element);
        continue;
      }
      if (it.kind === "attributes" && it.onset <= fromDiv + EPS) continue; // the head ones are the caller's business
      if (it.onset < fromDiv - EPS || it.onset >= toDiv - EPS) continue;
      m.appendChild(out.importNode(it.el, true) as Element);
      continue;
    }
    if (it.grace) {
      if (it.onset < fromDiv - EPS || it.onset >= toDiv - EPS) continue;
      for (const el of it.group) m.appendChild(out.importNode(el, true) as Element);
      continue;
    }
    const end = it.onset + it.duration;
    if (end <= fromDiv + EPS || it.onset >= toDiv - EPS) continue;
    const start = Math.max(it.onset, fromDiv);
    const stop = Math.min(end, limit);
    if (stop - start <= EPS) continue;
    const reattacked = start > it.onset + EPS;   // begun before the slice and still sounding into it
    const clipped = stop < end - EPS;
    const whole = !reattacked && !clipped;
    place(start);
    const pieces = whole ? [{ div: it.duration, value: null }] : valuesFor(stop - start, divisions);
    pieces.forEach((piece, i) => {
      for (const srcNote of it.group) {
        const note = out.importNode(srcNote, true) as Element;
        if (!whole) { setValue(out, note, piece.div, piece.value); renotated(note); }
        if (i > 0 || reattacked) removeChildren(note, "lyric"); // a continuation carries no new syllable
        keepVerse(note, verse);
        if (reattacked) dropTie(note, "stop");
        if (clipped && i === pieces.length - 1) dropTie(note, "start");
        if (i > 0) addTie(out, note, "stop");
        if (i < pieces.length - 1) addTie(out, note, "start");
        if (partial) removeChildren(note, "beam"); // a beam of a measure cut in two has lost its other half
        m.appendChild(note);
      }
      outPos += piece.div;
    });
  }
  return m;
}

// ---- the attributes, re-emitted only where they change --------------------------------------------

interface State { divisions: string; key: string; time: string; staves: string; clefs: Map<string, string> }

function sig(el: Element | null): string {
  return el ? new XMLSerializer().serializeToString(el) : "";
}

/** The attributes in force that differ from what the measure before wrote, as one `<attributes>`. */
function changedAttributes(out: XMLDocument, f: InForce, state: State): Element | null {
  const add: Element[] = [];
  for (const k of ["divisions", "key", "time", "staves"] as const) {
    const el = f[k];
    const s = sig(el);
    if (el && s !== state[k]) { add.push(el); state[k] = s; }
  }
  for (const [number, clef] of f.clefs) {
    const s = sig(clef);
    if (state.clefs.get(number) !== s) { add.push(clef); state.clefs.set(number, s); }
  }
  if (add.length === 0) return null;
  const attrs = make(out, "attributes");
  for (const el of add) insertOrdered(attrs, out.importNode(el, true) as Element, ATTRIBUTES_ORDER);
  return attrs;
}

/** The chord sounding at a beat: the last `<harmony>` written at or before it, measures back if need be. */
function harmonyInForce(partEl: Element, measure: number, onset: number): Element | null {
  const measures = children(partEl, "measure");
  for (let i = measure; i >= 0; i--) {
    let pos = 0, found: Element | null = null;
    for (const el of Array.from(measures[i].children)) {
      if (el.tagName === "harmony") { if (i < measure || pos <= onset + EPS) found = el; }
      else if (el.tagName === "note") { if (!child(el, "chord") && !child(el, "grace")) pos += Number(text(el, "duration", "0")) || 0; }
      else if (el.tagName === "backup") pos -= Number(text(el, "duration", "0")) || 0;
      else if (el.tagName === "forward") pos += Number(text(el, "duration", "0")) || 0;
    }
    if (found) return found;
  }
  return null;
}

// ---- ties across a join the expansion broke --------------------------------------------------------

/** The notes at the very start of a written measure: the first one and whatever sounds with it. */
function headNotes(m: Element): Element[] {
  const notes = children(m, "note");
  const out: Element[] = [];
  for (const n of notes) {
    if (out.length > 0 && !child(n, "chord")) break;
    out.push(n);
  }
  return out;
}

/** The notes at its very end. */
function tailNotes(m: Element): Element[] {
  const notes = children(m, "note");
  const out: Element[] = [];
  for (let i = notes.length - 1; i >= 0; i--) {
    out.unshift(notes[i]);
    if (!child(notes[i], "chord")) break;
  }
  return out;
}

/**
 * A slur whose other end is not in this part any more: dropped, both ends. Every pass edge can cut
 * one in two — the phrase ran on in the printed page and stops here — and a half slur is a warning in
 * every reader that checks (music21 and verovio both say so). Matched per staff and slur number, in
 * document order, which is how a reader matches them.
 */
function pruneSlurs(partEl: Element): void {
  const open = new Map<string, Element>();
  const drop = (el: Element | undefined) => { if (el) el.parentElement?.removeChild(el); };
  for (const note of Array.from(partEl.getElementsByTagName("note"))) {
    const notations = child(note, "notations");
    if (!notations) continue;
    const staff = text(note, "staff", "1");
    for (const slur of children(notations, "slur")) {
      const id = `${staff}/${slur.getAttribute("number") ?? "1"}`;
      const started = open.get(id);
      if (slur.getAttribute("type") === "start") {
        if (started) drop(started);      // its stop never came
        open.set(id, slur);
      } else {
        if (!started || started.parentElement === notations) { drop(started); drop(slur); } // none, or both on one note
        open.delete(id);
      }
    }
  }
  for (const slur of open.values()) drop(slur);
}

// ---- the expansion ---------------------------------------------------------------------------------

/**
 * The document written out in the order `passes` plays it. `names` is one heading per pass (`passNames`
 * of `form.ts`); without them the passes are written out unlabelled.
 *
 * The result is a whole document — title, part list, the parts' own identities — with every part's
 * measures replaced by the slices. A multi-part score is sliced identically in every part, so the parts
 * stay in step.
 */
export function expandScore(doc: XMLDocument, passes: Pass[], names: string[] = []): Expansion {
  const out = parse(serialize(doc));
  const srcParts = children(doc.documentElement, "part");
  const outParts = children(out.documentElement, "part");
  const durations = measureDurations(part(doc));
  const slices = sliceRanges(passes, durations, durations.length);
  let partial = 0;
  outParts.forEach((outPart, pi) => {
    const srcPart = srcParts[Math.min(pi, srcParts.length - 1)];
    const srcMeasures = children(srcPart, "measure");
    const divisions = divisionsByMeasure(srcPart);
    for (const m of children(outPart, "measure")) outPart.removeChild(m);
    const state: State = { divisions: "", key: "", time: "", staves: "", clefs: new Map() };
    const written: Element[] = [];
    slices.forEach((s, i) => {
      const src = srcMeasures[s.measure];
      if (!src) return;
      const per = divisions[s.measure];
      const fromDiv = Math.round(s.from * 4 * per);
      const toDiv = Math.round(s.to * 4 * per);
      const fullDiv = Math.round(durations[s.measure] * 4 * per);
      const verse = passes[s.pass]?.verse ?? null;
      const m = writeSlice(out, src, per, fromDiv, toDiv, s.cut, verse);
      // A measure entered or left on a beat of its own is not a bar of its own; and a pickup copied
      // whole is still a pickup, so a source measure the file marks stays marked (plan 0010: it is
      // what tells the live check an upbeat from an error).
      const isPartial = fromDiv > 0 || toDiv < fullDiv - EPS;
      m.setAttribute("implicit", isPartial || src.getAttribute("implicit") === "yes" ? "yes" : "no");
      if (isPartial && pi === 0) partial++;
      // the head: a new system and the pass's name, the attributes that changed, the chord in force
      const head: Element[] = [];
      const opensPass = i === 0 || slices[i - 1].pass !== s.pass;
      if (opensPass && i > 0) head.push(make(out, "print", undefined, { "new-system": "yes" }));
      const attrs = changedAttributes(out, inForce(srcPart, s.measure), state);
      if (attrs) head.push(attrs);
      const name = opensPass ? names[s.pass] : undefined;
      if (name) {
        const direction = make(out, "direction", undefined, { placement: "above" });
        const type = make(out, "direction-type");
        type.appendChild(make(out, "rehearsal", name));
        direction.appendChild(type);
        head.push(direction);
      }
      // A slice that starts under a chord nobody has written here yet says it again: the player goes
      // on sounding the chord over the edge, and the page has to say what is being played (decision 2).
      const startsUnder = (opensPass || fromDiv > 0)
        && !items(src).some((it) => it.kind === "harmony" && Math.abs(it.onset - fromDiv) < EPS);
      if (startsUnder) {
        const harmony = harmonyInForce(srcPart, s.measure, fromDiv);
        if (harmony) head.push(out.importNode(harmony, true) as Element);
      }
      for (const el of head.reverse()) m.insertBefore(el, m.firstChild);
      // ties that pointed at a measure no longer next door
      const prev = slices[i - 1];
      const joined = prev !== undefined && prev.measure === s.measure - 1 && !prev.cut && s.from <= EPS;
      if (!joined) {
        for (const n of headNotes(m)) dropTie(n, "stop");
        const before = written[written.length - 1];
        if (before) for (const n of tailNotes(before)) dropTie(n, "start");
      }
      written.push(m);
      outPart.appendChild(m);
    });
    const last = written[written.length - 1];
    if (last) {
      for (const n of tailNotes(last)) dropTie(n, "start");
      const bar = make(out, "barline", undefined, { location: "right" });
      bar.appendChild(make(out, "bar-style", "light-heavy"));
      last.appendChild(bar);
    }
    pruneSlurs(outPart);
    renumber(outPart);
  });
  return { xml: serialize(out), measures: slices.length, partial, passes: new Set(slices.map((s) => s.pass)).size };
}
