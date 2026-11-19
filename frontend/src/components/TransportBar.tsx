import { useEffect, useState } from "react";
import type { PlaybackState } from "../player";

/** The main controls' Play/Pause, Stop and Start, repeated in a compact bar while the main row is scrolled out of
 *  view. It only shows what the view hands it: the same state and handlers, so it cannot disagree with them. */
export function TransportBar({ watch, state, bpm, loading, error, preparing, onToggle, onStop, onRestart }: {
  watch: HTMLElement | null; state: PlaybackState; bpm: number; loading: boolean; error: boolean; preparing: boolean;
  onToggle: () => void; onStop: () => void; onRestart: () => void;
}) {
  const [away, setAway] = useState(false);
  const [lift, setLift] = useState(0);   // height of the editor's sticky toolbar, which the phone bar stacks above

  useEffect(() => {
    if (!watch || typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver(([entry]) => setAway(!entry.isIntersecting));
    io.observe(watch);
    return () => io.disconnect();
  }, [watch]);

  useEffect(() => {
    if (!away) return;
    const tb = document.querySelector<HTMLElement>(".toolbar");
    if (!tb || typeof ResizeObserver === "undefined") { setLift(0); return; }
    const ro = new ResizeObserver(() => setLift(tb.offsetHeight));
    ro.observe(tb);
    setLift(tb.offsetHeight);
    return () => ro.disconnect();
  }, [away]);

  if (!away) return null;
  return (
    <div className="transport-bar" role="toolbar" aria-label="Playback" style={{ ["--toolbar-h" as string]: `${lift}px` }}>
      <button className="primary" onClick={onToggle} disabled={loading || error || preparing}>
        {state === "playing" ? "Pause" : preparing ? "Loading sounds…" : "Play"}
      </button>
      <button onClick={onStop} disabled={loading || state === "stopped"}>Stop</button>
      <button onClick={onRestart} disabled={loading || error} aria-label="Back to the beginning">⏮ Start</button>
      <span className="transport-tempo">{bpm} bpm</span>
    </div>
  );
}
