/**
 * The words of the pass (plan 0004): while a pass with verse n plays, the other lyrics under each
 * note are dimmed by a layer over the sheet. A note with a single lyric keeps it (the chorus); a note
 * with several lyrics but none numbered n keeps them all.
 */
import type { OpenSheetMusicDisplay } from "opensheetmusicdisplay";

const SVG_NS = "http://www.w3.org/2000/svg";
const LAYER_CLASS = "verse-layer";
const UNIT = 10; // OSMD units to px at zoom 1

function svgOf(osmd: OpenSheetMusicDisplay): SVGSVGElement | null {
  return ((osmd as any).container as HTMLElement | undefined)?.querySelector("svg") ?? null;
}

export function clearVerses(osmd: OpenSheetMusicDisplay): void {
  svgOf(osmd)?.querySelectorAll(`g.${LAYER_CLASS}`).forEach((g) => g.remove());
}

/** Dim every lyric that is not verse `verse`; null clears the layer. */
export function dimVerses(osmd: OpenSheetMusicDisplay, verse: number | null): void {
  clearVerses(osmd);
  const svg = svgOf(osmd);
  if (!svg || verse === null) return;
  const scale = UNIT * (osmd.Zoom || 1);
  const layer = document.createElementNS(SVG_NS, "g");
  layer.setAttribute("class", LAYER_CLASS);
  const px = (v: number) => (v * scale).toFixed(1);
  const list: any[][] = (osmd.GraphicSheet as any)?.MeasureList ?? [];
  for (const staves of list) {
    for (const gm of staves ?? []) {
      for (const entry of gm?.staffEntries ?? []) {
        const lyrics: any[] = entry?.LyricsEntries ?? [];
        if (lyrics.length < 2) continue;
        const wanted = lyrics.some((l) => parseInt(String(l.LyricsEntry?.VerseNumber ?? ""), 10) === verse);
        if (!wanted) continue;
        for (const l of lyrics) {
          if (parseInt(String(l.LyricsEntry?.VerseNumber ?? ""), 10) === verse) continue;
          const bs = l.GraphicalLabel?.PositionAndShape;
          const ap = bs?.AbsolutePosition;
          if (!ap) continue;
          const rect = document.createElementNS(SVG_NS, "rect");
          rect.setAttribute("x", px(ap.x + (bs.BorderLeft ?? 0) - 0.3));
          rect.setAttribute("y", px(ap.y + (bs.BorderTop ?? 0) - 0.2));
          rect.setAttribute("width", px((bs.BorderRight ?? 0) - (bs.BorderLeft ?? 0) + 0.6));
          rect.setAttribute("height", px((bs.BorderBottom ?? 0) - (bs.BorderTop ?? 0) + 0.4));
          rect.setAttribute("class", "dim");
          layer.appendChild(rect);
        }
      }
    }
  }
  svg.appendChild(layer); // over the words
}
