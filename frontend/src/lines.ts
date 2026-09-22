/**
 * The lines of a page (ADR 0008, decision 1): one per staff, in the order they are printed.
 *
 * A line is what the user gives an instrument to and what may be told to go on playing underneath
 * the others, so it has to mean the same thing across a re-render and across a save: it is named by
 * its position in the sheet (0 for the top staff), never by an object. homr reads a two-staff page
 * as one part with staves 1 and 2, an imported file may have a part per line, and both come out here
 * as a flat list.
 *
 * The naming rule is pure and lives apart from OSMD so it can be held to cases: a page with one
 * staff has one line called *Melody* (the word the switch has always used), a page whose staves all
 * belong to one instrument names them by position, and a page with several named instruments uses
 * their names, saying which staff of the instrument when it has more than one.
 */
import type { OpenSheetMusicDisplay } from "opensheetmusicdisplay";

export interface Line {
  /** Position in the sheet, top staff first. This is the id everything else stores. */
  index: number;
  name: string;
  /** The instrument the staff belongs to, for the line's own tooltip; null when the document has no name. */
  instrument: string | null;
}

/** An instrument as the naming rule sees it: what it is called, and how many staves it holds. */
export interface InstrumentShape { name: string | null; staves: number }

const POSITIONS = ["Top staff", "Bottom staff"];

/**
 * `Piano`, `Part 1`, `Score`: what a document calls a staff group when it has nothing to say about
 * it — homr writes `Piano` on every page it reads, whatever is printed. `Vx. 1` and `Flûte` are not
 * generic and are kept exactly as the file spells them.
 */
const GENERIC = new Set(["piano", "score", "music"]);
const NUMBERED = /^(part|staff|stave|instrument|track)\s*\.?\s*\d*$/;

function isGeneric(name: string | null): boolean {
  const n = (name ?? "").trim().toLowerCase();
  return n === "" || GENERIC.has(n) || NUMBERED.test(n);
}

/** The staff's position said in words: two staves are top and bottom, more are numbered. */
function position(i: number, of: number): string {
  if (of === 2) return POSITIONS[i];
  return `Staff ${i + 1}`;
}

/**
 * One name per staff, in printed order. Pure: `instruments` is what the document says, nothing more.
 *
 * With one staff on the page the name is the document's own when it says something (`Flûte`) and
 * *Melody* otherwise. With one instrument holding every staff — a piano page, and everything homr
 * reads — the names are positions, because "Piano" twice tells the user nothing. With several
 * instruments the names are theirs, and a staff of a two-staff instrument says which one it is.
 */
export function lineNames(instruments: InstrumentShape[]): string[] {
  const total = instruments.reduce((n, i) => n + Math.max(1, i.staves), 0);
  if (total === 1) {
    const only = instruments[0]?.name?.trim();
    return [only && !isGeneric(only) ? only : "Melody"];
  }
  const named = instruments.filter((i) => !isGeneric(i.name)).length;
  const names: string[] = [];
  let at = 0;
  for (const instrument of instruments) {
    const staves = Math.max(1, instrument.staves);
    const own = (instrument.name ?? "").trim();
    for (let s = 0; s < staves; s++) {
      if (named === 0 || isGeneric(own)) names.push(position(at, total));
      else if (staves === 1) names.push(own);
      else names.push(`${own} (${position(s, staves).toLowerCase()})`);
      at++;
    }
  }
  return names;
}

/** The shapes of a rendered sheet's instruments, top to bottom. */
export function instrumentsOf(osmd: OpenSheetMusicDisplay): InstrumentShape[] {
  return (osmd.Sheet?.Instruments ?? []).map((instrument) => ({
    name: instrument.Name ?? null,
    staves: instrument.Staves?.length ?? 1,
  }));
}

/**
 * The lines of a rendered sheet, with a lookup from a staff object to its line.
 *
 * The lookup is by identity because OSMD's own `idInMusicSheet` is a field the reader fills and
 * nothing here needs to trust its numbering; the order of `Instruments` and of each one's `Staves`
 * is the printed order, which is what a line's index means.
 */
export function readLines(osmd: OpenSheetMusicDisplay): { lines: Line[]; lineOf: (staff: unknown) => number } {
  const shapes = instrumentsOf(osmd);
  const names = lineNames(shapes);
  const lines: Line[] = [];
  const byStaff = new Map<unknown, number>();
  let at = 0;
  for (const instrument of osmd.Sheet?.Instruments ?? []) {
    for (const staff of instrument.Staves ?? []) {
      byStaff.set(staff, at);
      lines.push({ index: at, name: names[at] ?? `Staff ${at + 1}`, instrument: instrument.Name ?? null });
      at++;
    }
  }
  if (lines.length === 0) lines.push({ index: 0, name: "Melody", instrument: null });
  return { lines, lineOf: (staff: unknown) => byStaff.get(staff) ?? 0 };
}
