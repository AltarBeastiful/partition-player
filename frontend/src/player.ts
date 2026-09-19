/**
 * Piano playback for a rendered OSMD score with the cursor following the notes.
 *
 * The sheet is walked once in printed order with OSMD's cursor (repeats ignored): one step per cursor
 * position with its notes, and the measure grid. Playback then follows a list of passes (plan 0004):
 * the printed steps of each pass's measures laid end to end on an unrolled timeline, so a verse
 * section can play four times and a chorus after each. Times are in whole notes; tempo is applied at
 * playback time. Scheduling is a classic look-ahead loop on the audio clock (no Tone.Transport):
 * every 25 ms it triggers the notes due in the next 120 ms and moves the cursor to the current
 * position (an interval rather than requestAnimationFrame, so it keeps working in a background tab).
 * Looping, pausing, seeking and tempo changes are all done by re-anchoring the position to the clock.
 */
import * as Tone from "tone";
import { accompaniment, collectChords, type ChordSymbol } from "./chords";
import type { Pass } from "./form";
import type { OpenSheetMusicDisplay } from "opensheetmusicdisplay";

export type PlaybackState = "stopped" | "playing" | "paused";
export interface LoopRange { from: number; to: number } // 1-based printed measure numbers, inclusive

export type Track = "melody" | "accompaniment";
interface NoteEvent { time: number; midi: number; length: number; track: Track; velocity: number } // whole notes
interface PrintedStep { time: number; measure: number; notes: { midi: number; length: number }[] }
interface Step { time: number; printed: number; measure: number; pass: number } // on the unrolled timeline

const SAMPLES: Record<string, string> = {
  A1: "A1.mp3", C2: "C2.mp3", "D#2": "Ds2.mp3", "F#2": "Fs2.mp3", A2: "A2.mp3", C3: "C3.mp3", "D#3": "Ds3.mp3",
  "F#3": "Fs3.mp3", A3: "A3.mp3", C4: "C4.mp3", "D#4": "Ds4.mp3", "F#4": "Fs4.mp3", A4: "A4.mp3", C5: "C5.mp3",
  "D#5": "Ds5.mp3", "F#5": "Fs5.mp3", A5: "A5.mp3", C6: "C6.mp3", "D#6": "Ds6.mp3", "F#6": "Fs6.mp3", A6: "A6.mp3",
};
const TICK_MS = 25;
const LOOKAHEAD_S = 0.12;

export class Player {
  measureCount = 0; // printed measures
  chords: ChordSymbol[] = [];
  passes: Pass[] = [];
  readonly tracks: Record<Track, boolean> = { melody: true, accompaniment: true };
  /** Called when the pass being played changes; null when stopped. */
  onPass: ((pass: number | null) => void) | null = null;

  // printed order
  private printed: PrintedStep[] = [];
  private measureStart: number[] = [];
  private measureDuration: number[] = [];
  private accompByMeasure: { at: number; midi: number; length: number; velocity: number }[][] = [];

  // unrolled timeline
  private events: NoteEvent[] = [];
  private steps: Step[] = [];
  private totalWholeNotes = 0;

  private sampler: Tone.Sampler | null = null;
  private ready: Promise<void> | null = null;
  private starting = false;

  private state: PlaybackState = "stopped";
  private bpm = 90;
  private loop = false;
  private winStart = 0;
  private winEnd = 0;
  // position (whole notes) = anchorPos + (ctxTime - anchorCtx) / secondsPerWhole
  private anchorCtx = 0;
  private anchorPos = 0;
  private nextEvent = 0;
  private cursorPrinted = 0; // the printed step the cursor stands on
  private currentPass: number | null = null;
  private pausedAt = 0;
  private pending: number | null = null; // where the next Play starts after a click on a note while stopped
  private timer: number | null = null;
  private lastTick = 0;

  constructor(private osmd: OpenSheetMusicDisplay, private onState: (s: PlaybackState) => void) {
    this.collect();
    this.setPasses(this.wholePage());
  }

  /** Read the sheet again after it was edited and re-rendered; the piano stays loaded. */
  rebuild(passes?: Pass[]): void {
    this.stop();
    this.collect();
    this.setPasses(passes ?? this.wholePage());
  }

  /** One pass over every printed measure. */
  wholePage(): Pass[] {
    return this.measureCount ? [{ ranges: [{ from: 0, to: this.measureCount - 1 }], verse: null }] : [];
  }

  /** The total length of the timeline in whole notes. */
  get length(): number {
    return this.totalWholeNotes;
  }

  private collect(): void {
    this.printed = [];
    this.measureStart = [];
    this.measureDuration = [];
    this.accompByMeasure = [];
    this.osmd.EngravingRules.CursorIgnoreRepetitions = true; // the printed order; the passes do the jumping
    const cursor = this.osmd.cursor;
    cursor.reset();
    let prev = -1;
    let guard = 200_000;
    while (!cursor.iterator.EndReached && guard-- > 0) {
      const t = cursor.iterator.currentTimeStamp.RealValue;
      if (t < prev) break; // never with repeats ignored; a guard against an iterator that still jumps
      prev = t;
      const step: PrintedStep = { time: t, measure: cursor.iterator.CurrentMeasureIndex, notes: [] };
      for (const voiceEntry of cursor.iterator.CurrentVoiceEntries ?? []) {
        for (const note of voiceEntry.Notes) {
          if (note.isRest() || !note.Pitch) continue;
          if (note.NoteTie && note.NoteTie.StartNote !== note) continue; // tied continuation
          const length = note.NoteTie ? note.NoteTie.Duration.RealValue : note.Length.RealValue;
          step.notes.push({ midi: note.halfTone + 12, length });
        }
      }
      this.printed.push(step);
      cursor.next();
    }
    cursor.reset();
    const { chords, measures } = collectChords(this.osmd);
    this.chords = chords;
    for (const m of measures) { this.measureStart.push(m.start); this.measureDuration.push(m.duration); this.accompByMeasure.push([]); }
    this.measureCount = measures.length;
    for (const e of accompaniment(chords, measures)) {
      const m = this.printedMeasureAt(e.time);
      if (m !== null) this.accompByMeasure[m].push({ at: e.time - this.measureStart[m], midi: e.midi, length: e.length, velocity: e.velocity });
    }
  }

  private printedMeasureAt(time: number): number | null {
    for (let m = this.measureStart.length - 1; m >= 0; m--) if (time >= this.measureStart[m] - 1e-9) return m;
    return null;
  }

  /** Lay the passes end to end. Stops playback, since every position changes meaning. */
  setPasses(passes: Pass[]): void {
    this.stop();
    this.passes = passes;
    this.events = [];
    this.steps = [];
    let t = 0;
    let last = 0;
    passes.forEach((pass, pi) => {
      for (const r of pass.ranges) {
        for (let m = Math.max(0, r.from); m <= Math.min(r.to, this.measureCount - 1); m++) {
          const start = this.measureStart[m];
          this.printed.forEach((step, si) => {
            if (step.measure !== m) return;
            const time = t + (step.time - start);
            this.steps.push({ time, printed: si, measure: m, pass: pi });
            for (const n of step.notes) { this.events.push({ time, midi: n.midi, length: n.length, track: "melody", velocity: 0.9 }); last = Math.max(last, time + n.length); }
          });
          for (const a of this.accompByMeasure[m]) { this.events.push({ time: t + a.at, midi: a.midi, length: a.length, track: "accompaniment", velocity: a.velocity }); last = Math.max(last, t + a.at + a.length); }
          t += this.measureDuration[m];
        }
      }
    });
    this.events.sort((a, b) => a.time - b.time);
    this.totalWholeNotes = Math.max(t, last);
  }

  /** The unrolled step at a position, searched from the start. */
  private stepIndex(position: number): number {
    let s = 0;
    while (s + 1 < this.steps.length && this.steps[s + 1].time <= position + 1e-9) s++;
    return s;
  }

  /** The start times of every occurrence of a printed measure on the timeline. */
  private occurrences(measure: number): number[] {
    const out: number[] = [];
    let lastPass = -1;
    for (const s of this.steps) {
      if (s.measure === measure && s.pass !== lastPass) { out.push(s.time - (this.printed[s.printed].time - this.measureStart[measure])); lastPass = s.pass; }
    }
    return out;
  }

  /** Where playback stands now, whatever the state. */
  private here(): number {
    if (this.state === "playing") return this.positionAt(Tone.now());
    if (this.state === "paused") return this.pausedAt;
    return this.pending ?? 0;
  }

  /**
   * The playback position of a note: in the occurrence of its measure that holds the current
   * position, else the next one, else the first; plus the onset. Null when the measure is not played.
   */
  positionOf(measure: number, onset: number): number | null {
    const occ = this.occurrences(measure);
    if (occ.length === 0) return null;
    const now = this.here();
    const duration = this.measureDuration[measure] ?? 0;
    const start = occ.find((s) => s + duration > now + 1e-9) ?? occ[0];
    const at = start + onset;
    return this.steps[this.stepIndex(at)]?.time ?? at;
  }

  /** Playback window [start, end) on the timeline for a range of printed measures. */
  private window(range: LoopRange | null): { start: number; end: number } {
    if (!range || this.steps.length === 0) return { start: 0, end: this.totalWholeNotes };
    const from = Math.max(1, Math.min(range.from, this.measureCount)) - 1;
    const to = Math.max(from, Math.min(range.to, this.measureCount) - 1);
    const start = this.occurrences(from)[0] ?? 0;
    const endStart = this.occurrences(to).find((s) => s >= start - 1e-9);
    const end = endStart === undefined ? this.totalWholeNotes : endStart + this.measureDuration[to];
    return { start, end: Math.min(end, this.totalWholeNotes) };
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

  setTrack(track: Track, on: boolean): void {
    this.tracks[track] = on;
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
      this.pausedAt = w.start;
      // A note clicked while stopped: start there. Outside the range, the range stretches to it.
      if (this.pending !== null) {
        if (this.pending < this.winStart || this.pending >= this.winEnd) {
          this.winStart = Math.min(this.winStart, this.pending);
          this.winEnd = this.totalWholeNotes;
        }
        this.pausedAt = this.pending;
        this.pending = null;
      }
    }
    const now = Tone.now() + 0.05;
    this.anchorCtx = now;
    this.anchorPos = this.pausedAt;
    this.nextEvent = this.events.findIndex((e) => e.time >= this.anchorPos);
    if (this.nextEvent === -1) this.nextEvent = this.events.length;
    this.moveTo(this.stepIndex(this.anchorPos));
    this.state = "playing";
    this.onState("playing");
    this.lastTick = 0;
    this.timer = window.setInterval(() => { this.tick(); this.followCursor(); }, TICK_MS);
  }

  /**
   * Lead playback to a position. Playing: the notes continue from there without a break. Paused:
   * resuming starts there. Stopped: the cursor moves there and the next Play starts there. A position
   * outside the measure range extends the range to the end of the score.
   */
  seek(position: number): void {
    const total = this.totalWholeNotes;
    position = Math.max(0, Math.min(position, total));
    if (this.state === "stopped") {
      this.pending = position;
      this.moveTo(this.stepIndex(position));
      return;
    }
    if (position < this.winStart || position >= this.winEnd) {
      this.winStart = Math.min(this.winStart, position);
      this.winEnd = total;
    }
    if (this.state === "paused") {
      this.pausedAt = position;
      this.moveTo(this.stepIndex(position));
      return;
    }
    this.sampler?.releaseAll();
    this.anchorCtx = Tone.now();
    this.anchorPos = position;
    this.nextEvent = this.events.findIndex((e) => e.time >= position);
    if (this.nextEvent === -1) this.nextEvent = this.events.length;
    this.moveTo(this.stepIndex(position));
  }

  /** Back to the beginning of the range: keeps playing from there, or stops at the start. */
  restart(): void {
    if (this.state === "playing") this.seek(this.winStart);
    else this.stop();
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
          if (this.tracks[ev.track]) {
            this.sampler?.triggerAttackRelease(Tone.Frequency(ev.midi + this.transpose, "midi").toNote(), ev.length * this.secondsPerWhole() * 0.95, Math.max(when, now), ev.velocity);
          }
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
      const target = this.stepIndex(pos);
      const s = this.steps[target];
      if (s && (s.printed !== this.cursorPrinted || s.pass !== this.currentPass)) this.moveTo(target);
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
    this.pending = null;
    this.state = "stopped";
    this.osmd.cursor.reset();
    this.cursorPrinted = 0;
    this.osmd.cursor.show();
    if (this.currentPass !== null) { this.currentPass = null; this.onPass?.(null); }
    this.onState("stopped");
  }

  private clearTimers(): void {
    if (this.timer !== null) { window.clearInterval(this.timer); this.timer = null; }
  }

  /** Put the cursor on an unrolled step and report its pass. */
  private moveTo(step: number): void {
    const s = this.steps[step];
    if (!s) return;
    this.moveCursor(s.printed);
    if (s.pass !== this.currentPass) { this.currentPass = s.pass; this.onPass?.(s.pass); }
  }

  /** Move the cursor to a printed step incrementally (rewind only when going backwards), then keep it in view. */
  private moveCursor(printed: number): void {
    const cursor = this.osmd.cursor;
    if (printed < this.cursorPrinted) {
      cursor.reset();
      this.cursorPrinted = 0;
    }
    let guard = this.printed.length + 1;
    while (this.cursorPrinted < printed && !cursor.iterator.EndReached && guard-- > 0) {
      cursor.next();
      this.cursorPrinted++;
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
