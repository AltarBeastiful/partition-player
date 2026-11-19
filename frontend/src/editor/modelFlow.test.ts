/**
 * The confirm step of Check with a model (ADR 0010, ticket 04): nothing that costs money runs until
 * the user has seen the estimate and said yes, and the visitor's key lives in memory only. The
 * network is the only thing replaced.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ModelDraft, ModelEstimate } from "../api";

vi.mock("../api", async (orig) => ({ ...(await orig<typeof import("../api")>()), estimateModelPass: vi.fn(), runModelPass: vi.fn() }));
import * as api from "../api";
import { ModelFlow, MODEL_NOTICE, modelNotice, visitorKey } from "./modelFlow";

const spans = [{ staff: 0, from: 0, to: 3, lyrics_source: "Lors-que" }];
const estimate: ModelEstimate = { calls: 2, estimated_tokens: 3000, estimated_cost_usd: 0.0123, model: "m", vision: true, confirm: false };
const draft = { id: "d1" } as ModelDraft;

beforeEach(() => {
  vi.mocked(api.estimateModelPass).mockResolvedValue(estimate);
  vi.mocked(api.runModelPass).mockResolvedValue(draft);
  visitorKey.set("");
});
afterEach(() => { vi.clearAllMocks(); localStorage.clear(); sessionStorage.clear(); });

describe("ModelFlow", () => {
  it("asking only fetches the estimate and runs nothing", async () => {
    const flow = new ModelFlow("j1");
    await flow.ask(spans);
    expect(flow.estimate).toEqual(estimate);
    expect(api.estimateModelPass).toHaveBeenCalledTimes(1);
    expect(api.runModelPass).not.toHaveBeenCalled();
  });

  it("confirming runs the same spans and hands back the draft", async () => {
    const flow = new ModelFlow("j1");
    await flow.ask(spans);
    expect(await flow.confirm()).toBe(draft);
    expect(api.runModelPass).toHaveBeenCalledWith("j1", { spans });
    expect(flow.estimate).toBeNull();
  });

  it("confirm without an estimate runs nothing", async () => {
    expect(await new ModelFlow("j1").confirm()).toBeNull();
    expect(api.runModelPass).not.toHaveBeenCalled();
  });

  it("cancelling drops the estimate so a confirm cannot follow", async () => {
    const flow = new ModelFlow("j1");
    await flow.ask(spans);
    flow.cancel();
    expect(await flow.confirm()).toBeNull();
    expect(api.runModelPass).not.toHaveBeenCalled();
  });

  it("an estimate error is kept and nothing can be confirmed", async () => {
    vi.mocked(api.estimateModelPass).mockRejectedValue(new Error("over the cap"));
    const flow = new ModelFlow("j1");
    await flow.ask(spans);
    expect(flow.error).toBe("over the cap");
    expect(await flow.confirm()).toBeNull();
  });

  it("the visitor's key goes with both calls, is shared by flows, and is written to no storage", async () => {
    visitorKey.set("sk-visitor");
    const flow = new ModelFlow("j1");
    await flow.ask(spans);
    await flow.confirm();
    expect(api.estimateModelPass).toHaveBeenCalledWith("j1", { spans, api_key: "sk-visitor" });
    expect(api.runModelPass).toHaveBeenCalledWith("j1", { spans, api_key: "sk-visitor" });
    expect(visitorKey.get()).toBe("sk-visitor");
    for (const s of [localStorage, sessionStorage]) expect(JSON.stringify({ ...s })).not.toContain("sk-visitor");
  });

  it("the notice says that crops leave the server for the provider", () => {
    expect(MODEL_NOTICE).toMatch(/sent to/i);
    expect(modelNotice("DeepSeek")).toMatch(/DeepSeek/);
    expect(MODEL_NOTICE).toMatch(/picture of words/);
  });
});
