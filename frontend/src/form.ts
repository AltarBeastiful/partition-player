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

export interface Range { from: number; to: number }
export interface Pass { ranges: Range[]; verse: number | null }
export interface Section { name: string; from: number; to: number }
export interface FormPass { section: number; verse: number | null }
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

/** A user form expanded into passes. */
export function expandForm(form: Form, measureCount: number): Pass[] {
  return form.passes.flatMap((p) => {
    const s = form.sections[p.section];
    if (!s) return [];
    const from = Math.max(0, Math.min(s.from, measureCount - 1)), to = Math.max(from, Math.min(s.to, measureCount - 1));
    return [{ ranges: [{ from, to }], verse: p.verse }];
  });
}

/** Sections and passes made from a pass list, so a default form can be edited. */
export function formFromPasses(passes: Pass[], measureCount: number): Form {
  const sections: Section[] = [];
  const out: FormPass[] = [];
  const key = (r: Range) => `${r.from}-${r.to}`;
  const index = new Map<string, number>();
  for (const p of passes) {
    // One section per distinct range; a multi-range pass becomes several passes with the same verse.
    for (const r of p.ranges) {
      let i = index.get(key(r));
      if (i === undefined) {
        i = sections.length;
        index.set(key(r), i);
        sections.push({ name: "", from: r.from, to: r.to });
      }
      out.push({ section: i, verse: p.verse });
    }
  }
  nameSections(sections, passes, measureCount);
  return { sections, passes: out };
}

/** Plain names: the section passed with verses is "Verse", one passed without is "Chorus", else by letter. */
export function nameSections(sections: Section[], passes: Pass[], measureCount: number): void {
  if (sections.length === 1) { sections[0].name = sections[0].from === 0 && sections[0].to === measureCount - 1 ? "Page" : "Part A"; return; }
  const withVerse = new Set<string>();
  for (const p of passes) if (p.verse !== null) for (const r of p.ranges) withVerse.add(`${r.from}-${r.to}`);
  let verse = 0, chorus = 0, letter = 0;
  for (const s of sections) {
    if (withVerse.has(`${s.from}-${s.to}`)) s.name = ++verse > 1 ? `Verse ${verse}` : "Verse";
    else if (chorus === 0 && passes.filter((p) => p.ranges.some((r) => r.from === s.from && r.to === s.to)).length > 1) { s.name = "Chorus"; chorus++; }
    else s.name = "Part " + String.fromCharCode(65 + letter++);
  }
}

/** The presets of the form panel. */
export function preset(kind: "printed" | "verses" | "chorus", printed: Pass[], verseCount: number, measureCount: number): Form {
  if (kind === "printed") return formFromPasses(printed, measureCount);
  const count = Math.max(1, verseCount);
  if (kind === "verses") {
    return { sections: [{ name: "Page", from: 0, to: measureCount - 1 }], passes: Array.from({ length: count }, (_, i) => ({ section: 0, verse: i + 1 })) };
  }
  // Chorus after every verse: the first stacked section is the verse, the rest of the page the chorus.
  const base = formFromPasses(printed, measureCount);
  const verseSection = base.sections.findIndex((s) => s.name.startsWith("Verse"));
  if (verseSection === -1 || base.sections.length < 2) {
    const half = Math.max(1, Math.floor(measureCount / 2));
    const sections: Section[] = [{ name: "Verse", from: 0, to: half - 1 }, { name: "Chorus", from: half, to: measureCount - 1 }];
    return { sections, passes: Array.from({ length: count }, (_, i) => [{ section: 0, verse: i + 1 }, { section: 1, verse: null }]).flat() };
  }
  const others = base.sections.map((_, i) => i).filter((i) => i !== verseSection);
  const passes: FormPass[] = [];
  for (let v = 1; v <= count; v++) { passes.push({ section: verseSection, verse: v }); for (const o of others) passes.push({ section: o, verse: null }); }
  return { sections: base.sections, passes };
}

/** Sections follow their measures when the measure list changes; a range whose edge goes shrinks. */
export function remapForm(form: Form, remap: (m: number) => number | null): Form {
  const sections = form.sections.map((s) => {
    let from = remap(s.from), to = remap(s.to);
    if (from === null) from = remap(s.from + 1) ?? to;
    if (to === null) to = remap(s.to - 1) ?? from;
    if (from === null || to === null) return null;
    return { ...s, from: Math.min(from, to), to: Math.max(from, to) };
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
  return form.passes.map((p) => { const s = form.sections[p.section]; const name = s?.name || "?"; return p.verse !== null ? `${name} ${p.verse}` : name; }).join(" · ");
}
