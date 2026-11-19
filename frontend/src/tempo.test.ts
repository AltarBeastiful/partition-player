/**
 * The tempo rules of the player (player controls, ticket 01): the range, stepping, typed values, the
 * score's own marking and what "default" means. Pure, so the cases are held exactly here.
 */
import { describe, expect, it } from "vitest";
import { clampTempo, defaultTempo, markedTempo, parseTempo, stepTempo, tempoRange } from "./tempo";

const score = (body: string) => `<?xml version="1.0"?><score-partwise><part id="P1"><measure number="1">${body}</measure></part></score-partwise>`;

describe("stepping and clamping", () => {
  it("steps by one bpm and stops at the ends of the range", () => {
    expect(stepTempo(90, 1)).toBe(91);
    expect(stepTempo(90, -1)).toBe(89);
    expect(stepTempo(180, 1)).toBe(180);
    expect(stepTempo(40, -1)).toBe(40);
  });
  it("clamps and rounds a value into the range", () => {
    expect(clampTempo(500)).toBe(180);
    expect(clampTempo(3)).toBe(40);
    expect(clampTempo(100.6)).toBe(101);
  });
  it("honours a wider range", () => {
    expect(stepTempo(200, 1, { min: 40, max: 240 })).toBe(201);
  });
});

describe("a typed value", () => {
  it("is read as a number and clamped", () => {
    expect(parseTempo("120")).toBe(120);
    expect(parseTempo(" 72 ")).toBe(72);
    expect(parseTempo("999")).toBe(180);
    expect(parseTempo("5")).toBe(40);
  });
  it("is ignored when it is not a number", () => {
    expect(parseTempo("")).toBeNull();
    expect(parseTempo("fast")).toBeNull();
    expect(parseTempo("12abc")).toBeNull();
  });
});

describe("the score's own tempo", () => {
  it("reads the sound tempo attribute", () => {
    expect(markedTempo(score(`<direction><sound tempo="112"/></direction>`))).toBe(112);
  });
  it("falls back to a metronome mark", () => {
    expect(markedTempo(score(`<direction><direction-type><metronome><beat-unit>quarter</beat-unit><per-minute>76</per-minute></metronome></direction-type></direction>`))).toBe(76);
  });
  const mm = (unit: string, dot: boolean, pm: number, sound = "") =>
    score(`<direction><direction-type><metronome><beat-unit>${unit}</beat-unit>${dot ? "<beat-unit-dot/>" : ""}<per-minute>${pm}</per-minute></metronome></direction-type>${sound}</direction>`);
  it("scales a metronome mark to quarters per minute by its beat unit", () => {
    expect(markedTempo(mm("half", false, 60))).toBe(120);
    expect(markedTempo(mm("quarter", true, 60))).toBe(90);
    expect(markedTempo(mm("eighth", false, 120))).toBe(60);
    expect(markedTempo(mm("eighth", true, 120))).toBe(90);
  });
  it("prefers the sound tempo of the same direction, already in quarters", () => {
    expect(markedTempo(mm("half", false, 60, `<sound tempo="118"/>`))).toBe(118);
  });
  it("stays inside what the server accepts, 40 to 400", () => {
    expect(defaultTempo(score(`<direction><sound tempo="20"/></direction>`))).toBe(40);
    expect(defaultTempo(score(`<direction><sound tempo="900"/></direction>`))).toBe(400);
  });
  it("takes the first marking of the score", () => {
    expect(markedTempo(score(`<direction><sound tempo="60"/></direction><direction><sound tempo="140"/></direction>`))).toBe(60);
  });
  it("is null when the score has none or the document is not XML", () => {
    expect(markedTempo(score(`<note/>`))).toBeNull();
    expect(markedTempo("not xml <<")).toBeNull();
  });
  it("is 90 when the score has no marking, the marking otherwise", () => {
    expect(defaultTempo(score(`<note/>`))).toBe(90);
    expect(defaultTempo(score(`<direction><sound tempo="112.5"/></direction>`))).toBe(113);
  });
});

describe("the range around a marking", () => {
  it("is the slider's 40 to 180 unless the marking falls outside, so reset is always reachable", () => {
    expect(tempoRange(90)).toEqual({ min: 40, max: 180 });
    expect(tempoRange(208)).toEqual({ min: 40, max: 208 });
    expect(tempoRange(30)).toEqual({ min: 30, max: 180 });
  });
});
