/** The editor's commands, shared by the toolbar and the keyboard (ADR 0005, decisions 4 and 5). */
import * as ops from "../score/edit";
import type { DurationType } from "../score/edit";
import type { EditorSession } from "./session";

export function commands(s: EditorSession) {
  const key = () => s.selected;
  const withKey = (fn: (k: NonNullable<typeof s.selected>) => void) => { const k = key(); if (k) fn(k); };
  const measure = () => s.selected?.measure ?? null;
  return {
    pitch: (delta: number) => withKey((k) => s.apply((d) => ops.stepPitch(d, k, delta))),
    octave: (delta: number) => withKey((k) => s.apply((d) => ops.shiftOctave(d, k, delta))),
    alter: (alter: number) => withKey((k) => s.apply((d) => ops.setAlter(d, k, alter))),
    duration: (type: DurationType) => withKey((k) => s.apply((d) => ops.setDuration(d, k, type, 0))),
    dot: () => withKey((k) => s.apply((d) => ops.toggleDot(d, k))),
    tie: () => withKey((k) => s.apply((d) => ops.toggleTie(d, k))),
    restToggle: () => withKey((k) => s.apply((d) => (k.midi === null ? ops.toNote(d, k) : ops.toRest(d, k)))),
    insert: (where: "before" | "after", kind: "note" | "rest") => withKey((k) => s.apply((d) => ops.insertEvent(d, k, where, kind))),
    remove: () => withKey((k) => s.apply((d) => ops.deleteEvent(d, k))),
    fill: () => { const m = measure(); if (m !== null) s.apply((d) => ops.fillMeasure(d, m)); },
    split: () => withKey((k) => s.apply((d) => ops.splitMeasure(d, k), (i) => (i > k.measure ? i + 1 : i))),
    merge: () => { const m = measure(); if (m !== null) s.apply((d) => { ops.mergeWithNext(d, m); }, (i) => (i === m + 1 ? m : i > m + 1 ? i - 1 : i)); },
    insertMeasure: (where: "before" | "after") => {
      const m = measure(); if (m === null) return;
      s.apply((d) => ops.insertMeasure(d, m, where), where === "before" ? (i) => (i >= m ? i + 1 : i) : (i) => (i > m ? i + 1 : i));
    },
    deleteMeasure: () => { const m = measure(); if (m !== null) s.apply((d) => ops.deleteMeasure(d, m), (i) => (i === m ? null : i > m ? i - 1 : i)); },
    time: (beats: number, beatType: number) => { const m = measure(); if (m !== null) s.apply((d) => { ops.setTime(d, m, beats, beatType); }); },
    key: (fifths: number) => { const m = measure(); if (m !== null) s.apply((d) => { ops.setKey(d, m, fifths); }); },
    clef: (staff: number, sign: "G" | "F" | "C") => { const m = measure(); if (m !== null) s.apply((d) => { ops.setClef(d, m, staff, sign); }); },
    repeat: (direction: "forward" | "backward") => { const m = measure(); if (m !== null) s.apply((d) => { ops.toggleRepeat(d, m, direction); }); },
    chord: (text: string) => withKey((k) => s.apply((d) => { ops.setChord(d, k, text); })),
    chordText: () => { const k = key(); try { return k ? ops.chordAt(s.doc, k) : ""; } catch { return ""; } },
    place: (direction: 1 | -1) => { const p = s.nextPlace(measure(), direction); if (p) s.selectMeasure(p.measure); },
    checked: () => { const m = measure(); if (m !== null) s.toggleChecked(m); },
    move: (direction: 1 | -1) => s.move(direction),
    undo: () => s.undo(),
    redo: () => s.redo(),
  };
}

export type Commands = ReturnType<typeof commands>;

const DURATION_KEYS: Record<string, DurationType> = { "1": "whole", "2": "half", "3": "quarter", "4": "eighth", "5": "16th", "6": "32nd" };

/** Keyboard shortcuts; returns true when the key was used. */
export function shortcut(e: KeyboardEvent, c: Commands, hasSelection: boolean): boolean {
  const mod = e.ctrlKey || e.metaKey;
  if (mod && e.key.toLowerCase() === "z") { if (e.shiftKey) c.redo(); else c.undo(); return true; }
  if (mod && e.key.toLowerCase() === "y") { c.redo(); return true; }
  if (mod) return false;
  if (e.key === "n") { c.place(1); return true; }
  if (e.key === "p") { c.place(-1); return true; }
  if (!hasSelection) return false;
  switch (e.key) {
    case "ArrowUp": if (e.shiftKey) c.octave(1); else c.pitch(1); return true;
    case "ArrowDown": if (e.shiftKey) c.octave(-1); else c.pitch(-1); return true;
    case "ArrowLeft": c.move(-1); return true;
    case "ArrowRight": c.move(1); return true;
    case "-": c.alter(-1); return true;
    case "=": case "+": c.alter(1); return true;
    case "0": c.alter(0); return true;
    case ".": c.dot(); return true;
    case "t": c.tie(); return true;
    case "r": c.restToggle(); return true;
    case "a": c.insert("after", "note"); return true;
    case "b": c.insert("before", "note"); return true;
    case "f": c.fill(); return true;
    case "c": c.checked(); return true;
    case "Delete": case "Backspace": c.remove(); return true;
  }
  if (e.key in DURATION_KEYS) { c.duration(DURATION_KEYS[e.key]); return true; }
  return false;
}
