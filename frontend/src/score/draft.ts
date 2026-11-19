/**
 * A model draft as the sheet shows it (plan 0016, step 6). The corrected score is the read score
 * with the ticked changes written into the lyrics, change by change; no note is touched. The server
 * writes the same thing on Apply (`apply_changes` in the backend), this is its preview, so the
 * sheet, the player and the download after Apply agree.
 *
 * A change names a note by measure and onset rank: the rank among the measure's sounding notes
 * (rests, grace notes and chord tones do not count), the convention of lyrics.json.
 */
import type { ModelChange, Syllable } from "../api";
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
export function correctedXml(xml: string, changes: ModelChange[], ticked: ReadonlySet<string>): string {
  const chosen = changes.filter((c) => ticked.has(c.id));
  if (chosen.length === 0) return xml;
  const doc = parse(xml);
  for (const c of chosen) setLyric(doc, c.span.staff, c.measure, c.onset, c.verse, c.new);
  return serialize(doc);
}

/** The sounding note of every change on part 0, for the marks on the sheet. */
export function markKeys(measures: MeasureInfo[], changes: ModelChange[]): EventKey[] {
  const keys: EventKey[] = [];
  for (const c of changes) {
    if (c.span.staff !== 0) continue;
    const sounding = measures[c.measure]?.events.filter((e) => !e.isRest && !e.isGrace && !e.inChord);
    const ev = sounding?.[c.onset];
    if (ev) keys.push(ev.key);
  }
  return keys;
}

const quote = (s: Syllable) => `"${s.text}"`;

/** One line of the change list: where, and what it was. */
export function changeLine(c: Pick<ModelChange, "measure" | "verse" | "old" | "new">): string {
  const where = `bar ${c.measure + 1}, verse ${c.verse}`;
  if (c.old && c.new) return `${where}: ${quote(c.old)} becomes ${quote(c.new)}`;
  if (c.old) return `${where}: ${quote(c.old)} is taken away`;
  if (c.new) return `${where}: new ${quote(c.new)}`;
  return where;
}
