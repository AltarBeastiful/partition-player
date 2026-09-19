import { useEffect, useState } from "react";
import { getLyrics, saveLyrics, type LyricsState } from "../api";

/** The words under the notes, one text field per verse, in the convention notation programs use:
 *  "-" splits a word into syllables, "_" holds a syllable over the next note, "*" skips a note. */
export function LyricsPanel({ jobId, version = 0, beforeSave, onSaved }: { jobId: string; version?: number; beforeSave?: () => Promise<void>; onSaved: () => void }) {
  const [state, setState] = useState<LyricsState | null>(null);
  const [verses, setVerses] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    getLyrics(jobId).then((s) => { setState(s); setVerses(s.verses.length ? s.verses : [""]); setOpen(s.verses.length > 0); })
      .catch((e) => setError((e as Error).message));
  }, [jobId, version]);

  const dirty = state !== null && verses.join("\n") !== state.verses.join("\n");

  async function save() {
    setSaving(true); setError(null);
    try {
      await beforeSave?.(); // a note edit still on its way must land first, or this save would be overwritten
      const s = await saveLyrics(jobId, verses);
      setState(s); setVerses(s.verses.length ? s.verses : [""]);
      onSaved();
    } catch (e) { setError((e as Error).message); } finally { setSaving(false); }
  }

  function count(text: string): number {
    return text.split(/\s+/).filter(Boolean).flatMap((w) => (/^\*+$/.test(w) ? [] : w.split("-").filter((p) => p.replace(/_+$/, "")))).length;
  }

  if (!state && !error) return null;
  return (
    <section className="card lyrics">
      <div className="controls">
        <strong>Lyrics</strong>
        {state && (
          <span className="muted">
            {state.verses.length === 0 ? "none read on the page" : `${state.syllables.reduce((a, b) => a + b, 0)} syllables in ${state.verses.length} verse${state.verses.length > 1 ? "s" : ""}`}
            {" "}under {state.notes} notes
          </span>
        )}
        <button className="quiet" onClick={() => setOpen((o) => !o)}>{open ? "Hide" : "Edit"}</button>
      </div>
      {open && (
        <>
          {verses.map((v, i) => (
            <label key={i} className="verse">
              <span className="muted">Verse {i + 1}, {count(v)} syllables{state && count(v) !== state.notes ? ` (${state.notes} notes)` : ""}</span>
              <textarea id={`verse-${i + 1}`} rows={3} value={v} spellCheck={false}
                onChange={(e) => setVerses((vs) => vs.map((x, k) => (k === i ? e.target.value : x)))} />
            </label>
          ))}
          <div className="controls">
            <button className="primary" onClick={save} disabled={saving || !dirty}>{saving ? "Saving…" : "Save lyrics"}</button>
            <button onClick={() => setVerses((vs) => [...vs, ""])} disabled={verses.length >= 12}>Add a verse</button>
            {verses.length > 1 && <button className="quiet" onClick={() => setVerses((vs) => vs.slice(0, -1))}>Remove the last verse</button>}
            <span className="muted">Write one syllable per note: "-" splits a word, "_" holds a syllable over the next note, "*" skips a note.</span>
          </div>
        </>
      )}
      {error && <div className="error">{error}</div>}
    </section>
  );
}
