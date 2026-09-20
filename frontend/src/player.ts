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
 * A preview (plan 0005) is a handful of notes played straight on the sampler, beside this timeline.
 */
import * as Tone from "tone";
import { accompaniment, collectChords, type ChordSymbol } from "./chords";
import { samePrefix, type Pass } from "./form";
import type { OpenSheetMusicDisplay } from "opensheetmusicdisplay";

export type PlaybackState = "stopped" | "playing" | "paused";
export interface LoopRange { from: number; to: number } // 1-based printed measure numbers, inclusive

export type Track = "melody" | "accompaniment";
/** A note of a preview: time and length in whole notes from the start of the excerpt (plan 0005). */
export interface PreviewNote { time: number; midi: number; length: number }
export interface NoteEvent { time: number; midi: number; length: number; track: Track; velocity: number } // whole notes
export interface PrintedStep { time: number; measure: number; notes: { midi: number; length: number }[] }
export interface Step { time: number; printed: number; measure: number; pass: number } // on the unrolled timeline
export interface AccompPulse { at: number; midi: number; length: number; velocity: number } // `at` from the measure start

/** The page in printed order: what the passes are laid out from. */
export interface PrintedScore {
  printed: PrintedStep[];
  measureStart: number[];
  measureDuration: number[];
  accompByMeasure: AccompPulse[][];
  measureCount: number;
}

/**
 * One stretch of one printed measure as it is played, in timeline order: where its beat 0 would
 * fall (`origin`, which is before the slice when the measure is entered on an upbeat) and which
 * part of it is actually played, in whole notes from the measure's start. A whole measure is
 * `from: 0, to: its duration`. Recorded rather than recomputed, because subtracting a step's
 * in-measure offset cannot tell a sliced measure from a whole one (plan 0007, step 5).
 */
export interface Slice { measure: number; pass: number; origin: number; from: number; to: number }

/**
 * Playback window [start, end) on the timeline for a range of printed measures.
 *
 * The range is given in printed measures and always applies, with or without the loop. A range that
 * runs to the last measure of the page means "to the end of the form": everything after the first
 * pass is played too. Only a range whose end is narrowed stops at the first stretch of that measure,
 * which is what practising a passage asks for. Before this, "measures 1 to 19" of a page sung
 * verse, chorus, verse, chorus stopped at the end of the first chorus — the page played once and
 * the rest of the form never came (plan 0007, the form panel made this easy to hit).
 *
 * A sliced measure is entered and left where its section says (plan 0007, step 5).
 */
export function windowOf(slices: Slice[], range: LoopRange | null, measureCount: number, total: number): { start: number; end: number } {
  if (!range || slices.length === 0) return { start: 0, end: total };
  const from = Math.max(1, Math.min(range.from, measureCount)) - 1;
  const to = Math.max(from, Math.min(range.to, measureCount) - 1);
  const first = slices.find((s) => s.measure === from);
  const start = first ? first.origin + first.from : 0;
  if (to >= measureCount - 1) return { start, end: total };
  const endSlice = slices.find((s) => s.measure === to && s.origin + s.from >= start - 1e-9);
  const end = endSlice === undefined ? total : endSlice.origin + endSlice.to;
  return { start, end: Math.min(end, total) };
}

/** The unrolled timeline: the notes to sound, the steps to follow, the slices, and how long it is. */
export interface Timeline { events: NoteEvent[]; steps: Step[]; slices: Slice[]; total: number }

/**
 * The passes laid end to end on one timeline (plan 0004; extracted whole and pure in plan 0007,
 * step 2, so that the arithmetic can be tested without Tone or a rendered sheet — and so that the
 * measure slice of step 5 has one place to live).
 */
export function layPasses(score: PrintedScore, passes: Pass[]): Timeline {
  const events: NoteEvent[] = [];
  const steps: Step[] = [];
  const slices: Slice[] = [];
  const EPS = 1e-9;
  let t = 0;
  let last = 0;
  passes.forEach((pass, pi) => {
    for (const r of pass.ranges) {
      const first = Math.max(0, r.from), lastMeasure = Math.min(r.to, score.measureCount - 1);
      for (let m = first; m <= lastMeasure; m++) {
        const duration = score.measureDuration[m];
        // the part of this measure that is played: the whole of it, unless the range enters or
        // leaves it on a beat of its own
        const from = m === r.from ? Math.max(0, Math.min(r.fromOnset ?? 0, duration)) : 0;
        const to = m === r.to && r.toOnset !== undefined ? Math.max(from, Math.min(r.toOnset, duration)) : duration;
        if (to - from <= EPS) continue; // a slice with nothing in it is not played at all
        // Inside a range the measures run on, so a note longer than its measure keeps ringing as it
        // always has; it is cut only where the section is left early.
        const cut = m === r.to && r.toOnset !== undefined ? to : Infinity;
        const origin = t - from;
        slices.push({ measure: m, pass: pi, origin, from, to });
        const start = score.measureStart[m];
        score.printed.forEach((step, si) => {
          if (step.measure !== m) return;
          const at = step.time - start;                    // the step's beat within the measure
          const time = origin + at;
          if (at >= from - EPS && at < to - EPS) {
            steps.push({ time, printed: si, measure: m, pass: pi });
            for (const n of step.notes) {
              const length = Math.min(n.length, cut - at);  // a note is cut where the section is left
              events.push({ time, midi: n.midi, length, track: "melody", velocity: 0.9 });
              last = Math.max(last, time + length);
            }
            return;
          }
          // a note begun before this slice but still sounding into it is heard from the edge
          if (at < from - EPS) {
            for (const n of step.notes) {
              if (at + n.length <= from + EPS) continue;
              const length = Math.min(at + n.length, cut) - from;
              events.push({ time: t, midi: n.midi, length, track: "melody", velocity: 0.9 });
              last = Math.max(last, t + length);
            }
          }
        });
        for (const a of score.accompByMeasure[m]) {
          if (a.at + a.length <= from + EPS || a.at >= to - EPS) continue;
          const at = Math.max(a.at, from);
          const length = Math.min(a.at + a.length, cut) - at;
          events.push({ time: origin + at, midi: a.midi, length, track: "accompaniment", velocity: a.velocity });
          last = Math.max(last, origin + at + length);
        }
        t += to - from;
      }
    }
  });
  events.sort((a, b) => a.time - b.time);
  return { events, steps, slices, total: Math.max(t, last) };
}

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
  private slices: Slice[] = [];
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
  private previewTimer: number | null = null;   // the end of a preview, watched off the transport
  private previewDone: (() => void) | null = null;

  constructor(private osmd: OpenSheetMusicDisplay, private onState: (s: PlaybackState) => void) {
    this.collect();
    this.setPasses(this.wholePage());
  }

  /** Read the sheet again after it was edited and re-rendered; the piano stays loaded. */
  /** A new document: collect it again and stop, as the re-render has already moved the sheet. */
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

  /** The length of a printed measure in whole notes; 0 when it is not on the page. */
  printedLength(measure: number): number {
    return this.measureDuration[measure] ?? 0;
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

  /**
   * Lay the passes end to end. `keep` carries the playback across the rebuild (plan 0007, step 2):
   * the position stays where it is when the new list plays the same up to it, and otherwise moves to
   * the start of the first pass that differs — the one the user has just edited — so that building a
   * form by ear does not stop the music. Without it every position changes meaning and playback
   * stops, which is what a new document or a new score needs.
   */
  setPasses(passes: Pass[], keep = false): void {
    const state = this.state;
    const carry = keep && this.steps.length > 0 && state !== "stopped";
    const from = carry ? this.here() : 0;
    const fromPass = carry ? this.steps[this.stepIndex(from)]?.pass ?? 0 : 0;
    // Stopped, the cursor is not a position but a note the user is looking at — and often the one
    // the next edit is about, since the panel's edges are taken from it. Keep it on that note.
    const note = keep && state === "stopped" ? this.at() : null;
    const common = samePrefix(this.passes, passes);
    if (keep) { this.clearTimers(); this.endPreview(false); this.sampler?.releaseAll(); } else { this.stop(); }
    this.passes = passes;
    const line = layPasses({
      printed: this.printed, measureStart: this.measureStart, measureDuration: this.measureDuration,
      accompByMeasure: this.accompByMeasure, measureCount: this.measureCount,
    }, passes);
    this.events = line.events;
    this.steps = line.steps;
    this.slices = line.slices;
    this.totalWholeNotes = line.total;
    if (!keep) return;
    // where to stand on the new timeline
    const target = carry && fromPass < common
      ? Math.min(from, this.totalWholeNotes)
      : (note && this.positionOf(note.measure, note.onset)) ?? this.passStart(Math.min(common, Math.max(0, passes.length - 1)));
    if (this.winEnd <= 0 || this.winEnd > this.totalWholeNotes || target < this.winStart || target >= this.winEnd) {
      this.winStart = 0;
      this.winEnd = this.totalWholeNotes;
    }
    this.nextEvent = this.events.findIndex((e) => e.time >= target);
    if (this.nextEvent === -1) this.nextEvent = this.events.length;
    if (state === "playing") {
      this.anchorCtx = Tone.now();
      this.anchorPos = target;
      this.moveTo(this.stepIndex(target));
      this.lastTick = 0;
      this.timer = window.setInterval(() => { this.tick(); this.followCursor(); }, TICK_MS);
    } else if (state === "paused") {
      this.pausedAt = target;
      this.moveTo(this.stepIndex(target));
    } else {
      this.pending = target > 0 ? target : null;
      this.moveTo(this.stepIndex(target));
    }
  }

  /** The start of a pass on the unrolled timeline. */
  private passStart(pass: number): number {
    return this.steps.find((s) => s.pass >= pass)?.time ?? 0;
  }

  /** The unrolled step at a position, searched from the start. */
  private stepIndex(position: number): number {
    let s = 0;
    while (s + 1 < this.steps.length && this.steps[s + 1].time <= position + 1e-9) s++;
    return s;
  }

  /** Every stretch of a printed measure on the timeline, in the order it is played. */
  private occurrences(measure: number): Slice[] {
    return this.slices.filter((s) => s.measure === measure);
  }

  /** Where playback stands now, whatever the state. */
  private here(): number {
    if (this.state === "playing") return this.positionAt(Tone.now());
    if (this.state === "paused") return this.pausedAt;
    return this.pending ?? 0;
  }

  /**
   * The playback position of a note: in the stretch of its measure that holds the current position,
   * else the next one, else the first; plus the onset. A measure split between two sections has a
   * stretch each, and only the one the note falls in can play it (plan 0007, step 5). Null when the
   * measure, or that beat of it, is never played.
   */
  positionOf(measure: number, onset: number): number | null {
    const occ = this.occurrences(measure).filter((s) => onset >= s.from - 1e-9 && onset < s.to - 1e-9);
    if (occ.length === 0) return null;
    const now = this.here();
    const slice = occ.find((s) => s.origin + s.to > now + 1e-9) ?? occ[0];
    const at = slice.origin + onset;
    return this.steps[this.stepIndex(at)]?.time ?? at;
  }

  /** Where the cursor stands, as a printed measure and a beat in it; null when nothing is laid out. */
  at(): { measure: number; onset: number } | null {
    const step = this.steps[this.stepIndex(this.here())];
    if (!step) return null;
    return { measure: step.measure, onset: this.printed[step.printed].time - this.measureStart[step.measure] };
  }

  private window(range: LoopRange | null): { start: number; end: number } {
    return windowOf(this.slices, range, this.measureCount, this.totalWholeNotes);
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
    this.stopPreview();
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
   * Play a short excerpt on the loaded piano, outside the timeline: the other readings of a measure
   * are compared by ear this way (plan 0005). The main playback is stopped first, so two things never
   * sound at once, and the state stays "stopped" (the cursor does not move). The notes are always
   * heard, since they are what is being compared; the accompaniment of the listed printed measures
   * follows when that track is on, each measure shifted to where it falls in the excerpt. Resolves
   * when the last note has sounded, or at once when it is cut short.
   */
  async preview(notes: PreviewNote[], accomp: { measure: number; at: number }[] = []): Promise<void> {
    this.stopPreview();
    this.stop();
    await this.ensureReady();
    const spw = this.secondsPerWhole();
    const start = Tone.now() + 0.05;
    let end = start;
    const sound = (time: number, midi: number, length: number, velocity: number) => {
      const when = start + time * spw;
      end = Math.max(end, when + length * spw);
      try {
        this.sampler?.triggerAttackRelease(Tone.Frequency(midi + this.transpose, "midi").toNote(), length * spw * 0.95, when, velocity);
      } catch (e) {
        console.warn("note skipped", midi, e);
      }
    };
    for (const n of notes) sound(n.time, n.midi, n.length, 0.9);
    if (this.tracks.accompaniment) {
      for (const a of accomp) for (const e of this.accompByMeasure[a.measure] ?? []) sound(a.at + e.at, e.midi, e.length, e.velocity);
    }
    return new Promise<void>((resolve) => {
      this.previewDone = resolve;
      this.previewTimer = window.setTimeout(() => this.endPreview(false), (end - Tone.now()) * 1000 + 120);
    });
  }

  /** Cut a preview short; a pending preview() promise resolves. */
  stopPreview(): void {
    this.endPreview(true);
  }

  private endPreview(release: boolean): void {
    if (this.previewTimer !== null) { window.clearTimeout(this.previewTimer); this.previewTimer = null; }
    if (release && this.previewDone) this.sampler?.releaseAll();
    const done = this.previewDone;
    this.previewDone = null;
    done?.();
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
    this.endPreview(false);
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
    this.endPreview(false);
    this.sampler?.dispose();
    this.sampler = null;
    this.ready = null;
  }
}
