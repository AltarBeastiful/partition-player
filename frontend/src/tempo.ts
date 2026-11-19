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
export const MAX_STORED_BPM = 400;   // the server's bound (review.MAX_TEMPO)

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

const UNIT_IN_QUARTERS: Record<string, number> = {
  maxima: 32, long: 16, breve: 8, whole: 4, half: 2, quarter: 1, eighth: 0.5, "16th": 0.25, "32nd": 0.125, "64th": 0.0625,
};

/** The first tempo written in the score, in quarters per minute: a sound tempo attribute (already
 *  quarters), else a metronome mark scaled by its beat unit and dot. Null when none. */
export function markedTempo(xml: string): number | null {
  const doc = new DOMParser().parseFromString(xml, "application/xml");
  if (doc.getElementsByTagName("parsererror").length) return null;
  const valid = (v: string | null | undefined) => {
    const n = Number(v);
    return v != null && v.trim() !== "" && Number.isFinite(n) && n > 0 ? n : null;
  };
  const inside = (el: Element, name: string) => Array.from(el.getElementsByTagName("*")).filter((c) => c.localName === name);
  // Document order: the first marking of either kind wins; a direction's sound tempo beats its metronome.
  for (const el of Array.from(doc.getElementsByTagName("*"))) {
    if (el.localName === "sound") {
      const n = valid(el.getAttribute("tempo"));
      if (n) return n;
    } else if (el.localName === "metronome") {
      const dir = el.closest("direction");
      const snd = dir ? inside(dir, "sound").map((s) => valid(s.getAttribute("tempo"))).find(Boolean) : null;
      if (snd) return snd;
      const pm = valid(inside(el, "per-minute")[0]?.textContent);
      if (!pm) continue;
      const unit = UNIT_IN_QUARTERS[inside(el, "beat-unit")[0]?.textContent?.trim() ?? "quarter"] ?? 1;
      return pm * unit * (inside(el, "beat-unit-dot").length ? 1.5 : 1);
    }
  }
  return null;
}

/** The score's marking as a whole number the server will keep (40 to 400), or 90. */
export function defaultTempo(xml: string): number {
  const m = markedTempo(xml);
  return m == null ? FALLBACK_BPM : Math.min(MAX_STORED_BPM, Math.max(MIN_BPM, Math.round(m)));
}

export function tempoRange(defaultBpm: number): TempoRange {
  return { min: Math.min(MIN_BPM, defaultBpm), max: Math.max(MAX_BPM, defaultBpm) };
}
