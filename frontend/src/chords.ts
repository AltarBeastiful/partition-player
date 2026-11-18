// Chord symbols from the loaded score, and a piano accompaniment generated from them (ADR 0003).
// Times are in whole notes, like everything else in the player.
import type { OpenSheetMusicDisplay } from "opensheetmusicdisplay";

export interface ChordSymbol { time: number; measure: number; root: number; kind: number; bass: number | null; text: string }
export interface MeasureInfo { start: number; duration: number; num: number; den: number }
export interface AccompEvent { time: number; midi: number; length: number; velocity: number }
/** A melody note of the printed score, absolute time in whole notes: what the comp plays under. */
export interface SungNote { time: number; length: number }

const NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"];
// ChordSymbolEnum (OSMD) -> intervals in semitones from the root
const INTERVALS: Record<number, number[]> = {
  0: [0, 4, 7], 1: [0, 3, 7], 2: [0, 4, 8], 3: [0, 3, 6], 4: [0, 4, 10, 7], 5: [0, 4, 11, 7], 6: [0, 3, 10, 7],
  7: [0, 3, 9, 6], 8: [0, 4, 10, 8], 9: [0, 3, 10, 6], 10: [0, 3, 11, 7], 11: [0, 4, 9, 7], 12: [0, 3, 9, 7],
  13: [0, 4, 10, 14], 14: [0, 4, 11, 14], 15: [0, 3, 10, 14], 16: [0, 7, 10, 17], 17: [0, 7, 11, 17], 18: [0, 3, 10, 17],
  19: [0, 4, 10, 21], 20: [0, 4, 11, 21], 21: [0, 3, 10, 21], 22: [0, 2, 7], 23: [0, 5, 7], 29: [0, 7],
};
const SUFFIX: Record<number, string> = {
  0: "", 1: "m", 2: "+", 3: "dim", 4: "7", 5: "maj7", 6: "m7", 7: "dim7", 8: "+7", 9: "m7b5", 10: "mM7", 11: "6", 12: "m6",
  13: "9", 14: "maj9", 15: "m9", 16: "11", 17: "maj11", 18: "m11", 19: "13", 20: "maj13", 21: "m13", 22: "sus2", 23: "sus4", 29: "5",
};

function pitchClass(p: { FundamentalNote: number; AccidentalHalfTones: number } | undefined | null): number | null {
  if (!p) return null;
  return ((p.FundamentalNote + p.AccidentalHalfTones) % 12 + 12) % 12;
}

/** Every chord symbol in the sheet with its absolute time, plus the measure grid. */
export function collectChords(osmd: OpenSheetMusicDisplay): { chords: ChordSymbol[]; measures: MeasureInfo[] } {
  const chords: ChordSymbol[] = [];
  const measures: MeasureInfo[] = [];
  const sheet = osmd.Sheet;
  if (!sheet) return { chords, measures };
  sheet.SourceMeasures.forEach((m, index) => {
    const ts = m.ActiveTimeSignature;
    measures.push({ start: m.AbsoluteTimestamp.RealValue, duration: m.Duration.RealValue, num: ts?.Numerator ?? 4, den: ts?.Denominator ?? 4 });
    for (const container of m.VerticalSourceStaffEntryContainers) {
      const time = container.getAbsoluteTimestamp().RealValue;
      for (const entry of container.StaffEntries) {
        for (const cc of entry?.ChordContainers ?? []) {
          const root = pitchClass(cc.RootPitch);
          if (root === null) continue;
          const bass = pitchClass(cc.BassPitch);
          const kind = cc.ChordKind as number;
          const text = NAMES[root] + (SUFFIX[kind] ?? "") + (bass !== null && bass !== root ? "/" + NAMES[bass] : "");
          chords.push({ time, measure: index, root, kind, bass, text });
        }
      }
    }
  });
  chords.sort((a, b) => a.time - b.time);
  return { chords, measures };
}

/** Bass in C2..B2, chord tones in E3..G4: below the melody, above the mud. */
function voicing(c: ChordSymbol): { bass: number; tones: number[] } {
  const bassPc = c.bass ?? c.root;
  const bass = 36 + bassPc;
  const rootMidi = 52 + ((c.root - 4 + 12) % 12);
  const tones = (INTERVALS[c.kind] ?? INTERVALS[0]).slice(0, 4).map((i) => {
    let n = rootMidi + i;
    while (n > 67) n -= 12;
    return n;
  });
  return { bass, tones };
}

/** Pulses of a measure as [time offset, isStrong] in whole notes, by time signature. */
function pulses(m: MeasureInfo): { at: number; strong: boolean }[] {
  const compound = m.den === 8 && m.num % 3 === 0 && m.num >= 6;
  if (compound) {
    const pulse = 3 / 8;
    const count = Math.max(1, Math.round(m.duration / pulse));
    return Array.from({ length: count }, (_, i) => ({ at: i * pulse, strong: i === 0 || (m.num === 12 && i === 2) }));
  }
  const beat = 1 / m.den;
  const count = Math.max(1, Math.round(m.duration / beat));
  return Array.from({ length: count }, (_, i) => ({ at: i * beat, strong: i === 0 || (count === 4 && i === 2) }));
}

/**
 * A simple piano accompaniment: bass on strong pulses and on every chord change, chord tones on
 * every pulse -- except a weak pulse over a silence that lasts to the end of its measure, which is
 * left out. The comp is meant to be heard under the melody; the last measure of a song or of a
 * section is written as a short note and then rests, and a pulse landing in those rests was heard
 * as a small extra note after the singing had stopped, once every time round the chorus.
 */
export function accompaniment(chords: ChordSymbol[], measures: MeasureInfo[], sung: SungNote[]): AccompEvent[] {
  if (chords.length === 0) return [];
  const events: AccompEvent[] = [];
  const notes = [...sung].sort((a, b) => a.time - b.time);
  let ni = 0; // notes before this one have all stopped before the pulse being laid (pulses only move on)
  const singing = (from: number, to: number): boolean => {
    while (ni < notes.length && notes[ni].time + notes[ni].length <= from + 1e-9) ni++;
    for (let j = ni; j < notes.length && notes[j].time < to - 1e-9; j++)
      if (notes[j].time + notes[j].length > from + 1e-9) return true;
    return false;
  };
  let ci = -1;
  let last: ChordSymbol | null = null;
  for (const m of measures) {
    const ps = pulses(m);
    ps.forEach((p, i) => {
      const t = m.start + p.at;
      const next = i + 1 < ps.length ? ps[i + 1].at : m.duration;
      const len = next - p.at;
      while (ci + 1 < chords.length && chords[ci + 1].time <= t + 1e-6) ci++;
      if (ci < 0) return; // nothing printed yet: silence, never an invented chord
      const c = chords[ci];
      const v = voicing(c);
      const changed = c !== last;
      last = c;
      if (!p.strong && !changed && !singing(t, m.start + m.duration)) return; // nothing left to play under
      if (p.strong || changed) events.push({ time: t, midi: v.bass, length: len * 0.95, velocity: 0.55 });
      for (const n of v.tones) events.push({ time: t, midi: n, length: len * 0.85, velocity: p.strong || changed ? 0.42 : 0.32 });
    });
  }
  return events;
}
