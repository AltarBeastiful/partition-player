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
  const [loop, setLoop] = useState(false);
  const [from, setFrom] = useState(1);
  const [to, setTo] = useState(1);
  const [measureCount, setMeasureCount] = useState(0);

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
        const player = new Player(osmd, setState);
        playerRef.current = player;
        (window as unknown as { __player?: Player }).__player = player; // debugging aid
        setMeasureCount(player.measureCount);
        setTo(player.measureCount);
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
    else await p.play(bpm, loop, { from, to });
  }, [state, bpm, loop, from, to]);

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
