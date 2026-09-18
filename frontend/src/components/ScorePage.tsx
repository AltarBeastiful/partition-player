import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, deleteJob, getJob, renameJob, type Job } from "../api";
import { Progress } from "./Progress";
import { LyricsPanel } from "./LyricsPanel";
import { ScoreView } from "./ScoreView";
import { navigate, onLinkClick } from "../router";

export function ScorePage({ id }: { id: string }) {
  const [job, setJob] = useState<Job | null>(null);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [editing, setEditing] = useState(false);
  const [copied, setCopied] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [version, setVersion] = useState(0); // bumped when the lyrics are saved, so the sheet reloads
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    getJob(id).then((j) => { setJob(j); setName(j.name); }).catch((e) => {
      if (e instanceof ApiError && e.status === 404) setMissing(true); else setError((e as Error).message);
    });
  }, [id]);

  const onDone = useCallback((j: Job) => { setJob(j); setName(j.name); }, []);

  useEffect(() => { if (editing) { input.current?.focus(); input.current?.select(); } }, [editing]);

  async function saveName() {
    setEditing(false);
    if (!job || name.trim() === job.name) { setName(job?.name ?? ""); return; }
    try { const j = await renameJob(id, name); setJob(j); setName(j.name); } catch (e) { setError((e as Error).message); }
  }

  async function copyLink() {
    try { await navigator.clipboard.writeText(location.href); setCopied(true); window.setTimeout(() => setCopied(false), 2000); }
    catch { setError("Could not copy. The link is the address of this page."); }
  }

  async function remove() {
    try { await deleteJob(id); navigate("/"); } catch (e) { setError((e as Error).message); }
  }

  if (missing) {
    return (
      <section className="card">
        <p>This score does not exist any more. It may have been deleted.</p>
        <a className="button" href="/" onClick={onLinkClick}>Back to the library</a>
      </section>
    );
  }

  return (
    <>
      <section className="card score-head">
        {editing ? (
          <form className="name-form" onSubmit={(e) => { e.preventDefault(); saveName(); }}>
            <input id="score-name" ref={input} value={name} maxLength={120} onChange={(e) => setName(e.target.value)}
              onBlur={saveName} onKeyDown={(e) => { if (e.key === "Escape") { setName(job?.name ?? ""); setEditing(false); } }} />
            <button type="submit" className="primary">Save</button>
          </form>
        ) : (
          <h2 className="score-title">
            <span>{job ? job.name || "Untitled score" : "Loading…"}</span>
            {job && <button className="quiet" onClick={() => setEditing(true)}>Rename</button>}
          </h2>
        )}
        <div className="controls">
          <button onClick={copyLink}>{copied ? "Link copied" : "Copy link"}</button>
          {confirming ? (
            <>
              <button className="danger" onClick={remove}>Delete for everyone</button>
              <button onClick={() => setConfirming(false)}>Keep</button>
            </>
          ) : (
            <button className="quiet" onClick={() => setConfirming(true)}>Delete</button>
          )}
          {job && <span className="muted">from {job.input_name}</span>}
        </div>
        {error && <div className="error">{error}</div>}
      </section>
      {job && job.status !== "done" && <Progress jobId={id} onDone={onDone} />}
      {job && job.status === "done" && <ScoreView job={job} version={version} />}
      {job && job.status === "done" && <LyricsPanel jobId={id} onSaved={() => setVersion((v) => v + 1)} />}
    </>
  );
}
