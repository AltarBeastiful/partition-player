/**
 * Plan 0016: a score that arrives without beam markup (a photographed page, an import that has none)
 * is engraved with OSMD's autoBeam; a score that carries its own beams is engraved as written. Checked
 * on what is drawn (the beams in the SVG), through the one function the views call before `load`.
 */
import { beforeAll, describe, expect, it } from "vitest";
import { hasBeamMarkup, chooseBeams } from "./beaming";

let OpenSheetMusicDisplay: typeof import("opensheetmusicdisplay").OpenSheetMusicDisplay;

beforeAll(async () => {
  (HTMLCanvasElement.prototype as any).getContext = function () {
    return {
      font: "", fillStyle: "", measureText: (t: string) => ({ width: 8 * (t ? t.length : 1), actualBoundingBoxAscent: 8, actualBoundingBoxDescent: 2 }),
      save() {}, restore() {}, fillText() {}, scale() {}, translate() {}, beginPath() {}, moveTo() {}, lineTo() {}, stroke() {}, fill() {},
      clearRect() {}, fillRect() {}, arc() {}, closePath() {}, setTransform() {}, getImageData() { return { data: [] }; },
    };
  };
  ({ OpenSheetMusicDisplay } = await import("opensheetmusicdisplay"));
});

/** One 4/4 measure of eight eighth notes; `beams` is the beam state of each, or null for no markup. */
function eighths(beams: (string | null)[]): string {
  const pitches = ["C", "D", "E", "F", "G", "A", "B", "C"];
  const notes = pitches.map((step, i) => `<note><pitch><step>${step}</step><octave>${i === 7 ? 5 : 4}</octave></pitch><duration>1</duration><type>eighth</type>${beams[i] ? `<beam number="1">${beams[i]}</beam>` : ""}</note>`).join("");
  return `<?xml version="1.0"?><score-partwise version="3.1"><part-list><score-part id="P1"><part-name>P</part-name></score-part></part-list>
<part id="P1"><measure number="1"><attributes><divisions>2</divisions><key><fifths>0</fifths></key><time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef></attributes>${notes}</measure></part></score-partwise>`;
}

const PLAIN = eighths(Array(8).fill(null));
// Written as two groups of three and a pair left alone: begin, continue, end, begin, continue, end, then two unbeamed.
const OWN = eighths(["begin", "continue", "end", "begin", "continue", "end", null, null]);

async function beamsDrawn(xml: string): Promise<number> {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const osmd = new OpenSheetMusicDisplay(host, { autoResize: false, drawingParameters: "compacttight" });
  chooseBeams(osmd, xml);
  await osmd.load(xml);
  osmd.render();
  const n = host.querySelectorAll(".vf-beam").length;
  host.remove();
  return n;
}

describe("beams", () => {
  it("knows a score with beam markup from one without", () => {
    expect(hasBeamMarkup(PLAIN)).toBe(false);
    expect(hasBeamMarkup(OWN)).toBe(true);
  });

  it("beams a score that has no beam markup", async () => {
    expect(await beamsDrawn(PLAIN)).toBeGreaterThan(0);
  }, 30_000);

  it("draws the beams a score carries, as written and no others", async () => {
    expect(await beamsDrawn(OWN)).toBe(2);
  }, 30_000);
});
