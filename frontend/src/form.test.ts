/**
 * Plan 0004: the default pass list is OSMD's expansion of the repeat signs with the verse multiplier.
 * OSMD runs headless here (jsdom, a stub canvas) on the benchmark truth files, so an OSMD upgrade that
 * changes its expansion is caught.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import JSZip from "jszip";
import { beforeAll, describe, expect, it } from "vitest";
import { defaultPasses, describePasses, expandForm, formFromPasses, preset, remapForm, type Pass } from "./form";

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

  it("follows its measures through a merge and a deleted edge", () => {
    const form = formFromPasses(printed, 17);
    const merged = remapForm(form, (i) => (i === 9 ? 8 : i > 9 ? i - 1 : i)); // measure 9 merged into 8
    expect(merged.sections.map((s) => [s.from, s.to])).toEqual([[0, 8], [8, 15]]);
    const cut = remapForm(form, (i) => (i === 0 ? null : i - 1)); // the first measure deleted
    expect(cut.sections.map((s) => [s.from, s.to])).toEqual([[0, 7], [8, 15]]);
    expect(cut.passes.length).toBe(3);
  });
});
