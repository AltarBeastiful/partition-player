import { describe, expect, it } from "vitest";
import { fitZoom } from "./readingFit";

describe("fitZoom", () => {
  it("keeps the zoom when the measure already fits", () => {
    expect(fitZoom({ natural: 200, available: 300, zoom: 0.7, minZoom: 0.4 })).toEqual({ zoom: 0.7, fits: true });
  });
  it("shrinks in proportion so the whole measure shows", () => {
    const r = fitZoom({ natural: 600, available: 300, zoom: 0.7, minZoom: 0.3 });
    expect(r.fits).toBe(true);
    expect(r.zoom).toBeCloseTo(0.35, 5);
  });
  it("stops at the minimum readable zoom and says it does not fit", () => {
    expect(fitZoom({ natural: 900, available: 300, zoom: 0.7, minZoom: 0.4 })).toEqual({ zoom: 0.4, fits: false });
  });
  it("accepts a measure that fits exactly at the minimum", () => {
    const r = fitZoom({ natural: 700, available: 400, zoom: 0.7, minZoom: 0.4 });
    expect(r.fits).toBe(true);
    expect(r.zoom).toBeCloseTo(0.4, 5);
  });
  it("leaves the zoom alone when nothing was measured", () => {
    expect(fitZoom({ natural: 0, available: 300, zoom: 0.7, minZoom: 0.4 })).toEqual({ zoom: 0.7, fits: true });
    expect(fitZoom({ natural: 500, available: 0, zoom: 0.7, minZoom: 0.4 })).toEqual({ zoom: 0.7, fits: true });
  });
});
