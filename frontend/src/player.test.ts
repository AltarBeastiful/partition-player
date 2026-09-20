/**
 * The unrolled timeline (plan 0007, step 2): `layPasses` is the whole of the player's arithmetic,
 * pure and away from Tone and from a rendered sheet, so it can be held to exact numbers here. The
 * measure slice of step 5 lands in this same function and these same tests.
 */
import { describe, expect, it } from "vitest";
import { samePrefix, type Pass } from "./form";
import { layPasses, windowOf, type PrintedScore } from "./player";

/** Four 4/4 measures, one whole note a measure (C4, D4, E4, F4), a chord on the downbeat of each. */
function score(): PrintedScore {
  const midi = [60, 62, 64, 65];
  return {
    printed: midi.map((m, i) => ({ time: i, measure: i, notes: [{ midi: m, length: 1 }] })),
    measureStart: [0, 1, 2, 3],
    measureDuration: [1, 1, 1, 1],
    accompByMeasure: midi.map((m) => [{ at: 0, midi: m - 12, length: 1, velocity: 0.5 }]),
    measureCount: 4,
  };
}

const pass = (from: number, to: number, verse: number | null = null): Pass => ({ ranges: [{ from, to }], verse });

describe("layPasses", () => {
  it("lays one pass over the whole page in printed order", () => {
    const { steps, events, total } = layPasses(score(), [pass(0, 3)]);
    expect(steps.map((s) => [s.time, s.measure, s.pass])).toEqual([[0, 0, 0], [1, 1, 0], [2, 2, 0], [3, 3, 0]]);
    expect(total).toBe(4);
    expect(events.filter((e) => e.track === "melody").map((e) => e.midi)).toEqual([60, 62, 64, 65]);
    expect(events.filter((e) => e.track === "accompaniment").map((e) => e.time)).toEqual([0, 1, 2, 3]);
  });

  it("repeats a section, giving each pass its own stretch of the timeline", () => {
    const { steps, total } = layPasses(score(), [pass(0, 1, 1), pass(2, 3), pass(0, 1, 2), pass(2, 3)]);
    expect(total).toBe(8); // eight measures of one whole note, laid end to end
    expect(steps.map((s) => s.time)).toEqual([0, 1, 2, 3, 4, 5, 6, 7]);
    expect(steps.map((s) => s.measure)).toEqual([0, 1, 2, 3, 0, 1, 2, 3]);
    expect(steps.map((s) => s.pass)).toEqual([0, 0, 1, 1, 2, 2, 3, 3]);
  });

  it("keeps the melody and the accompaniment together on a repeated measure", () => {
    const { events } = layPasses(score(), [pass(1, 1), pass(1, 1)]);
    // the sort is stable and the melody of a measure is pushed before its accompaniment
    expect(events.map((e) => [e.time, e.midi, e.track])).toEqual([
      [0, 62, "melody"], [0, 50, "accompaniment"],
      [1, 62, "melody"], [1, 50, "accompaniment"],
    ]);
  });

  it("clamps a range that runs past the last measure, and drops one that starts after it", () => {
    expect(layPasses(score(), [pass(2, 99)]).steps.map((s) => s.measure)).toEqual([2, 3]);
    expect(layPasses(score(), [pass(9, 12)]).steps).toEqual([]);
    expect(layPasses(score(), []).total).toBe(0);
  });

  it("carries a note that rings past the last measure into the total", () => {
    const long = score();
    long.printed[3] = { time: 3, measure: 3, notes: [{ midi: 65, length: 2.5 }] };
    expect(layPasses(long, [pass(0, 3)]).total).toBe(5.5);
  });
});

describe("layPasses with a section that starts or ends inside a measure (plan 0007, step 5)", () => {
  /** Anton in little: measure 1 holds a quarter on beat 1 and the chorus upbeat on beat 2 (2/4). */
  function anton(): PrintedScore {
    return {
      printed: [
        { time: 0, measure: 0, notes: [{ midi: 60, length: 0.25 }] },   // "…relles." beat 1
        { time: 0.25, measure: 0, notes: [{ midi: 67, length: 0.125 }] }, // "An-" beat 2
        { time: 0.5, measure: 1, notes: [{ midi: 60, length: 0.125 }] }, // "-ton,"
      ],
      measureStart: [0, 0.5],
      measureDuration: [0.5, 0.5],
      accompByMeasure: [[{ at: 0, midi: 48, length: 0.5, velocity: 0.5 }], [{ at: 0, midi: 55, length: 0.5, velocity: 0.5 }]],
      measureCount: 2,
    };
  }

  const chorus = { ranges: [{ from: 0, to: 1, fromOnset: 0.25 }], verse: null };

  it("plays the chorus from its upbeat, not from the downbeat before it", () => {
    const { steps, total } = layPasses(anton(), [chorus]);
    expect(steps.map((s) => [s.time, s.measure])).toEqual([[0, 0], [0.25, 1]]); // "An-" then "-ton,"
    expect(total).toBe(0.75); // half of measure 1, then measure 2
  });

  it("keeps the chord under the upbeat, clamped to the edge rather than dropped", () => {
    const { events } = layPasses(anton(), [chorus]);
    const chords = events.filter((e) => e.track === "accompaniment");
    expect(chords.map((e) => [e.time, e.midi, e.length])).toEqual([[0, 48, 0.25], [0.25, 55, 0.5]]);
  });

  it("sounds a note that began before the edge and still rings over it", () => {
    const long = anton();
    long.printed[0] = { time: 0, measure: 0, notes: [{ midi: 60, length: 0.5 }] }; // a half note over the bar's two beats
    const melody = layPasses(long, [chorus]).events.filter((e) => e.track === "melody");
    expect(melody[0]).toMatchObject({ time: 0, midi: 60, length: 0.25 }); // heard from the edge, for what is left of it
  });

  it("leaves a section early, cutting the note that would ring past it", () => {
    const verse = { ranges: [{ from: 0, to: 0, toOnset: 0.25 }], verse: 1 };
    const { steps, events, total } = layPasses(anton(), [verse]);
    expect(steps.map((s) => s.time)).toEqual([0]);        // only the beat-1 note
    expect(total).toBe(0.25);
    expect(events.filter((e) => e.track === "accompaniment")[0].length).toBe(0.25); // the chord is cut too
  });

  it("lays verse then chorus end to end, the shared measure counted once each way", () => {
    const verse = { ranges: [{ from: 0, to: 0, toOnset: 0.25 }], verse: 1 };
    const { steps, slices, total } = layPasses(anton(), [verse, chorus]);
    expect(total).toBe(1); // a quarter of verse, then three quarters of chorus
    expect(steps.map((s) => [s.time, s.measure, s.pass])).toEqual([[0, 0, 0], [0.25, 0, 1], [0.5, 1, 1]]);
    // measure 1 is played twice, a different stretch each time, and its beat 0 sits before the chorus
    expect(slices.filter((s) => s.measure === 0)).toEqual([
      { measure: 0, pass: 0, origin: 0, from: 0, to: 0.25 },
      { measure: 0, pass: 1, origin: 0, from: 0.25, to: 0.5 },
    ]);
  });

  it("drops a slice with nothing in it rather than laying a pass of no length", () => {
    const empty = { ranges: [{ from: 0, to: 0, fromOnset: 0.5 }], verse: null };
    expect(layPasses(anton(), [empty]).steps).toEqual([]);
    expect(layPasses(anton(), [empty]).total).toBe(0);
  });

  it("clamps an edge that a shortened measure no longer has", () => {
    const past = { ranges: [{ from: 0, to: 1, fromOnset: 9 }], verse: null };
    const { steps } = layPasses(anton(), [past]); // the whole of measure 1 is skipped, measure 2 plays
    expect(steps.map((s) => s.measure)).toEqual([1]);
  });
});

describe("windowOf: what Play actually plays", () => {
  // the page sung verse, chorus, verse, chorus — the shape the form panel makes easy
  const form = [pass(0, 1, 1), pass(2, 3), pass(0, 1, 2), pass(2, 3)];
  const line = () => layPasses(score(), form);

  it("plays the whole form when the range covers the page", () => {
    const { slices, total } = line();
    expect(total).toBe(8);
    expect(windowOf(slices, { from: 1, to: 4 }, 4, total)).toEqual({ start: 0, end: 8 });
  });

  it("plays to the end of the form from a measure in the middle", () => {
    const { slices, total } = line();
    expect(windowOf(slices, { from: 3, to: 4 }, 4, total)).toEqual({ start: 2, end: 8 }); // "play from here"
  });

  it("stops at the first stretch of a narrowed end, for practising a passage", () => {
    const { slices, total } = line();
    expect(windowOf(slices, { from: 1, to: 2 }, 4, total)).toEqual({ start: 0, end: 2 });
  });

  it("takes a sliced measure from where its section is entered to where it is left", () => {
    const sliced = layPasses(score(), [{ ranges: [{ from: 0, to: 1, fromOnset: 0.5 }], verse: null }]);
    expect(windowOf(sliced.slices, { from: 1, to: 4 }, 4, sliced.total)).toEqual({ start: 0, end: 1.5 });
  });

  it("gives the whole timeline when there is no range at all", () => {
    const { slices, total } = line();
    expect(windowOf(slices, null, 4, total)).toEqual({ start: 0, end: 8 });
  });
});

describe("samePrefix", () => {
  const list = [pass(0, 1, 1), pass(2, 3), pass(0, 1, 2), pass(2, 3)];

  it("counts the leading passes two lists play the same", () => {
    expect(samePrefix(list, list)).toBe(4);
    expect(samePrefix(list, [...list, pass(2, 3)])).toBe(4);          // a chorus added at the end
    expect(samePrefix(list, [list[0], list[1], pass(2, 3)])).toBe(2); // the third pass changed
    expect(samePrefix(list, [])).toBe(0);
  });

  it("tells a different verse and a different range apart", () => {
    expect(samePrefix([pass(0, 1, 1)], [pass(0, 1, 2)])).toBe(0);
    expect(samePrefix([pass(0, 1, 1)], [pass(0, 2, 1)])).toBe(0);
  });
});
