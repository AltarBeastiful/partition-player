import { useCallback, useEffect, useRef, useState } from "react";
import { OpenSheetMusicDisplay } from "opensheetmusicdisplay";
import { scoreUrl, type Job } from "../api";
import { clearNoteNames, drawNoteNames, keepNoteNames, reserveNoteNamesSpace } from "../noteNames";
import { Player, type PlaybackState } from "../player";

const NOTE_NAMES_PREF = "pp.noteNames"; // a practice preference, not a property of the score

function readNoteNamesPref(): boolean {
  try { return localStorage.getItem(NOTE_NAMES_PREF) === "1"; } catch { return false; }
}

function writeNoteNamesPref(on: boolean): void {
  try { localStorage.setItem(NOTE_NAMES_PREF, on ? "1" : "0"); } catch { /* private browsing */ }
}

export function ScoreView({ job, version = 0 }: { job: Job; version?: number }) {
  const host = useRef<HTMLDivElement>(null);
  const osmdRef = useRef<OpenSheetMusicDisplay | null>(null);
  const playerRef = useRef<Player | null>(null);
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
        await osmd.load(scoreUrl(job.id, version));
        if (cancelled) return;
        reserveNoteNamesSpace(osmd, noteNamesRef.current); // before the first render, so nothing jumps
        osmd.render();
        osmd.cursor.show();
        osmdRef.current = osmd;
        const player = new Player(osmd, setState);
        playerRef.current = player;
        (window as unknown as { __player?: Player }).__player = player; // debugging aid
        setMeasureCount(player.measureCount);
        setChordCount(player.chords.length);
        setTo(player.measureCount);
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
      playerRef.current?.dispose();
      playerRef.current = null;
      osmdRef.current?.clear();
      osmdRef.current = null;
      host.current?.replaceChildren();
    };
  }, [job.id, version]);

  const toggle = useCallback(async () => {
    const p = playerRef.current;
    if (!p) return;
    if (state === "playing") p.pause();
    else await p.play(bpm, loop, { from, to });
  }, [state, bpm, loop, from, to]);

  const stop = useCallback(() => playerRef.current?.stop(), []);

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
  }, [noteNames, loading]);

  // OSMD re-renders by itself, on resize: the names have to be put back each time it does.
  useEffect(() => {
    const osmd = osmdRef.current;
    if (!noteNames || loading || !osmd || !host.current) return;
    return keepNoteNames(osmd, host.current);
  }, [noteNames, loading]);

  const stats = job.result?.stats;
  return (
    <section className="card">
      <div className="controls">
        <button className="primary" onClick={toggle} disabled={loading || !!error}>
          {state === "playing" ? "Pause" : "Play"}
        </button>
        <button onClick={stop} disabled={loading || state === "stopped"}>Stop</button>
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
      </div>
      {chordCount > 0 && (
        <div className="controls loop">
          <label><input id="melody" type="checkbox" checked={melodyOn} onChange={(e) => setMelodyOn(e.target.checked)} /> Melody</label>
          <label><input id="accompaniment" type="checkbox" checked={accompOn} onChange={(e) => setAccompOn(e.target.checked)} /> Accompaniment</label>
          <span className="muted">Piano chords from the {chordCount} chord symbols on the page. Turn the melody off to sing it yourself.</span>
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
      {loading && <p className="muted">Rendering the score…</p>}
      {error && <div className="error">{error}</div>}
      <div className="sheet" ref={host} />
    </section>
  );
}
