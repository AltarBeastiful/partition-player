/**
 * The generated piano comp (ADR 0003), and the silence rule that keeps it from sounding after the
 * singing has stopped: a weak pulse over a rest that runs to the end of its measure is left out.
 *
 * The grid is Anton's: 19 measures of 2/4, so two pulses a measure, beat 1 strong and beat 2 weak.
 */
import { describe, expect, it } from "vitest";
import { accompaniment, type ChordSymbol, type MeasureInfo, type SungNote } from "./chords";

const BAR = 0.5; // a 2/4 measure in whole notes
const measures: MeasureInfo[] = Array.from({ length: 19 }, (_, i) => ({ start: i * BAR, duration: BAR, num: 2, den: 4 }));
const Cm = (m: number): ChordSymbol => ({ time: m * BAR, measure: m, root: 0, kind: 1, bass: null, text: "Cm" });
const G = (m: number): ChordSymbol => ({ time: m * BAR, measure: m, root: 7, kind: 0, bass: null, text: "G" });

/** Two eighths on each beat, as the chorus is written, for the measures listed. */
const eighths = (ms: number[]): SungNote[] => ms.flatMap((m) => [{ time: m * BAR, length: 0.125 }, { time: m * BAR + 0.25, length: 0.125 }]);
const beatsOf = (ev: { time: number }[], m: number) =>
  ev.filter((e) => e.time >= m * BAR - 1e-9 && e.time < (m + 1) * BAR - 1e-9).map((e) => (e.time - m * BAR) / 0.25 + 1);

describe("accompaniment", () => {
  it("pulses on every beat while the melody is singing", () => {
    const ev = accompaniment([Cm(16)], measures, eighths([16, 17]));
    expect([...new Set(beatsOf(ev, 17))]).toEqual([1, 2]);   // beat 1 bass + tones, beat 2 tones
    expect(ev.filter((e) => e.time === 17 * BAR).map((e) => e.midi)).toEqual([36, 60, 63, 67]);
    expect(ev.filter((e) => e.time === 17 * BAR + 0.25).map((e) => e.midi)).toEqual([60, 63, 67]);
  });

  it("leaves out the weak pulse of a last measure, where the song rests after its final note", () => {
    // measure 19 as printed: an eighth on beat 1 ("moi."), then an eighth rest and a quarter rest
    const ev = accompaniment([Cm(18)], measures, [{ time: 18 * BAR, length: 0.125 }]);
    expect([...new Set(beatsOf(ev, 18))]).toEqual([1]); // the chord lands once, under the note
  });

  it("keeps a weak pulse under a note that is still ringing over it", () => {
    const ev = accompaniment([Cm(18)], measures, [{ time: 18 * BAR, length: BAR }]); // a half note filling the measure
    expect([...new Set(beatsOf(ev, 18))]).toEqual([1, 2]);
  });

  it("keeps a weak pulse where the chord changes, silence or not", () => {
    const half: MeasureInfo[] = [{ start: 0, duration: BAR, num: 2, den: 4 }];
    const ev = accompaniment([Cm(0), { ...G(0), time: 0.25 }], half, [{ time: 0, length: 0.125 }]);
    expect([...new Set(beatsOf(ev, 0))]).toEqual([1, 2]);
    expect(ev.filter((e) => e.time === 0.25).map((e) => e.midi)).toEqual([43, 55, 59, 62]); // G, bass and all
  });

  it("plays nothing at all before the first chord symbol, and nothing without one", () => {
    expect(accompaniment([], measures, eighths([0]))).toEqual([]);
    expect(accompaniment([Cm(2)], measures, eighths([0, 1, 2])).every((e) => e.time >= 2 * BAR - 1e-9)).toBe(true);
  });

  it("silences only the one beat of Anton's whole page", () => {
    const chords = [Cm(0), { ...Cm(4), root: 5, text: "Fm" }, Cm(6), { ...Cm(7), root: 5, text: "Fm" }, G(8), Cm(10), G(12), Cm(14), G(16), Cm(18)];
    const all = measures.flatMap((_, m) => (m === 18 ? [{ time: 18 * BAR, length: 0.125 }] : eighths([m])));
    const weak = accompaniment(chords, measures, all).filter((e) => Math.abs((e.time % BAR) - 0.25) < 1e-9);
    expect([...new Set(weak.map((e) => Math.floor(e.time / BAR) + 1))]).toEqual(
      [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18], // every measure but the 19th
    );
  });
});
