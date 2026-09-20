/**
 * The session's undo timeline where the form takes part in it (plan 0007, step 1): a form change is
 * a step of its own, a run of keystrokes in one field is a single step, and undoing a note edit no
 * longer reverts a form built after it.
 *
 * `touch()` arms a real 1200 ms autosave that would call fetch, so every test runs on fake timers
 * and the session is disposed at the end.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReviewState } from "../api";
import type { Form } from "../form";
import { toRest } from "../score/edit";
import { part, walk } from "../score/xml";
import { EditorSession } from "./session";

const GROUND_TRUTH = readFileSync(resolve(process.cwd(), "../bench/samples/anton_yvan_boris_ground_truth.musicxml"), "utf8");

const review: ReviewState = { doubts: [], checked: [], revision: 1, layout: null, has_image: false, has_original: false, form: null };

const form = (name: string, to = 10): Form => ({
  sections: [{ name, from: 0, to }, { name: "Chorus", from: to + 1, to: 18 }],
  passes: [{ section: 0, verse: 1 }, { section: 1, verse: null }],
});

let session: EditorSession;

beforeEach(() => {
  vi.useFakeTimers();
  session = new EditorSession("test", GROUND_TRUTH, { ...review });
});

afterEach(() => {
  session.dispose();
  vi.useRealTimers();
});

describe("the form in the undo timeline", () => {
  it("keeps a form built after a note edit when that edit is undone", () => {
    const clean = session.xml;
    const first = walk(part(session.doc))[0].events[0].key;
    expect(session.apply((d) => toRest(d, first))).toBe(true);
    const edited = session.xml;
    expect(edited).not.toBe(clean);
    session.setForm(form("Verse"));

    session.undo(); // undoes the form change, and only it
    expect(session.form).toBeNull();
    expect(session.xml).toBe(edited); // the note edit is still there
    session.undo(); // now the note edit
    expect(session.xml).toBe(clean);
    expect(session.form).toBeNull();
    session.redo();
    expect(session.form).toBeNull();
    session.redo();
    expect(session.form?.sections[0].name).toBe("Verse");
  });

  it("undoes a form change on its own, without touching the document", () => {
    const before = session.xml;
    const docVersion = session.docVersion;
    session.setForm(form("Verse"));
    expect(session.canUndo).toBe(true);

    session.undo();
    expect(session.form).toBeNull();
    expect(session.xml).toBe(before);
    expect(session.docVersion).toBe(docVersion); // the sheet is not re-rendered for a form undo

    session.redo();
    expect(session.form?.sections).toHaveLength(2);
    expect(session.docVersion).toBe(docVersion);
  });

  it("makes a run of keystrokes in one field a single undo step", () => {
    for (const name of ["C", "Ch", "Cho", "Chor", "Choru", "Chorus"]) session.setForm(form(name), "name:0");
    expect(session.form?.sections[0].name).toBe("Chorus");

    session.undo();
    expect(session.form).toBeNull();
    expect(session.canUndo).toBe(false);
  });

  it("starts a new step for another field, and for a change that carries no key", () => {
    session.setForm(form("Verse"), "name:0");
    session.setForm({ ...form("Verse"), passes: [{ section: 0, verse: 2 }] }, "verse:0");
    session.setForm({ ...form("Verse"), passes: [] }); // structural: its own step

    session.undo();
    expect(session.form?.passes).toHaveLength(1);
    session.undo();
    expect(session.form?.passes[0].verse).toBe(1);
    session.undo();
    expect(session.form).toBeNull();
  });

  it("ends a coalescing run at a document edit, so the two do not merge", () => {
    session.setForm(form("Verse"), "name:0");
    const first = walk(part(session.doc))[0].events[0].key;
    session.apply((d) => toRest(d, first));
    session.setForm(form("Verses"), "name:0");

    session.undo();
    expect(session.form?.sections[0].name).toBe("Verse"); // the second run is its own step
    session.undo();
    expect(session.form?.sections[0].name).toBe("Verse"); // the note edit, form untouched
    session.undo();
    expect(session.form).toBeNull();
  });

  it("autosaves a form change once the run is over", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ ...review, revision: 2, check: [], stats: {} }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    session.setForm(form("Verse"), "name:0");
    expect(session.status).toBe("unsaved");
    await vi.advanceTimersByTimeAsync(1300);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    vi.unstubAllGlobals();
  });
});
