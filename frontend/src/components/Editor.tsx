import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { reviewImageUrl, type Layout } from "../api";
import { TYPES, tiedToNext, typeOf, type DurationType } from "../score/edit";
import { find, type Event, type EventKey } from "../score/xml";
import type { Commands } from "../editor/commands";
import type { EditorSession, Place } from "../editor/session";

const LABEL: Record<DurationType, string> = { breve: "breve", whole: "whole", half: "half", quarter: "quarter", eighth: "8th", "16th": "16th", "32nd": "32nd", "64th": "64th" };
const KEYS = [-7, -6, -5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5, 6, 7];
const KEY_NAMES: Record<number, string> = { "-7": "C♭", "-6": "G♭", "-5": "D♭", "-4": "A♭", "-3": "E♭", "-2": "B♭", "-1": "F", 0: "C", 1: "G", 2: "D", 3: "A", 4: "E", 5: "B", 6: "F♯", 7: "C♯" };

export function pitchName(ev: Event): string {
  if (ev.isRest || !ev.pitch) return "rest";
  const acc = ev.pitch.alter > 0 ? "♯".repeat(ev.pitch.alter) : ev.pitch.alter < 0 ? "♭".repeat(-ev.pitch.alter) : "";
  return `${ev.pitch.step}${acc}${ev.pitch.octave}`;
}

function beat(ev: Event, beatType: number): string {
  const b = ev.key.onset * beatType + 1;
  return Number.isInteger(b) ? `beat ${b}` : `beat ${Number(b.toFixed(2))}`;
}

/** "4 places to check", the current one in words, and the way from one to the next. */
export function ReviewBar({ session, c, hasPhoto, showPhoto, setShowPhoto }: {
  session: EditorSession; c: Commands; hasPhoto: boolean; showPhoto: boolean; setShowPhoto: (v: boolean) => void;
}) {
  const places = session.places();
  const open = session.open();
  const m = session.selected?.measure ?? null;
  const here: Place | undefined = m === null ? undefined : places.find((p) => p.measure === m);
  const edited = session.canUndo || session.revision > 1;
  const photo = hasPhoto && (
    <label className="photo-toggle"><input type="checkbox" checked={showPhoto} onChange={(e) => setShowPhoto(e.target.checked)} /> Photo</label>
  );
  if (places.length === 0 && !edited && !session.selected) {
    return (
      <div className="review">
        <span className="ok">Every measure adds up.</span>
        <span className="muted">Click a note on the sheet to correct it{hasPhoto ? "; the photo is one click away" : ""}.</span>
        {photo}
      </div>
    );
  }
  return (
    <div className="review">
      {open.length > 0
        ? <strong>{open.length} place{open.length > 1 ? "s" : ""} to check</strong>
        : places.length > 0 ? <span className="ok">Every flagged measure has been checked.</span> : <span className="ok">Every measure adds up.</span>}
      {open.length > 0 && (
        <span className="nav">
          <button className="quiet" onClick={() => c.place(-1)} title="Previous place (p)">‹ Previous</button>
          <button onClick={() => c.place(1)} title="Next place (n)">Next place ›</button>
        </span>
      )}
      {here && (
        <span className={"here" + (here.info && !here.live ? " info" : "")}>
          Measure {here.measure + 1}: {here.texts.join("; ")}.
          {!here.info && (
            <button className="quiet" onClick={c.checked} title="Mark this measure as checked (c)">
              {here.checked && !here.live ? "Unmark" : "Mark checked"}
            </button>
          )}
        </span>
      )}
      {photo}
    </div>
  );
}

/** The tools for the selected event and its measure. */
export function Toolbar({ session, c, onPlayFrom, onRevert, onReload, onDone, staves }: {
  session: EditorSession; c: Commands; onPlayFrom: (measure: number) => void; onRevert: () => void; onReload: () => void; onDone: () => void; staves: number;
}) {
  const [panel, setPanel] = useState<"time" | "key" | "clef" | null>(null);
  const [chord, setChord] = useState("");
  const sel = session.selected;
  const ev = sel ? find(session.measures, sel) : null;
  const m = sel ? session.measures[sel.measure] : null;
  const t = ev ? typeOf(ev) : null;
  const chordOnBeat = c.chordText();
  useEffect(() => { setChord(chordOnBeat); }, [chordOnBeat, sel?.measure, sel?.onset]);
  const isRest = !ev || ev.isRest;
  const disabled = !ev;
  const check = m ? session.checks[m.index] : null;

  return (
    <div className="toolbar" role="toolbar" aria-label="Score editor">
      <div className="toolbar-head">
        {ev && m ? (
          <span className="selection">
            <strong>Measure {m.index + 1}</strong>, {beat(ev, m.beatType)}: {pitchName(ev)}{t ? `, ${LABEL[t.type]}${".".repeat(t.dots)}` : ""}
            {ev.inChord ? " (in a chord)" : ""}{tiedToNext(ev) ? ", tied" : ""}
            {check && check.status !== "ok" && <span className="bad"> · {check.status === "underfull" ? "short" : check.status === "overfull" ? "long" : "empty"}</span>}
          </span>
        ) : <span className="muted">Click a note on the sheet, or press n for the next place to check.</span>}
        <span className="save-state">
          <button className="quiet" onClick={c.undo} disabled={!session.canUndo} title="Undo (Ctrl+Z)">Undo</button>
          <button className="quiet" onClick={c.redo} disabled={!session.canRedo} title="Redo (Ctrl+Y)">Redo</button>
          {session.status === "saved" && <span className="muted">Saved</span>}
          {session.status === "unsaved" && <span className="muted">Unsaved…</span>}
          {session.status === "saving" && <span className="muted">Saving…</span>}
          {session.status === "error" && <button className="danger" onClick={() => void session.save()}>Save again</button>}
          {session.status === "stale" && <button className="danger" onClick={onReload}>Reload</button>}
          <button className="primary" onClick={onDone} title="Leave edit mode (Esc)">Done</button>
        </span>
      </div>
      {session.message && <div className="error">{session.message}</div>}
      {ev && <div className="groups">
        <div className="group">
          <span className="label">Pitch</span>
          <button onClick={() => c.pitch(1)} disabled={disabled || isRest} title="A step up (↑)">▲</button>
          <button onClick={() => c.pitch(-1)} disabled={disabled || isRest} title="A step down (↓)">▼</button>
          <button onClick={() => c.alter(-1)} disabled={disabled || isRest} title="Flat (-)">♭</button>
          <button onClick={() => c.alter(0)} disabled={disabled || isRest} title="Natural (0)">♮</button>
          <button onClick={() => c.alter(1)} disabled={disabled || isRest} title="Sharp (+)">♯</button>
          <button onClick={() => c.octave(1)} disabled={disabled || isRest} title="An octave up (Shift+↑)">8va</button>
          <button onClick={() => c.octave(-1)} disabled={disabled || isRest} title="An octave down (Shift+↓)">8vb</button>
        </div>
        <div className="group">
          <span className="label">Length</span>
          {TYPES.map((type, i) => (
            <button key={type} className={t?.type === type ? "on" : ""} onClick={() => c.duration(type)} disabled={disabled} title={`${LABEL[type]} (${i + 1})`}>{LABEL[type]}</button>
          ))}
          <button className={t?.dots ? "on" : ""} onClick={c.dot} disabled={disabled} title="Dot (.)">·</button>
          <button className={ev && tiedToNext(ev) ? "on" : ""} onClick={c.tie} disabled={disabled || isRest} title="Tie to the next note (t)">tie</button>
        </div>
        <div className="group">
          <span className="label">Event</span>
          <button onClick={c.restToggle} disabled={disabled} title="Note ↔ rest (r)">{isRest ? "→ note" : "→ rest"}</button>
          <button onClick={() => c.insert("before", "note")} disabled={disabled} title="Insert a note before (b)">+ before</button>
          <button onClick={() => c.insert("after", "note")} disabled={disabled} title="Insert a note after (a)">+ after</button>
          <button onClick={() => c.insert("after", "rest")} disabled={disabled} title="Insert a rest after">+ rest</button>
          <button onClick={c.remove} disabled={disabled} title="Delete (Del)">Delete</button>
        </div>
        <div className="group">
          <span className="label">Chord</span>
          <input className="chord" value={chord} placeholder="none" size={7} disabled={disabled} spellCheck={false}
            onChange={(e) => setChord(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") { c.chord(chord); (e.target as HTMLInputElement).blur(); } if (e.key === "Escape") { setChord(chordOnBeat); (e.target as HTMLInputElement).blur(); } }}
            onBlur={() => { if (chord.trim() !== chordOnBeat) c.chord(chord); }}
            title="The chord symbol on this beat: C, Am7, F#dim, Bb/D… Empty removes it." />
        </div>
        <div className="group">
          <span className="label">Measure</span>
          <button onClick={c.fill} disabled={!check || check.status !== "underfull"} title="Fill the missing length with rests (f)">Fill</button>
          <button onClick={c.split} disabled={disabled || !ev || ev.key.onset === 0} title="Start a new measure at this note">Split here</button>
          <button onClick={c.merge} disabled={!m || m.index >= session.measures.length - 1} title="Join with the next measure">Merge next</button>
          <button onClick={() => c.insertMeasure("after")} disabled={!m} title="Insert an empty measure after">+ measure</button>
          <button onClick={c.deleteMeasure} disabled={!m || session.measures.length < 2} title="Delete this measure">Delete measure</button>
          <button onClick={() => m && onPlayFrom(m.index)} disabled={!m} title="Play from this measure">▶ from here</button>
        </div>
        <div className="group">
          <span className="label">Score</span>
          <button className={panel === "time" ? "on" : ""} onClick={() => setPanel(panel === "time" ? null : "time")} disabled={!m}>Time {m ? `${m.beats}/${m.beatType}` : ""}</button>
          <button className={panel === "key" ? "on" : ""} onClick={() => setPanel(panel === "key" ? null : "key")} disabled={!m}>Key {m ? KEY_NAMES[m.fifths] ?? m.fifths : ""}</button>
          <button className={panel === "clef" ? "on" : ""} onClick={() => setPanel(panel === "clef" ? null : "clef")} disabled={!m}>Clef</button>
          {session.hasOriginal && <button className="quiet" onClick={onRevert} title="Put the recognized score back, dropping every edit">Revert</button>}
        </div>
      </div>}
      {panel === "time" && m && (
        <div className="panel">
          <span>Time signature from measure {m.index + 1} on:</span>
          {["2/4", "3/4", "4/4", "6/8", "2/2", "3/8", "9/8", "12/8", "5/4"].map((ts) => (
            <button key={ts} className={`${m.beats}/${m.beatType}` === ts ? "on" : ""} onClick={() => { c.time(Number(ts.split("/")[0]), Number(ts.split("/")[1])); setPanel(null); }}>{ts}</button>
          ))}
        </div>
      )}
      {panel === "key" && m && (
        <div className="panel">
          <span>Key signature from measure {m.index + 1} on:</span>
          {KEYS.map((f) => (
            <button key={f} className={m.fifths === f ? "on" : ""} onClick={() => { c.key(f); setPanel(null); }} title={`${Math.abs(f)} ${f < 0 ? "flat" : "sharp"}${Math.abs(f) === 1 ? "" : "s"}`}>{KEY_NAMES[f]}</button>
          ))}
        </div>
      )}
      {panel === "clef" && m && (
        <div className="panel">
          <span>Clef from measure {m.index + 1} on{staves > 1 ? `, staff ${sel?.staff}` : ""}:</span>
          <button onClick={() => { c.clef(sel?.staff ?? 1, "G"); setPanel(null); }}>𝄞 treble</button>
          <button onClick={() => { c.clef(sel?.staff ?? 1, "F"); setPanel(null); }}>𝄢 bass</button>
          <button onClick={() => { c.clef(sel?.staff ?? 1, "C"); setPanel(null); }}>𝄡 alto</button>
        </div>
      )}
      {ev && <div className="muted keys">Keys: ↑ ↓ pitch, Shift+↑ ↓ octave, − 0 + accidental, 1…6 length, . dot, t tie, r rest, a b insert, Del, f fill, ← → move, n p next and previous place, c checked, Ctrl+Z undo.</div>}
    </div>
  );
}

/** The strip of the photo the selected measure was read from, the measure framed. */
export function PrintedStrip({ jobId, layout, measure, onOpen }: { jobId: string; layout: Layout; measure: number | null; onOpen: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () => setWidth(el.clientWidth);
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const system = measure === null ? null : layout.systems.find((s) => s.measures.some((mm) => mm.index === measure)) ?? null;
  const unit = system?.unit || 30;
  const margin = 4 * unit;
  const x0 = system ? Math.max(0, system.x0 - margin) : 0;
  const x1 = system ? Math.min(layout.width, system.x1 + margin) : layout.width;
  const y0 = system ? Math.max(0, system.top - 7 * unit) : 0;
  const y1 = system ? Math.min(layout.height, system.bottom + 8 * unit) : Math.min(layout.height, 300);
  const scale = width > 0 ? width / (x1 - x0) : 0;
  const box = system?.measures.find((mm) => mm.index === measure);
  return (
    <div className="strip" ref={ref} style={{ height: scale ? (y1 - y0) * scale : 80 }} onClick={onOpen} title="Open the whole photo">
      {scale > 0 && (
        <img src={reviewImageUrl(jobId)} alt="The printed page" draggable={false}
          style={{ width: layout.width * scale, left: -x0 * scale, top: -y0 * scale }} />
      )}
      {scale > 0 && box && (
        <div className="strip-box" style={{ left: (box.x0 - x0) * scale, width: (box.x1 - box.x0) * scale, top: (system!.top - 2 * unit - y0) * scale, height: (system!.bottom - system!.top + 4 * unit) * scale }} />
      )}
      {measure !== null && !system && <span className="muted strip-none">This measure is not located on the photo.</span>}
    </div>
  );
}

export function Lightbox({ jobId, onClose }: { jobId: string; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="lightbox" onClick={onClose} role="dialog" aria-label="The photo">
      <button className="close" onClick={onClose}>Close</button>
      <img src={reviewImageUrl(jobId)} alt="The uploaded photo" onClick={(e) => e.stopPropagation()} />
    </div>
  );
}

export type { EventKey };
