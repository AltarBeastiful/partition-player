import { useEffect, useRef, useState } from "react";
import { getModelDraft, getModelRoutes } from "../api";
import type { ModelEstimate, ModelSpanIn } from "../api";
import { pictureToBase64 } from "../editor/picture";
import { initialRoute, spanRefusal, type ModelRoute } from "../modelRoute";
import { changeLine } from "../score/draft";
import type { EditorSession } from "../editor/session";
import { modelNotice, ModelFlow, visitorKey } from "../editor/modelFlow";

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
  const [routes, setRoutes] = useState<ModelRoute[]>([]);
  const [routeId, setRouteId] = useState("");
  const route = routes.find((r) => r.id === routeId);
  const [picture, setPicture] = useState<File | null>(null);
  const vision = route?.vision ?? true; // unknown until the routes arrive: the server refuses if it cannot
  const [estimate, setEstimate] = useState<ModelEstimate | null>(null);
  const [key, setKey] = useState(visitorKey.get());
  const flow = useRef<ModelFlow | null>(null);
  if (!flow.current) flow.current = new ModelFlow(session.jobId);
  const draft = session.draft;
  const doubts = session.doubtSpans();
  const spanKey = (d: { staff: number; from: number }) => `${d.staff}:${d.from}`;
  const [picked, setPicked] = useState<Set<string> | null>(null);
  const chosen = picked ?? new Set(doubts.filter((d) => d.level === "wrong").map(spanKey));   // strong doubts are ticked until the user says otherwise
  const togglePick = (k: string) => setPicked((p) => { const n = new Set(p ?? chosen); if (n.has(k)) n.delete(k); else n.add(k); return n; });

  useEffect(() => {
    let live = true;
    getModelRoutes().then((rs) => { if (live) { setRoutes(rs); setRouteId(initialRoute(rs)?.id ?? ""); } }).catch(() => { /* the default route is used */ });
    return () => { live = false; };
  }, []);

  // A draft left from an earlier visit comes back in the sheet.
  useEffect(() => {
    let live = true;
    getModelDraft(session.jobId).then((d) => { if (live && d && !session.draft) { session.openDraft(d); setOpen(true); } }).catch(() => { /* no route or no draft: the panel stays closed */ });
    return () => { live = false; };
  }, [session]);

  useEffect(() => { setTo((t) => (t > measureCount || t < 1 ? measureCount || 1 : t)); }, [measureCount]);

  async function ask(spans: ModelSpanIn[]) {
    setRunning(true); setError(null); setApplied(null);
    try {
      if (session.dirty) await session.save(); // the pass reads the score as the server holds it
      visitorKey.set(key);
      for (const span of spans) {
        const refused = spanRefusal(route, span);
        if (refused) { setError(refused); return; }
      }
      flow.current!.routeId = routeId;
      await flow.current!.ask(spans);
      setEstimate(flow.current!.estimate); setError(flow.current!.error);
    } catch (e) { setError((e as Error).message); } finally { setRunning(false); }
  }

  /** The words of the staff, typed or as a picture: the model places them under the notes. */
  async function start() {
    const range = { staff, from: from - 1, to: to - 1 };
    try {
      await ask([picture
        ? { ...range, lyrics_picture: await pictureToBase64(picture), needs_image: true }
        : { ...range, lyrics_source: text, needs_image: false }]);
    } catch (e) { setError((e as Error).message); }
  }

  /** Ticket 10: no words; the model re-reads the notes and chords of the span, told what the engine doubted there. */
  async function checkNotes(spans: { staff: number; from: number; to: number }[]) {
    await ask(spans.map((sp) => ({ ...sp, needs_image: false, note: session.doubtNote(sp) })));
  }

  /** Try harder (ticket 08): one span of the draft again, on the larger model; its draft replaces this one once confirmed. */
  async function tryHarder(span: { staff: number; from: number; to: number; lyrics_source: string; note?: string }) {
    setRunning(true); setError(null);
    try {
      flow.current!.routeId = routeId; visitorKey.set(key);
      await flow.current!.askHarder({ staff: span.staff, from: span.from, to: span.to, ...(span.lyrics_source ? { lyrics_source: span.lyrics_source } : { note: span.note ?? "" }) });
      setEstimate(flow.current!.estimate); setError(flow.current!.error);
    } catch (e) { setError((e as Error).message); } finally { setRunning(false); }
  }

  async function confirm() {
    setRunning(true); setError(null);
    const d = await flow.current!.confirm();
    setEstimate(null); setRunning(false);
    if (d) session.openDraft(d); else setError(flow.current!.error);
  }

  function cancel() { flow.current!.cancel(); setEstimate(null); }

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
        <span className="muted">Paste the words of a staff and a model places the syllables under the notes, or have it re-read the notes and chords of doubtful measures. You look at the draft here before anything is kept.</span>
        {!draft && <button className="quiet" onClick={() => setOpen((o) => !o)}>{open ? "Hide" : "Open"}</button>}
      </div>
      {open && !draft && (
        <>
          {routes.length > 1 && (
            <div className="controls">
              <label>Model <select value={routeId} onChange={(e) => setRouteId(e.target.value)}>
                {routes.map((r) => <option key={r.id} value={r.id}>{r.label} ({r.model})</option>)}
              </select></label>
              {route && !route.vision && <span className="muted">No image reading on this route: typed words only.</span>}
            </div>
          )}
          {doubts.length > 0 && (
            <div className="controls doubt-spans">
              <span className="muted">Doubtful in the recognition, strongest first:</span>
              {doubts.map((d) => (
                <span key={spanKey(d)}>
                  <input type="checkbox" aria-label={`Check the notes of measures ${d.from + 1} to ${d.to + 1}`} checked={chosen.has(spanKey(d))} onChange={() => togglePick(spanKey(d))} />
                  <button className="quiet" title={d.level === "wrong" ? "A measure that cannot be right" : "Worth a look"}
                    onClick={() => { setStaff(d.staff); setFrom(d.from + 1); setTo(d.to + 1); }}>
                    {d.level === "wrong" ? "Wrong" : "Check"}: {staves > 1 ? `staff ${d.staff + 1}, ` : ""}measure{d.from === d.to ? "" : "s"} {d.from + 1}{d.from === d.to ? "" : `-${d.to + 1}`}
                  </button>
                </span>
              ))}
              <button onClick={() => void checkNotes(doubts.filter((d) => chosen.has(spanKey(d))))} disabled={running || !!estimate || chosen.size === 0}
                title="The model re-reads the notes and chords of the ticked spans; you look at the draft before anything is kept">
                Check the notes of the {chosen.size} ticked
              </button>
            </div>
          )}
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
            <textarea rows={5} value={text} spellCheck={false} disabled={!!picture} onChange={(e) => setText(e.target.value)} />
          </label>
          <div className="controls lyrics-picture">
            <label>Or a picture of the words{" "}
              <input type="file" accept="image/png,image/jpeg,image/webp" disabled={!vision} title={vision ? undefined : `${route?.label ?? "This model"} cannot read pictures: type the words instead.`}
                onChange={(e) => setPicture(e.target.files?.[0] ?? null)} />
            </label>
            {!vision && <span className="muted">{route ? route.label : "This model"} cannot read pictures: type the words instead.</span>}
            {picture && <button className="quiet" onClick={() => setPicture(null)}>Remove the picture</button>}
          </div>
          <label className="verse">
            <span className="muted">Your API key, if the site has none of its own. Kept in this page until you close it; never stored.</span>
            <input type="password" autoComplete="off" value={key} placeholder="sk-ant-…" onChange={(e) => { setKey(e.target.value); visitorKey.set(e.target.value); }} />
          </label>
          {estimate ? (
            <div className="controls">
              <span>{estimate.calls} call{estimate.calls === 1 ? "" : "s"} to {estimate.model}, about {estimate.estimated_tokens} tokens, about ${estimate.estimated_cost_usd.toFixed(4)}.</span>
              <button className="primary" onClick={confirm} disabled={running}>{running ? "Asking the model…" : "Confirm and run"}</button>
              <button onClick={cancel} disabled={running}>Cancel</button>
            </div>
          ) : (
            <div className="controls">
              <button className="primary" onClick={start} disabled={running || (!picture && !text.trim())}>{running ? "Estimating…" : "Place the words"}</button>
              <button onClick={() => void checkNotes([{ staff, from: from - 1, to: to - 1 }])} disabled={running}
                title="No words needed: the model re-reads the notes and chords of these measures">Check the notes and chords</button>
            </div>
          )}
          <p className="muted">{modelNotice(route?.label)}</p>
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
          {(draft.draft.escalated ?? []).length > 0 && (
            <p className="muted">The first answer failed the check, so the larger model answered: {(draft.draft.escalated ?? []).map((e) => `${e.verse === 0 ? "notes and chords" : `verse ${e.verse}`} of measures ${e.span.from + 1}-${e.span.to + 1} (${e.model})`).join("; ")}.</p>
          )}
          {draft.draft.dropped.length > 0 && (
            <p className="muted">Not used: {draft.draft.dropped.map((d) => `${d.kind === "notes" ? "notes and chords" : `verse ${d.verse}`} of measures ${d.span.from + 1}-${d.span.to + 1} (${d.reason})`).join("; ")}</p>
          )}
          {draft.draft.spans.filter((sp) => draft.draft.dropped.some((d) => d.span.staff === sp.staff && d.span.from === sp.from && d.span.to === sp.to)).map((sp) => (
            <div className="controls" key={`${sp.staff}:${sp.from}:${sp.to}`}>
              <button onClick={() => tryHarder(sp)} disabled={running || applying}>Try harder: measures {sp.from + 1}-{sp.to + 1}</button>
            </div>
          ))}
          {estimate && (
            <div className="controls">
              <span>{estimate.calls} call{estimate.calls === 1 ? "" : "s"} to {estimate.model}, about ${estimate.estimated_cost_usd.toFixed(4)}. The draft shown is replaced by this span's new one.</span>
              <button className="primary" onClick={confirm} disabled={running}>{running ? "Asking the model…" : "Confirm and run"}</button>
              <button onClick={cancel} disabled={running}>Cancel</button>
            </div>
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
