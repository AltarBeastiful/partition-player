/**
 * Reviewing a model draft in the session (plan 0016, step 6): the sheet shows the read or the
 * corrected score, ticking a change moves the corrected one, Apply is the server's one revision
 * and a single undo takes it all back. The network is the only thing replaced.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ModelChange, ModelDraft, ReviewState } from "../api";
import { parse, part } from "../score/xml";
import { lyricAt } from "../score/draft";

vi.mock("../api", async (orig) => ({ ...(await orig<typeof import("../api")>()), applyModelDraft: vi.fn(), getScoreText: vi.fn(), saveScore: vi.fn() }));
import * as api from "../api";
import { EditorSession } from "./session";

const GROUND_TRUTH = readFileSync(resolve(process.cwd(), "../bench/samples/anton_yvan_boris_ground_truth.musicxml"), "utf8");

const review: ReviewState = { doubts: [], checked: [], revision: 3, layout: null, has_image: false, has_original: false, form: null, lines: [], unders: [] };
const span = { staff: 0, from: 0, to: 3 };
const ch = (id: string, measure: number, onset: number, old: ModelChange["old"], now: ModelChange["new"]): ModelChange =>
  ({ id, span, verse: 1, measure, onset, old, new: now, ticked: true, conflict: false });
const draft: ModelDraft = {
  id: "d1", created: "now", base_revision: 3, route: { kind: "api", model: "m" }, spans: [{ ...span, lyrics_source: "x" }], dropped: [],
  changes: [
    ch("c1", 0, 0, { text: "Lors", syllabic: "begin" }, { text: "Lorsque", syllabic: "single" }),
    ch("c2", 1, 0, { text: "tions", syllabic: "end" }, { text: "tion", syllabic: "end" }),
    { ...ch("c3", 2, 1, { text: "sur", syllabic: "single" }, { text: "sus", syllabic: "single" }), ticked: false, conflict: true },
  ],
};

let session: EditorSession;
const first = (xml?: string) => lyricAt(xml ? parse(xml) : session.doc, 0, 0, 0, 1)?.text;

beforeEach(() => {
  vi.useFakeTimers();
  vi.mocked(api.saveScore).mockResolvedValue({ ...review, revision: 4, check: [], stats: {} as api.Stats });
  session = new EditorSession("t", GROUND_TRUTH, { ...review });
  session.openDraft(draft);
});
afterEach(() => { session.dispose(); vi.useRealTimers(); vi.resetAllMocks(); });

describe("showing the draft", () => {
  it("opens on the corrected version, with the ticks the server proposed", () => {
    expect(session.draft?.view).toBe("corrected");
    expect([...session.draft!.ticked].sort()).toEqual(["c1", "c2"]);   // a conflict comes unticked
    expect(first(session.shownXml)).toBe("Lorsque");
  });

  it("flips to the read version and back; the edited document is never touched", () => {
    session.setView("read");
    expect(first(session.shownXml)).toBe("Lors");
    session.setView("corrected");
    expect(first(session.shownXml)).toBe("Lorsque");
    expect(first()).toBe("Lors");
    expect(session.canUndo).toBe(false);
  });

  it("re-renders the sheet when the shown version or a tick changes", () => {
    const v = session.docVersion;
    session.setView("read");
    session.setView("corrected");
    session.tick("c1", false);
    expect(session.docVersion).toBe(v + 3);
  });

  it("an unticked change drops out of the corrected version", () => {
    session.tick("c1", false);
    expect(first(session.shownXml)).toBe("Lors");
    expect(lyricAt(parse(session.shownXml), 0, 1, 0, 1)?.text).toBe("tion");
    session.tick("c1", true);
    expect(first(session.shownXml)).toBe("Lorsque");
  });

  it("does not save anything while the draft is only being looked at", () => {
    session.tick("c1", false);
    vi.advanceTimersByTime(5000);
    expect(api.saveScore).not.toHaveBeenCalled();
  });
});

describe("applying", () => {
  beforeEach(() => {
    vi.mocked(api.applyModelDraft).mockResolvedValue({ ...review, revision: 4 });
    vi.mocked(api.getScoreText).mockImplementation(async () => session.shownXml);
  });

  it("sends the ticked ids in one call and takes the new revision", async () => {
    session.tick("c2", false);
    await session.applyDraft();
    expect(api.applyModelDraft).toHaveBeenCalledTimes(1);
    expect(api.applyModelDraft).toHaveBeenCalledWith("t", ["c1"]);
    expect(session.revision).toBe(4);
    expect(session.draft).toBeNull();
    expect(first()).toBe("Lorsque");
    expect(lyricAt(session.doc, 0, 1, 0, 1)?.text).toBe("tions");
  });

  it("is one undo step, and the undo brings back every syllable", async () => {
    await session.applyDraft();
    expect(session.canUndo).toBe(true);
    session.undo();
    expect(first()).toBe("Lors");
    expect(lyricAt(session.doc, 0, 1, 0, 1)?.text).toBe("tions");
    expect(session.canUndo).toBe(false);
  });

  it("is already saved: no second save of what the server wrote", async () => {
    await session.applyDraft();
    expect(session.status).toBe("saved");
    vi.advanceTimersByTime(5000);
    expect(api.saveScore).not.toHaveBeenCalled();
  });

  it("keeps the draft open and says why when the server refuses", async () => {
    vi.mocked(api.applyModelDraft).mockRejectedValue(new Error("a ticked change is not part of this draft"));
    await session.applyDraft();
    expect(session.draft).not.toBeNull();
    expect(session.message).toMatch(/not part of this draft/);
  });

  it("sends a pending edit first, so the server applies to what is on the screen", async () => {
    session.apply(() => undefined);
    await session.applyDraft();
    expect(api.saveScore).toHaveBeenCalledTimes(1);
  });
});

/** Your edits win (ticket 05): a place edited by hand is a conflict, unticked, and the rest still applies. */
describe("conflicts with hand edits", () => {
  const edit = (measure: number, text: string) => session.apply((d) => {
    const m = part(d, 0).getElementsByTagName("measure")[measure];
    const note = [...m.getElementsByTagName("note")].find((n) => !n.getElementsByTagName("rest").length && !n.getElementsByTagName("chord").length)!;
    note.getElementsByTagName("text")[0].textContent = text;
  });
  const flags = () => Object.fromEntries(session.draft!.draft.changes.map((c) => [c.id, [c.conflict, session.draft!.ticked.has(c.id)]]));

  it("marks a change conflicting and unticks it when its place is edited while the draft is open", () => {
    edit(0, "Lers");
    expect(flags()).toEqual({ c1: [true, false], c2: [false, true], c3: [true, false] });
    expect(first(session.shownXml)).toBe("Lers");                       // the hand edit stays on the sheet
    expect(lyricAt(parse(session.shownXml), 0, 1, 0, 1)?.text).toBe("tion");   // the others still show
  });

  it("marks a place edited since the pass as soon as the draft opens, whatever the server said", () => {
    session.dispose();
    session = new EditorSession("t", GROUND_TRUTH, { ...review });
    edit(0, "Lers");
    session.openDraft(draft);
    expect(flags().c1).toEqual([true, false]);
    expect(flags().c2).toEqual([false, true]);
  });

  it("applies only the others, and the hand edit is not overwritten", async () => {
    vi.mocked(api.applyModelDraft).mockResolvedValue({ ...review, revision: 5 });
    vi.mocked(api.getScoreText).mockImplementation(async () => session.shownXml);
    edit(0, "Lers");
    await session.applyDraft();
    expect(api.applyModelDraft).toHaveBeenCalledWith("t", ["c2"]);
    expect(first()).toBe("Lers");
  });

  it("writes over the hand edit only when the conflict is ticked on purpose", () => {
    edit(0, "Lers");
    session.tick("c1", true);
    expect(first(session.shownXml)).toBe("Lorsque");
  });

  it("clears the conflict, and ticks the change again, when the hand edit is undone", () => {
    edit(0, "Lers");
    session.undo();
    expect(flags().c1).toEqual([false, true]);
  });

  it("does not undo a deliberate tick by editing elsewhere", () => {
    edit(0, "Lers");
    session.tick("c1", true);
    edit(1, "tionz");
    expect(flags().c1).toEqual([true, true]);
  });
});

describe("applying while an autosave is in flight", () => {
  it("waits for the save, then applies, and sends nothing after", async () => {
    let release!: () => void;
    vi.mocked(api.saveScore).mockImplementation(() => new Promise((r) => { release = () => r({ ...review, revision: 4, check: [], stats: {} as api.Stats }); }));
    vi.mocked(api.applyModelDraft).mockResolvedValue({ ...review, revision: 5 });
    vi.mocked(api.getScoreText).mockImplementation(async () => session.shownXml);
    session.apply(() => undefined);
    vi.advanceTimersByTime(2000);                    // the autosave starts and hangs
    expect(api.saveScore).toHaveBeenCalledTimes(1);
    const applying = session.applyDraft();
    await Promise.resolve();
    expect(api.applyModelDraft).not.toHaveBeenCalled();
    release();
    await applying;
    expect(api.applyModelDraft).toHaveBeenCalledTimes(1);
    expect(session.revision).toBe(5);
    expect(api.saveScore).toHaveBeenCalledTimes(1);
  });
});

describe("closing without applying", () => {
  it("leaves the score as read", () => {
    session.closeDraft();
    expect(session.draft).toBeNull();
    expect(first(session.shownXml)).toBe("Lors");
  });
});
