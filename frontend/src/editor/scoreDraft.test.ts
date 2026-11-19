/**
 * Notes and chords in a model draft (ADR 0010, plan 0016): the draft logic. A change is the editor's operations
 * (score/edit.ts) replayed on a clone of the score as read, checked the way the server checked them: nothing
 * outside the span, no measure that added up stops adding up. The same cases as backend/tests/test_model_notes.py,
 * on the Anton ground truth (2/4, three flats; bar 1 has a Cm chord, bar 2 is four eighths G4 Ab4 Ab4 G4).
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ModelChange, ModelDraft, ReviewState, ScoreChange } from "../api";
import { changeLine, correctedXml, markKeys } from "../score/draft";
import { summariseMeasure, chordTextAt } from "../score/modelOps";
import { parse, part, walk } from "../score/xml";

vi.mock("../api", async (orig) => ({ ...(await orig<typeof import("../api")>()), applyModelDraft: vi.fn(), getScoreText: vi.fn(), saveScore: vi.fn(), estimateModelPass: vi.fn(), runModelPass: vi.fn() }));
import * as api from "../api";
import { EditorSession } from "./session";
import { ModelFlow } from "./modelFlow";

const XML = readFileSync(resolve(process.cwd(), "../bench/samples/anton_yvan_boris_ground_truth.musicxml"), "utf8");
const span = { staff: 0, from: 0, to: 1 };
const review: ReviewState = { doubts: [], checked: [], revision: 3, layout: null, has_image: false, has_original: false, form: null, lines: [], unders: [] };

const notes = (id: string, measure: number, ops: ScoreChange["ops"], old: string, now: string, extra: Partial<ScoreChange> = {}): ScoreChange =>
  ({ id, kind: "notes", span, measure, ops, old: { text: old }, new: { text: now }, ticked: true, conflict: false, ...extra });
const chord = (id: string, event: number, text: string, old: string): ScoreChange =>
  ({ id, kind: "chord", span, measure: 0, event, ops: [{ op: "setChord", measure: 0, event, text }], old: { text: old }, new: { text }, ticked: true, conflict: false });

const BAR2 = "G4 eighth, Ab4 eighth, Ab4 eighth, G4 eighth";
const UP = notes("n1", 1, [{ op: "stepPitch", measure: 1, event: 0, delta: 1 }], BAR2, "Ab4 eighth, Ab4 eighth, Ab4 eighth, G4 eighth", { marks: [0] });
const CM7 = chord("h1", 0, "Cm7", "Cm");
const lengthen = { op: "setDuration", measure: 1, event: 0, type: "quarter", dots: 0 };
const BALANCED = notes("n2", 1, [lengthen, { op: "deleteEvent", measure: 1, event: 3 }], BAR2, "G4 quarter, Ab4 eighth, Ab4 eighth");

const shown = (changes: ScoreChange[], ticked = changes.map((c) => c.id)) => parse(correctedXml(XML, changes, new Set(ticked)));
const bar = (doc: XMLDocument, m: number) => summariseMeasure(doc, m);

describe("the corrected score with notes and chords", () => {
  it("replays a pitch change and a chord change, and leaves the read score alone", () => {
    const doc = shown([UP, CM7]);
    expect(bar(doc, 1)).toBe("Ab4 eighth, Ab4 eighth, Ab4 eighth, G4 eighth");   // the key writes the step above G as A-flat
    expect(chordTextAt(doc, 0, 0)).toBe("Cm7");
    expect(bar(parse(XML), 1)).toBe(BAR2);
    expect(chordTextAt(parse(XML), 0, 0)).toBe("Cm");
  });

  it("leaves an unticked change as read", () => {
    const doc = shown([UP, CM7], ["h1"]);
    expect(bar(doc, 1)).toBe(BAR2);
    expect(chordTextAt(doc, 0, 0)).toBe("Cm7");
  });

  it("keeps a balanced group of operations together and the measure count", () => {
    const doc = shown([BALANCED]);
    expect(bar(doc, 1)).toBe("G4 quarter, Ab4 eighth, Ab4 eighth");
    expect(walk(part(doc)).length).toBe(19);
  });

  it("skips a change that throws on this score, and one that unbalances a measure that added up", () => {
    const gone = notes("n3", 1, [{ op: "stepPitch", measure: 1, event: 99, delta: 1 }], BAR2, "x");
    const over = notes("n4", 1, [lengthen], BAR2, "x");              // 1 + 3 eighths in 2/4: three quarters
    const doc = shown([gone, over, CM7]);
    expect(bar(doc, 1)).toBe(BAR2);
    expect(chordTextAt(doc, 0, 0)).toBe("Cm7");                       // the others still apply
  });

  it("does not touch anything outside the span", () => {
    const outside = notes("n5", 3, [{ op: "stepPitch", measure: 3, event: 0, delta: 1 }], "", "x", { span: { staff: 0, from: 0, to: 1 } });
    const before = bar(parse(XML), 3);
    expect(bar(shown([outside]), 3)).toBe(before);
  });

  it("names a note by where it was read: an earlier deletion does not move the next operation's target", () => {
    const both = notes("n6", 1, [{ op: "deleteEvent", measure: 1, event: 0 }, { op: "setDuration", measure: 1, event: 1, type: "quarter", dots: 0 }], BAR2, "Ab4 quarter, Ab4 eighth, G4 eighth");
    expect(bar(shown([both]), 1)).toBe("Ab4 quarter, Ab4 eighth, G4 eighth");
  });
});

describe("marks and lines", () => {
  it("marks the notes a change moved, in the version shown, whatever the staff arithmetic", () => {
    const doc = shown([UP]);
    const keys = markKeys(walk(part(doc)), [UP, CM7]);
    expect(keys.map((k) => [k.measure, k.onset])).toEqual([[1, 0], [0, 0]]);
  });

  it("says where it was and what it was", () => {
    expect(changeLine(UP)).toBe(`bar 2, notes: ${BAR2} becomes Ab4 eighth, Ab4 eighth, Ab4 eighth, G4 eighth`);
    expect(changeLine(CM7)).toBe('bar 1, chord: "Cm" becomes "Cm7"');
    expect(changeLine(chord("h2", 0, "", "Cm"))).toBe('bar 1, chord: "Cm" is taken away');
    expect(changeLine(chord("h3", 0, "Am", ""))).toBe('bar 1, chord: new "Am"');
  });
});

describe("in the session", () => {
  let session: EditorSession;
  const draft: ModelDraft = { id: "d1", created: "now", base_revision: 3, route: { kind: "api", model: "m" }, spans: [{ ...span, lyrics_source: "" }], dropped: [], changes: [UP, CM7] };
  beforeEach(() => { vi.useFakeTimers(); session = new EditorSession("t", XML, { ...review }); session.openDraft(draft); });
  afterEach(() => { session.dispose(); vi.useRealTimers(); vi.resetAllMocks(); });

  it("shows the corrected notes and plays them, and the read ones on request", () => {
    expect(bar(parse(session.shownXml), 1)).toBe("Ab4 eighth, Ab4 eighth, Ab4 eighth, G4 eighth");
    expect(session.shownMeasures[1].events[0].key.midi).toBe(68);           // A-flat4: what the player hears
    session.setView("read");
    expect(session.shownMeasures[1].events[0].key.midi).toBe(67);
  });

  it("flags a change as a conflict when its notes were edited by hand, and ticks it again when the edit is undone", () => {
    session.apply((d) => { const n = walk(part(d))[1].events[0]; n.el.getElementsByTagName("octave")[0].textContent = "5"; });
    const flags = () => Object.fromEntries(session.draft!.draft.changes.map((c) => [c.id, [c.conflict, session.draft!.ticked.has(c.id)]]));
    expect(flags()).toEqual({ n1: [true, false], h1: [false, true] });
    session.undo();
    expect(flags()).toEqual({ n1: [false, true], h1: [false, true] });
  });

  it("sends the ticked ids of notes and chords alike when applying", async () => {
    vi.mocked(api.applyModelDraft).mockResolvedValue({ ...review, revision: 4 });
    vi.mocked(api.getScoreText).mockImplementation(async () => session.shownXml);
    session.tick("h1", false);
    await session.applyDraft();
    expect(api.applyModelDraft).toHaveBeenCalledWith("t", ["n1"], []);
    expect(bar(session.doc, 1)).toBe("Ab4 eighth, Ab4 eighth, Ab4 eighth, G4 eighth");
    expect(chordTextAt(session.doc, 0, 0)).toBe("Cm");
  });
});

describe("from the engine's doubts", () => {
  afterEach(() => { vi.useRealTimers(); vi.resetAllMocks(); });
  const doubts: ReviewState["doubts"] = [
    { measure: 2, kind: "heads_more", text: "a second reading disagrees", level: "check" },
    { measure: 7, kind: "overfull", text: "longer than 2/4 by an eighth", level: "wrong" },
    { measure: 7, kind: "heads_more", text: "a second reading disagrees", level: "check" },
    { measure: 9, kind: "pickup", text: "a pickup", level: "info", info: true },
  ];

  it("lists the strong doubts first, and tells the model what the engine said of each span", () => {
    vi.useFakeTimers();
    const s = new EditorSession("t", XML, { ...review, doubts });
    expect(s.doubtSpans().map((d) => [d.from, d.level])).toEqual([[7, "wrong"], [2, "check"]]);
    expect(s.doubtNote({ staff: 0, from: 7, to: 7 })).toBe("measure 7: longer than 2/4 by an eighth; measure 7: a second reading disagrees");
    expect(s.doubtNote({ staff: 0, from: 9, to: 9 })).toBe("");           // information only: not worth a call's words
    s.dispose();
  });

  it("asks for notes and chords with spans that carry no words, and runs only after the estimate", async () => {
    const estimate = { calls: 2, estimated_tokens: 900, estimated_cost_usd: 0.002, model: "m", confirm: false as const };
    vi.mocked(api.estimateModelPass).mockResolvedValue(estimate);
    vi.mocked(api.runModelPass).mockResolvedValue({ id: "d", created: "", base_revision: 1, route: { kind: "api", model: "m" }, spans: [], changes: [UP], dropped: [] });
    const flow = new ModelFlow("t");
    const spans = [{ staff: 0, from: 7, to: 7, needs_image: false, note: "measure 7: longer" }, { staff: 0, from: 2, to: 3, needs_image: false, note: "" }];
    await flow.ask(spans);
    expect(api.estimateModelPass).toHaveBeenCalledWith("t", { spans });
    expect(api.runModelPass).not.toHaveBeenCalled();
    const d = await flow.confirm();
    expect(api.runModelPass).toHaveBeenCalledWith("t", { spans });
    expect(d?.changes[0]).toBe(UP);
  });
});

// a lyric change keeps its old shape
const _lyric: ModelChange = { id: "c1", span, verse: 1, measure: 0, onset: 0, old: null, new: { text: "a", syllabic: "single" }, ticked: true, conflict: false };
void _lyric;
