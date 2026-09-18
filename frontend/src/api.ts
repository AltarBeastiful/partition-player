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
  result: { engine: string; seconds: number; stats: { measures: number; notes: number; rests: number; padded_measures: number; warnings: string[] } } | null;
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

export function scoreUrl(id: string): string {
  return `/api/jobs/${id}/score.musicxml`;
}

export function thumbUrl(id: string): string {
  return `/api/jobs/${id}/thumb.jpg`;
}
