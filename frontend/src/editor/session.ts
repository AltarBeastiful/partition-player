/**
 * The editing session of one score (ADR 0005, decision 3): the document as a DOM, the selection,
 * undo and redo as serializations, the doubts and the checked measures, and the autosave that sends
 * the whole document with the revision it was edited from. React reads it through subscribe().
 */
import { revertScore, saveScore, type Doubt, type Form, type Layout, type ReviewState, type Stats } from "../api";
import { remapForm } from "../form";
import { checkMeasures, checkText, type MeasureCheck } from "../score/check";
import { EditError } from "../score/edit";
import { find, nearest, parse, part, serialize, walk, type EventKey, type MeasureInfo } from "../score/xml";

export type SaveStatus = "saved" | "unsaved" | "saving" | "error" | "stale";

interface Snapshot { xml: string; doubts: Doubt[]; checked: number[]; selected: EventKey | null; form: Form | null }

/** One measure with something to look at: the recognition's doubts and the live check, together. */
export interface Place { measure: number; texts: string[]; info: boolean; live: boolean; checked: boolean }

const SAVE_DELAY_MS = 1200;

export class EditorSession {
  doc: XMLDocument;
  measures: MeasureInfo[] = [];
  checks: MeasureCheck[] = [];
  doubts: Doubt[];
  checked: Set<number>;
  revision: number;
  form: Form | null;  // the user's form, or null for the automatic one (plan 0004)
  readonly layout: Layout | null;
  readonly hasImage: boolean;
  readonly hasOriginal: boolean;
  selected: EventKey | null = null;
  status: SaveStatus = "saved";
  message: string | null = null;   // the last thing to tell the user (an operation refused, a save error)
  version = 0;       // bumped on every change React should see
  docVersion = 0;    // bumped when the document changed and the sheet must be re-rendered
  canUndo = false;
  canRedo = false;
  onStats: ((s: Stats) => void) | null = null;

  private xmlCache: string | null = null;
  private undoStack: Snapshot[] = [];
  private redoStack: Snapshot[] = [];
  private listeners = new Set<() => void>();
  private timer = 0;
  private saving = false;
  private pending = false;

  constructor(readonly jobId: string, xml: string, review: ReviewState) {
    this.doc = parse(xml);
    this.doubts = review.doubts;
    this.checked = new Set(review.checked);
    this.revision = review.revision;
    this.form = review.form ?? null;
    this.layout = review.layout;
    this.hasImage = review.has_image;
    this.hasOriginal = review.has_original;
    this.refresh();
  }

  subscribe(fn: () => void): () => void {
    this.listeners.add(fn);
    return () => { this.listeners.delete(fn); };
  }

  private emit(): void {
    this.version++;
    for (const fn of this.listeners) fn();
  }

  get xml(): string {
    if (this.xmlCache === null) this.xmlCache = serialize(this.doc);
    return this.xmlCache;
  }

  get dirty(): boolean {
    return this.status === "unsaved" || this.status === "saving" || this.status === "error";
  }

  private refresh(): void {
    this.xmlCache = null;
    this.measures = walk(part(this.doc));
    this.checks = checkMeasures(this.measures);
    this.canUndo = this.undoStack.length > 0;
    this.canRedo = this.redoStack.length > 0;
  }

  // ---- places -------------------------------------------------------------------------------------

  places(): Place[] {
    const by = new Map<number, Place>();
    const get = (m: number) => {
      let p = by.get(m);
      if (!p) { p = { measure: m, texts: [], info: true, live: false, checked: this.checked.has(m) }; by.set(m, p); }
      return p;
    };
    for (const d of this.doubts) {
      const p = get(d.measure);
      p.texts.push(d.text);
      if (!d.info) p.info = false;
    }
    for (const c of this.checks) {
      if (c.status === "ok") continue;
      const p = get(c.index);
      const t = checkText(c);
      if (!p.texts.some((x) => x.startsWith(t.split(" by ")[0]))) p.texts.push(t);
      p.info = false;
      p.live = true;
    }
    return [...by.values()].sort((a, b) => a.measure - b.measure);
  }

  /** The places still to look at: not checked, or the live check still complains. */
  open(): Place[] {
    return this.places().filter((p) => !p.info && (!p.checked || p.live));
  }

  nextPlace(from: number | null, direction: 1 | -1): Place | null {
    const open = this.open();
    if (open.length === 0) return null;
    if (from === null) return direction === 1 ? open[0] : open[open.length - 1];
    const after = direction === 1 ? open.find((p) => p.measure > from) : [...open].reverse().find((p) => p.measure < from);
    return after ?? (direction === 1 ? open[0] : open[open.length - 1]);
  }

  toggleChecked(measure: number): void {
    if (this.checked.has(measure)) this.checked.delete(measure); else this.checked.add(measure);
    this.touch();
  }

  /** The way the page is played; null goes back to the automatic form. Saved with the score, not undoable. */
  setForm(form: Form | null): void {
    this.form = form;
    this.touch();
  }

  // ---- selection ----------------------------------------------------------------------------------

  select(key: EventKey | null): void {
    this.selected = key;
    this.message = null;
    this.emit();
  }

  selectMeasure(measure: number): void {
    const m = this.measures[measure];
    const first = m?.events.find((e) => !e.inChord) ?? m?.events[0];
    this.select(first ? first.key : null);
  }

  /** Move the selection along the voice: the next or previous event, into the next measure. */
  move(direction: 1 | -1): void {
    if (!this.selected) { this.selectMeasure(0); return; }
    const all = this.measures.flatMap((m) => m.events.filter((e) => !e.inChord && e.key.staff === this.selected!.staff && e.key.voice === this.selected!.voice));
    const ev = find(this.measures, this.selected);
    const at = ev ? all.findIndex((e) => e.el === ev.el) : -1;
    const target = all[at + direction];
    if (target) this.select(target.key);
  }

  // ---- editing ------------------------------------------------------------------------------------

  /**
   * Run an operation on the document. `remap` says where each measure index went when the
   * operation changed the measure list, so the doubts and the checked marks follow their measures.
   */
  apply(fn: (doc: XMLDocument) => EventKey | null | void | number, remap?: (m: number) => number | null): boolean {
    const before: Snapshot = this.snapshot();
    const measureBefore = this.selected?.measure ?? null;
    let result: EventKey | null | void | number;
    try {
      result = fn(this.doc);
    } catch (e) {
      this.message = e instanceof EditError ? e.message : "This change could not be made: " + (e as Error).message;
      // the document may be half changed: put the snapshot back
      this.doc = parse(before.xml);
      this.refresh();
      this.emit();
      return false;
    }
    if (remap) {
      this.doubts = this.doubts.flatMap((d) => { const m = remap(d.measure); return m === null ? [] : [{ ...d, measure: m }]; });
      this.checked = new Set([...this.checked].map(remap).filter((m): m is number => m !== null));
      if (this.form) this.form = remapForm(this.form, remap);
    }
    this.refresh();
    if (measureBefore !== null && this.doubts.some((d) => d.measure === (remap ? remap(measureBefore) : measureBefore) && !d.info)) {
      const m = remap ? remap(measureBefore) : measureBefore;
      if (m !== null) this.checked.add(m); // an edited measure has been looked at
    }
    if (typeof result === "number") this.selected = this.measures[result]?.events[0]?.key ?? null;
    else if (result === undefined) this.selected = this.selected ? nearest(this.measures, this.selected)?.key ?? null : null;
    else this.selected = result;
    this.undoStack.push(before);
    if (this.undoStack.length > 200) this.undoStack.shift();
    this.redoStack = [];
    this.canUndo = true; this.canRedo = false;
    this.message = null;
    this.docVersion++;
    this.touch();
    return true;
  }

  undo(): void {
    const snap = this.undoStack.pop();
    if (!snap) return;
    this.redoStack.push(this.snapshot());
    this.restore(snap);
  }

  redo(): void {
    const snap = this.redoStack.pop();
    if (!snap) return;
    this.undoStack.push(this.snapshot());
    this.restore(snap);
  }

  private snapshot(): Snapshot {
    return { xml: this.xml, doubts: this.doubts, checked: [...this.checked], selected: this.selected, form: this.form };
  }

  private restore(snap: Snapshot): void {
    this.doc = parse(snap.xml);
    this.doubts = snap.doubts;
    this.checked = new Set(snap.checked);
    this.form = snap.form;
    this.refresh();
    this.selected = snap.selected ? nearest(this.measures, snap.selected)?.key ?? null : null;
    this.message = null;
    this.docVersion++;
    this.touch();
  }

  // ---- saving -------------------------------------------------------------------------------------

  private touch(): void {
    if (this.status !== "stale") {
      this.status = "unsaved";
      window.clearTimeout(this.timer);
      this.timer = window.setTimeout(() => { void this.save(); }, SAVE_DELAY_MS);
    }
    this.emit();
  }

  /** Send the document now (the autosave calls this; so does a lyrics save that must not race it). */
  async save(): Promise<void> {
    window.clearTimeout(this.timer);
    if (this.status === "stale" || this.status === "saved") return;
    if (this.saving) { this.pending = true; return; }
    this.saving = true;
    this.status = "saving";
    this.emit();
    try {
      const result = await saveScore(this.jobId, { musicxml: this.xml, checked: [...this.checked], revision: this.revision, doubts: this.doubts, form: this.form });
      this.revision = result.revision;
      this.onStats?.(result.stats);
      this.status = this.pending ? "unsaved" : "saved";
    } catch (e) {
      const status = (e as { status?: number }).status;
      this.status = status === 409 ? "stale" : "error";
      this.message = status === 409
        ? "This score was changed elsewhere. Reload the page to get the latest version; your unsaved changes here will be lost."
        : "Could not save: " + (e as Error).message;
    } finally {
      this.saving = false;
    }
    this.emit();
    if (this.pending) { this.pending = false; void this.save(); }
  }

  async revert(): Promise<void> {
    window.clearTimeout(this.timer);
    const result = await revertScore(this.jobId);
    this.onStats?.(result.stats);
    this.revision = result.revision;
    this.form = null;
  }

  dispose(): void {
    window.clearTimeout(this.timer);
    this.listeners.clear();
  }
}
