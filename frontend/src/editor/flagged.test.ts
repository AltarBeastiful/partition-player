/**
 * "This looks wrong" (ADR 0010, plan 0016): in edit mode the user flags a measure range, with a note to the
 * model. The flags are session state beside the doubts; they go through the same pass, flow and draft.
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
const session = (doubts: ReviewState["doubts"] = []) => { vi.useFakeTimers(); return new EditorSession("t", XML, { ...base, doubts }); };

afterEach(() => { vi.useRealTimers(); vi.clearAllMocks(); });

describe("flagging a measure range", () => {
  it("flags the selected measure and keeps what the user wrote", () => {
    const s = session();
    s.selectMeasure(3);
    s.flagSelected();
    s.setFlagNote(0, "a triplet here");
    expect(s.flagged).toEqual([{ staff: 0, from: 3, to: 3, note: "a triplet here" }]);
    s.dispose();
  });

  it("joins a flag to the neighbouring one on the same staff and flags nothing twice", () => {
    const s = session();
    s.flag({ staff: 0, from: 2, to: 3 });
    s.flag({ staff: 0, from: 4, to: 5 });
    s.flag({ staff: 0, from: 3, to: 4 });
    s.flag({ staff: 1, from: 2, to: 2 });
    expect(s.flagged.map((f) => [f.staff, f.from, f.to])).toEqual([[0, 2, 5], [1, 2, 2]]);
    s.unflag(0);
    expect(s.flagged.map((f) => [f.staff, f.from, f.to])).toEqual([[1, 2, 2]]);
    s.dispose();
  });

  it("asks the model about the flagged spans, the user's note first and the engine's doubts after it", async () => {
    const s = session([{ measure: 3, kind: "overfull", text: "longer", level: "wrong" }]);
    s.flag({ staff: 0, from: 3, to: 4 }, "I see a triplet");
    vi.mocked(api.estimateModelPass).mockResolvedValue({ calls: 1, estimated_tokens: 10, estimated_cost_usd: 0.1, model: "m", confirm: false } as ModelEstimate);
    vi.mocked(api.runModelPass).mockResolvedValue({ spans: [], changes: [], dropped: [] } as unknown as ModelDraft);
    const flow = new ModelFlow("t");
    await flow.ask(s.flaggedSpans());
    const sent = vi.mocked(api.estimateModelPass).mock.calls[0][1].spans;
    expect(sent).toHaveLength(1);
    expect(sent[0]).toMatchObject({ staff: 0, from: 3, to: 4, needs_image: false });
    expect(sent[0].note).toMatch(/^I see a triplet/);
    expect(sent[0].note).toContain("longer");
    expect(api.runModelPass).not.toHaveBeenCalled();
    s.dispose();
  });
});
