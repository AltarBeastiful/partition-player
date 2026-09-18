/**
 * French note names (do ré mi fa sol la si) over the printed notes.
 *
 * The names are read from the pitches of the score OSMD has already laid out and drawn as <text>
 * nodes in its SVG, so nothing is written into the MusicXML and the switch can be flipped while the
 * piece plays. Each staff gets one row above it, so the space under the notes stays free for the
 * words; the names of a chord are stacked low to high like its noteheads. The row goes as low as the
 * staff's own ink allows (OSMD's skyline: chord symbols, notes on ledger lines). OSMD lays the page
 * out without knowing about these labels, so before rendering it is told to keep the row's height
 * free between staves, between systems and at the top of the page; a staff of a piano score would
 * otherwise have no room over it. Names are those of the printed pitches: transposing the playback
 * does not rename them.
 */
import type { OpenSheetMusicDisplay } from "opensheetmusicdisplay";

/* OSMD's graphical model and engraving rules are reached through `any`: the parts used here
   (staff lines, staff entries, notes, the sky line, the spacing rules) are public at runtime but
   only partly in the published types. */
/* eslint-disable @typescript-eslint/no-explicit-any */

const SVG_NS = "http://www.w3.org/2000/svg";
const UNIT_IN_PIXELS = 10; // OSMD's unitInPixels: one staff-line distance
const LAYER_CLASS = "note-names";
// NoteEnum is in semitones from C, so the fundamental already names the letter.
const LETTER: Record<number, string> = { 0: "do", 2: "ré", 4: "mi", 5: "fa", 7: "sol", 9: "la", 11: "si" };
const SIGN: Record<string, string> = { "-2": "bb", "-1": "b", "0": "", "1": "#", "2": "##" };
const STAFF_HEIGHT = 4;  // a staff is four staff-line distances high
const ROW_GAP = 1.1;     // between the highest ink of the staff and the row of names
const LINE_STEP = 1.2;   // between the names of one chord
const CLEARANCE = 0.6;   // between the names and whatever is printed above them
const MIN_LIFT = 1.4;    // the names stay at least this far over the top line of their staff

/** "mib" for E flat: the letter in French and the alteration of the pitch as printed. */
export function frenchNoteName(fundamental: number, accidentalHalfTones: number): string {
  const letter = LETTER[fundamental];
  if (!letter) return "";
  return letter + (SIGN[String(Math.round(accidentalHalfTones))] ?? "");
}

interface Label { x: number; names: string[] } // one onset; a chord holds its names low to high

interface Reserved { staves: number; systems: number; top: number; need: number }

const reserved = new WeakMap<object, Reserved>();

/**
 * Widen (or restore) the gaps OSMD leaves above every staff, by the height the names need. Returns
 * true when the rules changed, which means the caller has to render again for them to take effect.
 */
export function reserveNoteNamesSpace(osmd: OpenSheetMusicDisplay, on: boolean): boolean {
  const rules = osmd.EngravingRules as any;
  if (!rules) return false;
  const previous: Reserved | undefined = reserved.get(rules);
  if (!on) {
    if (!previous) return false;
    rules.MinSkyBottomDistBetweenStaves = previous.staves;
    rules.MinSkyBottomDistBetweenSystems = previous.systems;
    rules.PageTopMargin = previous.top;
    reserved.delete(rules);
    return true;
  }
  const need = spaceNeeded(osmd);
  if (previous && Math.abs(previous.need - need) < 0.05) return false; // already set for this score
  const base: Reserved = previous ?? {
    staves: rules.MinSkyBottomDistBetweenStaves,
    systems: rules.MinSkyBottomDistBetweenSystems,
    top: rules.PageTopMargin,
    need,
  };
  rules.MinSkyBottomDistBetweenStaves = base.staves + need;
  rules.MinSkyBottomDistBetweenSystems = base.systems + need;
  rules.PageTopMargin = base.top + need;
  reserved.set(rules, { ...base, need });
  return true;
}

/** The height of the tallest row on the page: a chord is as tall as it has noteheads. */
function spaceNeeded(osmd: OpenSheetMusicDisplay): number {
  let lines = 1;
  for (const measure of (osmd.Sheet as any)?.SourceMeasures ?? []) {
    for (const container of measure.VerticalSourceStaffEntryContainers ?? []) {
      for (const entry of container.StaffEntries ?? []) {
        let notes = 0;
        for (const voiceEntry of entry?.VoiceEntries ?? []) {
          notes += (voiceEntry.Notes ?? []).filter((n: any) => !n.isRest?.()).length;
        }
        lines = Math.max(lines, notes);
      }
    }
  }
  return ROW_GAP + (lines - 1) * LINE_STEP + CLEARANCE;
}

/** Keep the names in place across OSMD's own re-renders: it re-renders by itself on resize, and a
 * plain resize listener would race it. Returns a function that stops watching. */
export function keepNoteNames(osmd: OpenSheetMusicDisplay, host: HTMLElement): () => void {
  let timer = 0;
  const observer = new MutationObserver((records) => {
    if (records.every(ours)) return; // our own layer going in or out is not a reason to draw again
    window.clearTimeout(timer);
    timer = window.setTimeout(() => drawNoteNames(osmd), 100);
  });
  observer.observe(host, { childList: true, subtree: true });
  return () => { observer.disconnect(); window.clearTimeout(timer); };
}

function ours(record: MutationRecord): boolean {
  const nodes = [...record.addedNodes, ...record.removedNodes];
  return nodes.length > 0 && nodes.every((n) => (n as Element).classList?.contains(LAYER_CLASS));
}

/** Remove the names from every page. Safe to call when none were drawn. */
export function clearNoteNames(osmd: OpenSheetMusicDisplay): void {
  for (const backend of backends(osmd)) {
    backend.getSvgElement?.().querySelectorAll(`g.${LAYER_CLASS}`).forEach((g) => g.remove());
  }
}

/** Draw a French name over every sounding note. Returns how many were written. */
export function drawNoteNames(osmd: OpenSheetMusicDisplay): number {
  clearNoteNames(osmd);
  const pages = osmd.GraphicSheet?.MusicPages ?? [];
  const svgs = backends(osmd).map((b) => b.getSvgElement?.());
  const zoom = osmd.Zoom || 1;
  const scale = UNIT_IN_PIXELS * zoom;
  let written = 0;

  pages.forEach((page, pageIndex) => {
    const svg = svgs[pageIndex];
    if (!svg) return;
    const layer = document.createElementNS(SVG_NS, "g");
    layer.setAttribute("class", LAYER_CLASS);
    let ceiling = MIN_LIFT; // absolute y under which our names must stay: the page top, then each staff

    for (const system of page.MusicSystems ?? []) {
      for (const staffLine of system.StaffLines ?? []) {
        const top: number = staffLine.PositionAndShape?.AbsolutePosition?.y ?? 0;
        const labels = collect(staffLine);
        if (labels.length > 0) {
          const lines = Math.max(...labels.map((l) => l.names.length));
          const row = rowY(staffLine, top, lines, ceiling);
          for (const label of labels) {
            const x = (label.x * scale).toFixed(1);
            label.names.forEach((name, line) => {
              const text = document.createElementNS(SVG_NS, "text");
              text.setAttribute("x", x);
              text.setAttribute("y", ((row - line * LINE_STEP) * scale).toFixed(1));
              text.setAttribute("text-anchor", "middle");
              text.textContent = name;
              layer.appendChild(text);
              written++;
            });
          }
        }
        ceiling = top + STAFF_HEIGHT; // the next staff's names stay below this staff
      }
    }
    if (layer.childElementCount > 0) svg.appendChild(layer);
  });
  return written;
}

function backends(osmd: OpenSheetMusicDisplay): { getSvgElement?: () => SVGElement }[] {
  return ((osmd.Drawer as any)?.Backends ?? []) as { getSvgElement?: () => SVGElement }[];
}

/** One label per onset of the staff line, holding the names of the chord from the lowest note up. */
function collect(staffLine: any): Label[] {
  const labels: Label[] = [];
  for (const measure of staffLine.Measures ?? []) {
    for (const entry of measure.staffEntries ?? []) {
      const names: { name: string; halfTone: number; x: number }[] = [];
      for (const voiceEntry of entry.graphicalVoiceEntries ?? []) {
        for (const note of voiceEntry.notes ?? []) {
          const source = note.sourceNote;
          if (!source || source.isRest?.() || !source.Pitch) continue;
          if (source.NoteTie && source.NoteTie.StartNote !== source) continue; // tied continuation
          const name = frenchNoteName(source.Pitch.FundamentalNote, source.Pitch.AccidentalHalfTones);
          if (!name) continue;
          names.push({ name, halfTone: source.halfTone ?? 0, x: note.PositionAndShape?.AbsolutePosition?.x ?? 0 });
        }
      }
      if (names.length === 0) continue;
      names.sort((a, b) => a.halfTone - b.halfTone);
      labels.push({ x: names[0].x, names: names.map((n) => n.name) });
    }
  }
  return labels;
}

/**
 * The baseline of the row, between the staff's own ink and whatever is printed above it. Smaller y is
 * higher up the page: `ceiling` is the bottom of the staff above (or the top of the page), `lowest`
 * keeps the names off the staff itself. When the gap is too tight for the whole stack the names stay
 * over their own staff and lean into the space above, which is the readable way round.
 */
function rowY(staffLine: any, top: number, lines: number, ceiling: number): number {
  let lift = MIN_LIFT;
  const sky: number | undefined = staffLine.SkyBottomLineCalculator?.getSkyLineMin?.();
  // The skyline is relative to the top line of the staff and negative upwards.
  if (typeof sky === "number" && isFinite(sky) && sky < 0) lift = Math.max(MIN_LIFT, Math.min(14, -sky) + ROW_GAP);
  const stack = (lines - 1) * LINE_STEP;
  const row = Math.max(top - lift, ceiling + CLEARANCE + stack);
  return Math.min(row, top - MIN_LIFT);
}
