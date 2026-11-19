/** Fitting a reading card's engraved measure to its card (spec player-controls, ticket 03). */

/** Below this zoom the notes are too small to judge; the card goes full-row instead. */
export const MIN_READING_ZOOM = 0.4;

/**
 * The zoom at which a measure of `natural` px (engraved at `zoom`) fits `available` px, never below
 * `minZoom`. `fits` is false when even the minimum is too wide: that card takes the full row.
 * A width that was not measured (0) leaves the zoom as it is.
 */
export function fitZoom(a: { natural: number; available: number; zoom: number; minZoom: number }): { zoom: number; fits: boolean } {
  const { natural, available, zoom, minZoom } = a;
  if (natural <= 0 || available <= 0 || natural <= available) return { zoom, fits: true };
  const z = (zoom * available) / natural;
  if (z >= minZoom - 1e-9) return { zoom: z, fits: true };
  return { zoom: minZoom, fits: false };
}
