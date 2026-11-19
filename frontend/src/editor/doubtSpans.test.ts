/**
 * Lyric spans from the engine's doubts (ADR 0010, ticket 08) and "Try harder": which stretches of the
 * score the panel offers, strongest doubt first, and that one span can be retried on its own with the
 * larger model. Only the network is replaced.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ModelDraft, ModelEstimate, ReviewState } from "../api";

vi.mock("../api", async (orig) => ({ ...(await orig<typeof import("../api")>()), estimateModelPass: vi.fn(), runModelPass: vi.fn() }));
import * as api from "../api";
import { EditorSession } from "./session";
import { ModelFlow } from "./modelFlow";

const XML = readFileSync(resolve(process.cwd(), "../bench/samples/anton_yvan_boris_ground_truth.musicxml"), "utf8");
const base: ReviewState = { doubts: [], checked: [], revision: 1, layout: null, has_image: false, has_original: false, form: null, lines: [], unders: [] };
const withDoubts = (doubts: ReviewState["doubts"]) => { vi.useFakeTimers(); return new EditorSession("t", XML, { ...base, doubts }); };

afterEach(() => { vi.useRealTimers(); vi.clearAllMocks(); });

describe("lyric spans from the doubts", () => {
  it("offers each doubtful stretch, strong doubts first, joining neighbouring measures of one staff", () => {
    const s = withDoubts([
      { measure: 2, kind: "heads_more", text: "a second reading disagrees", level: "check" },
      { measure: 3, kind: "heads_more", text: "a second reading disagrees", level: "check" },
      { measure: 7, kind: "overfull", text: "longer", level: "wrong" },
      { measure: 9, kind: "pickup", text: "a pickup", level: "info", info: true },
      { measure: 12, kind: "heads_more", text: "x", level: "check", part: 1 },
    ]);
    expect(s.doubtSpans()).toEqual([
      { staff: 0, from: 7, to: 7, level: "wrong" },
      { staff: 0, from: 2, to: 3, level: "check" },
      { staff: 1, from: 12, to: 12, level: "check" },
    ]);
    s.dispose();
  });

  it("offers nothing when the engine doubts nothing", () => {
    const s = withDoubts([]);
    expect(s.doubtSpans()).toEqual([]);
    s.dispose();
  });
});

describe("Try harder", () => {
  const estimate = { calls: 1, estimated_tokens: 10, estimated_cost_usd: 0.1, model: "big", confirm: false } as ModelEstimate;

  it("asks the larger model for the one span only", async () => {
    vi.mocked(api.estimateModelPass).mockResolvedValue(estimate);
    vi.mocked(api.runModelPass).mockResolvedValue({ id: "d2" } as ModelDraft);
    const flow = new ModelFlow("j1");
    const draftSpans = [{ staff: 0, from: 0, to: 1, lyrics_source: "a" }, { staff: 0, from: 4, to: 5, lyrics_source: "b" }];
    await flow.askHarder(draftSpans[1]);
    await flow.confirm();
    expect(api.runModelPass).toHaveBeenCalledWith("j1", { spans: [draftSpans[1]], larger: true });
  });

  it("an ordinary pass never asks for the larger model", async () => {
    vi.mocked(api.estimateModelPass).mockResolvedValue(estimate);
    const flow = new ModelFlow("j1");
    await flow.ask([{ staff: 0, from: 0, to: 1, lyrics_source: "a" }]);
    expect(vi.mocked(api.estimateModelPass).mock.calls[0][1]).not.toHaveProperty("larger");
  });
});
