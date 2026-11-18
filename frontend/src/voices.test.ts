/**
 * The voice bank's table and the instrument lookup (plan 0011, step 2). Nothing here touches Tone's
 * audio: the table is data and `instrumentAt` is arithmetic over measure ranges.
 */
import { describe, expect, it } from "vitest";
import { DEFAULT_VOICE, PIANO, VOICES, instrumentAt, isVoice, outsideRange, voiceSet, type Voicing } from "./voices";

const NOTE = /^[A-G]#?-?\d$/;

describe("the table of sets", () => {
  it("offers the piano first and a handful of others", () => {
    expect(VOICES[0]).toBe(PIANO);
    expect(VOICES.length).toBeGreaterThan(8);
    expect(new Set(VOICES.map((v) => v.id)).size).toBe(VOICES.length);
  });

  it("names every sample with a note Tone can parse, and keeps every set small", () => {
    for (const set of VOICES) {
      const keys = Object.keys(set.urls);
      expect(keys.length, set.id).toBeGreaterThan(0);
      // the generated sets are thinned to 16; the piano keeps the 21 it has always fetched
      expect(keys.length, set.id).toBeLessThanOrEqual(set === PIANO ? 21 : 16);
      for (const key of keys) expect(key, `${set.id} ${key}`).toMatch(NOTE);
      for (const file of Object.values(set.urls)) expect(file, set.id).toMatch(/\.mp3$/);
    }
  });

  it("fetches every set from the pinned commit", () => {
    for (const set of VOICES.slice(1)) {
      expect(set.baseUrl, set.id).toContain("@622c2f1c32c8cfce4158ddc3eb26e518ddef37e5/");
    }
  });

  it("carries a written range that holds the samples it names", () => {
    for (const set of VOICES) expect(set.lowest, set.id).toBeLessThan(set.highest);
    expect(outsideRange(voiceSet("flute"), 60)).toBe(0);      // C4, the flute's lowest
    expect(outsideRange(voiceSet("flute"), 55)).toBe(5);      // the canon's lower voice, under the set
  });

  it("falls back to the piano for a name it does not know", () => {
    expect(voiceSet("ondes-martenot")).toBe(PIANO);
    expect(isVoice("flute")).toBe(true);
    expect(isVoice("ondes-martenot")).toBe(false);
  });
});

describe("instrumentAt", () => {
  const canon: Voicing[] = [
    { line: 0, from: 0, to: 7, instrument: "flute" },   // measures 1 to 8: the flute
    { line: 0, from: 8, to: 19, instrument: "piano" },  // from measure 9 the same staff is Vx. 1
  ];

  it("gives the piano when nothing is set", () => {
    expect(instrumentAt([], 0, 0)).toBe(DEFAULT_VOICE);
    expect(instrumentAt(canon, 1, 0)).toBe(DEFAULT_VOICE); // the other line has no entry
  });

  it("changes instrument at the measure the range says", () => {
    expect(instrumentAt(canon, 0, 0)).toBe("flute");
    expect(instrumentAt(canon, 0, 7)).toBe("flute");
    expect(instrumentAt(canon, 0, 8)).toBe("piano");
    expect(instrumentAt(canon, 0, 19)).toBe("piano");
  });

  it("lets a later entry win where two cover the same measure", () => {
    const over: Voicing[] = [{ line: 0, from: 0, to: 19, instrument: "organ" }, { line: 0, from: 4, to: 5, instrument: "harp" }];
    expect(instrumentAt(over, 0, 3)).toBe("organ");
    expect(instrumentAt(over, 0, 4)).toBe("harp");
    expect(instrumentAt(over, 0, 6)).toBe("organ");
  });
});
