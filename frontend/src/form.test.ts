/**
 * Plan 0004: the default pass list is OSMD's expansion of the repeat signs with the verse multiplier.
 * OSMD runs headless here (jsdom, a stub canvas) on the benchmark truth files, so an OSMD upgrade that
 * changes its expansion is caught.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import JSZip from "jszip";
import { beforeAll, describe, expect, it } from "vitest";
import { UNDER_PASS, defaultPasses, resolveUnders, describePasses, expandForm, formFromPasses, parseForm, preset, remapForm, sliceRanges, underSlices, type Form, type Pass, type Section, type Under } from "./form";

let OpenSheetMusicDisplay: typeof import("opensheetmusicdisplay").OpenSheetMusicDisplay;

beforeAll(async () => {
  // VexFlow measures text on a canvas; jsdom has none.
  (HTMLCanvasElement.prototype as any).getContext = function () {
    return {
      font: "", fillStyle: "", measureText: (t: string) => ({ width: 8 * (t ? t.length : 1), actualBoundingBoxAscent: 8, actualBoundingBoxDescent: 2 }),
      save() {}, restore() {}, fillText() {}, scale() {}, translate() {}, beginPath() {}, moveTo() {}, lineTo() {}, stroke() {}, fill() {},
      clearRect() {}, fillRect() {}, arc() {}, closePath() {}, setTransform() {}, getImageData() { return { data: [] }; },
    };
  };
  ({ OpenSheetMusicDisplay } = await import("opensheetmusicdisplay"));
});

async function truth(name: string): Promise<string> {
  const zip = await JSZip.loadAsync(readFileSync(resolve(process.cwd(), `../bench/songs/leadsheets/${name}.mxl`)));
  const entry = Object.keys(zip.files).find((f) => !f.startsWith("META-INF") && /\.(xml|musicxml)$/.test(f))!;
  return zip.files[entry].async("string");
}

async function passesOf(xml: string): Promise<{ passes: Pass[]; measures: number }> {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const osmd = new OpenSheetMusicDisplay(host, { autoResize: false, drawingParameters: "compacttight" });
  await osmd.load(xml);
  const passes = defaultPasses(osmd);
  return { passes, measures: osmd.Sheet.SourceMeasures.length };
}

const text = (passes: Pass[]) => passes.map((p) => `${p.ranges.map((r) => `${r.from}-${r.to}`).join("+")}${p.verse !== null ? ` v${p.verse}` : ""}`).join(" | ");

describe("defaultPasses on the benchmark truth", () => {
  it("plays a page with no repeat sign once per stacked verse", async () => {
    const { passes, measures } = await passesOf(await truth("de_die_gedanken_sind_frei"));
    expect(measures).toBe(17);
    expect(text(passes)).toBe("0-16 v1 | 0-16 v2 | 0-16 v3 | 0-16 v4");
  }, 30_000);

  it("sings the chorus after every verse when many verses are stacked under a repeat and a single-lyric part follows", async () => {
    const { passes } = await passesOf(await truth("en_camptown_races"));
    expect(text(passes)).toBe("0-8 v1 | 9-16 | 0-8 v2 | 9-16 | 0-8 v3 | 9-16 | 0-8 v4 | 9-16 | 0-8 v5 | 9-16 | 0-8 v6 | 9-16 | 0-8 v7 | 9-16 | 0-8 v8 | 9-16");
  }, 30_000);

  it("takes the endings in turn", async () => {
    const { passes } = await passesOf(await truth("es_alfonsina_y_el_mar"));
    expect(text(passes)).toBe("0-8 | 9-20 v1 | 9-19+21-33 v2");
  }, 30_000);

  it("follows three endings and Fine", async () => {
    const { passes } = await passesOf(await truth("fr_la_marche_des_rois"));
    expect(text(passes)).toBe("0-0 | 1-19 v1 | 1-7+9-19 v2 | 1-7+11-19 v3");
  }, 30_000);

  it("repeats the verses of Kristallen and plays its end once", async () => {
    const { passes } = await passesOf(await truth("sv_kristallen_den_fina"));
    expect(text(passes)).toBe("0-4 v1 | 0-4 v2 | 5-15");
  }, 30_000);

  it("sings the page once per verse when stacked verses continue outside the repeat", async () => {
    const { passes } = await passesOf(await truth("en_my_grandfathers_clock"));
    expect(text(passes)).toBe("0-4 v1 | 5-9 v1 | 10-22 | 0-4 v2 | 5-9 v2 | 10-22 | 0-4 v3 | 5-9 v3 | 10-22 | 0-4 v4 | 5-9 v4 | 10-22 | 0-4 v5 | 5-9 v5 | 10-22 | 0-4 v6 | 5-9 v6 | 10-22");
  }, 30_000);

  it("keeps a third ending that runs to the end of the page in one pass", async () => {
    const { passes } = await passesOf(await truth("fr_les_gens_bien_eleves"));
    expect(text(passes)).toBe("0-3 | 4-35 v1 | 4-35 v2 | 4-19+36-57 v3");
  }, 30_000);
});

describe("forms", () => {
  const printed: Pass[] = [{ ranges: [{ from: 0, to: 8 }], verse: 1 }, { ranges: [{ from: 0, to: 8 }], verse: 2 }, { ranges: [{ from: 9, to: 16 }], verse: null }];

  it("turns the printed passes into named sections and back", () => {
    const form = formFromPasses(printed, 17);
    expect(form.sections).toEqual([{ name: "Verse", from: 0, to: 8 }, { name: "Part A", from: 9, to: 16 }]);
    expect(form.passes).toEqual([{ section: 0, verse: 1 }, { section: 0, verse: 2 }, { section: 1, verse: null }]);
    expect(text(expandForm(form, 17))).toBe("0-8 v1 | 0-8 v2 | 9-16");
    expect(describePasses(printed, form)).toBe("Verse 1 · Verse 2 · Part A");
  });

  it("presets: once per verse, and the chorus after every verse", () => {
    expect(text(expandForm(preset("verses", printed, 3, 17), 17))).toBe("0-16 v1 | 0-16 v2 | 0-16 v3");
    expect(text(expandForm(preset("chorus", printed, 3, 17), 17))).toBe("0-8 v1 | 9-16 | 0-8 v2 | 9-16 | 0-8 v3 | 9-16");
  });

  it("folds a pass played twice in a row into one chip with a count", () => {
    const doubled: Pass[] = [
      { ranges: [{ from: 0, to: 8 }], verse: 1 }, { ranges: [{ from: 9, to: 16 }], verse: null }, { ranges: [{ from: 9, to: 16 }], verse: null },
      { ranges: [{ from: 0, to: 8 }], verse: 2 }, { ranges: [{ from: 9, to: 16 }], verse: null },
    ];
    const form = formFromPasses(doubled, 17);
    expect(form.passes).toEqual([
      { section: 0, verse: 1 }, { section: 1, verse: null, times: 2 }, { section: 0, verse: 2 }, { section: 1, verse: null },
    ]);
    expect(describePasses(doubled, form)).toBe("Verse 1 · Chorus ×2 · Verse 2 · Chorus");
    expect(text(expandForm(form, 17))).toBe(text(doubled)); // the fold plays exactly what it folded
  });

  it("presets build on the sections the panel already has", () => {
    const mine: Form = { sections: [{ name: "Verse", from: 0, to: 10 }, { name: "Chorus", from: 11, to: 18 }], passes: [{ section: 0, verse: 1 }] };
    const made = preset("chorus", printed, 2, 19, { current: mine });
    expect(made.sections).toEqual(mine.sections); // not the half-page guess, and not the printed ones
    expect(text(expandForm(made, 19))).toBe("0-10 v1 | 11-18 | 0-10 v2 | 11-18");
    const twice = preset("chorus", printed, 2, 19, { current: mine, chorusTwice: true });
    expect(describePasses(expandForm(twice, 19), twice)).toBe("Verse 1 · Chorus ×2 · Verse 2 · Chorus ×2");
    // with nothing to build on it still invents them, as before
    expect(text(expandForm(preset("chorus", printed, 3, 17), 17))).toBe("0-8 v1 | 9-16 | 0-8 v2 | 9-16 | 0-8 v3 | 9-16");
  });

  it("reads a form written as one line", () => {
    const sections: Section[] = [{ name: "Verse", from: 0, to: 10 }, { name: "Chorus", from: 11, to: 18 }];
    const anton = parseForm("V1 C×2 V2 C×2 V3 C V4 C×2 V5 C×2", sections);
    expect(anton.error).toBeNull();
    const form: Form = { sections, passes: anton.passes! };
    expect(expandForm(form, 19)).toHaveLength(14);
    expect(describePasses(expandForm(form, 19), form))
      .toBe("Verse 1 · Chorus ×2 · Verse 2 · Chorus ×2 · Verse 3 · Chorus · Verse 4 · Chorus ×2 · Verse 5 · Chorus ×2");
  });

  it("takes the summary's own line back, dots and all", () => {
    const sections: Section[] = [{ name: "Verse", from: 0, to: 10 }, { name: "Chorus", from: 11, to: 18 }];
    const form: Form = { sections, passes: [{ section: 0, verse: 1 }, { section: 1, verse: null, times: 2 }] };
    const line = describePasses(expandForm(form, 19), form);
    expect(line).toBe("Verse 1 · Chorus ×2");
    expect(parseForm(line, sections).passes).toEqual(form.passes);
    expect(parseForm("verse 1 x2 · chorus", sections).passes).toEqual([{ section: 0, verse: 1, times: 2 }, { section: 1, verse: null }]);
  });

  it("refuses a line it cannot place, and says why", () => {
    const sections: Section[] = [{ name: "Verse", from: 0, to: 10 }, { name: "Chorus", from: 11, to: 18 }, { name: "Coda", from: 18, to: 18 }];
    expect(parseForm("V1 Bridge", sections).error).toMatch(/no section called “Bridge”/);
    expect(parseForm("V1 C", sections).error).toMatch(/fits Chorus and Coda/);
    expect(parseForm("", sections).error).toMatch(/Name a section/);
    expect(parseForm("Verse×99", sections).error).toMatch(/1 to 50/);
    expect(parseForm("V1", []).error).toMatch(/no section to play/);
    expect(parseForm("V1 Bridge", sections).passes).toBeNull(); // nothing is applied from a bad line
  });

  it("names a section with a space when it is quoted", () => {
    const sections: Section[] = [{ name: "Verse 2", from: 0, to: 4 }, { name: "Chorus", from: 5, to: 9 }];
    expect(parseForm('"Verse 2" 3 · Chorus', sections).passes).toEqual([{ section: 0, verse: 3 }, { section: 1, verse: null }]);
  });

  it("follows its measures through a merge and a deleted edge", () => {
    const form = formFromPasses(printed, 17);
    const merged = remapForm(form, (i) => (i === 9 ? 8 : i > 9 ? i - 1 : i)); // measure 9 merged into 8
    expect(merged.sections.map((s) => [s.from, s.to])).toEqual([[0, 8], [8, 15]]);
    const cut = remapForm(form, (i) => (i === 0 ? null : i - 1)); // the first measure deleted
    expect(cut.sections.map((s) => [s.from, s.to])).toEqual([[0, 7], [8, 15]]);
    expect(cut.passes.length).toBe(3);
  });
});

describe("underSlices: a line that goes on playing underneath (plan 0011, step 4)", () => {
  /** The canon page's shape: twenty 4/4 measures, except measure 19 (index 18), which is 6/4. */
  const durations = Array.from({ length: 20 }, (_, i) => (i === 18 ? 1.5 : 1));
  const wholePage: Pass[] = [{ ranges: [{ from: 0, to: 19 }], verse: null }];
  const flute: Under = { line: 0, from: 0, to: 7, startAt: 8, instrument: "flute" };
  const slices = () => sliceRanges(wholePage, durations, 20);
  const total = () => durations.reduce((a, b) => a + b, 0);

  it("starts where the form first reaches its measure and fills to the end", () => {
    const tiles = underSlices(flute, durations, 20, slices(), total());
    expect(tiles[0].origin).toBe(8);                       // the voices' first measure
    const end = tiles[tiles.length - 1];
    expect(end.origin + end.to).toBeCloseTo(total(), 9);   // and not a beat further
    expect(tiles.every((t) => t.pass === UNDER_PASS)).toBe(true);
  });

  it("lays one round and a half of eight measures under twelve", () => {
    const tiles = underSlices(flute, durations, 20, slices(), total());
    expect(tiles.map((t) => t.measure)).toEqual([0, 1, 2, 3, 4, 5, 6, 7, 0, 1, 2, 3, 4]);
    expect(tiles.filter((t) => t.cut)).toHaveLength(1);
    expect(tiles[tiles.length - 1]).toMatchObject({ measure: 4, from: 0, to: 0.5, cut: true });
  });

  it("stays on time when the page turns 6/4 in the middle, so the tiles leave the barlines", () => {
    const tiles = underSlices(flute, durations, 20, slices(), total());
    // the twelfth tile starts half a whole note after the printed measure it runs under, because
    // measure 19 of the page is longer than the measures the flute is looping
    expect(tiles[8].origin).toBe(16);
    expect(tiles[12].origin).toBe(20);
    expect(total()).toBe(20.5);
  });

  it("gives nothing when the form never reaches the measure it should start at", () => {
    const short: Pass[] = [{ ranges: [{ from: 0, to: 3 }], verse: null }];
    expect(underSlices(flute, durations, 20, sliceRanges(short, durations, 20), 4)).toEqual([]);
  });

  it("reads a reversed range as the one measure it names", () => {
    const empty: Under = { ...flute, from: 5, to: 4 };
    const tiles = underSlices(empty, durations, 20, slices(), total());
    expect(tiles.map((t) => t.measure)).toEqual(Array(13).fill(5)); // from..to reversed is one measure
  });
});

describe("a line that goes on playing, counted (plan 0011, follow-up)", () => {
  const durations = Array.from({ length: 20 }, () => 1);
  const wholePage: Pass[] = [{ ranges: [{ from: 0, to: 19 }], verse: null }];
  const slices = () => sliceRanges(wholePage, durations, 20);
  const flute: Under = { line: 0, from: 0, to: 7, startAt: 8, instrument: "flute" };

  it("fills the form's time when no count is given, as an ostinato does", () => {
    const tiles = underSlices(flute, durations, 20, slices(), 20);
    expect(tiles).toHaveLength(12);                       // measures 9 to 20: a round and a half
  });

  it("plays exactly the rounds it is asked for, and then stops", () => {
    const twice = underSlices({ ...flute, times: 2 }, durations, 20, slices(), 32);
    expect(twice).toHaveLength(16);                       // two rounds of eight measures
    expect(twice.map((t) => t.measure)).toEqual([0, 1, 2, 3, 4, 5, 6, 7, 0, 1, 2, 3, 4, 5, 6, 7]);
    const once = underSlices({ ...flute, times: 1 }, durations, 20, slices(), 32);
    expect(once).toHaveLength(8);
  });

  it("is still cut where the form ends, however many rounds it was promised", () => {
    const tiles = underSlices({ ...flute, times: 5 }, durations, 20, slices(), 20);
    expect(tiles).toHaveLength(12);                       // twelve measures left, not forty
    expect(tiles[tiles.length - 1].measure).toBe(3);
  });
});

describe("resolveUnders: coming in with a section (plan 0011, follow-up)", () => {
  const form: Form = {
    sections: [{ name: "Flute", from: 0, to: 7 }, { name: "Voices", from: 8, to: 19 }],
    passes: [{ section: 0, verse: null }, { section: 1, verse: null }],
  };
  const under: Under = { line: 0, from: 0, to: 7, startAt: 0, instrument: "flute", startSection: 1 };

  it("comes in where its section begins, not where its number says", () => {
    expect(resolveUnders([under], form)[0].startAt).toBe(8);
  });

  it("follows the section when it moves", () => {
    const moved: Form = { ...form, sections: [form.sections[0], { ...form.sections[1], from: 10 }] };
    expect(resolveUnders([under], moved)[0].startAt).toBe(10);
  });

  it("leaves a bare measure alone, and keeps the last measure when the section is gone", () => {
    expect(resolveUnders([{ ...under, startSection: undefined, startAt: 8 }], form)[0].startAt).toBe(8);
    expect(resolveUnders([under], null)[0].startAt).toBe(0);
    expect(resolveUnders([{ ...under, startSection: 9 }], form)[0].startAt).toBe(0);
  });
});
