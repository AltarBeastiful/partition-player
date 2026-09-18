/**
 * Piano playback for a rendered OSMD score with the cursor following the notes.
 *
 * Note events are read by walking the OSMD cursor once; timestamps come from the cursor iterator in
 * whole-note units, so tempo is applied at schedule time. Sound is a Tone.js sampler with a few
 * Salamander grand piano samples, pitch-shifted in between.
 */
import * as Tone from "tone";
import type { OpenSheetMusicDisplay } from "opensheetmusicdisplay";

export type PlaybackState = "stopped" | "playing" | "paused";

interface NoteEvent { time: number; midi: number; length: number; step: number } // times in whole notes

const SAMPLES: Record<string, string> = {
  A1: "A1.mp3", C2: "C2.mp3", "D#2": "Ds2.mp3", "F#2": "Fs2.mp3", A2: "A2.mp3", C3: "C3.mp3", "D#3": "Ds3.mp3",
  "F#3": "Fs3.mp3", A3: "A3.mp3", C4: "C4.mp3", "D#4": "Ds4.mp3", "F#4": "Fs4.mp3", A4: "A4.mp3", C5: "C5.mp3",
  "D#5": "Ds5.mp3", "F#5": "Fs5.mp3", A5: "A5.mp3", C6: "C6.mp3", "D#6": "Ds6.mp3", "F#6": "Fs6.mp3", A6: "A6.mp3",
};

export class Player {
  private sampler: Tone.Sampler | null = null;
  private events: NoteEvent[] = [];
  private steps: number[] = []; // cursor step -> time in whole notes
  private part: Tone.Part<NoteEvent> | null = null;
  private stepPart: Tone.Part<{ time: number; step: number }> | null = null;
  private totalWholeNotes = 0;
  private bpm = 90;

  constructor(private osmd: OpenSheetMusicDisplay, private onState: (s: PlaybackState) => void) {
    this.collect();
  }

  private collect(): void {
    const cursor = this.osmd.cursor;
    cursor.reset();
    let step = 0;
    let last = 0;
    while (!cursor.iterator.EndReached) {
      const t = cursor.iterator.currentTimeStamp.RealValue;
      this.steps.push(t);
      for (const voiceEntry of cursor.iterator.CurrentVoiceEntries ?? []) {
        for (const note of voiceEntry.Notes) {
          if (note.isRest() || !note.Pitch || note.NoteTie?.StartNote !== note && note.NoteTie) continue;
          const midi = note.halfTone + 12; // OSMD halfTone is relative to C0 = 12
          const length = note.Length.RealValue;
          this.events.push({ time: t, midi, length, step });
          last = Math.max(last, t + length);
        }
      }
      cursor.next();
      step++;
    }
    this.totalWholeNotes = last;
    cursor.reset();
  }

  private secondsPerWhole(): number {
    return (60 / this.bpm) * 4;
  }

  setBpm(bpm: number): void {
    this.bpm = bpm;
    Tone.getTransport().bpm.value = bpm;
  }

  async play(bpm: number): Promise<void> {
    await Tone.start();
    if (!this.sampler) {
      this.sampler = new Tone.Sampler({ urls: SAMPLES, baseUrl: "https://tonejs.github.io/audio/salamander/", release: 1 }).toDestination();
      await Tone.loaded();
    }
    this.setBpm(bpm);
    const transport = Tone.getTransport();
    if (transport.state === "paused") {
      transport.start();
      this.onState("playing");
      return;
    }
    this.disposeParts();
    // Transport time in seconds at bpm; a whole note = 4 beats.
    const spw = () => this.secondsPerWhole();
    this.part = new Tone.Part<NoteEvent>((time, ev) => {
      this.sampler?.triggerAttackRelease(Tone.Frequency(ev.midi, "midi").toNote(), ev.length * spw() * 0.95, time);
    }, this.events.map((e) => ({ ...e, time: e.time * spw() }) as NoteEvent & { time: number })).start(0);
    this.stepPart = new Tone.Part<{ time: number; step: number }>((time, ev) => {
      Tone.getDraw().schedule(() => this.moveCursor(ev.step), time);
    }, this.steps.map((t, step) => ({ time: t * spw(), step }))).start(0);
    transport.stop();
    transport.position = 0;
    transport.scheduleOnce(() => { this.stop(); }, this.totalWholeNotes * spw() + 0.5);
    transport.start("+0.05");
    this.onState("playing");
  }

  pause(): void {
    Tone.getTransport().pause();
    this.onState("paused");
  }

  stop(): void {
    const transport = Tone.getTransport();
    transport.stop();
    transport.position = 0;
    this.disposeParts();
    this.osmd.cursor.reset();
    this.currentStep = 0;
    this.osmd.cursor.show();
    this.onState("stopped");
  }

  private currentStep = 0;

  /** Move the cursor to `step` incrementally (no rewind unless going backwards), then keep it in view. */
  private moveCursor(step: number): void {
    const cursor = this.osmd.cursor;
    if (step < this.currentStep) {
      cursor.reset();
      this.currentStep = 0;
    }
    while (this.currentStep < step && !cursor.iterator.EndReached) {
      cursor.next();
      this.currentStep++;
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

  private disposeParts(): void {
    this.part?.dispose(); this.part = null;
    this.stepPart?.dispose(); this.stepPart = null;
    Tone.getTransport().cancel(0);
  }

  dispose(): void {
    this.disposeParts();
    Tone.getTransport().stop();
    this.sampler?.dispose();
    this.sampler = null;
  }
}
