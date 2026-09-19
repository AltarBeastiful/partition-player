import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { OpenSheetMusicDisplay } from "opensheetmusicdisplay";
import { getReview, getScoreText, scoreUrl, type Form, type Job, type Stats } from "../api";
import { defaultPasses, expandForm, versesByMeasure, type Pass } from "../form";
import { clearVerses, dimVerses } from "../verses";
import { commands, shortcut } from "../editor/commands";
import { EditorSession } from "../editor/session";
import { drawOverlay, hitTest, keepOverlay, rectOf } from "../editor/sheet";
import { clearNoteNames, drawNoteNames, keepNoteNames, reserveNoteNamesSpace } from "../noteNames";
import { Player, type PlaybackState } from "../player";
import type { EventKey } from "../score/xml";
import { FormPanel, Lightbox, PrintedStrip, ReviewBar, Toolbar } from "./Editor";
import { ReadingsDialog } from "./Readings";

const NOTE_NAMES_PREF = "pp.noteNames"; // a practice preference, not a property of the score

function readNoteNamesPref(): boolean {
  try { return localStorage.getItem(NOTE_NAMES_PREF) === "1"; } catch { return false; }
}

function writeNoteNamesPref(on: boolean): void {
  try { localStorage.setItem(NOTE_NAMES_PREF, on ? "1" : "0"); } catch { /* private browsing */ }
}

function inTextField(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el) return false;
  if (el.tagName === "INPUT") return !["checkbox", "radio", "range", "button", "submit"].includes((el as HTMLInputElement).type);
  return ["TEXTAREA", "SELECT"].includes(el.tagName) || el.isContentEditable;
}

export function ScoreView({ job, version = 0, onStats, registerFlush, onReload }: {
  job: Job; version?: number; onStats?: (s: Stats) => void; registerFlush?: (flush: (() => Promise<void>) | null) => void; onReload: () => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const osmdRef = useRef<OpenSheetMusicDisplay | null>(null);
  const playerRef = useRef<Player | null>(null);
  const renderedDoc = useRef(0);
  const [session, setSession] = useState<EditorSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [state, setState] = useState<PlaybackState>("stopped");
  const [bpm, setBpm] = useState(90);
  const [transpose, setTranspose] = useState(0);
  const [chordCount, setChordCount] = useState(0);
  const [melodyOn, setMelodyOn] = useState(true);
  const [accompOn, setAccompOn] = useState(true);
  const [loop, setLoop] = useState(false);
  const [noteNames, setNoteNames] = useState(readNoteNamesPref);
  const noteNamesRef = useRef(noteNames); // read inside load(), which must not re-run on a toggle
  noteNamesRef.current = noteNames;
  const [from, setFrom] = useState(1);
  const [to, setTo] = useState(1);
  const [measureCount, setMeasureCount] = useState(0);
  const [stats, setStats] = useState<Stats | undefined>(job.result?.stats);
  const [showPhoto, setShowPhoto] = useState(false);
  const [lightbox, setLightbox] = useState(false);
  const [staves, setStaves] = useState(1);
  const [editing, setEditing] = useState(false);
  const [readingsFor, setReadingsFor] = useState<EventKey | null>(null); // the note the readings dialog is about
  const [printed, setPrinted] = useState<Pass[]>([]);   // the automatic passes
  const [passes, setPasses] = useState<Pass[]>([]);     // what plays
  const [verseCount, setVerseCount] = useState(1);
  const [currentPass, setCurrentPass] = useState<number | null>(null);
  const lastForm = useRef<Form | null | undefined>(undefined);
  const verseRef = useRef<number | null>(null);

  const subscribe = useCallback((fn: () => void) => (session ? session.subscribe(fn) : () => {}), [session]);
  useSyncExternalStore(subscribe, () => session?.version ?? 0);

  useEffect(() => { setStats(job.result?.stats); }, [job]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    async function load() {
      if (!host.current) return;
      const osmd = new OpenSheetMusicDisplay(host.current, {
        autoResize: true,
        drawTitle: false,  // homr's OCR of the title is unreliable; the page shows the editable name instead
        drawPartNames: false,
        followCursor: false,
        cursorsOptions: [{ type: 0, color: "#0e7490", alpha: 0.35, follow: false }],
      });
      try {
        const [xml, review] = await Promise.all([getScoreText(job.id, version), getReview(job.id)]);
        if (cancelled) return;
        const s = new EditorSession(job.id, xml, review);
        s.onStats = (st) => { setStats(st); onStats?.(st); };
        await osmd.load(s.xml);
        if (cancelled) return;
        reserveNoteNamesSpace(osmd, noteNamesRef.current); // before the first render, so nothing jumps
        osmd.render();
        osmd.cursor.show();
        osmdRef.current = osmd;
        const player = new Player(osmd, setState);
        player.onPass = setCurrentPass;
        playerRef.current = player;
        const auto = defaultPasses(osmd);
        const played = s.form ? expandForm(s.form, player.measureCount) : auto;
        player.setPasses(played);
        lastForm.current = s.form;
        setPrinted(auto); setPasses(played);
        setVerseCount(Math.max(1, ...versesByMeasure(osmd).flat()));
        (window as unknown as { __player?: Player; __session?: EditorSession }).__player = player; // debugging aid
        (window as unknown as { __session?: EditorSession }).__session = s;
        renderedDoc.current = s.docVersion;
        setMeasureCount(player.measureCount);
        setChordCount(player.chords.length);
        setStaves(Math.max(1, ...s.measures.flatMap((m) => m.events.map((e) => e.key.staff))));
        setTo(player.measureCount);
        setSession(s);
        registerFlush?.(() => s.save());
        setLoading(false);
      } catch (e) {
        setError("Could not render the score: " + (e as Error).message);
        setLoading(false);
      }
    }
    load();
    // A saved edit bumps `version` and this runs again with a new OSMD on the same container. OSMD
    // leaves its SVG and cursor behind when it is dropped, so the old sheet has to be taken down
    // here or the page ends up showing both.
    return () => {
      cancelled = true;
      registerFlush?.(null);
      playerRef.current?.dispose();
      playerRef.current = null;
      osmdRef.current?.clear();
      osmdRef.current = null;
      host.current?.replaceChildren();
      setSession((s) => { s?.dispose(); return null; });
    };
  }, [job.id, version]); // eslint-disable-line react-hooks/exhaustive-deps

  const redraw = useCallback(() => {
    const osmd = osmdRef.current;
    if (!osmd || !session) return;
    drawOverlay(osmd, session.places(), session.selected);
    if (verseRef.current !== null) dimVerses(osmd, verseRef.current); else clearVerses(osmd);
  }, [session]);

  // The document changed (an edit, undo, redo): render it again and read the events again.
  useEffect(() => {
    const osmd = osmdRef.current, player = playerRef.current;
    if (!osmd || !player || !session || loading || session.docVersion === renderedDoc.current) return;
    renderedDoc.current = session.docVersion;
    let cancelled = false;
    (async () => {
      try {
        await osmd.load(session.xml);
        if (cancelled) return;
        osmd.render();
        osmd.cursor.show();
        player.rebuild();
        const auto = defaultPasses(osmd);
        const played = session.form ? expandForm(session.form, player.measureCount) : auto;
        player.setPasses(played);
        // The re-render stopped the playback: put it back on the edited note, so Space replays it.
        if (session.selected) {
          const at = player.positionOf(session.selected.measure, session.selected.onset);
          if (at !== null) player.seek(at);
        }
        lastForm.current = session.form;
        setPrinted(auto); setPasses(played);
        setVerseCount(Math.max(1, ...versesByMeasure(osmd).flat()));
        setMeasureCount(player.measureCount);
        setChordCount(player.chords.length);
        setTo((t) => Math.min(Math.max(t, 1), player.measureCount || 1));
        setFrom((f) => Math.min(Math.max(f, 1), player.measureCount || 1));
        if (noteNamesRef.current) drawNoteNames(osmd);
        redraw();
        setError(null);
      } catch (e) {
        setError("Could not render the edited score: " + (e as Error).message + ". Undo the last change.");
      }
    })();
    return () => { cancelled = true; };
  }, [session, session?.docVersion, loading, redraw]);

  // The form changed (the panel, undo, revert): the player plays the new passes.
  useEffect(() => {
    const player = playerRef.current;
    if (loading || !session || !player || lastForm.current === session.form) return;
    lastForm.current = session.form;
    const played = session.form ? expandForm(session.form, player.measureCount) : printed;
    player.setPasses(played);
    setPasses(played);
  }, [session, session?.version, loading, printed]);

  // The pass being played: its verse's words stay, the others are dimmed.
  useEffect(() => {
    const osmd = osmdRef.current;
    if (!osmd || loading) return;
    verseRef.current = currentPass === null ? null : passes[currentPass]?.verse ?? null;
    dimVerses(osmd, verseRef.current);
  }, [currentPass, passes, loading]);

  // Selection or places changed: the overlay only.
  useEffect(() => {
    if (loading || !session) return;
    redraw();
    const osmd = osmdRef.current;
    if (osmd && session.selected) {
      const r = rectOf(osmd, session.selected);
      if (r && (r.top < 60 || r.bottom > window.innerHeight - 200)) window.scrollBy({ top: r.top - window.innerHeight / 3, behavior: "smooth" });
    }
  }, [session, session?.version, loading, redraw]);

  // OSMD re-renders by itself on resize: put the overlay back each time it does.
  useEffect(() => {
    if (loading || !host.current || !session) return;
    return keepOverlay(host.current, redraw);
  }, [loading, session, redraw]);

  const toggle = useCallback(async () => {
    const p = playerRef.current;
    if (!p) return;
    if (state === "playing") p.pause();
    else await p.play(bpm, loop, { from, to });
  }, [state, bpm, loop, from, to]);

  const stop = useCallback(() => playerRef.current?.stop(), []);
  const restart = useCallback(() => playerRef.current?.restart(), []);

  const playFrom = useCallback(async (measure: number) => {
    const p = playerRef.current;
    if (!p) return;
    p.stop();
    await p.play(bpm, false, { from: measure + 1, to: p.measureCount });
  }, [bpm]);

  useEffect(() => { playerRef.current?.setBpm(bpm); }, [bpm]);
  useEffect(() => { playerRef.current?.setTranspose(transpose); }, [transpose]);
  useEffect(() => { playerRef.current?.setTrack("melody", melodyOn); }, [melodyOn]);
  useEffect(() => { playerRef.current?.setTrack("accompaniment", accompOn); }, [accompOn]);

  // Turning the names on widens the gaps over the staves, which needs a new layout; the names
  // themselves are then drawn into the SVG that layout produced.
  useEffect(() => {
    const osmd = osmdRef.current;
    if (!osmd || loading) return;
    if (reserveNoteNamesSpace(osmd, noteNames)) {
      osmd.render(); // the wider gaps only take effect on a new layout
      osmd.cursor.show();
    }
    if (noteNames) drawNoteNames(osmd); else clearNoteNames(osmd);
    redraw();
  }, [noteNames, loading, redraw]);

  // OSMD re-renders by itself, on resize: the names have to be put back each time it does.
  useEffect(() => {
    const osmd = osmdRef.current;
    if (!noteNames || loading || !osmd || !host.current) return;
    return keepNoteNames(osmd, host.current);
  }, [noteNames, loading]);

  // A click on the sheet leads the playback to the note, in both modes; in edit mode it also selects it.
  const onSheetClick = useCallback((e: React.MouseEvent) => {
    const osmd = osmdRef.current, player = playerRef.current;
    if (!osmd || !session) return;
    const key = hitTest(osmd, e.clientX, e.clientY);
    if (editing) session.select(key);
    if (!key || !player) return;
    const at = player.positionOf(key.measure, key.onset);
    if (at !== null) player.seek(at);
  }, [session, editing]);

  // A double click asks what else this note could have been, entering edit mode on the way.
  const onSheetDoubleClick = useCallback((e: React.MouseEvent) => {
    const osmd = osmdRef.current;
    if (!osmd || !session) return;
    const key = hitTest(osmd, e.clientX, e.clientY);
    if (!key) return;
    session.select(key);
    playerRef.current?.stop();
    setEditing(true);
    setReadingsFor(key);
  }, [session]);

  const enterEdit = useCallback(() => { playerRef.current?.stop(); setEditing(true); }, []);
  const leaveEdit = useCallback(() => {
    session?.select(null);
    if (session?.dirty) void session.save();
    setReadingsFor(null);
    setEditing(false);
  }, [session]);

  // Keyboard: the editor's shortcuts, space for play and pause, Escape to drop the selection.
  useEffect(() => {
    if (!session) return;
    const c = commands(session);
    const onKey = (e: KeyboardEvent) => {
      if (inTextField(e.target) || e.altKey) return;
      if (e.key === " ") { e.preventDefault(); void toggle(); return; }
      if (e.key === "Home" && !e.ctrlKey && !e.metaKey) { e.preventDefault(); restart(); return; }
      if (!editing) return; // the editing keys only act in edit mode
      if (readingsFor) { // the readings dialog has the keyboard while it is open (state, not the DOM: its own Escape closes it in this same event); undo and redo still reach the score
        if ((e.ctrlKey || e.metaKey) && ["z", "y"].includes(e.key.toLowerCase())) { e.preventDefault(); if (e.key.toLowerCase() === "y" || e.shiftKey) session.redo(); else session.undo(); }
        return;
      }
      if (e.key === "Escape") {
        if (document.querySelector(".lightbox")) return;
        if (session.selected) session.select(null); else leaveEdit();
        return;
      }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); void session.save(); return; }
      if (e.key === "o" && session.selected) { e.preventDefault(); setReadingsFor(session.selected); return; }
      if (shortcut(e, c, session.selected !== null)) e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [session, toggle, restart, editing, leaveEdit, readingsFor]);

  // Leaving with unsaved changes asks first.
  useEffect(() => {
    const onLeave = (e: BeforeUnloadEvent) => { if (session?.dirty) { e.preventDefault(); } };
    window.addEventListener("beforeunload", onLeave);
    return () => window.removeEventListener("beforeunload", onLeave);
  }, [session]);

  // A new document (reload after a lyrics save or a revert) starts in playing mode.
  useEffect(() => { setEditing(false); setReadingsFor(null); }, [job.id, version]);

  async function revert() {
    if (!session) return;
    if (!window.confirm("Put the recognized score back? Every correction made here will be dropped.")) return;
    try { await session.revert(); onReload(); } catch (e) { setError((e as Error).message); }
  }

  const c = session ? commands(session) : null;

  return (
    <section className={"card" + (editing ? " editing" : "")}>
      <div className="controls">
        <button className="primary" onClick={toggle} disabled={loading || !!error}>
          {state === "playing" ? "Pause" : "Play"}
        </button>
        <button onClick={stop} disabled={loading || state === "stopped"}>Stop</button>
        <button onClick={restart} disabled={loading || !!error} title="Back to the beginning (Home): keeps playing from there, or stops at the start">⏮ Start</button>
        <label>
          Tempo <input id="tempo" type="range" min={40} max={180} value={bpm} onChange={(e) => setBpm(Number(e.target.value))} />
          <span style={{ fontVariantNumeric: "tabular-nums" }}>{bpm} bpm</span>
        </label>
        <label className="transpose" title="Shift every note by this many semitones during playback; the sheet stays as printed">
          Transpose
          <button id="transpose-down" onClick={() => setTranspose((t) => Math.max(-12, t - 1))} disabled={loading} aria-label="One semitone down">−</button>
          <span style={{ fontVariantNumeric: "tabular-nums", minWidth: "3ch", textAlign: "center" }}>{transpose > 0 ? `+${transpose}` : transpose}</span>
          <button id="transpose-up" onClick={() => setTranspose((t) => Math.min(12, t + 1))} disabled={loading} aria-label="One semitone up">+</button>
          {transpose !== 0 && <button className="quiet" onClick={() => setTranspose(0)}>reset</button>}
        </label>
        <a href={scoreUrl(job.id)} download={`${(job.name || "score").replace(/[^\w.-]+/g, "_")}.musicxml`}>Download MusicXML</a>
      </div>
      <div className="controls loop">
        <label>
          <input id="loop" type="checkbox" checked={loop} onChange={(e) => setLoop(e.target.checked)} disabled={loading} />
          Loop
        </label>
        <label>
          measures <input id="loop-from" type="number" min={1} max={measureCount || 1} value={from} disabled={loading}
            onChange={(e) => { const v = Number(e.target.value); setFrom(v); if (v > to) setTo(v); }} />
        </label>
        <label>
          to <input id="loop-to" type="number" min={1} max={measureCount || 1} value={to} disabled={loading}
            onChange={(e) => { const v = Number(e.target.value); setTo(v); if (v < from) setFrom(v); }} />
        </label>
        <span className="muted">of {measureCount}. Range applies with or without loop; changes take effect on the next Play.</span>
      </div>
      <div className="controls loop">
        <label title="Write the French name of every printed note above the staff. Transposing the playback does not rename them.">
          <input id="note-names" type="checkbox" checked={noteNames} disabled={loading || !!error}
            onChange={(e) => { setNoteNames(e.target.checked); writeNoteNamesPref(e.target.checked); }} />
          Note names
        </label>
        <span className="muted">do, ré, mi… above the staff, read from the pitches on the page.</span>
        {chordCount > 0 && (
          <>
            <label><input id="melody" type="checkbox" checked={melodyOn} onChange={(e) => setMelodyOn(e.target.checked)} /> Melody</label>
            <label><input id="accompaniment" type="checkbox" checked={accompOn} onChange={(e) => setAccompOn(e.target.checked)} /> Accompaniment</label>
            <span className="muted">Piano chords from the {chordCount} chord symbols on the page.</span>
          </>
        )}
      </div>
      {session && c && editing && <ReviewBar session={session} c={c} hasPhoto={session.hasImage} showPhoto={showPhoto} setShowPhoto={setShowPhoto} />}
      {session && !editing && session.open().length > 0 && (
        <div className="review toast" role="status">
          <strong>{session.open().length} place{session.open().length > 1 ? "s" : ""} to check</strong>
          <span>The recognition was unsure there: they are tinted on the sheet with a "?".</span>
          <button className="primary edit" onClick={enterEdit}>Edit the score</button>
        </div>
      )}
      {session && !loading && (
        <FormPanel form={session.form} passes={passes} printed={printed} measureCount={measureCount} verseCount={verseCount} currentPass={currentPass}
          onChange={(f) => session.setForm(f)} />
      )}
      {session && showPhoto && editing && session.layout && (
        <PrintedStrip jobId={job.id} layout={session.layout} measure={session.selected?.measure ?? null} onOpen={() => setLightbox(true)} />
      )}
      {session && showPhoto && editing && !session.layout && session.hasImage && (
        <div className="strip whole" onClick={() => setLightbox(true)}><img src={`/api/jobs/${job.id}/review.webp`} alt="The uploaded photo" /></div>
      )}
      {loading && <p className="muted">Rendering the score…</p>}
      {error && <div className="error">{error}</div>}
      {editing && <div className="mode"><span className="mode-badge">Edit mode</span><span className="muted">A click selects the note and leads the playback there; Space plays from it. Double-click it for its other readings.</span></div>}
      <div className="sheet" ref={host} onClick={onSheetClick} onDoubleClick={onSheetDoubleClick} />
      {session && c && editing && (
        <Toolbar session={session} c={c} onPlayFrom={playFrom} onReadings={() => { if (session.selected) setReadingsFor(session.selected); }}
          onRevert={revert} onReload={onReload} onDone={leaveEdit} staves={staves} />
      )}
      {session && !editing && (
        <div className="edit-row">
          <button className="edit" onClick={enterEdit}>Edit the score</button>
          <span className="muted">
            {session.open().length > 0 ? `${session.open().length} place${session.open().length > 1 ? "s" : ""} to check. ` : ""}
            Correct notes, rests, measures, chords, time and key. Outside edit mode, clicking a note plays from there.
            Double-click a note for its other readings.
          </span>
        </div>
      )}
      {stats && (
        <div className="stats">
          <span>{stats.measures} measures</span>
          <span>{stats.notes} notes</span>
          <span>{stats.rests} rests</span>
          {stats.padded_measures > 0 && <span>{stats.padded_measures} measures padded with rests</span>}
          {(stats.chords ?? 0) > 0 && <span>{stats.chords} chord symbols</span>}
          {(stats.lyrics_syllables ?? 0) > 0 && <span>{stats.lyrics_syllables} syllables of lyrics</span>}
          <span>read by {job.result?.engine} in {job.result?.seconds}s</span>
          {job.edited_at && <span>edited</span>}
        </div>
      )}
      {stats && (stats.chord_warnings?.length || stats.chords_seen?.length || stats.lyrics_seen?.length) ? (
        <div className="stats notes">
          {stats.chord_warnings?.map((w, i) => <span key={"w" + i}>{w}</span>)}
          {stats.lyrics_seen && stats.lyrics_seen.length > 0 && (
            <span>Text seen under the staves but not used as lyrics: {stats.lyrics_seen.map((s) => `"${s.text}" (line ${s.staff}, ${s.reason})`).join(", ")}</span>
          )}
          {stats.chords_seen && stats.chords_seen.length > 0 && (
            <span>Seen above the staves but not used: {stats.chords_seen.map((s) => `"${s.text}" (line ${s.system}, ${s.reason})`).join(", ")}</span>
          )}
        </div>
      ) : null}
      {lightbox && <Lightbox jobId={job.id} onClose={() => setLightbox(false)} />}
      {session && editing && readingsFor && playerRef.current && (
        <ReadingsDialog session={session} jobId={job.id} target={readingsFor} bpm={bpm} player={playerRef.current}
          onApply={(r) => { if (session.apply(r.apply)) setReadingsFor(session.selected); }}
          onClose={() => setReadingsFor(null)} />
      )}
    </section>
  );
}
