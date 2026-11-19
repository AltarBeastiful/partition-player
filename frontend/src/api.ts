export type JobStatus = "queued" | "preprocessing" | "recognizing" | "importing" | "postprocessing" | "done" | "failed";
/** Where the page came from (plan 0010): a photo the engine read, or a MusicXML file opened as it is. */
export type JobSource = "image" | "musicxml" | "pdf";

export interface Job {
  id: string;
  status: JobStatus;
  message: string;
  created_at: string;
  updated_at: string;
  input_name: string;
  source: JobSource;
  name: string;
  error: string | null;
  result: { engine: string; seconds: number; stats: Stats; pages?: PageInfo[]; text_source?: string } | null;
  edited_at?: string | null;
}

/** One page of a PDF, as the reader found it (plan 0012). */
export interface PageInfo { index: number; kind: "digital" | "outlined" | "scan"; dpi: number; measures: number; width_pt: number; height_pt: number }

export interface Stats {
  measures: number; notes: number; rests: number; padded_measures: number; warnings: string[];
  chords?: number; chord_warnings?: string[];
  chords_seen?: { system: number; text: string; reading: string; confidence: number; reason: string }[];
  lyrics_verses?: number; lyrics_syllables?: number; lyrics_read?: number; lyric_warnings?: string[];
  lyrics_seen?: { staff: number; text: string; reason: string }[];
  doubts?: Doubt[];
}

export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

async function check<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).error ?? msg; } catch { /* keep statusText */ }
    throw new ApiError(msg, r.status);
  }
  if (r.status === 204) return undefined as T;
  return r.json() as Promise<T>;
}

/** `name` is for a caller that already knows the score's name: the file's own title does not override it. */
export async function createJob(file: File, name?: string): Promise<Job> {
  const body = new FormData();
  body.append("file", file, file.name);
  if (name) body.append("name", name);
  return check<Job>(await fetch("/api/jobs", { method: "POST", body }));
}

export async function getJob(id: string): Promise<Job> {
  return check<Job>(await fetch(`/api/jobs/${id}`));
}

export async function listJobs(limit = 50): Promise<Job[]> {
  return check<Job[]>(await fetch(`/api/jobs?limit=${limit}`));
}

export async function renameJob(id: string, name: string): Promise<Job> {
  return check<Job>(await fetch(`/api/jobs/${id}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }),
  }));
}

export async function deleteJob(id: string): Promise<void> {
  return check<void>(await fetch(`/api/jobs/${id}`, { method: "DELETE" }));
}

export function scoreUrl(id: string, version = 0): string {
  return version ? `/api/jobs/${id}/score.musicxml?v=${version}` : `/api/jobs/${id}/score.musicxml`;
}

export interface LyricsState {
  verses: string[];      // one text per verse, in the editor convention
  syllables: number[];   // per verse
  notes: number;         // sounding notes in the score
  measures: number[];    // sounding notes per measure
}

export async function getLyrics(id: string): Promise<LyricsState> {
  return check<LyricsState>(await fetch(`/api/jobs/${id}/lyrics`));
}

export async function saveLyrics(id: string, verses: string[]): Promise<LyricsState> {
  return check<LyricsState>(await fetch(`/api/jobs/${id}/lyrics`, {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ verses }),
  }));
}

export function thumbUrl(id: string): string {
  return `/api/jobs/${id}/thumb.jpg`;
}

// ---- the editor (ADR 0005) ----

export interface Doubt { measure: number; part?: number; kind: string; text: string; info?: boolean; [k: string]: unknown }
export interface LayoutMeasure { index: number; x0: number; x1: number }
export interface LayoutSystem { index: number; x0: number; x1: number; top: number; bottom: number; unit: number; staves: { top: number; bottom: number }[]; measures: LayoutMeasure[] }
export interface Layout { width: number; height: number; systems: LayoutSystem[] }
/**
 * How the page is played (plan 0004): null is the automatic form from the repeat signs and the
 * verses. The shape is the one `form.ts` works in and the one the server stores; it was declared
 * twice until a `times` added on one side went missing on the other (plan 0007).
 */
import type { Form, Under } from "./form";
import type { Voicing } from "./voices";
import type { ModelRoute } from "./modelRoute";
export type { Form, FormPass, Section as FormSection } from "./form";
export type { Under } from "./form";
export type { Voicing } from "./voices";
/**
 * How the page sounds (plan 0011): `lines` is the instrument each staff plays over which measures,
 * `unders` the staves that go on playing underneath the form. Both are playback only and both are
 * empty for every score made before ADR 0008.
 */
export interface ReviewState { doubts: Doubt[]; checked: number[]; revision: number; layout: Layout | null; has_image: boolean; has_original: boolean; form: Form | null; lines: Voicing[]; unders: Under[]; model_readings?: AnyReading[] }
export interface SaveResult extends ReviewState { check: Doubt[]; stats: Stats }

export async function getReview(id: string): Promise<ReviewState> {
  return check<ReviewState>(await fetch(`/api/jobs/${id}/review`));
}

export async function getScoreText(id: string, version = 0): Promise<string> {
  const r = await fetch(scoreUrl(id, version || Date.now()));
  if (!r.ok) throw new ApiError(r.statusText, r.status);
  return r.text();
}

export async function saveScore(id: string, body: { musicxml: string; checked: number[]; revision: number; doubts: Doubt[]; form: Form | null; lines?: Voicing[]; unders?: Under[] }): Promise<SaveResult> {
  return check<SaveResult>(await fetch(`/api/jobs/${id}/score`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  }));
}

export async function revertScore(id: string): Promise<SaveResult> {
  return check<SaveResult>(await fetch(`/api/jobs/${id}/revert`, { method: "POST" }));
}

export function reviewImageUrl(id: string): string {
  return `/api/jobs/${id}/review.webp`;
}

// ---- the model pass (ADR 0010, plan 0016) ----

/** One staff over measures `from` to `to` (0-based, inclusive); `staff` is the part's index. */
export interface ModelSpan { staff: number; from: number; to: number; note?: string }
export interface Syllable { text: string; syllabic: "single" | "begin" | "middle" | "end" }
/**
 * One syllable the pass would write. `measure` and `onset` are 0-based, `onset` the rank among the
 * measure's sounding notes (the convention of lyrics.json); `verse` is 1-based. `old` null is a new
 * syllable, `new` null one that goes. `conflict` is a place edited by hand since the pass.
 */
export interface ModelChange { id: string; kind?: "lyric"; span: ModelSpan; verse: number; measure: number; onset: number; old: Syllable | null; new: Syllable | null; ticked: boolean; conflict: boolean }
/** One operation of the editor's vocabulary (score/edit.ts), naming a note by `measure` and `event`: its place among the
 *  measure's <note> elements as the score was read, which an earlier operation of the same answer does not move. */
export interface ScoreOp { op: string; measure: number; event: number; [param: string]: unknown }
/**
 * What the pass would do to the notes of one measure (`kind` notes: all its operations, kept or dropped together
 * because they must add up together) or to one chord symbol (`kind` chord). `old` and `new` are the values in words:
 * the measure's notes ("G4 eighth, Ab4 eighth"), or the chord ("Cm"; empty is none). `marks` are the event indices
 * that differ, for the marks on the sheet; a chord change marks `event`.
 */
export interface ScoreChange {
  id: string; kind: "notes" | "chord"; span: ModelSpan; measure: number; event?: number; ops: ScoreOp[]; marks?: number[];
  old: { text: string }; new: { text: string }; ticked: boolean; conflict: boolean;
}
export type AnyChange = ModelChange | ScoreChange;
export const isScoreChange = (c: AnyChange): c is ScoreChange => c.kind === "notes" || c.kind === "chord";
/** A change the user did not take, stored with the job (ADR 0010); `rejected` hides it, nothing deletes it. */
export interface ModelReading {
  kind?: "lyric"; id: string; draft: string; span: ModelSpan; verse: number; measure: number; onset: number; old: Syllable | null; new: Syllable | null;
  route: string; model: string; time: string; status: "proposed" | "accepted" | "rejected";
}
export interface ScoreReading {
  id: string; draft: string; kind: "notes" | "chord"; span: ModelSpan; measure: number; ops: ScoreOp[]; old: { text: string }; new: { text: string };
  route: string; model: string; time: string; status: "proposed" | "accepted" | "rejected";
}
export type AnyReading = ModelReading | ScoreReading;
export const isLyricReading = (r: AnyReading): r is ModelReading => r.kind !== "notes" && r.kind !== "chord";
export interface ModelDraft {
  id: string; created: string; base_revision: number; route: { kind: string; model: string };
  spans: (ModelSpan & { lyrics_source: string; note?: string })[]; changes: AnyChange[];
  /** `kind` notes is a span checked for notes and chords (its `verse` is 0). */
  dropped: { span: ModelSpan; verse: number; reason: string; kind?: "notes" }[];
  /** Verses the larger model had to answer after the first answer failed validation. */
  escalated?: { span: ModelSpan; verse: number; model: string }[];
}
export interface ModelEstimate { calls: number; estimated_tokens: number; estimated_cost_usd: number; model: string; vision?: boolean; confirm: false }
/** A span's words are typed (`lyrics_source`) or a picture of them (`lyrics_picture`, bare base64 PNG/JPEG/WebP), not both.
 *  `needs_image` is set on a picture span so a route without vision refuses it before any call. */
export interface ModelSpanIn extends ModelSpan { lyrics_source?: string; lyrics_picture?: string; needs_image?: boolean; note?: string }
export interface ModelPassRequest { spans: ModelSpanIn[]; api_key?: string; route?: string; larger?: boolean }

/** The routes the server offers (Anthropic, DeepSeek), with whether each holds a key and can read images. */
export async function getModelRoutes(): Promise<ModelRoute[]> {
  return check<ModelRoute[]>(await fetch("/api/model-routes"));
}

/** Without `confirm` the server only says what the pass would cost; with it the draft comes back. */
export async function estimateModelPass(id: string, body: ModelPassRequest): Promise<ModelEstimate> {
  return check<ModelEstimate>(await fetch(`/api/jobs/${id}/model-pass`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...body, confirm: false }),
  }));
}

export async function runModelPass(id: string, body: ModelPassRequest): Promise<ModelDraft> {
  return check<ModelDraft>(await fetch(`/api/jobs/${id}/model-pass`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...body, confirm: true }),
  }));
}

/** The stored draft, or null when there is none. */
export async function getModelDraft(id: string): Promise<ModelDraft | null> {
  const r = await fetch(`/api/jobs/${id}/model-draft`);
  if (r.status === 404) return null;
  return check<ModelDraft>(r);
}

/** Hide a stored model reading; the server keeps it with status rejected. */
export async function rejectModelReading(id: string, readingId: string): Promise<ReviewState> {
  return check<ReviewState>(await fetch(`/api/jobs/${id}/model-readings/${encodeURIComponent(readingId)}/reject`, { method: "POST" }));
}

/** Apply the ticked changes as one revision; the others stay as stored readings. */
export async function applyModelDraft(id: string, ticked: string[]): Promise<ReviewState> {
  return check<ReviewState>(await fetch(`/api/jobs/${id}/model-draft/apply`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ticked }),
  }));
}
