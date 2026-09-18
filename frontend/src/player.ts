/**
 * Piano playback for a rendered OSMD score with the cursor following the notes.
 *
 * Note events are read by walking the OSMD cursor once; times are in whole notes, so tempo is applied
 * at playback time. Scheduling is a classic look-ahead loop on the audio clock (no Tone.Transport):
 * every 25 ms it triggers the notes due in the next 120 ms and moves the cursor to the current position
 * (an interval rather than requestAnimationFrame, so it keeps working in a background tab). Looping,
 * pausing and tempo changes are all done by re-anchoring the position to the clock.
 */
import * as Tone from "tone";
import type { OpenSheetMusicDisplay } from "opensheetmusicdisplay";

export type PlaybackState = "stopped" | "playing" | "paused";
export interface LoopRange { from: number; to: number } // 1-based measure numbers, inclusive

interface NoteEvent { time: number; midi: number; length: number } // whole notes

const SAMPLES: Record<string, string> = {
  A1: "A1.mp3", C2: "C2.mp3", "D#2": "Ds2.mp3", "F#2": "Fs2.mp3", A2: "A2.mp3", C3: "C3.mp3", "D#3": "Ds3.mp3",
  "F#3": "Fs3.mp3", A3: "A3.mp3", C4: "C4.mp3", "D#4": "Ds4.mp3", "F#4": "Fs4.mp3", A4: "A4.mp3", C5: "C5.mp3",
  "D#5": "Ds5.mp3", "F#5": "Fs5.mp3", A5: "A5.mp3", C6: "C6.mp3", "D#6": "Ds6.mp3", "F#6": "Fs6.mp3", A6: "A6.mp3",
};
const TICK_MS = 25;
const LOOKAHEAD_S = 0.12;

export class Player {
  measureCount = 0;

  private events: NoteEvent[] = [];
  private steps: number[] = []; // cursor step -> time in whole notes
  private stepMeasure: number[] = []; // cursor step -> 0-based measure index
  private totalWholeNotes = 0;

  private sampler: Tone.Sampler | null = null;
  private ready: Promise<void> | null = null;
  private starting = false;

  private state: PlaybackState = "stopped";
  private bpm = 90;
  private loop = false;
  private winStart = 0;
  private winEnd = 0;
  private startStep = 0;
  // position (whole notes) = anchorPos + (ctxTime - anchorCtx) / secondsPerWhole
  private anchorCtx = 0;
  private anchorPos = 0;
  private nextEvent = 0;
  private cursorStep = 0;
  private pausedAt = 0;
  private timer: number | null = null;
  private lastTick = 0;

  constructor(private osmd: OpenSheetMusicDisplay, private onState: (s: PlaybackState) => void) {
    this.collect();
  }

  private collect(): void {
    const cursor = this.osmd.cursor;
    cursor.reset();
    let prev = -1;
    let last = 0;
    while (!cursor.iterator.EndReached) {
      const t = cursor.iterator.currentTimeStamp.RealValue;
      if (t < prev) break; // the iterator jumped back for a repeat; v1 plays the page straight through
      prev = t;
      this.steps.push(t);
      this.stepMeasure.push(cursor.iterator.CurrentMeasureIndex);
      for (const voiceEntry of cursor.iterator.CurrentVoiceEntries ?? []) {
        for (const note of voiceEntry.Notes) {
          if (note.isRest() || !note.Pitch) continue;
          if (note.NoteTie && note.NoteTie.StartNote !== note) continue; // tied continuation
          const length = note.NoteTie ? note.NoteTie.Duration.RealValue : note.Length.RealValue;
          this.events.push({ time: t, midi: note.halfTone + 12, length });
          last = Math.max(last, t + length);
        }
      }
      cursor.next();
    }
    this.events.sort((a, b) => a.time - b.time);
    this.totalWholeNotes = last;
    this.measureCount = this.stepMeasure.length ? this.stepMeasure[this.stepMeasure.length - 1] + 1 : 0;
    cursor.reset();
  }

  /** Playback window [start, end) in whole notes and the first cursor step for a measure range. */
  private window(range: LoopRange | null): { start: number; end: number; startStep: number } {
    if (!range || this.steps.length === 0) return { start: 0, end: this.totalWholeNotes, startStep: 0 };
    const from = Math.max(1, Math.min(range.from, this.measureCount)) - 1;
    const to = Math.max(from, Math.min(range.to, this.measureCount) - 1);
    const startStep = Math.max(0, this.stepMeasure.findIndex((m) => m >= from));
    const endStep = this.stepMeasure.findIndex((m) => m > to);
    return { start: this.steps[startStep], end: endStep === -1 ? this.totalWholeNotes : this.steps[endStep], startStep };
  }

  private secondsPerWhole(): number {
    return (60 / this.bpm) * 4;
  }

  private positionAt(ctxTime: number): number {
    return this.anchorPos + (ctxTime - this.anchorCtx) / this.secondsPerWhole();
  }

  private ctxTimeAt(position: number): number {
    return this.anchorCtx + (position - this.anchorPos) * this.secondsPerWhole();
  }

  /** Resume the audio context and load the piano once; concurrent callers share the same promise. */
  private ensureReady(): Promise<void> {
    if (!this.ready) {
      this.ready = (async () => {
        await Tone.start();
        this.sampler = new Tone.Sampler({ urls: SAMPLES, baseUrl: "https://tonejs.github.io/audio/salamander/", release: 1 }).toDestination();
        await Tone.loaded();
      })().catch((e) => { this.ready = null; throw e; });
    }
    return this.ready;
  }

  /** Semitones added to every note at playback time, so a song can sit in the singer's range. */
  transpose = 0;

  setTranspose(semitones: number): void {
    this.transpose = Math.max(-24, Math.min(24, Math.round(semitones)));
  }

  setBpm(bpm: number): void {
    if (this.state === "playing") {
      const now = Tone.now();
      this.anchorPos = this.positionAt(now);
      this.anchorCtx = now;
    }
    this.bpm = bpm;
  }

  async play(bpm: number, loop = false, range: LoopRange | null = null): Promise<void> {
    if (this.starting || this.state === "playing") return;
    this.starting = true;
    try {
      await this.ensureReady();
    } finally {
      this.starting = false;
    }
    this.bpm = bpm;
    const resume = this.state === "paused";
    if (!resume) {
      const w = this.window(range);
      this.loop = loop;
      this.winStart = w.start;
      this.winEnd = w.end;
      this.startStep = w.startStep;
      this.pausedAt = w.start;
    }
    const now = Tone.now() + 0.05;
    this.anchorCtx = now;
    this.anchorPos = this.pausedAt;
    this.nextEvent = this.events.findIndex((e) => e.time >= this.anchorPos);
    if (this.nextEvent === -1) this.nextEvent = this.events.length;
    this.moveCursor(this.stepAt(this.anchorPos));
    this.state = "playing";
    this.onState("playing");
    this.lastTick = 0;
    this.timer = window.setInterval(() => { this.tick(); this.followCursor(); }, TICK_MS);
  }

  private stepAt(position: number): number {
    let s = this.startStep;
    while (s + 1 < this.steps.length && this.steps[s + 1] <= position) s++;
    return s;
  }

  private tick(): void {
    const now = Tone.now();
    // Hidden tabs throttle timers to once a second or worse; widen the look-ahead to cover the observed gap.
    const gap = this.lastTick ? now - this.lastTick : 0;
    this.lastTick = now;
    const horizon = now + Math.min(3, Math.max(LOOKAHEAD_S, gap * 1.5));
    // Schedule everything due before the horizon, wrapping at the window end when looping.
    for (let guard = 0; guard < 4; guard++) {
      while (this.nextEvent < this.events.length && this.events[this.nextEvent].time < this.winEnd) {
        const ev = this.events[this.nextEvent];
        const when = this.ctxTimeAt(ev.time);
        if (when > horizon) return;
        this.nextEvent++;
        try {
          this.sampler?.triggerAttackRelease(Tone.Frequency(ev.midi + this.transpose, "midi").toNote(), ev.length * this.secondsPerWhole() * 0.95, Math.max(when, now));
        } catch (e) {
          console.warn("note skipped", ev.midi, e);
        }
      }
      // Reached the end of the window.
      const endCtx = this.ctxTimeAt(this.winEnd);
      if (!this.loop) {
        if (now >= endCtx + 0.3) this.stop();
        return;
      }
      if (endCtx > horizon) return;
      // Re-anchor so that position winStart happens exactly at endCtx, then keep scheduling.
      this.anchorCtx = endCtx;
      this.anchorPos = this.winStart;
      this.nextEvent = this.events.findIndex((e) => e.time >= this.winStart);
      if (this.nextEvent === -1) this.nextEvent = this.events.length;
    }
  }

  private followCursor(): void {
    if (this.state !== "playing") return;
    const pos = this.positionAt(Tone.now());
    if (pos >= this.winStart && pos < this.winEnd) {
      const target = this.stepAt(pos);
      if (target !== this.cursorStep) this.moveCursor(target);
    }
  }

  pause(): void {
    if (this.state !== "playing") return;
    this.pausedAt = Math.min(this.positionAt(Tone.now()), this.winEnd);
    this.clearTimers();
    this.sampler?.releaseAll();
    this.state = "paused";
    this.onState("paused");
  }

  stop(): void {
    this.clearTimers();
    this.sampler?.releaseAll();
    this.state = "stopped";
    this.osmd.cursor.reset();
    this.cursorStep = 0;
    this.osmd.cursor.show();
    this.onState("stopped");
  }

  private clearTimers(): void {
    if (this.timer !== null) { window.clearInterval(this.timer); this.timer = null; }
  }

  /** Move the cursor to `step` incrementally (rewind only when going backwards), then keep it in view. */
  private moveCursor(step: number): void {
    const cursor = this.osmd.cursor;
    if (step < this.cursorStep) {
      cursor.reset();
      this.cursorStep = 0;
    }
    let guard = this.steps.length + 1;
    while (this.cursorStep < step && !cursor.iterator.EndReached && guard-- > 0) {
      cursor.next();
      this.cursorStep++;
    }
    cursor.show();
    const el = cursor.cursorElement;
    if (el) {
      const r = el.getBoundingClientRect();
      if (r.top < 80 || r.bottom > window.innerHeight - 40) {
        el.scrollIntoView({ block: "center", behavior: "smooth" });
      }
    }
  }

  dispose(): void {
    this.clearTimers();
    this.sampler?.dispose();
    this.sampler = null;
    this.ready = null;
  }
}
