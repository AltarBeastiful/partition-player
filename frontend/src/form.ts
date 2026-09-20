/**
 * The form of a song (plan 0004): the order the page is played in, as a list of passes.
 *
 * A pass is a list of measure ranges (0-based, inclusive) with a verse number or none. The player
 * always plays a pass list. The default list is OSMD's own expansion of the repeat signs in the
 * document, with the multiplier OSMD meant to have and never applied: a repetition is played once per
 * lyric verse under it (at least once per ending), and the page as a whole once per verse in the
 * measures outside every repeat. The user can replace it with a `Form`: named sections over measure
 * ranges and passes through them, saved with the score.
 */
import type { OpenSheetMusicDisplay } from "opensheetmusicdisplay";

/**
 * Measures, inclusive. A section that starts or ends inside a measure carries the beat it does so
 * on (plan 0007, step 5): `fromOnset` is where the first measure is entered, `toOnset` where the
 * last is left, both in whole notes from that measure's start. Absent means the whole measure, so
 * every form written before this reads the same.
 */
export interface Range { from: number; to: number; fromOnset?: number; toOnset?: number }
export interface Pass { ranges: Range[]; verse: number | null }
export interface Section { name: string; from: number; to: number; fromOnset?: number; toOnset?: number }
export interface FormPass { section: number; verse: number | null; times?: number } // times: played over and over, absent = once
export interface Form { sections: Section[]; passes: FormPass[] }

/** The lyric verse numbers present in each measure, from the loaded sheet. */
export function versesByMeasure(osmd: OpenSheetMusicDisplay): number[][] {
  const out: number[][] = [];
  for (const m of osmd.Sheet?.SourceMeasures ?? []) {
    const set = new Set<number>();
    for (const container of m.VerticalSourceStaffEntryContainers ?? []) {
      for (const entry of container.StaffEntries ?? []) {
        for (const ve of entry?.VoiceEntries ?? []) {
          for (const k of ve.LyricsEntries?.keys() ?? []) {
            const n = parseInt(String(k), 10);
            if (Number.isFinite(n) && n > 0) set.add(n);
          }
        }
      }
    }
    out.push([...set].sort((a, b) => a - b));
  }
  return out;
}

function maxVerse(verses: number[][], from: number, to: number): number {
  let best = 0;
  for (let i = from; i <= to && i < verses.length; i++) for (const v of verses[i]) best = Math.max(best, v);
  return best;
}

/**
 * OSMD's expansion of the repeat signs with the verse multiplier, read from its iterator. Leaves the
 * sheet with repeats ignored, which is how the player walks it. OSMD's virtual whole-page repetition
 * never jumps whatever its count, so the whole-page multiplier is applied here as rounds of the list.
 */
export function defaultPasses(osmd: OpenSheetMusicDisplay): Pass[] {
  const sheet = osmd.Sheet;
  const n = sheet?.SourceMeasures.length ?? 0;
  if (!sheet || n === 0) return [];
  const verses = versesByMeasure(osmd);
  const real: Range[] = [];
  for (const r of sheet.Repetitions ?? []) {
    if (r.FromWords && r.StartIndex === 0 && r.EndIndex === n - 1) continue; // the virtual one
    real.push({ from: r.StartIndex, to: r.EndIndex });
    // the setter rebuilds the ending order; MusicPartManager.reInit() is not needed by the iterator and crashes on a back jump
    r.UserNumberOfRepetitions = Math.max(1, r.NumberOfEndings, maxVerse(verses, r.StartIndex, r.EndIndex));
  }
  const rules = osmd.EngravingRules;
  rules.CursorIgnoreRepetitions = false;
  const visited: number[] = [];
  try {
    const it = sheet.MusicPartManager.getIterator();
    let last = -1;
    let guard = 200_000;
    while (!it.EndReached && guard-- > 0) {
      const m = it.CurrentMeasureIndex;
      if (m !== last) { visited.push(m); last = m; }
      it.moveToNext();
    }
  } finally {
    rules.CursorIgnoreRepetitions = true;
  }
  return passesFromVisits(visited, verses, real);
}

/**
 * The visit order compressed into passes: a new range at every forward skip, a new pass at every
 * backward jump and at the edge of every repeat (so sections come out whole); outside the repeats,
 * a pass is also cut where stacked verses start or stop. A pass's verse is one more than the number
 * of earlier passes over the same measures; a pass over measures that never hold more than one lyric
 * has none.
 *
 * Then the songbook rule. The literal signs say "verses N times, then the chorus once"; the page is
 * sung verse, chorus, verse, chorus. So when the page has no repeat sign, or when three or more
 * verses are stacked and a single-lyric part follows them, the list is played in rounds: round k
 * plays every pass in order, the stacked ones with verse k (a repeat's k-th pass, or the whole
 * stacked part), the single-lyric ones every time. Two stacked verses under a repeat sign are taken
 * literally (a first phrase sung twice, not a chorus).
 */
export function passesFromVisits(visited: number[], verses: number[][], real: Range[]): Pass[] {
  const stackedAt = (i: number) => (verses[i]?.length ?? 0) > 1;
  const coveredAt = (i: number) => real.some((r) => i >= r.from && i <= r.to);
  const starts = new Set(real.map((r) => r.from));
  const ends = new Set(real.map((r) => r.to + 1));
  const passes: Pass[] = [];
  let ranges: Range[] = [];
  const close = () => { if (ranges.length) passes.push({ ranges, verse: null }); ranges = []; };
  let last = -1;
  for (const m of visited) {
    const cur = ranges[ranges.length - 1];
    // leaving a repeat ends the pass, unless the pass already jumped forward into an ending
    let edge = starts.has(m) || (ends.has(m) && ranges.length === 1);
    if (!edge && cur && !coveredAt(m) && !coveredAt(last) && stackedAt(m) !== stackedAt(last)) edge = true;
    if (cur && m === last + 1 && !edge) { cur.to = m; last = m; continue; }
    if (cur && (m <= last || edge)) close();
    ranges.push({ from: m, to: m });
    last = m;
  }
  close();
  const overlaps = (a: Range, b: Range) => a.from <= b.to && b.from <= a.to;
  const stacked = (p: Pass) => p.ranges.some((r) => { for (let i = r.from; i <= r.to; i++) if (stackedAt(i)) return true; return false; });
  const covered = (p: Pass) => coveredAt(p.ranges[0].from);
  passes.forEach((p, i) => {
    p.verse = stacked(p) ? 1 + passes.slice(0, i).filter((q) => overlaps(q.ranges[0], p.ranges[0])).length : null;
  });
  let n = 0;
  for (const p of passes) if (stacked(p)) for (const r of p.ranges) n = Math.max(n, maxVerse(verses, r.from, r.to));
  const lastStacked = passes.map(stacked).lastIndexOf(true);
  const tail = lastStacked >= 0 && passes.slice(lastStacked + 1).some((p) => !stacked(p));
  const rounds = n >= 2 && (real.length === 0 || (n >= 3 && tail));
  if (!rounds) return passes;
  const out: Pass[] = [];
  for (let k = 1; k <= n; k++) {
    for (const p of passes) {
      if (covered(p) && p.verse !== null && p.verse !== k) continue;
      out.push({ ranges: p.ranges.map((r) => ({ ...r })), verse: stacked(p) ? k : null });
    }
  }
  return out;
}

/**
 * Do two expanded pass lists play the same? The panel changes the form object on every keystroke,
 * and a section's name or a chip's colour is nothing to the player; only this tells them apart
 * (plan 0007, step 1), so a rename no longer rebuilds the timeline and stops the sound.
 */
export function samePass(p: Pass, q: Pass): boolean {
  return p.verse === q.verse && p.ranges.length === q.ranges.length
    && p.ranges.every((r, k) => r.from === q.ranges[k].from && r.to === q.ranges[k].to
      && (r.fromOnset ?? 0) === (q.ranges[k].fromOnset ?? 0) && (r.toOnset ?? null) === (q.ranges[k].toOnset ?? null));
}

export function samePasses(a: Pass[], b: Pass[]): boolean {
  return a.length === b.length && a.every((p, i) => samePass(p, b[i]));
}

/** How many leading passes two lists share: where a rebuilt timeline still means the same. */
export function samePrefix(a: Pass[], b: Pass[]): number {
  let i = 0;
  while (i < a.length && i < b.length && samePass(a[i], b[i])) i++;
  return i;
}

export const MAX_TIMES = 50;

/** A user form expanded into passes; a pass with `times` is laid out that many times over. */
export function expandForm(form: Form, measureCount: number): Pass[] {
  return form.passes.flatMap((p) => {
    const s = form.sections[p.section];
    if (!s) return [];
    const from = Math.max(0, Math.min(s.from, measureCount - 1)), to = Math.max(from, Math.min(s.to, measureCount - 1));
    const times = Math.max(1, Math.min(Math.round(p.times ?? 1), MAX_TIMES));
    const range: Range = { from, to };
    if (s.fromOnset !== undefined && s.fromOnset > 0 && from === s.from) range.fromOnset = s.fromOnset;
    if (s.toOnset !== undefined && to === s.to) range.toOnset = s.toOnset;
    return Array.from({ length: times }, () => ({ ranges: [{ ...range }], verse: p.verse }));
  });
}

/** Sections and passes made from a pass list, so a default form can be edited. */
export function formFromPasses(passes: Pass[], measureCount: number): Form {
  const sections: Section[] = [];
  const out: FormPass[] = [];
  const key = (r: Range) => `${r.from}-${r.to}-${r.fromOnset ?? 0}-${r.toOnset ?? ""}`;
  const index = new Map<string, number>();
  for (const p of passes) {
    // One section per distinct range; a multi-range pass becomes several passes with the same verse.
    for (const r of p.ranges) {
      let i = index.get(key(r));
      if (i === undefined) {
        i = sections.length;
        index.set(key(r), i);
        sections.push({ name: "", from: r.from, to: r.to, ...(r.fromOnset ? { fromOnset: r.fromOnset } : {}), ...(r.toOnset !== undefined ? { toOnset: r.toOnset } : {}) });
      }
      // A pass repeated straight after itself is one chip with a count, the way it is sung
      // (plan 0007): "Chorus ×2", not two chorus chips.
      const last = out[out.length - 1];
      if (last && last.section === i && last.verse === p.verse && (last.times ?? 1) < MAX_TIMES) last.times = (last.times ?? 1) + 1;
      else out.push({ section: i, verse: p.verse });
    }
  }
  nameSections(sections, passes, measureCount);
  return { sections, passes: out };
}

/** Plain names: the section passed with verses is "Verse", one passed without is "Chorus", else by letter. */
export function nameSections(sections: Section[], passes: Pass[], measureCount: number): void {
  if (sections.length === 1) { sections[0].name = sections[0].from === 0 && sections[0].to === measureCount - 1 ? "Page" : "Part A"; return; }
  const withVerse = new Set<string>();
  const rangeKey = (r: { from: number; to: number; fromOnset?: number; toOnset?: number }) => `${r.from}-${r.to}-${r.fromOnset ?? 0}-${r.toOnset ?? ""}`;
  for (const p of passes) if (p.verse !== null) for (const r of p.ranges) withVerse.add(rangeKey(r));
  let verse = 0, chorus = 0, letter = 0;
  for (const s of sections) {
    if (withVerse.has(rangeKey(s))) s.name = ++verse > 1 ? `Verse ${verse}` : "Verse";
    else if (chorus === 0 && passes.filter((p) => p.ranges.some((r) => rangeKey(r) === rangeKey(s))).length > 1) { s.name = "Chorus"; chorus++; }
    else s.name = "Part " + String.fromCharCode(65 + letter++);
  }
}

export interface PresetOptions {
  /** The form on the panel now: a preset orders the sections the user has rather than replacing them (plan 0007). */
  current?: Form | null;
  /** The chorus sung twice each time round, which is how three of the thirty benchmark songs print it. */
  chorusTwice?: boolean;
}

/** The presets of the form panel. */
export function preset(kind: "printed" | "verses" | "chorus", printed: Pass[], verseCount: number, measureCount: number, options: PresetOptions = {}): Form {
  if (kind === "printed") return formFromPasses(printed, measureCount); // "as printed" is the one that starts over
  const count = Math.max(1, verseCount);
  const current = options.current ?? null;
  if (kind === "verses") {
    const whole = current?.sections.findIndex((s) => s.from === 0 && s.to === measureCount - 1) ?? -1;
    const sections = whole >= 0 ? [current!.sections[whole]] : [{ name: "Page", from: 0, to: measureCount - 1 }];
    return { sections, passes: Array.from({ length: count }, (_, i) => ({ section: 0, verse: i + 1 })) };
  }
  // Chorus after every verse. The sections on the panel win when there are several: the one named
  // like a verse is the verse, the rest are sung after it. Only when there is nothing to build on
  // are they invented, from the printed passes and then from half the page.
  let sections: Section[];
  let verseSection: number;
  if (current && current.sections.length >= 2) {
    sections = current.sections;
    const named = sections.findIndex((s) => /^verse/i.test(s.name));
    verseSection = named === -1 ? 0 : named;
  } else {
    const base = formFromPasses(printed, measureCount);
    const named = base.sections.findIndex((s) => s.name.startsWith("Verse"));
    if (named === -1 || base.sections.length < 2) {
      const half = Math.max(1, Math.floor(measureCount / 2));
      sections = [{ name: "Verse", from: 0, to: half - 1 }, { name: "Chorus", from: half, to: measureCount - 1 }];
      verseSection = 0;
    } else {
      sections = base.sections;
      verseSection = named;
    }
  }
  const others = sections.map((_, i) => i).filter((i) => i !== verseSection);
  const times = options.chorusTwice ? 2 : undefined;
  const passes: FormPass[] = [];
  for (let v = 1; v <= count; v++) {
    passes.push({ section: verseSection, verse: v });
    for (const o of others) passes.push(times ? { section: o, verse: null, times } : { section: o, verse: null });
  }
  return { sections, passes };
}

/**
 * The form written as one line, in the words of the summary: "Verse 1 · Chorus ×2 · Verse 2". A
 * section is named by its shortest unique prefix, or in quotes when its name holds a space; a bare
 * number after it is the verse, `×n` (or `xn`) how often it is played. Nothing is applied unless the
 * whole line parses (plan 0007): a line cannot create a section, only order the ones that exist.
 */
export function parseForm(line: string, sections: Section[]): { passes: FormPass[]; error: null } | { passes: null; error: string } {
  const fail = (error: string) => ({ passes: null, error });
  const chunks = (line.includes("·") ? line.split("·") : line.trim().split(/\s+/)).map((c) => c.trim()).filter(Boolean);
  if (chunks.length === 0) return fail("Name a section, like \u201cVerse 1 \u00b7 Chorus\u201d.");
  if (sections.length === 0) return fail("There is no section to play yet.");
  const passes: FormPass[] = [];
  for (const chunk of chunks) {
    let rest = chunk;
    let times: number | undefined;
    let verse: number | null = null;
    const timesMatch = rest.match(/[\u00d7x]\s*(\d+)$/i);
    if (timesMatch) {
      times = parseInt(timesMatch[1], 10);
      if (!(times >= 1 && times <= MAX_TIMES)) return fail(`\u201c${chunk}\u201d: a pass can be played 1 to ${MAX_TIMES} times.`);
      rest = rest.slice(0, -timesMatch[0].length).trim();
    }
    const quoted = rest.match(/^"([^"]*)"\s*(\d+)?$/);
    if (quoted) {
      rest = quoted[1].trim();
      if (quoted[2]) verse = parseInt(quoted[2], 10);
    } else {
      const verseMatch = rest.match(/\s*(\d+)$/);
      if (verseMatch && rest.length > verseMatch[0].length) {
        verse = parseInt(verseMatch[1], 10);
        rest = rest.slice(0, -verseMatch[0].length).trim();
      }
    }
    if (verse !== null && !(verse >= 1 && verse <= 50)) return fail(`\u201c${chunk}\u201d: a verse number runs from 1 to 50.`);
    if (!rest) return fail(`\u201c${chunk}\u201d: name the section first.`);
    const lower = rest.toLowerCase();
    let found = sections.findIndex((s) => s.name.toLowerCase() === lower);
    if (found === -1) {
      const starting = sections.map((_, i) => i).filter((i) => sections[i].name.toLowerCase().startsWith(lower));
      if (starting.length === 1) found = starting[0];
      else if (starting.length > 1) return fail(`\u201c${rest}\u201d fits ${starting.map((i) => sections[i].name).join(" and ")}; write more of the name.`);
      else return fail(`There is no section called \u201c${rest}\u201d. The sections are ${sections.map((s) => s.name || "?").join(", ")}.`);
    }
    passes.push(times === undefined ? { section: found, verse } : { section: found, verse, times });
  }
  return { passes, error: null };
}

/** Sections follow their measures when the measure list changes; a range whose edge goes shrinks. */
export function remapForm(form: Form, remap: (m: number) => number | null): Form {
  const sections = form.sections.map((s) => {
    let from = remap(s.from), to = remap(s.to);
    if (from === null) from = remap(s.from + 1) ?? to;
    if (to === null) to = remap(s.to - 1) ?? from;
    if (from === null || to === null) return null;
    return { ...s, from: Math.min(from, to), to: Math.max(from, to) }; // the onsets ride along; the player clamps them to the measure
  });
  const keep = sections.map((s) => s !== null);
  const newIndex = sections.map((_, i) => keep.slice(0, i).filter(Boolean).length);
  return {
    sections: sections.filter((s): s is Section => s !== null),
    passes: form.passes.filter((p) => keep[p.section]).map((p) => ({ ...p, section: newIndex[p.section] })),
  };
}

/** The pass list in words: "Verse 1 · Chorus · Verse 2 · Chorus". */
export function describePasses(passes: Pass[], form: Form | null): string {
  if (!form) {
    return passes.map((p) => (p.verse !== null ? `Verse ${p.verse}` : `m. ${p.ranges.map((r) => (r.from === r.to ? r.from + 1 : `${r.from + 1}–${r.to + 1}`)).join("+")}`)).join(" · ");
  }
  return form.passes.map((p) => {
    const s = form.sections[p.section];
    const name = s?.name || "?";
    const times = (p.times ?? 1) > 1 ? ` ×${p.times}` : "";
    return (p.verse !== null ? `${name} ${p.verse}` : name) + times;
  }).join(" · ");
}
