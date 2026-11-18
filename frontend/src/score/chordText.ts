/**
 * Chord symbol text to and from MusicXML <harmony>, with the grammar of ADR 0003 (root, accidental,
 * quality, extension, optional slash bass) so what the user types is what the pipeline would have
 * read, and what the pipeline wrote reads back as the same text.
 */
import { child, children, make, text } from "./xml";

export interface Degree { value: number; alter: number; type: string }
export interface ChordSpec { root: string; rootAlter: number; kind: string; bass: string | null; bassAlter: number; degrees: Degree[] }

type KindEntry = [string, Degree[]];
const KINDS: Record<string, KindEntry> = {
  "": ["major", []], maj: ["major", []], Maj: ["major", []], M: ["major", []],
  m: ["minor", []], min: ["minor", []], Min: ["minor", []], "-": ["minor", []],
  "7": ["dominant", []], maj7: ["major-seventh", []], Maj7: ["major-seventh", []], M7: ["major-seventh", []],
  m7: ["minor-seventh", []], min7: ["minor-seventh", []], Min7: ["minor-seventh", []], "-7": ["minor-seventh", []],
  dim: ["diminished", []], dim7: ["diminished-seventh", []],
  aug: ["augmented", []], "+": ["augmented", []], aug7: ["augmented-seventh", []], "+7": ["augmented-seventh", []],
  "6": ["major-sixth", []], m6: ["minor-sixth", []], min6: ["minor-sixth", []],
  "9": ["dominant-ninth", []], maj9: ["major-ninth", []], Maj9: ["major-ninth", []], M9: ["major-ninth", []],
  m9: ["minor-ninth", []], "11": ["dominant-11th", []], "13": ["dominant-13th", []],
  sus4: ["suspended-fourth", []], sus2: ["suspended-second", []],
  "7sus4": ["suspended-fourth", [{ value: 7, alter: -1, type: "add" }]], sus47: ["suspended-fourth", [{ value: 7, alter: -1, type: "add" }]],
  "7sus2": ["suspended-second", [{ value: 7, alter: -1, type: "add" }]], "5": ["power", []],
  "69": ["major-sixth", [{ value: 9, alter: 0, type: "add" }]], add9: ["major", [{ value: 9, alter: 0, type: "add" }]],
  madd9: ["minor", [{ value: 9, alter: 0, type: "add" }]],
  "7b5": ["dominant", [{ value: 5, alter: -1, type: "alter" }]], "7#5": ["dominant", [{ value: 5, alter: 1, type: "alter" }]],
  m7b5: ["half-diminished", []], "7b9": ["dominant", [{ value: 9, alter: -1, type: "add" }]], "7#9": ["dominant", [{ value: 9, alter: 1, type: "add" }]],
};

/** The text written for a kind, the first spelling of the table. */
const SUFFIX: Record<string, string> = {};
for (const [suffix, [kind, degrees]] of Object.entries(KINDS)) {
  const k = kind + degreeKey(degrees);
  if (!(k in SUFFIX)) SUFFIX[k] = suffix;
}

function degreeKey(degrees: Degree[]): string {
  return degrees.map((d) => `|${d.value}${d.alter}${d.type}`).join("");
}

const ROOT = /^([A-G])(#|b)?(.*)$/;

/** Parse "F#m7/A", "Bb", "Csus4"; null when the text is not a chord of the grammar. */
export function parseChord(input: string): ChordSpec | null {
  const s = input.trim().replace(/♭/g, "b").replace(/♯/g, "#");
  if (!s) return null;
  const [main, slash, ...rest] = s.split("/");
  if (rest.length) return null;
  const m = ROOT.exec(main);
  if (!m) return null;
  const entry = KINDS[m[3]];
  if (!entry) return null;
  let bass: string | null = null, bassAlter = 0;
  if (slash !== undefined) {
    const b = /^([A-G])(#|b)?$/.exec(slash.trim());
    if (!b) return null;
    bass = b[1]; bassAlter = b[2] === "#" ? 1 : b[2] === "b" ? -1 : 0;
  }
  return { root: m[1], rootAlter: m[2] === "#" ? 1 : m[2] === "b" ? -1 : 0, kind: entry[0], bass, bassAlter, degrees: entry[1] };
}

function acc(alter: number): string {
  return alter > 0 ? "#".repeat(alter) : alter < 0 ? "b".repeat(-alter) : "";
}

export function chordText(c: ChordSpec): string {
  const suffix = SUFFIX[c.kind + degreeKey(c.degrees)] ?? SUFFIX[c.kind] ?? "";
  return c.root + acc(c.rootAlter) + suffix + (c.bass ? "/" + c.bass + acc(c.bassAlter) : "");
}

export function readHarmony(h: Element): ChordSpec | null {
  const root = child(h, "root");
  if (!root) return null;
  const bass = child(h, "bass");
  const degrees = children(h, "degree").map((d) => ({
    value: Number(text(d, "degree-value", "0")), alter: Number(text(d, "degree-alter", "0")) || 0, type: text(d, "degree-type", "add"),
  }));
  return {
    root: text(root, "root-step", "C"), rootAlter: Number(text(root, "root-alter", "0")) || 0, kind: text(h, "kind", "major") || "major",
    bass: bass ? text(bass, "bass-step", "C") : null, bassAlter: bass ? Number(text(bass, "bass-alter", "0")) || 0 : 0, degrees,
  };
}

export function harmonyElement(doc: XMLDocument, c: ChordSpec): Element {
  const h = make(doc, "harmony");
  const root = make(doc, "root");
  root.appendChild(make(doc, "root-step", c.root));
  if (c.rootAlter) root.appendChild(make(doc, "root-alter", String(c.rootAlter)));
  h.appendChild(root);
  h.appendChild(make(doc, "kind", c.kind));
  if (c.bass) {
    const b = make(doc, "bass");
    b.appendChild(make(doc, "bass-step", c.bass));
    if (c.bassAlter) b.appendChild(make(doc, "bass-alter", String(c.bassAlter)));
    h.appendChild(b);
  }
  for (const d of c.degrees) {
    const el = make(doc, "degree");
    el.appendChild(make(doc, "degree-value", String(d.value)));
    el.appendChild(make(doc, "degree-alter", String(d.alter)));
    el.appendChild(make(doc, "degree-type", d.type));
    h.appendChild(el);
  }
  return h;
}
