import { useEffect, useState } from "react";
import { getModelDraft, runModelPass } from "../api";
import { changeLine } from "../score/draft";
import type { EditorSession } from "../editor/session";

/**
 * Check with a model (ADR 0010, plan 0016 step 6): on a staff, paste the words, start the pass, then
 * look at the draft in the ordinary sheet. The sheet shows what `session.shownXml` says, so the
 * player follows the version on show. The draft lives in the session, not in the document: nothing is
 * saved until Apply, which is one revision and one undo.
 */
export function ModelPanel({ session, measureCount, staves, onApplied }: {
  session: EditorSession; measureCount: number; staves: number; onApplied?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [staff, setStaff] = useState(0);
  const [from, setFrom] = useState(1);
  const [to, setTo] = useState(measureCount || 1);
  const [text, setText] = useState("");
  const [running, setRunning] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [applied, setApplied] = useState<number | null>(null);
  const draft = session.draft;

  // A draft left from an earlier visit comes back in the sheet.
  useEffect(() => {
    let live = true;
    getModelDraft(session.jobId).then((d) => { if (live && d && !session.draft) { session.openDraft(d); setOpen(true); } }).catch(() => { /* no route or no draft: the panel stays closed */ });
    return () => { live = false; };
  }, [session]);

  useEffect(() => { setTo((t) => (t > measureCount || t < 1 ? measureCount || 1 : t)); }, [measureCount]);

  async function start() {
    setRunning(true); setError(null); setApplied(null);
    try {
      if (session.dirty) await session.save(); // the pass reads the score as the server holds it
      const d = await runModelPass(session.jobId, { spans: [{ staff, from: from - 1, to: to - 1, lyrics_source: text }] });
      session.openDraft(d);
    } catch (e) { setError((e as Error).message); } finally { setRunning(false); }
  }

  async function apply() {
    if (!draft) return;
    const n = draft.ticked.size;
    setApplying(true);
    await session.applyDraft();
    setApplying(false);
    if (!session.draft) { setApplied(n); onApplied?.(); }
  }

  return (
    <section className="card model-panel">
      <div className="controls">
        <strong>Check with a model</strong>
        <span className="muted">Paste the words of a staff; a model places the syllables under the notes and you look at the draft here before anything is kept.</span>
        {!draft && <button className="quiet" onClick={() => setOpen((o) => !o)}>{open ? "Hide" : "Open"}</button>}
      </div>
      {open && !draft && (
        <>
          <div className="controls">
            {staves > 1 && (
              <label>Staff <select value={staff} onChange={(e) => setStaff(Number(e.target.value))}>
                {Array.from({ length: staves }, (_, i) => <option key={i} value={i}>{i + 1}</option>)}
              </select></label>
            )}
            <label>measures <input type="number" min={1} max={measureCount || 1} value={from} onChange={(e) => { const v = Number(e.target.value); setFrom(v); if (v > to) setTo(v); }} /></label>
            <label>to <input type="number" min={1} max={measureCount || 1} value={to} onChange={(e) => { const v = Number(e.target.value); setTo(v); if (v < from) setFrom(v); }} /></label>
          </div>
          <label className="verse">
            <span className="muted">The words, as typed: a blank line between verses.</span>
            <textarea rows={5} value={text} spellCheck={false} onChange={(e) => setText(e.target.value)} />
          </label>
          <div className="controls">
            <button className="primary" onClick={start} disabled={running || !text.trim()}>{running ? "Asking the model…" : "Place the words"}</button>
          </div>
        </>
      )}
      {draft && (
        <>
          <div className="controls" role="radiogroup" aria-label="Version shown">
            <label><input type="radio" name="draft-view" checked={draft.view === "read"} onChange={() => session.setView("read")} /> As read</label>
            <label><input type="radio" name="draft-view" checked={draft.view === "corrected"} onChange={() => session.setView("corrected")} /> As corrected</label>
            <span className="muted">{draft.ticked.size} of {draft.draft.changes.length} changes ticked, marked on the sheet. Play follows the version shown.</span>
          </div>
          {draft.draft.changes.length === 0 && <p className="muted">The model changed nothing.</p>}
          <ul className="draft-changes">
            {draft.draft.changes.map((c) => (
              <li key={c.id} className={c.conflict ? "conflict" : ""}>
                <label>
                  <input type="checkbox" checked={draft.ticked.has(c.id)} onChange={(e) => session.tick(c.id, e.target.checked)} /> {changeLine(c)}
                </label>
                {c.conflict && <span className="muted"> — edited by hand since the pass</span>}
              </li>
            ))}
          </ul>
          {draft.draft.dropped.length > 0 && (
            <p className="muted">Not used: {draft.draft.dropped.map((d) => `verse ${d.verse} (${d.reason})`).join("; ")}</p>
          )}
          <div className="controls">
            <button className="primary" onClick={apply} disabled={applying || draft.ticked.size === 0}>{applying ? "Applying…" : `Apply ${draft.ticked.size} change${draft.ticked.size === 1 ? "" : "s"}`}</button>
            <button onClick={() => session.closeDraft()} disabled={applying}>Close the draft</button>
          </div>
        </>
      )}
      {applied !== null && !draft && (
        <div className="controls">
          <span className="ok">Applied {applied} change{applied === 1 ? "" : "s"}.</span>
          <button onClick={() => { session.undo(); setApplied(null); }} disabled={!session.canUndo}>Undo</button>
        </div>
      )}
      {error && <div className="error">{error}</div>}
      {session.message && <div className="error">{session.message}</div>}
    </section>
  );
}
