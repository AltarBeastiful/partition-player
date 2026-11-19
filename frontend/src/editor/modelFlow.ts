import { estimateModelPass, runModelPass } from "../api";
import type { ModelDraft, ModelEstimate, ModelPassRequest } from "../api";

/** Shown with the button (ADR 0010): what leaves the server. */
export const MODEL_NOTICE = "Crops of your score and the words you pasted are sent to the model's provider (Anthropic by default).";

let key = "";
/** The visitor's own API key: held in this page's memory for the session, never written to any storage. */
export const visitorKey = { get: () => key, set: (k: string) => { key = k.trim(); } };

/**
 * Ask, then confirm (ticket 04): `ask` fetches the estimate and runs nothing, `confirm` runs exactly
 * the spans that were estimated, once, and only after an estimate came back.
 */
export class ModelFlow {
  estimate: ModelEstimate | null = null;
  error: string | null = null;
  /** The route the visitor picked (a preset name); empty is the server's default. */
  routeId = "";
  private spans: ModelPassRequest["spans"] = [];

  constructor(private readonly jobId: string) {}

  private request(): ModelPassRequest {
    const k = visitorKey.get();
    const route = this.routeId ? { route: this.routeId } : {};
    return k ? { spans: this.spans, api_key: k, ...route } : { spans: this.spans, ...route };
  }

  async ask(spans: ModelPassRequest["spans"]): Promise<void> {
    this.spans = spans; this.estimate = null; this.error = null;
    try { this.estimate = await estimateModelPass(this.jobId, this.request()); }
    catch (e) { this.error = (e as Error).message; }
  }

  async confirm(): Promise<ModelDraft | null> {
    if (!this.estimate) return null;
    this.estimate = null;
    try { return await runModelPass(this.jobId, this.request()); }
    catch (e) { this.error = (e as Error).message; return null; }
  }

  cancel(): void { this.estimate = null; }
}
