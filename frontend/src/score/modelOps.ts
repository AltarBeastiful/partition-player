/**
 * Notes and chords of a model draft (ADR 0010, ticket 10): the operations the model answered with, replayed on a
 * clone of the score with the editor's own functions (`edit.ts`). The server validated them on the MusicXML
 * (`backend/partition_player/model/notes_pass.py`, a port of the same functions); this is the browser's second
 * check, on the document the sheet and the player show, so a draft that cannot hold here is not shown as if it did.
 *
 * Both sides write the old and new values of a change in the same words (`summariseMeasure`, `chordTextAt`), which
 * is also how a hand edit since the pass is found (a conflict).
 */
import type { ScoreChange, ScoreOp } from "../api";
import { filledQuarters } from "./check";
import { chordText, readHarmony } from "./chordText";
import { EditError, deleteEvent, harmonyAt, insertEvent, setAlter, setChord, setDuration, shiftOctave, stepPitch, toRest, toggleTie, type DurationType } from "./edit";
import { child, children, part, walk, type Event } from "./xml";

function noteName(el: Element): string {
  const p = child(el, "pitch");
  if (!p) return "?";
  const alter = Number(child(p, "alter")?.textContent ?? "0") || 0;
  return (child(p, "step")?.textContent ?? "C") + (alter > 0 ? "#".repeat(alter) : "b".repeat(-alter)) + (child(p, "octave")?.textContent ?? "4");
}

/** One note as the change lists show it: "Ab4 eighth.", "rest quarter", "+G4 half" (a chord tone), "grace E4 eighth"; "~" when tied on. */
export function describeNote(el: Element): string {
  const kind = child(el, "type")?.textContent?.trim() || "?";
  const dots = ".".repeat(children(el, "dot").length);
  const tied = children(el, "tie").some((t) => t.getAttribute("type") === "start") ? "~" : "";
  const head = child(el, "rest") ? "rest" : noteName(el);
  return (child(el, "grace") ? "grace " : child(el, "chord") ? "+" : "") + `${head} ${kind}${dots}${tied}`;
}

/** The notes of a measure in words, in the order of the <note> elements: what a notes change was and became. */
export function summariseMeasure(doc: XMLDocument, measure: number): string {
  const m = children(part(doc), "measure")[measure];
  return m ? children(m, "note").map(describeNote).join(", ") : "";
}

/** The chord symbol over the event, "" when there is none. */
export function chordTextAt(doc: XMLDocument, measure: number, event: number): string {
  const m = walk(part(doc))[measure];
  const ev = m?.events[event];
  const h = ev && harmonyAt(m, ev.key.onset);
  const spec = h ? readHarmony(h) : null;
  return spec ? chordText(spec) : "";
}

/** What the score holds now at the place a change names, in the words of its old/new values. */
export function currentText(doc: XMLDocument, c: ScoreChange): string {
  return c.kind === "chord" ? chordTextAt(doc, c.measure, c.event ?? 0) : summariseMeasure(doc, c.measure);
}

// ---- replay ---------------------------------------------------------------------------------------------

function run(doc: XMLDocument, origs: Element[][], op: ScoreOp): void {
  const el = origs[op.measure]?.[op.event];
  const measure = walk(part(doc))[op.measure];
  const ev: Event | undefined = el && measure?.events.find((e) => e.el === el);
  if (!ev) throw new EditError("the note is not there any more");
  const key = ev.key;
  const num = (name: string) => Number(op[name]);
  switch (op.op) {
    case "stepPitch": stepPitch(doc, key, num("delta")); break;
    case "setAlter": setAlter(doc, key, num("alter")); break;
    case "shiftOctave": shiftOctave(doc, key, num("delta")); break;
    case "setDuration": setDuration(doc, key, op.type as DurationType, num("dots")); break;
    case "toRest": toRest(doc, key); break;
    case "deleteEvent": deleteEvent(doc, key); break;
    case "toggleTie": toggleTie(doc, key); break;
    case "insertEvent": insertEvent(doc, key, op.where as "before" | "after", op.kind as "note" | "rest"); break;
    case "setChord": setChord(doc, key, String(op.text ?? "")); break;
    default: throw new EditError(`unknown operation ${String(op.op)}`);
  }
}

/** Every child of every measure with a copy of it, so a failed change can be taken back with the same element objects. */
function snapshot(partEl: Element): { m: Element; kids: [Element, Element][] }[] {
  return children(partEl, "measure").map((m) => ({ m, kids: Array.from(m.children).map((el): [Element, Element] => [el, el.cloneNode(true) as Element]) }));
}

function restore(snap: ReturnType<typeof snapshot>): void {
  for (const { m, kids } of snap) {
    while (m.firstChild) m.removeChild(m.firstChild);
    for (const [el, saved] of kids) {
      for (const a of Array.from(el.attributes)) el.removeAttribute(a.name);
      for (const a of Array.from(saved.attributes)) el.setAttribute(a.name, a.value);
      el.replaceChildren(...Array.from(saved.childNodes));
      m.appendChild(el);
    }
  }
}

const ser = (el: Element) => new XMLSerializer().serializeToString(el);

/** Per measure the clef, key, time and divisions: what a pass must never move. */
function fixed(doc: XMLDocument): string[] {
  return children(part(doc), "measure").map((m) =>
    children(m, "attributes").flatMap((a) => Array.from(a.children).filter((c) => ["clef", "key", "time", "divisions"].includes(c.tagName)).map(ser)).join(""));
}

function outside(doc: XMLDocument, from: number, to: number): string[] {
  return children(part(doc), "measure").filter((_, i) => i < from || i > to).map(ser);
}

function lengths(doc: XMLDocument): { filled: number; expected: number }[] {
  return walk(part(doc)).map((m) => ({ filled: filledQuarters(m.el, m.divisions), expected: (m.beats * 4) / m.beatType }));
}

/** The server's rule: a measure that added up still does, one that was wrong does not get worse. */
function holds(before: { filled: number; expected: number }[], after: { filled: number; expected: number }[]): boolean {
  if (before.length !== after.length) return false;
  return before.every((b, i) => {
    const was = Math.abs(b.filled - b.expected), now = Math.abs(after[i].filled - after[i].expected);
    return was < 1e-9 ? now < 1e-9 : now <= was + 1e-9;
  });
}

/**
 * Write the changes into the document, each one as a transaction: an operation that throws, a measure that stops
 * adding up, a hand outside the span, and the change is taken back whole. Returns the ids that held.
 */
export function applyScoreChanges(doc: XMLDocument, changes: ScoreChange[]): string[] {
  const partEl = part(doc);
  const origs = children(partEl, "measure").map((m) => children(m, "note"));   // the numbering of the score as read
  const applied: string[] = [];
  for (const c of changes) {
    const snap = snapshot(partEl);
    const before = lengths(doc), around = outside(doc, c.span.from, c.span.to), still = fixed(doc);
    try {
      for (const op of c.ops) {
        if (op.measure < c.span.from || op.measure > c.span.to) throw new EditError("outside the span");
        run(doc, origs, op);
      }
      const bad = !holds(before, lengths(doc)) || outside(doc, c.span.from, c.span.to).join() !== around.join() || fixed(doc).join() !== still.join();
      if (bad) throw new EditError("the change does not hold");
    } catch (e) {
      if (!(e instanceof EditError)) throw e;
      restore(snap);
      continue;
    }
    applied.push(c.id);
  }
  return applied;
}
