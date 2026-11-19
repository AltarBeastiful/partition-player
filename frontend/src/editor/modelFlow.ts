import { estimateModelPass, runModelPass } from "../api";
import type { ModelDraft, ModelEstimate, ModelPassRequest } from "../api";

/** Shown with the button (ADR 0010): what leaves the server. */
export function modelNotice(provider = "Anthropic"): string {
  return `Crops of your score, the words you pasted and any picture of words you add are sent to the model's provider (${provider}).`;
}
export const MODEL_NOTICE = modelNotice();

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
  private larger = false;

  constructor(private readonly jobId: string) {}

  private request(): ModelPassRequest {
    const k = visitorKey.get();
    const route = this.routeId ? { route: this.routeId } : {};
    const more = this.larger ? { larger: true } : {};
    return k ? { spans: this.spans, api_key: k, ...route, ...more } : { spans: this.spans, ...route, ...more };
  }

  async ask(spans: ModelPassRequest["spans"]): Promise<void> {
    this.larger = false;
    await this.estimateFor(spans);
  }

  /** Try harder (ticket 08): this one span again, straight to the route's larger model. */
  async askHarder(span: ModelPassRequest["spans"][number]): Promise<void> {
    this.larger = true;
    await this.estimateFor([span]);
  }

  private async estimateFor(spans: ModelPassRequest["spans"]): Promise<void> {
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
