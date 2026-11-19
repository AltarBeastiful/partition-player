/**
 * Plan 0016: the one place that decides whether OSMD groups eighth notes into beams on its own.
 * A page read by homr carries no beam markup, so it would print every eighth with a flag. A score
 * that does carry beams (an import fixed in MuseScore) is drawn as written. The decision is made
 * from the MusicXML itself, not from where it came from.
 */
import type { OpenSheetMusicDisplay } from "opensheetmusicdisplay";

/** True when the score has at least one `<beam>` element. */
export function hasBeamMarkup(xml: string): boolean {
  return /<beam[\s>]/.test(xml);
}

/** Set the beam rule of `osmd` for the score it is about to load. Call before `load`. */
export function chooseBeams(osmd: OpenSheetMusicDisplay, xml: string): void {
  osmd.setOptions({ autoBeam: !hasBeamMarkup(xml) });
}
