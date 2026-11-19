/**
 * Model readings in the session (ticket 06, ADR 0010): the changes the user did not take stay as
 * stored readings; accepting one is an ordinary undoable edit, rejecting hides it on the server.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ModelReading, ReviewState } from "../api";
import { lyricAt } from "../score/draft";

vi.mock("../api", async (orig) => ({ ...(await orig<typeof import("../api")>()), rejectModelReading: vi.fn(), saveScore: vi.fn() }));
import * as api from "../api";
import { EditorSession } from "./session";

const GROUND_TRUTH = readFileSync(resolve(process.cwd(), "../bench/samples/anton_yvan_boris_ground_truth.musicxml"), "utf8");

const reading = (id: string, measure: number, onset: number, now: ModelReading["new"], status: ModelReading["status"] = "proposed"): ModelReading => ({
  id, draft: "d1", span: { staff: 0, from: 0, to: 3 }, verse: 1, measure, onset, old: { text: "Lors", syllabic: "begin" }, new: now,
  route: "api", model: "m", time: "now", status,
});
const stored: ModelReading[] = [
  reading("r1", 0, 0, { text: "Lorsque", syllabic: "single" }),
  reading("r2", 1, 0, { text: "tion", syllabic: "end" }),
  reading("r3", 1, 0, { text: "x", syllabic: "single" }, "rejected"),
  reading("r4", 0, 1, { text: "que", syllabic: "end" }, "accepted"),
];
const review: ReviewState = { doubts: [], checked: [], revision: 3, layout: null, has_image: false, has_original: false, form: null, lines: [], unders: [], model_readings: stored };

let session: EditorSession;
const first = () => lyricAt(session.doc, 0, 0, 0, 1)?.text;

beforeEach(() => {
  vi.useFakeTimers();
  session = new EditorSession("t", GROUND_TRUTH, { ...review });
});
afterEach(() => { session.dispose(); vi.useRealTimers(); vi.resetAllMocks(); });

describe("which readings a measure offers", () => {
  it("lists the proposed ones of that measure, not the rejected or accepted", () => {
    expect(session.modelReadingsAt(0).map((r) => r.id)).toEqual(["r1"]);
    expect(session.modelReadingsAt(1).map((r) => r.id)).toEqual(["r2"]);
    expect(session.modelReadingsAt(5)).toEqual([]);
  });

  it("is empty for a score saved before the model pass existed", () => {
    const old = new EditorSession("t", GROUND_TRUTH, { ...review, model_readings: undefined } as unknown as ReviewState);
    expect(old.modelReadingsAt(0)).toEqual([]);
    old.dispose();
  });
});

describe("accepting", () => {
  it("writes the syllable as an ordinary edit, and one undo takes it back", () => {
    expect(first()).toBe("Lors");
    expect(session.acceptModelReading("r1")).toBe(true);
    expect(first()).toBe("Lorsque");
    expect(session.canUndo).toBe(true);
    expect(session.status).toBe("unsaved");
    session.undo();
    expect(first()).toBe("Lors");
  });

  it("stops offering a reading the sheet already says", () => {
    session.acceptModelReading("r1");
    expect(session.modelReadingsAt(0)).toEqual([]);
    session.undo();
    expect(session.modelReadingsAt(0).map((r) => r.id)).toEqual(["r1"]);
  });
});

describe("rejecting", () => {
  it("asks the server, then hides the reading", async () => {
    vi.mocked(api.rejectModelReading).mockResolvedValue({ ...review, model_readings: stored.map((r) => (r.id === "r1" ? { ...r, status: "rejected" as const } : r)) });
    await session.rejectModelReading("r1");
    expect(api.rejectModelReading).toHaveBeenCalledWith("t", "r1");
    expect(session.modelReadingsAt(0)).toEqual([]);
    expect(session.canUndo).toBe(false);   // hiding is not an edit of the score
  });

  it("keeps the reading and says why when the server refuses", async () => {
    vi.mocked(api.rejectModelReading).mockRejectedValue(new Error("no such reading"));
    await session.rejectModelReading("r1");
    expect(session.modelReadingsAt(0).map((r) => r.id)).toEqual(["r1"]);
    expect(session.message).toMatch(/no such reading/);
  });
});

describe("after a save", () => {
  it("keeps the readings the server sends back", async () => {
    vi.mocked(api.saveScore).mockResolvedValue({ ...review, revision: 4, check: [], stats: {} as api.Stats });
    session.acceptModelReading("r1");
    await session.save();
    expect(session.modelReadingsAt(1).map((r) => r.id)).toEqual(["r2"]);
  });
});
