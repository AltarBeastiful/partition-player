import { useCallback, useEffect, useState } from "react";
import { deleteJob, listJobs, thumbUrl, type Job } from "../api";
import { onLinkClick, scorePath } from "../router";

const RUNNING = new Set(["queued", "preprocessing", "recognizing", "postprocessing"]);

function when(iso: string): string {
  const d = new Date(iso);
  const days = (Date.now() - d.getTime()) / 86_400_000;
  if (days < 1) return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  if (days < 7) return d.toLocaleDateString(undefined, { weekday: "long" });
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: days > 300 ? "numeric" : undefined });
}

export function Library() {
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try { setJobs(await listJobs()); setError(null); } catch (e) { setError((e as Error).message); }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);
  // Keep polling while something is still being read, so the list updates without a reload.
  useEffect(() => {
    if (!jobs?.some((j) => RUNNING.has(j.status))) return;
    const t = window.setInterval(refresh, 3000);
    return () => window.clearInterval(t);
  }, [jobs, refresh]);

  async function remove(id: string) {
    try { await deleteJob(id); setConfirming(null); refresh(); } catch (e) { setError((e as Error).message); }
  }

  return (
    <section className="card library">
      <div className="topbar">
        <h2>Scores</h2>
        {jobs && jobs.length > 0 && <span className="muted">{jobs.length} saved. Anyone with the link can open one.</span>}
      </div>
      {error && <div className="error">{error}</div>}
      {jobs && jobs.length === 0 && <p className="muted">Nothing yet. Every score you read is kept here, with its own link.</p>}
      {jobs && jobs.length > 0 && (
        <ul className="scores">
          {jobs.map((j) => (
            <li key={j.id} className={"score-row" + (j.status === "failed" ? " failed" : "")}>
              <a className="thumb" href={scorePath(j.id)} onClick={onLinkClick} aria-hidden="true" tabIndex={-1}>
                <img src={thumbUrl(j.id)} alt="" loading="lazy" onError={(e) => { e.currentTarget.style.visibility = "hidden"; }} />
              </a>
              <div className="score-main">
                <a className="score-name" href={scorePath(j.id)} onClick={onLinkClick}>{j.name || "Untitled score"}</a>
                <div className="score-meta muted">
                  <span>{when(j.created_at)}</span>
                  {j.status === "done" && j.result && <span>{j.result.stats.measures} measures · {j.result.stats.notes} notes</span>}
                  {RUNNING.has(j.status) && <span className="pill running">{j.message}</span>}
                  {j.status === "failed" && <span className="pill bad">failed</span>}
                </div>
              </div>
              <div className="score-actions">
                {confirming === j.id ? (
                  <>
                    <button className="danger" onClick={() => remove(j.id)}>Delete</button>
                    <button onClick={() => setConfirming(null)}>Keep</button>
                  </>
                ) : (
                  <button className="quiet" onClick={() => setConfirming(j.id)} aria-label={`Delete ${j.name}`}>Delete</button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
