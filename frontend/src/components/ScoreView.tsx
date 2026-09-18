import { useCallback, useEffect, useRef, useState } from "react";
import { OpenSheetMusicDisplay } from "opensheetmusicdisplay";
import { scoreUrl, type Job } from "../api";
import { Player, type PlaybackState } from "../player";

export function ScoreView({ job }: { job: Job }) {
  const host = useRef<HTMLDivElement>(null);
  const osmdRef = useRef<OpenSheetMusicDisplay | null>(null);
  const playerRef = useRef<Player | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [state, setState] = useState<PlaybackState>("stopped");
  const [bpm, setBpm] = useState(90);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      if (!host.current) return;
      const osmd = new OpenSheetMusicDisplay(host.current, {
        autoResize: true,
        drawTitle: true,
        drawPartNames: false,
        followCursor: false,
        cursorsOptions: [{ type: 0, color: "#0e7490", alpha: 0.35, follow: false }],
      });
      try {
        await osmd.load(scoreUrl(job.id));
        if (cancelled) return;
        osmd.render();
        osmd.cursor.show();
        osmdRef.current = osmd;
        playerRef.current = new Player(osmd, setState);
        setLoading(false);
      } catch (e) {
        setError("Could not render the score: " + (e as Error).message);
        setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; playerRef.current?.dispose(); };
  }, [job.id]);

  const toggle = useCallback(async () => {
    const p = playerRef.current;
    if (!p) return;
    if (state === "playing") p.pause();
    else await p.play(bpm);
  }, [state, bpm]);

  const stop = useCallback(() => playerRef.current?.stop(), []);

  useEffect(() => { playerRef.current?.setBpm(bpm); }, [bpm]);

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
        <a href={scoreUrl(job.id)} download={`score-${job.id}.musicxml`}>Download MusicXML</a>
      </div>
      {stats && (
        <div className="stats">
          <span>{stats.measures} measures</span>
          <span>{stats.notes} notes</span>
          <span>{stats.rests} rests</span>
          {stats.padded_measures > 0 && <span>{stats.padded_measures} measures padded with rests</span>}
          <span>read by {job.result?.engine} in {job.result?.seconds}s</span>
        </div>
      )}
      {loading && <p className="muted">Rendering the score…</p>}
      {error && <div className="error">{error}</div>}
      <div className="sheet" ref={host} />
    </section>
  );
}
