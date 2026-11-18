/**
 * The naming of lines (plan 0011, step 1). The rule is pure — what the document calls its
 * instruments and how many staves each holds — so the cases that matter are held exactly here: the
 * lead sheet the app has always played, the two-staff page homr gives for the canon photo, and a
 * file with a part per line.
 */
import { describe, expect, it } from "vitest";
import { lineNames, type InstrumentShape } from "./lines";

const shape = (name: string | null, staves = 1): InstrumentShape => ({ name, staves });

describe("lineNames", () => {
  it("calls the only line of a lead sheet Melody", () => {
    expect(lineNames([shape("Piano")])).toEqual(["Melody"]);
    expect(lineNames([shape(null)])).toEqual(["Melody"]);
    expect(lineNames([])).toEqual([]);
  });

  it("keeps a real name when the page has one staff and the document names it", () => {
    expect(lineNames([shape("Flûte")])).toEqual(["Flûte"]);
  });

  it("names the staves of a one-instrument page by position: the canon photo", () => {
    // homr reads the canon page as one part called Piano with staves 1 and 2.
    expect(lineNames([shape("Piano", 2)])).toEqual(["Top staff", "Bottom staff"]);
  });

  it("numbers the staves beyond two", () => {
    expect(lineNames([shape("Piano", 3)])).toEqual(["Staff 1", "Staff 2", "Staff 3"]);
  });

  it("uses the instruments' own names when a file has a part per line", () => {
    expect(lineNames([shape("Flûte"), shape("Vx. 1"), shape("Vx. 2")])).toEqual(["Flûte", "Vx. 1", "Vx. 2"]);
  });

  it("says which staff of an instrument that has two", () => {
    expect(lineNames([shape("Chant"), shape("Orgue", 2)]))
      .toEqual(["Chant", "Orgue (top staff)", "Orgue (bottom staff)"]);
  });

  it("keeps a numbered voice, which is a name and not a placeholder", () => {
    expect(lineNames([shape("Vx. 1"), shape("Vx. 2")])).toEqual(["Vx. 1", "Vx. 2"]);
  });

  it("falls back to positions when no instrument is really named", () => {
    expect(lineNames([shape("Part 1"), shape("Part 2")])).toEqual(["Top staff", "Bottom staff"]);
    expect(lineNames([shape(" "), shape(null)])).toEqual(["Top staff", "Bottom staff"]);
  });
});
