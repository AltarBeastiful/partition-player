/**
 * Plan 0004, step 3's check: the passes the app derives from what it read (the engine's repeat signs
 * and the lyrics it placed) against the hand-written truth of how each song is sung. The song runs in
 * bench/out predate the pipeline keeping repeat signs, so the engine's signs are put back into the
 * saved score by measure index. Writes bench/out/form.txt.
 */
import { existsSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { it } from "vitest";
import { defaultPasses, type Pass } from "./form";

const BENCH = resolve(process.cwd(), "../bench");

function withRepeats(scoreXml: string, engineXml: string): Document {
  const parser = new DOMParser();
  const score = parser.parseFromString(scoreXml, "application/xml");
  const engine = parser.parseFromString(engineXml, "application/xml");
  const sm = Array.from(score.querySelector("part")!.querySelectorAll(":scope > measure"));
  const em = Array.from(engine.querySelector("part")!.querySelectorAll(":scope > measure"));
  em.forEach((m, i) => {
    const target = sm[i];
    if (!target) return;
    for (const b of Array.from(m.querySelectorAll(":scope > barline"))) {
      const repeat = b.querySelector("repeat");
      if (!repeat) continue;
      // as postprocess now normalizes them: the location and the style follow the direction
      const forward = repeat.getAttribute("direction") === "forward";
      const copy = score.createElement("barline");
      copy.setAttribute("location", forward ? "left" : "right");
      const style = score.createElement("bar-style"); style.textContent = forward ? "heavy-light" : "light-heavy"; copy.appendChild(style);
      const r = score.createElement("repeat"); r.setAttribute("direction", forward ? "forward" : "backward"); copy.appendChild(r);
      if (forward) target.insertBefore(copy, target.firstChild); else target.appendChild(copy);
    }
  });
  return score;
}

const text = (passes: Pass[]) => passes.map((p) => `${p.ranges.map((r) => `${r.from}-${r.to}`).join("+")}${p.verse !== null ? ` v${p.verse}` : ""}`).join(" | ");

/**
 * How much hand work the page leaves: the passes to add, remove or change to turn the automatic
 * list into the truth (plan 0007). This is the number the form panel is judged on — the exact-match
 * column above says how often the panel is not needed at all, this one how long the visit is.
 */
function passEdits(a: Pass[], b: Pass[]): number {
  const x = a.map((p) => text([p])), y = b.map((p) => text([p]));
  const d: number[][] = Array.from({ length: x.length + 1 }, (_, i) => Array.from({ length: y.length + 1 }, (_, j) => (i === 0 ? j : j === 0 ? i : 0)));
  for (let i = 1; i <= x.length; i++) {
    for (let j = 1; j <= y.length; j++) {
      d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (x[i - 1] === y[j - 1] ? 0 : 1));
    }
  }
  return d[x.length][y.length];
}

const median = (xs: number[]) => {
  const s = [...xs].sort((a, b) => a - b);
  return s.length === 0 ? 0 : s.length % 2 ? s[(s.length - 1) / 2] : (s[s.length / 2 - 1] + s[s.length / 2]) / 2;
};
const order = (passes: Pass[]) => passes.flatMap((p) => p.ranges.flatMap((r) => Array.from({ length: r.to - r.from + 1 }, (_, i) => r.from + i))).join(",");

it("scores the automatic form of every song run against the hand truth", async () => {
  (HTMLCanvasElement.prototype as any).getContext = function () {
    return { font: "", fillStyle: "", measureText: (t: string) => ({ width: 8 * (t ? t.length : 1), actualBoundingBoxAscent: 8, actualBoundingBoxDescent: 2 }), save() {}, restore() {}, fillText() {}, scale() {}, translate() {}, beginPath() {}, moveTo() {}, lineTo() {}, stroke() {}, fill() {}, clearRect() {}, fillRect() {}, arc() {}, closePath() {}, setTransform() {}, getImageData() { return { data: [] }; } };
  };
  const { OpenSheetMusicDisplay } = await import("opensheetmusicdisplay");
  const runs = resolve(BENCH, "out/songs/leadsheets/run");
  const lines: string[] = [];
  let exact = 0, sameOrder = 0, sameCount = 0, n = 0, versesFound = 0, versesPrinted = 0;
  const edits: number[] = [];
  const newRanges: number[] = [];
  for (const name of readdirSync(runs).sort()) {
    const base = name.endsWith("_photo") ? name.slice(0, -6) : name;
    const truthPath = resolve(BENCH, `songs/leadsheets/${base}.form.json`);
    const scorePath = resolve(runs, name, "score.musicxml");
    const enginePath = resolve(runs, name, "homr/engine.musicxml");
    if (!existsSync(truthPath) || !existsSync(scorePath) || !existsSync(enginePath)) continue;
    const truth: Pass[] = JSON.parse(readFileSync(truthPath, "utf8")).passes.map((p: { ranges: number[][]; verse: number | null }) => ({ ranges: p.ranges.map(([from, to]) => ({ from, to })), verse: p.verse }));
    const host = document.createElement("div");
    document.body.appendChild(host);
    const osmd = new OpenSheetMusicDisplay(host, { autoResize: false, drawingParameters: "compacttight" });
    let got: Pass[] = [];
    try {
      await osmd.load(withRepeats(readFileSync(scorePath, "utf8"), readFileSync(enginePath, "utf8")));
      got = defaultPasses(osmd);
    } catch (e) {
      lines.push(`${name}: OSMD could not load the score: ${(e as Error).message}`);
      continue;
    }
    host.remove();
    n++;
    const ok = text(got) === text(truth);
    const okOrder = order(got) === order(truth);
    const okCount = got.length === truth.length;
    exact += ok ? 1 : 0; sameOrder += okOrder ? 1 : 0; sameCount += okCount ? 1 : 0;
    const printed = Math.max(0, ...truth.map((p) => p.verse ?? 0));
    const found = Math.max(0, ...got.map((p) => p.verse ?? 0));
    versesPrinted += printed; versesFound += Math.min(found, printed);
    const edit = passEdits(got, truth);
    edits.push(edit);
    if (edit > 0) {
      const has = new Set(got.map((p) => p.ranges.map((r) => `${r.from}-${r.to}`).join("+")));
      newRanges.push(truth.filter((p) => !has.has(p.ranges.map((r) => `${r.from}-${r.to}`).join("+"))).length > 0 ? 1 : 0);
    }
    lines.push(`${ok ? "ok   " : okOrder ? "order" : okCount ? "count" : "no   "} ${name} (${edit} pass edit${edit === 1 ? "" : "s"} from the truth)\n      app   ${text(got)}\n      truth ${text(truth)}`);
  }
  const work = edits.filter((e) => e > 0);
  const hand = `pages needing the panel ${work.length}: pass edits median ${median(work)}, mean ${(work.reduce((a, b) => a + b, 0) / Math.max(1, work.length)).toFixed(1)}, worst ${Math.max(0, ...work)}; a section the app never proposed on ${newRanges.reduce((a, b) => a + b, 0)} of them`;
  const summary = `pages ${n}: exact ${exact} (${(exact / n * 100).toFixed(0)} %), same measure order ${sameOrder} (${(sameOrder / n * 100).toFixed(0)} %), same pass count ${sameCount}; verses sung ${versesFound} of ${versesPrinted} printed\n${hand}`;
  writeFileSync(resolve(BENCH, "out/form.txt"), summary + "\n\n" + lines.join("\n") + "\n");
  console.log(summary);
});
