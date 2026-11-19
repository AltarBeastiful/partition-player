/**
 * A model draft as the sheet shows it (plan 0016, step 6). The corrected score is the read score
 * with the ticked changes written into the lyrics, change by change; no note is touched. The server
 * writes the same thing on Apply (`apply_changes` in the backend), this is its preview, so the
 * sheet, the player and the download after Apply agree.
 *
 * A change names a note by measure and onset rank: the rank among the measure's sounding notes
 * (rests, grace notes and chord tones do not count), the convention of lyrics.json.
 */
import { isScoreChange, type AnyChange, type ModelChange, type ScoreChange, type Syllable } from "../api";
import { applyScoreChanges } from "./modelOps";
import { child, children, insertOrdered, make, parse, part, serialize, type EventKey, type MeasureInfo } from "./xml";

const ELISION = "‿";

function soundingNotes(measure: Element): Element[] {
  return children(measure, "note").filter((n) => !child(n, "rest") && !child(n, "grace") && !child(n, "chord"));
}

function noteAt(doc: XMLDocument, staff: number, measure: number, onset: number): Element | null {
  const m = children(part(doc, staff), "measure")[measure];
  return m ? soundingNotes(m)[onset] ?? null : null;
}

function lyricElement(doc: XMLDocument, verse: number, s: Syllable): Element {
  const el = make(doc, "lyric", undefined, { number: String(verse) });
  const pieces = s.text.split(ELISION);
  pieces.forEach((piece, k) => {
    if (k > 0) el.appendChild(make(doc, "elision", ELISION));
    el.appendChild(make(doc, "syllabic", k === pieces.length - 1 ? s.syllabic : "single"));
    el.appendChild(make(doc, "text", piece));
  });
  return el;
}

/** The syllable of `verse` under a note, as the backend reads it back; null when there is none. */
export function lyricAt(doc: XMLDocument, staff: number, measure: number, onset: number, verse: number): Syllable | null {
  const note = noteAt(doc, staff, measure, onset);
  const lyric = note && children(note, "lyric").find((l) => Number(l.getAttribute("number") || 1) === verse);
  if (!lyric) return null;
  const texts = children(lyric, "text").map((t) => t.textContent ?? "");
  if (texts.length === 0) return null;
  const syl = children(lyric, "syllabic").map((s) => s.textContent ?? "single");
  return { text: texts.join(ELISION), syllabic: (syl[syl.length - 1] ?? "single") as Syllable["syllabic"] };
}

/** Write `syllable` (or take the verse away, when null) under a note; false when the note is not there. */
export function setLyric(doc: XMLDocument, staff: number, measure: number, onset: number, verse: number, syllable: Syllable | null): boolean {
  const note = noteAt(doc, staff, measure, onset);
  if (!note) return false;
  for (const old of children(note, "lyric")) if (Number(old.getAttribute("number") || 1) === verse) note.removeChild(old);
  if (syllable) insertOrdered(note, lyricElement(doc, verse, syllable));
  return true;
}

/** The read score with the ticked changes written in. With none ticked, the text comes back as it was. */
export function correctedXml(xml: string, changes: AnyChange[], ticked: ReadonlySet<string>): string {
  const chosen = changes.filter((c) => ticked.has(c.id));
  if (chosen.length === 0) return xml;
  const doc = parse(xml);
  // the words first, then the notes and chords: the server does the same, and a note is named by where it was read
  for (const c of chosen) if (!isScoreChange(c)) setLyric(doc, c.span.staff, c.measure, c.onset, c.verse, c.new);
  applyScoreChanges(doc, chosen.filter(isScoreChange));
  return serialize(doc);
}

/**
 * The notes of every change, for the marks on the sheet: `measures` are those of the version shown (a lyric names
 * the sounding note of part 0; a notes change the events that differ; a chord change its event).
 */
export function markKeys(measures: MeasureInfo[], changes: AnyChange[]): EventKey[] {
  const keys: EventKey[] = [];
  for (const c of changes) {
    if (c.span.staff !== 0) continue;
    if (isScoreChange(c)) {
      for (const i of c.kind === "chord" ? [c.event ?? 0] : c.marks ?? []) {
        const ev = measures[c.measure]?.events[i];
        if (ev) keys.push(ev.key);
      }
      continue;
    }
    const sounding = measures[c.measure]?.events.filter((e) => !e.isRest && !e.isGrace && !e.inChord);
    const ev = sounding?.[c.onset];
    if (ev) keys.push(ev.key);
  }
  return keys;
}

const quote = (s: Syllable) => `"${s.text}"`;

/** One line of the change list: where, and what it was. */
export function changeLine(c: Pick<ModelChange, "measure" | "verse" | "old" | "new"> | Pick<ScoreChange, "kind" | "measure" | "old" | "new">): string {
  if (!("verse" in c)) {
    const at = `bar ${c.measure + 1}, ${c.kind === "chord" ? "chord" : "notes"}`;
    if (c.kind === "notes") return `${at}: ${c.old.text} becomes ${c.new.text}`;
    if (c.old.text && c.new.text) return `${at}: "${c.old.text}" becomes "${c.new.text}"`;
    return c.old.text ? `${at}: "${c.old.text}" is taken away` : `${at}: new "${c.new.text}"`;
  }
  const where = `bar ${c.measure + 1}, verse ${c.verse}`;
  if (c.old && c.new) return `${where}: ${quote(c.old)} becomes ${quote(c.new)}`;
  if (c.old) return `${where}: ${quote(c.old)} is taken away`;
  if (c.new) return `${where}: new ${quote(c.new)}`;
  return where;
}
