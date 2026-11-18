/**
 * The voices a line can be played with (ADR 0008, decisions 2 and 3).
 *
 * The piano is the one the app has always used — the Salamander set on tonejs.github.io — and it is
 * the default, the fallback, and what the accompaniment always plays. The others come from the
 * sample collection pinned in `voices.data.ts`, fetched the first time a line is given one: the
 * bundle holds no audio and the image holds none either, which is what lets the app run on the small
 * ARM VPS it is deployed on.
 *
 * `instrumentAt` is the other half, and it is pure: an instrument belongs to a line *over a stretch
 * of measures*, because a printed page reuses its staves — on the canon page the top staff is a
 * flute for eight measures and a voice for twelve after it.
 */
import * as Tone from "tone";
import { SETS } from "./voices.data";

export interface SampleSet {
  id: string;
  label: string;
  baseUrl: string;
  /** The written range of the set, in MIDI numbers, before thinning. */
  lowest: number;
  highest: number;
  /** Trim in dB, so the sets sit level with the piano. */
  gain: number;
  urls: Record<string, string>;
}

/** The Salamander grand, CC-BY 3.0, as `player.ts` has fetched it since the first day. */
export const PIANO: SampleSet = {
  id: "piano",
  label: "Piano",
  baseUrl: "https://tonejs.github.io/audio/salamander/",
  lowest: 33,
  highest: 93,
  gain: 0,
  urls: {
    A1: "A1.mp3", C2: "C2.mp3", "D#2": "Ds2.mp3", "F#2": "Fs2.mp3", A2: "A2.mp3", C3: "C3.mp3", "D#3": "Ds3.mp3",
    "F#3": "Fs3.mp3", A3: "A3.mp3", C4: "C4.mp3", "D#4": "Ds4.mp3", "F#4": "Fs4.mp3", A4: "A4.mp3", C5: "C5.mp3",
    "D#5": "Ds5.mp3", "F#5": "Fs5.mp3", A5: "A5.mp3", C6: "C6.mp3", "D#6": "Ds6.mp3", "F#6": "Fs6.mp3", A6: "A6.mp3",
  },
};

export const VOICES: SampleSet[] = [PIANO, ...SETS];
export const DEFAULT_VOICE = PIANO.id;

export function voiceSet(id: string): SampleSet {
  return VOICES.find((v) => v.id === id) ?? PIANO;
}

export function isVoice(id: string): boolean {
  return VOICES.some((v) => v.id === id);
}

/**
 * A line's instrument over a stretch of printed measures, 0-based and inclusive (ADR 0008,
 * decision 2). A line with no entry plays the piano.
 */
export interface Voicing { line: number; from: number; to: number; instrument: string }

/** The instrument a line sounds with in a measure: the last entry that covers it, or the piano. */
export function instrumentAt(voicings: Voicing[], line: number, measure: number): string {
  let found = DEFAULT_VOICE;
  for (const v of voicings) {
    if (v.line !== line || measure < v.from || measure > v.to) continue;
    found = v.instrument;
  }
  return found;
}

/** How far a note falls outside a set's written range, in semitones; 0 when it is inside. */
export function outsideRange(set: SampleSet, midi: number): number {
  if (midi < set.lowest) return set.lowest - midi;
  if (midi > set.highest) return midi - set.highest;
  return 0;
}

/**
 * The samplers in play, made once each and kept.
 *
 * A set is loaded when a line is first given it; until it is there the caller keeps playing what it
 * had, and a set that cannot be fetched (an offline browser, a CDN that is down) falls back to the
 * piano and says so once, through `onFailure`.
 */
export class VoiceBank {
  private loaded = new Map<string, Tone.Sampler>();
  private loading = new Map<string, Promise<Tone.Sampler>>();
  private failed = new Set<string>();

  constructor(private onFailure: ((set: SampleSet) => void) | null = null) {}

  /** The sampler for an instrument if it is ready, else the piano if that is, else null. */
  get(id: string): Tone.Sampler | null {
    return this.loaded.get(id) ?? this.loaded.get(PIANO.id) ?? null;
  }

  ready(id: string): boolean {
    return this.loaded.has(id);
  }

  /** Fetch a set. Resolves to the piano's sampler when the set cannot be loaded. */
  load(id: string): Promise<Tone.Sampler> {
    const ready = this.loaded.get(id);
    if (ready) return Promise.resolve(ready);
    const started = this.loading.get(id);
    if (started) return started;
    const set = voiceSet(id);
    const task = new Promise<Tone.Sampler>((resolve, reject) => {
      const sampler = new Tone.Sampler({
        urls: set.urls,
        baseUrl: set.baseUrl,
        release: 1,
        onload: () => resolve(sampler),
        onerror: (e) => reject(e),
      }).toDestination();
      sampler.volume.value = set.gain;
    })
      .then((sampler) => {
        this.loaded.set(id, sampler);
        return sampler;
      })
      .catch(async () => {
        this.loading.delete(id);
        if (!this.failed.has(id)) {
          this.failed.add(id);
          this.onFailure?.(set);
        }
        if (id === PIANO.id) throw new Error("the piano could not be loaded");
        return this.load(PIANO.id);
      });
    this.loading.set(id, task);
    return task;
  }

  /** Every sampler in play, for releasing notes on a stop or a seek. */
  all(): Tone.Sampler[] {
    return [...this.loaded.values()];
  }

  releaseAll(): void {
    for (const sampler of this.loaded.values()) sampler.releaseAll();
  }

  dispose(): void {
    for (const sampler of this.loaded.values()) sampler.dispose();
    this.loaded.clear();
    this.loading.clear();
  }
}
