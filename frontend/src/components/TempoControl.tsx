import { useEffect, useRef, useState } from "react";
import { parseTempo, stepTempo, type TempoRange } from "../tempo";

const HOLD_DELAY = 400;   // ms before a held button starts repeating
const HOLD_EVERY = 70;    // ms between repeated steps

/** −/+ stepper (±1 bpm, repeating while held), a typed value, the slider and a reset. The rules live in tempo.ts. */
export function TempoControl({ bpm, range, differs, disabled, onChange, onReset }: {
  bpm: number; range: TempoRange; differs: boolean; disabled?: boolean;
  onChange: (bpm: number) => void; onReset: () => void;
}) {
  const [text, setText] = useState(String(bpm));
  const [editing, setEditing] = useState(false);
  useEffect(() => { if (!editing) setText(String(bpm)); }, [bpm, editing]);

  // A held button steps from the latest value, so the step reads it through a ref.
  const current = useRef(bpm);
  current.current = bpm;
  const timers = useRef<{ delay?: number; every?: number }>({});
  const release = () => {
    window.clearTimeout(timers.current.delay);
    window.clearInterval(timers.current.every);
    timers.current = {};
  };
  useEffect(() => release, []);
  // A press that ends outside the button (or while the button is disabled) must not leave it repeating.
  useEffect(() => {
    window.addEventListener("pointerup", release);
    window.addEventListener("pointercancel", release);
    return () => { window.removeEventListener("pointerup", release); window.removeEventListener("pointercancel", release); };
  }, []);
  useEffect(() => { if (disabled) release(); }, [disabled]);
  const press = (delta: number) => (e: React.PointerEvent) => {
    if (disabled) return;
    e.preventDefault();
    release();
    const step = () => { current.current = stepTempo(current.current, delta, range); onChange(current.current); };
    step();
    timers.current.delay = window.setTimeout(() => { timers.current.every = window.setInterval(step, HOLD_EVERY); }, HOLD_DELAY);
  };
  const held = (delta: number) => ({
    onPointerDown: press(delta), onPointerUp: release, onPointerLeave: release, onPointerCancel: release,
    onKeyDown: (e: React.KeyboardEvent) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onChange(stepTempo(current.current, delta, range)); } },
  });

  const reverting = useRef(false);   // Escape: the blur that follows must not commit the half-typed text
  const commit = () => {
    setEditing(false);
    if (reverting.current) { reverting.current = false; setText(String(bpm)); return; }
    const n = parseTempo(text, range);
    if (n == null) setText(String(bpm));
    else { setText(String(n)); if (n !== bpm) onChange(n); }
  };

  return (
    <div className="tempo-control">
      <span className="tempo-label">Tempo</span>
      <button className="step" aria-label="One bpm slower" disabled={disabled} {...held(-1)}>−</button>
      <input id="tempo-value" className="tempo-value" type="text" inputMode="numeric" aria-label="Tempo in bpm" value={text} disabled={disabled}
        onFocus={() => setEditing(true)} onChange={(e) => setText(e.target.value)} onBlur={commit}
        onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); if (e.key === "Escape") { reverting.current = true; setText(String(bpm)); (e.target as HTMLInputElement).blur(); } }} />
      <button className="step" aria-label="One bpm faster" disabled={disabled} {...held(1)}>+</button>
      <span className="tempo-unit">bpm</span>
      <input id="tempo" type="range" aria-label="Tempo" min={range.min} max={range.max} value={bpm} disabled={disabled} onChange={(e) => onChange(Number(e.target.value))} />
      {differs && <button className="tempo-reset" onClick={onReset} disabled={disabled} title="Back to the score's own tempo">Reset</button>}
    </div>
  );
}
