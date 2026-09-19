export type JobStatus = "queued" | "preprocessing" | "recognizing" | "postprocessing" | "done" | "failed";

export interface Job {
  id: string;
  status: JobStatus;
  message: string;
  created_at: string;
  updated_at: string;
  input_name: string;
  name: string;
  error: string | null;
  result: { engine: string; seconds: number; stats: Stats } | null;
  edited_at?: string | null;
}

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

export async function createJob(file: File): Promise<Job> {
  const body = new FormData();
  body.append("file", file, file.name);
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
export interface FormSection { name: string; from: number; to: number }
export interface FormPass { section: number; verse: number | null }
/** How the page is played (plan 0004): null is the automatic form from the repeat signs and the verses. */
export interface Form { sections: FormSection[]; passes: FormPass[] }
export interface ReviewState { doubts: Doubt[]; checked: number[]; revision: number; layout: Layout | null; has_image: boolean; has_original: boolean; form: Form | null }
export interface SaveResult extends ReviewState { check: Doubt[]; stats: Stats }

export async function getReview(id: string): Promise<ReviewState> {
  return check<ReviewState>(await fetch(`/api/jobs/${id}/review`));
}

export async function getScoreText(id: string, version = 0): Promise<string> {
  const r = await fetch(scoreUrl(id, version || Date.now()));
  if (!r.ok) throw new ApiError(r.statusText, r.status);
  return r.text();
}

export async function saveScore(id: string, body: { musicxml: string; checked: number[]; revision: number; doubts: Doubt[]; form: Form | null }): Promise<SaveResult> {
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
