/**
 * The tempo rules of the player (player controls). One place for the range, the step, a typed value
 * and what "default" means, so the slider, the stepper and the reset all agree.
 *
 * The slider's 40 to 180 is kept; it only widens when the score's own marking falls outside it, so
 * that reset is always reachable. A score with no marking plays at 90.
 */
export interface TempoRange { min: number; max: number }

export const MIN_BPM = 40;
export const MAX_BPM = 180;
export const FALLBACK_BPM = 90;

const BASE: TempoRange = { min: MIN_BPM, max: MAX_BPM };

export function clampTempo(bpm: number, range: TempoRange = BASE): number {
  return Math.min(range.max, Math.max(range.min, Math.round(bpm)));
}

export function stepTempo(bpm: number, delta: number, range: TempoRange = BASE): number {
  return clampTempo(bpm + delta, range);
}

/** A typed value: a plain number is clamped into the range, anything else is null (the field reverts). */
export function parseTempo(text: string, range: TempoRange = BASE): number | null {
  const t = text.trim();
  if (!/^\d+(\.\d+)?$/.test(t)) return null;
  return clampTempo(Number(t), range);
}

/** The first tempo written in the score: a sound tempo attribute, else a metronome mark. Null when none. */
export function markedTempo(xml: string): number | null {
  const doc = new DOMParser().parseFromString(xml, "application/xml");
  if (doc.getElementsByTagName("parsererror").length) return null;
  const valid = (v: string | null | undefined) => {
    const n = Number(v);
    return v != null && v.trim() !== "" && Number.isFinite(n) && n > 0 ? n : null;
  };
  // Document order: the first marking of either kind wins.
  for (const el of Array.from(doc.getElementsByTagName("*"))) {
    if (el.localName === "sound") {
      const n = valid(el.getAttribute("tempo"));
      if (n) return n;
    } else if (el.localName === "per-minute") {
      const n = valid(el.textContent);
      if (n) return n;
    }
  }
  return null;
}

export function defaultTempo(xml: string): number {
  const m = markedTempo(xml);
  return m == null ? FALLBACK_BPM : Math.round(m);
}

export function tempoRange(defaultBpm: number): TempoRange {
  return { min: Math.min(MIN_BPM, defaultBpm), max: Math.max(MAX_BPM, defaultBpm) };
}
