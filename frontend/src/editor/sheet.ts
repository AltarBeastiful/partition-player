/**
 * The rendered sheet as the editor sees it (ADR 0005, decision 5): a click on OSMD's SVG becomes the
 * key of an event of the document, a key becomes the graphical note to mark, and the doubts are
 * drawn as a layer under the notes, like the note names.
 */
/* eslint-disable @typescript-eslint/no-explicit-any */
import type { OpenSheetMusicDisplay } from "opensheetmusicdisplay";
import { sameKey, type EventKey } from "../score/xml";
import type { Place } from "./session";

const SVG_NS = "http://www.w3.org/2000/svg";
const UNIT = 10; // OSMD's unitInPixels
export const LAYER_CLASS = "editor-layer";
const HIT_X = 2.2, HIT_Y = 2.4; // units around a notehead that select it (a finger on a phone)

export function keyOfSource(osmd: OpenSheetMusicDisplay, note: any): EventKey | null {
  const measure = (osmd.Sheet?.SourceMeasures ?? []).indexOf(note?.SourceMeasure);
  if (measure < 0) return null;
  const staff = Number(note.ParentStaff?.Id ?? 1) || 1;
  const voice = Number(note.ParentVoiceEntry?.ParentVoice?.VoiceId ?? 1) || 1;
  const onset = Number(note.ParentVoiceEntry?.Timestamp?.RealValue ?? 0);
  const midi = note.isRest?.() || !note.Pitch ? null : Number(note.halfTone) + 12;
  return { measure, staff, voice, onset, midi };
}

function svgOf(osmd: OpenSheetMusicDisplay): SVGSVGElement | null {
  const backends = (osmd.Drawer as any)?.Backends ?? [];
  return backends[0]?.getSvgElement?.() ?? null;
}

/** Client pixels to OSMD units, whatever the CSS did to the SVG's size. */
function toUnits(osmd: OpenSheetMusicDisplay, svg: SVGSVGElement, clientX: number, clientY: number): { x: number; y: number } | null {
  const ctm = svg.getScreenCTM();
  if (!ctm) return null;
  const pt = svg.createSVGPoint();
  pt.x = clientX; pt.y = clientY;
  const p = pt.matrixTransform(ctm.inverse());
  const scale = UNIT * (osmd.Zoom || 1);
  return { x: p.x / scale, y: p.y / scale };
}

function* graphicalNotes(osmd: OpenSheetMusicDisplay): Generator<{ gn: any; measure: number }> {
  const list: any[][] = (osmd.GraphicSheet as any)?.MeasureList ?? [];
  for (let m = 0; m < list.length; m++) {
    for (const gm of list[m] ?? []) {
      if (!gm) continue;
      for (const se of gm.staffEntries ?? []) {
        for (const gve of se.graphicalVoiceEntries ?? []) {
          for (const gn of gve.notes ?? []) yield { gn, measure: m };
        }
      }
    }
  }
}

/** What a click lands on: a note within reach, else the nearest event of the measure under it. */
export function hitTest(osmd: OpenSheetMusicDisplay, clientX: number, clientY: number): EventKey | null {
  const svg = svgOf(osmd);
  if (!svg) return null;
  const p = toUnits(osmd, svg, clientX, clientY);
  if (!p) return null;
  let best: { gn: any; d: number } | null = null;
  for (const { gn } of graphicalNotes(osmd)) {
    const pos = gn.PositionAndShape?.AbsolutePosition;
    if (!pos) continue;
    const dx = Math.abs(p.x - pos.x), dy = Math.abs(p.y - pos.y);
    if (dx > HIT_X || dy > HIT_Y) continue;
    const d = dx * dx + dy * dy * 1.5;
    if (!best || d < best.d) best = { gn, d };
  }
  if (best) return keyOfSource(osmd, best.gn.sourceNote);
  // no note under the finger: the measure it is in, the entry nearest in x, its first note
  const list: any[][] = (osmd.GraphicSheet as any)?.MeasureList ?? [];
  for (const row of list) {
    for (const gm of row ?? []) {
      const ap = gm?.PositionAndShape?.AbsolutePosition, size = gm?.PositionAndShape?.Size;
      if (!ap || !size) continue;
      if (p.x < ap.x || p.x > ap.x + size.width || p.y < ap.y - 3 || p.y > ap.y + size.height + 3) continue;
      let nearest: any = null, dist = Infinity;
      for (const se of gm.staffEntries ?? []) {
        const x = se.PositionAndShape?.AbsolutePosition?.x ?? Infinity;
        const d = Math.abs(x - p.x);
        if (d < dist) { dist = d; nearest = se; }
      }
      const gn = nearest?.graphicalVoiceEntries?.[0]?.notes?.[0];
      if (gn) return keyOfSource(osmd, gn.sourceNote);
    }
  }
  return null;
}

/** The graphical note that shows a key, after any render. */
export function graphicalFor(osmd: OpenSheetMusicDisplay, key: EventKey): any | null {
  const list: any[][] = (osmd.GraphicSheet as any)?.MeasureList ?? [];
  for (const gm of list[key.measure] ?? []) {
    if (!gm) continue;
    for (const se of gm.staffEntries ?? []) {
      for (const gve of se.graphicalVoiceEntries ?? []) {
        for (const gn of gve.notes ?? []) {
          const k = keyOfSource(osmd, gn.sourceNote);
          if (k && sameKey(k, key)) return gn;
        }
      }
    }
  }
  return null;
}

export function clearOverlay(osmd: OpenSheetMusicDisplay): void {
  svgOf(osmd)?.querySelectorAll(`g.${LAYER_CLASS}`).forEach((g) => g.remove());
}

/** The box of a measure across its staves, in units, or null when it is not drawn. */
function measureBox(osmd: OpenSheetMusicDisplay, measure: number): { x: number; y: number; w: number; h: number } | null {
  const list: any[][] = (osmd.GraphicSheet as any)?.MeasureList ?? [];
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const gm of list[measure] ?? []) {
    const ap = gm?.PositionAndShape?.AbsolutePosition, size = gm?.PositionAndShape?.Size;
    if (!ap || !size) continue;
    x0 = Math.min(x0, ap.x); y0 = Math.min(y0, ap.y);
    x1 = Math.max(x1, ap.x + size.width); y1 = Math.max(y1, ap.y + Math.max(size.height, 4));
  }
  if (!isFinite(x0)) return null;
  return { x: x0, y: y0 - 1.5, w: x1 - x0, h: y1 - y0 + 3 };
}

export const SECTION_CLASS = "section-layer";

/** The x of the first note at or after a beat of a measure, in units; null when there is none. */
function onsetX(osmd: OpenSheetMusicDisplay, measure: number, onset: number): number | null {
  let best: number | null = null;
  let bestOnset = Infinity;
  for (const { gn, measure: m } of graphicalNotes(osmd)) {
    if (m !== measure) continue;
    const at = Number(gn?.sourceNote?.ParentVoiceEntry?.Timestamp?.RealValue ?? NaN);
    const x = gn?.PositionAndShape?.AbsolutePosition?.x;
    if (!isFinite(at) || x === undefined || at < onset - 1e-9 || at >= bestOnset) continue;
    bestOnset = at; best = x - 0.8; // a little room before the notehead
  }
  return best;
}

export function clearSections(osmd: OpenSheetMusicDisplay): void {
  svgOf(osmd)?.querySelectorAll(`g.${SECTION_CLASS}`).forEach((g) => g.remove());
}

/**
 * A band over the measures of every section, named at its start (plan 0007, step 5): the form is
 * read on the page, so the sections are shown there rather than only as numbers in the panel. A
 * section that crosses a system break gets one band per row, and an edge inside a measure is drawn
 * at the note it falls on. Every coordinate is read at draw time — 2.x snaps staff lines to half
 * pixels, so nothing here may be cached between renders.
 */
export function drawSections(osmd: OpenSheetMusicDisplay, sections: { name: string; from: number; to: number; fromOnset?: number; toOnset?: number }[]): void {
  const svg = svgOf(osmd);
  if (!svg) return;
  clearSections(osmd);
  if (sections.length === 0) return;
  const scale = UNIT * (osmd.Zoom || 1);
  const px = (v: number) => (v * scale).toFixed(1);
  const layer = document.createElementNS(SVG_NS, "g");
  layer.setAttribute("class", SECTION_CLASS);
  sections.forEach((section, i) => {
    // the measures of this section, grouped into the rows of the page they are drawn on
    const rows: { x0: number; x1: number; y: number; first: boolean; last: boolean }[] = [];
    for (let m = section.from; m <= section.to; m++) {
      const box = measureBox(osmd, m);
      if (!box) continue;
      const row = rows[rows.length - 1];
      if (row && Math.abs(row.y - box.y) < 0.5) { row.x1 = box.x + box.w; row.last = m === section.to; }
      else rows.push({ x0: box.x, x1: box.x + box.w, y: box.y, first: m === section.from, last: m === section.to });
    }
    if (rows.length === 0) return;
    if (section.fromOnset) {
      const x = onsetX(osmd, section.from, section.fromOnset);
      if (x !== null) rows[0].x0 = Math.max(rows[0].x0, x);
    }
    if (section.toOnset !== undefined) {
      const x = onsetX(osmd, section.to, section.toOnset);
      if (x !== null) rows[rows.length - 1].x1 = Math.min(rows[rows.length - 1].x1, x);
    }
    for (const [k, row] of rows.entries()) {
      const rect = document.createElementNS(SVG_NS, "rect");
      rect.setAttribute("x", px(row.x0));
      rect.setAttribute("y", px(row.y - 2.2));
      rect.setAttribute("width", px(Math.max(0.4, row.x1 - row.x0)));
      rect.setAttribute("height", px(1.4));
      rect.setAttribute("class", `section-band band-${i % 6}`);
      layer.appendChild(rect);
      if (k === 0 && section.name) {
        const label = document.createElementNS(SVG_NS, "text");
        label.setAttribute("x", px(row.x0 + 0.3));
        label.setAttribute("y", px(row.y - 2.6));
        label.setAttribute("class", `section-name band-${i % 6}`);
        label.textContent = section.name;
        layer.appendChild(label);
      }
    }
  });
  svg.appendChild(layer);
}

/** Draw the doubts and the selection. Cheap; called after every render and every selection change. */
export function drawOverlay(osmd: OpenSheetMusicDisplay, places: Place[], selected: EventKey | null): void {
  const svg = svgOf(osmd);
  if (!svg) return;
  clearOverlay(osmd);
  const scale = UNIT * (osmd.Zoom || 1);
  const layer = document.createElementNS(SVG_NS, "g");
  layer.setAttribute("class", LAYER_CLASS);
  const px = (v: number) => (v * scale).toFixed(1);

  for (const place of places) {
    const box = measureBox(osmd, place.measure);
    if (!box) continue;
    const level = place.info && !place.live ? "info"
      : place.checked && !place.live ? "checked"
      : place.level === "check" ? "check"   // a second reading disagrees; the measure still adds up
      : "doubt";
    const rect = document.createElementNS(SVG_NS, "rect");
    rect.setAttribute("x", px(box.x)); rect.setAttribute("y", px(box.y));
    rect.setAttribute("width", px(box.w)); rect.setAttribute("height", px(box.h));
    rect.setAttribute("rx", "3");
    rect.setAttribute("class", `place ${level}`);
    const title = document.createElementNS(SVG_NS, "title");
    title.textContent = `Measure ${place.measure + 1}: ${place.texts.join("; ")}`;
    rect.appendChild(title);
    layer.appendChild(rect);
    if (level !== "checked") {
      const badge = document.createElementNS(SVG_NS, "text");
      badge.setAttribute("x", px(box.x + 0.4)); badge.setAttribute("y", px(box.y - 0.4));
      badge.setAttribute("class", `badge ${level}`);
      badge.textContent = level === "info" ? "i" : "?";
      if (level === "check") badge.classList.add("quiet");
      layer.appendChild(badge);
    }
  }
  if (selected) {
    const box = measureBox(osmd, selected.measure);
    if (box) {
      const rect = document.createElementNS(SVG_NS, "rect");
      rect.setAttribute("x", px(box.x)); rect.setAttribute("y", px(box.y));
      rect.setAttribute("width", px(box.w)); rect.setAttribute("height", px(box.h));
      rect.setAttribute("rx", "3");
      rect.setAttribute("class", "selected-measure");
      layer.appendChild(rect);
    }
    const gn = graphicalFor(osmd, selected);
    const pos = gn?.PositionAndShape?.AbsolutePosition;
    if (pos) {
      const mark = document.createElementNS(SVG_NS, "rect");
      const r = 1.35;
      mark.setAttribute("x", px(pos.x - r)); mark.setAttribute("y", px(pos.y - r));
      mark.setAttribute("width", px(2 * r)); mark.setAttribute("height", px(2 * r));
      mark.setAttribute("rx", px(0.5));
      mark.setAttribute("class", "selected-note");
      layer.appendChild(mark);
    }
  }
  svg.insertBefore(layer, svg.firstChild); // under the notes, so the ink stays black
}

/**
 * Mark notes on a sheet of their own (the mini sheets of the other readings, plan 0005): a box round
 * each notehead, like the selection. The marks are a layer apart, so a sheet that also has doubts on
 * it keeps them.
 */
export function markNotes(osmd: OpenSheetMusicDisplay, keys: EventKey[], cls = "changed-note"): void {
  const svg = svgOf(osmd);
  if (!svg) return;
  svg.querySelectorAll(`g.${LAYER_CLASS}.marks`).forEach((g) => g.remove());
  const scale = UNIT * (osmd.Zoom || 1);
  const px = (v: number) => (v * scale).toFixed(1);
  const layer = document.createElementNS(SVG_NS, "g");
  layer.setAttribute("class", `${LAYER_CLASS} marks`);
  for (const key of keys) {
    const pos = graphicalFor(osmd, key)?.PositionAndShape?.AbsolutePosition;
    if (!pos) continue;
    const r = 1.35;
    const rect = document.createElementNS(SVG_NS, "rect");
    rect.setAttribute("x", px(pos.x - r)); rect.setAttribute("y", px(pos.y - r));
    rect.setAttribute("width", px(2 * r)); rect.setAttribute("height", px(2 * r));
    rect.setAttribute("rx", px(0.5));
    rect.setAttribute("class", cls);
    layer.appendChild(rect);
  }
  svg.insertBefore(layer, svg.firstChild); // under the notes, so the ink stays black
}

/** The client rectangle of a selected note, to keep it in view. */
export function rectOf(osmd: OpenSheetMusicDisplay, key: EventKey): DOMRect | null {
  const svg = svgOf(osmd);
  const gn = graphicalFor(osmd, key);
  const pos = gn?.PositionAndShape?.AbsolutePosition;
  if (!svg || !pos) return null;
  const ctm = svg.getScreenCTM();
  if (!ctm) return null;
  const scale = UNIT * (osmd.Zoom || 1);
  const pt = svg.createSVGPoint();
  pt.x = pos.x * scale; pt.y = pos.y * scale;
  const p = pt.matrixTransform(ctm);
  return new DOMRect(p.x - 10, p.y - 10, 20, 20);
}

/** Redraw the overlay after OSMD's own re-renders (it re-renders on resize). Returns a stop function. */
export function keepOverlay(host: HTMLElement, draw: () => void): () => void {
  let timer = 0;
  const observer = new MutationObserver((records) => {
    if (records.every((r) => [...r.addedNodes, ...r.removedNodes].every((n) => {
      const c = (n as Element).classList;
      // the layers this module draws itself, or drawing one would ask for another draw for ever
      return c?.contains(LAYER_CLASS) || c?.contains(SECTION_CLASS) || c?.contains("verse-layer") || c?.contains("note-names");
    }))) return;
    window.clearTimeout(timer);
    timer = window.setTimeout(draw, 120);
  });
  observer.observe(host, { childList: true, subtree: true });
  return () => { observer.disconnect(); window.clearTimeout(timer); };
}
