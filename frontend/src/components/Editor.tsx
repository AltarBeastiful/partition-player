import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { reviewImageUrl, type Form, type Layout } from "../api";
import { MAX_TIMES, describePasses, formFromPasses, parseForm, preset, type FormPass, type Pass } from "../form";
import { TYPES, hasRepeat, tiedToNext, typeOf, type DurationType } from "../score/edit";
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
export function Toolbar({ session, c, onPlayFrom, onReadings, onRevert, onReload, onDone, staves }: {
  session: EditorSession; c: Commands; onPlayFrom: (measure: number) => void; onReadings: () => void;
  onRevert: () => void; onReload: () => void; onDone: () => void; staves: number;
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
        <button onClick={onReadings} disabled={!ev} title="Other readings of this note (o)">Other readings</button>
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
          <span className="label">Repeat</span>
          <button className={m && hasRepeat(m.el, "forward") ? "on" : ""} onClick={() => c.repeat("forward")} disabled={!m} title="Repeat sign at the start of this measure (play from here again)">𝄆 from here</button>
          <button className={m && hasRepeat(m.el, "backward") ? "on" : ""} onClick={() => c.repeat("backward")} disabled={!m} title="Repeat sign at the end of this measure (go back from here)">𝄇 back here</button>
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

/**
 * The strip of the photo the selected measure was read from, the measure framed. "measure" zoom
 * crops to the measure with one measure of print on each side, for a close comparison (plan 0005).
 */
export function PrintedStrip({ jobId, layout, measure, zoom = "system", onOpen }: {
  jobId: string; layout: Layout; measure: number | null; zoom?: "system" | "measure"; onOpen: () => void;
}) {
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
  const box = system?.measures.find((mm) => mm.index === measure);
  // A close crop spans three measure widths, never less than a system's worth of print, so a lone
  // half note at the end of a line is not blown up to the size of the screen.
  const span = zoom === "measure" && box ? Math.max(3 * (box.x1 - box.x0), 36 * unit) : 0;
  const cx = box ? (box.x0 + box.x1) / 2 : 0;
  const x0 = span ? Math.max(0, cx - span / 2) : system ? Math.max(0, system.x0 - margin) : 0;
  const x1 = span ? Math.min(layout.width, cx + span / 2) : system ? Math.min(layout.width, system.x1 + margin) : layout.width;
  const y0 = system ? Math.max(0, system.top - 7 * unit) : 0;
  const y1 = system ? Math.min(layout.height, system.bottom + 8 * unit) : Math.min(layout.height, 300);
  const scale = width > 0 ? width / (x1 - x0) : 0;
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

/**
 * How the page is played (plan 0004): the pass list in words, and a panel to change it: presets,
 * sections over measure ranges, the passes in order with a verse each.
 */
/** A section that begins and ends on the same beat of the same measure would never be heard. */
function nothingIn(s: { from: number; to: number; fromOnset?: number; toOnset?: number }): boolean {
  return s.from === s.to && s.toOnset !== undefined && s.toOnset <= (s.fromOnset ?? 0) + 1e-9;
}

/** An onset in whole notes as the beat a musician counts: quarters, or eighths in a compound meter. */
function beatOf(onset: number, unit = 0.25): number {
  const beat = onset / unit + 1;
  return Math.round(beat * 10) / 10;
}

export function FormPanel({ form, passes, printed, measureCount, verseCount, currentPass, onChange, cursorAt, onOpen }: {
  form: Form | null; passes: Pass[]; printed: Pass[]; measureCount: number; verseCount: number; currentPass: number | null;
  onChange: (form: Form | null, coalesce?: string) => void;
  /** Where the cursor stands on the sheet, for the edges taken from it (plan 0007, step 5). */
  cursorAt?: () => { measure: number; onset: number; beat: number } | null;
  /** The page draws the section bands while the panel is open. */
  onOpen?: (open: boolean) => void;
}) {
  const [open, setOpen] = useState(false);
  const [verses, setVerses] = useState(verseCount);
  const [twice, setTwice] = useState(false);
  const [selected, setSelected] = useState<number | null>(null);  // the chip a new pass lands after
  const [line, setLine] = useState<string | null>(null);          // the form being typed as one line
  const [lineError, setLineError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);          // what just happened, in one line
  useEffect(() => { setVerses(verseCount); }, [verseCount]);
  const summary = describePasses(passes, form);
  const current = form ?? formFromPasses(printed, measureCount);
  // `coalesce` names the field being typed in, so a run of keystrokes in it is one undo step
  // (plan 0007, step 1); a structural change passes nothing and gets its own step.
  const update = (f: Form, coalesce?: string) => onChange(f, coalesce);
  const setSection = (i: number, patch: Partial<Form["sections"][number]>, coalesce?: string) => {
    const sections = current.sections.map((s, k) => (k === i ? { ...s, ...patch } : s));
    const sec = sections[i];
    sec.from = Math.max(0, Math.min(sec.from, measureCount - 1)); sec.to = Math.max(sec.from, Math.min(sec.to, measureCount - 1));
    if (nothingIn(sec)) { delete sec.fromOnset; delete sec.toOnset; } // the beats no longer make sense
    update({ ...current, sections }, coalesce);
  };
  /** "Starts here" / "ends here": the boundary is the note the cursor stands on, which belongs to
   *  the section that starts there. Clicking a note leads the playback to it, so the cursor is
   *  already where the ear says the chorus begins (plan 0007, step 5). */
  const edgeFromCursor = (i: number, edge: "from" | "to") => {
    const at = cursorAt?.();
    if (!at) { setNote("Click the note on the sheet where it starts, then press this again."); return; }
    const s = current.sections[i];
    const sections = current.sections.map((sec, k) => {
      if (k !== i) return sec;
      const next = { ...sec };
      if (edge === "from") { next.from = at.measure; if (at.onset > 0) next.fromOnset = at.onset; else delete next.fromOnset; }
      else { next.to = at.measure; if (at.onset > 0) next.toOnset = at.onset; else delete next.toOnset; }
      return next;
    });
    const sec = sections[i];
    if (sec.to < sec.from || nothingIn(sec)) {
      setNote(`“${s.name || "This section"}” would end where it starts, with nothing in it. Put the cursor on the other edge first.`);
      return;
    }
    setNote(`“${sec.name || "Section"}” ${edge === "from" ? "starts" : "ends"} at measure ${at.measure + 1}${at.onset > 0 ? `, beat ${at.beat}` : ""}.`);
    update({ ...current, sections });
  };
  const clearEdge = (i: number, edge: "from" | "to") => {
    setNote(null);
    update({ ...current, sections: current.sections.map((sec, k) => {
      if (k !== i) return sec;
      const next = { ...sec };
      if (edge === "from") delete next.fromOnset; else delete next.toOnset;
      return next;
    }) });
  };
  const removeSection = (i: number) => {
    update({ sections: current.sections.filter((_, k) => k !== i), passes: current.passes.filter((p) => p.section !== i).map((p) => ({ ...p, section: p.section > i ? p.section - 1 : p.section })) });
  };
  const addSection = () => {
    const last = current.sections[current.sections.length - 1];
    const from = last ? Math.min(last.to + 1, measureCount - 1) : 0;
    update({ ...current, sections: [...current.sections, { name: "Part " + String.fromCharCode(65 + current.sections.length), from, to: measureCount - 1 }] });
  };
  // A new pass lands after the chip last touched, not always at the end (plan 0007, step 4).
  const insertAt = (ps: FormPass[], pass: FormPass): FormPass[] => {
    const at = selected === null || selected >= ps.length ? ps.length : selected + 1;
    const out = [...ps.slice(0, at), pass, ...ps.slice(at)];
    setSelected(at);
    return out;
  };
  const addPass = (section: number) => {
    const before = current.passes.filter((p) => p.section === section);
    const verse = before.some((p) => p.verse !== null) ? Math.max(...before.map((p) => p.verse ?? 0)) + 1 : null;
    update({ ...current, passes: insertAt(current.passes, { section, verse }) });
  };
  const duplicatePass = (i: number) => {
    const p = current.passes[i];
    if (!p) return;
    setSelected(i);
    update({ ...current, passes: [...current.passes.slice(0, i + 1), { ...p }, ...current.passes.slice(i + 1)] });
    setSelected(i + 1);
  };
  const setPass = (i: number, verse: number | null) => update({ ...current, passes: current.passes.map((p, k) => (k === i ? { ...p, verse } : p)) }, `verse:${i}`);
  /** The chip's count goes 1, 2, 3, 4 and back to 1: a misclick is three clicks from undone, and a
   *  count past four (rare) is written in the line below (plan 0007, step 5). */
  const setTimes = (i: number, times: number) => {
    const n = times > 4 ? 1 : Math.max(1, Math.min(times, MAX_TIMES));
    update({ ...current, passes: current.passes.map((p, k) => (k === i ? (n === 1 ? { section: p.section, verse: p.verse } : { ...p, times: n }) : p)) });
  };
  const removePass = (i: number) => {
    setSelected(i > 0 ? i - 1 : null);
    update({ ...current, passes: current.passes.filter((_, k) => k !== i) });
  };
  const movePass = (i: number, d: -1 | 1) => {
    const ps = [...current.passes]; const j = i + d; if (j < 0 || j >= ps.length) return;
    [ps[i], ps[j]] = [ps[j], ps[i]]; setSelected(j); update({ ...current, passes: ps });
  };
  /** 1, 2, 3 … over the passes that carry a verse, in the order they are played. */
  const numberVerses = () => {
    let n = 0;
    update({ ...current, passes: current.passes.map((p) => (p.verse === null ? p : { ...p, verse: ++n })) });
  };
  const applyLine = () => {
    if (line === null) return;
    const read = parseForm(line, current.sections);
    if (read.passes === null) { setLineError(read.error); return; }
    setLineError(null);
    setLine(null);
    update({ ...current, passes: read.passes });
  };
  // `currentPass` counts the passes as they are played; a chip can stand for several (plan 0007).
  const chipOfPlayed: number[] = [];
  current.passes.forEach((p, i) => { for (let k = 0; k < Math.max(1, p.times ?? 1); k++) chipOfPlayed.push(i); });
  const nowChip = currentPass === null ? null : chipOfPlayed[currentPass] ?? null;
  return (
    <div className={"form" + (open ? " open" : "")}>
      <div className="form-head">
        <span className="label">Played as</span>
        <span className="summary">
          {summary.split(" · ").map((label, i) => passes.length > 0 && <span key={i} className={"pass" + (i === nowChip ? " now" : "")}>{label}</span>)}
          {passes.length === 0 && <span className="muted">once through</span>}
        </span>
        <span className="muted">{form ? "your form" : "from the repeat signs and the verses"}</span>
        <button className="quiet" onClick={() => { setOpen(!open); onOpen?.(!open); }}>{open ? "Close" : "Change"}</button>
      </div>
      {open && (
        <div className="form-body">
          <div className="row">
            <span className="label">Presets</span>
            <button onClick={() => onChange(null)} disabled={!form}>Automatic</button>
            <button onClick={() => update(preset("printed", printed, verses, measureCount))}>As printed</button>
            <button onClick={() => update(preset("verses", printed, verses, measureCount, { current: form }))}>Once per verse</button>
            <button onClick={() => update(preset("chorus", printed, verses, measureCount, { current: form, chorusTwice: twice }))}>Chorus after every verse</button>
            <label>verses <input type="number" min={1} max={20} value={verses} onChange={(e) => setVerses(Math.max(1, Math.min(20, Number(e.target.value) || 1)))} /></label>
            <label title="The chorus sung twice each time round"><input type="checkbox" checked={twice} onChange={(e) => setTwice(e.target.checked)} /> chorus twice</label>
          </div>
          <div className="row sections">
            <span className="label">Sections</span>
            {current.sections.map((s, i) => (
              <span key={i} className="section">
                <input className="name" value={s.name} maxLength={20} onChange={(e) => setSection(i, { name: e.target.value }, `name:${i}`)} aria-label="Section name" />
                <label>m. <input type="number" min={1} max={measureCount} value={s.from + 1} onChange={(e) => setSection(i, { from: Number(e.target.value) - 1 }, `from:${i}`)} /></label>
                {s.fromOnset ? <button className="quiet edge" onClick={() => clearEdge(i, "from")} title="From the start of the measure instead">beat {beatOf(s.fromOnset)} ×</button> : null}
                <label>to <input type="number" min={1} max={measureCount} value={s.to + 1} onChange={(e) => setSection(i, { to: Number(e.target.value) - 1 }, `to:${i}`)} /></label>
                {s.toOnset !== undefined ? <button className="quiet edge" onClick={() => clearEdge(i, "to")} title="To the end of the measure instead">before beat {beatOf(s.toOnset)} ×</button> : null}
                <button className="quiet" onClick={() => edgeFromCursor(i, "from")} title="Starts at the note the cursor is on — click that note on the sheet first">starts here</button>
                <button className="quiet" onClick={() => edgeFromCursor(i, "to")} title="Ends just before the note the cursor is on — that note belongs to the next section">ends here</button>
                <button className="quiet" onClick={() => addPass(i)} title="Add a pass through this section">+ pass</button>
                <button className="quiet" onClick={() => removeSection(i)} title="Remove this section" disabled={current.sections.length < 2}>×</button>
              </span>
            ))}
            <button className="quiet" onClick={addSection}>+ section</button>
          </div>
          <div className="row passes">
            <span className="label">Order</span>
            {current.passes.map((p, i) => (
              <span key={i} className={"chip" + (i === nowChip ? " now" : "") + (i === selected ? " picked" : "")} onClick={() => setSelected(i)}>
                <button className="quiet" onClick={() => movePass(i, -1)} disabled={i === 0} title="Earlier">‹</button>
                {current.sections[p.section]?.name || "?"}
                <input type="number" min={1} max={20} placeholder="–" value={p.verse ?? ""} title="The verse sung on this pass; empty for none"
                  onChange={(e) => setPass(i, e.target.value === "" ? null : Math.max(1, Math.min(20, Number(e.target.value))))} />
                <button className="quiet times" onClick={() => setTimes(i, (p.times ?? 1) + 1)} onContextMenu={(e) => { e.preventDefault(); setTimes(i, (p.times ?? 1) - 1); }}
                  title="How often this section is played here: click for once more, and after four times it goes back to once">×{p.times ?? 1}</button>
                <button className="quiet" onClick={() => duplicatePass(i)} title="One more pass through this section, here">+</button>
                <button className="quiet" onClick={() => movePass(i, 1)} disabled={i === current.passes.length - 1} title="Later">›</button>
                <button className="quiet" onClick={() => removePass(i)} title="Remove this pass">×</button>
              </span>
            ))}
            {current.passes.length === 0 && <span className="muted">no pass: nothing plays. Add one with "+ pass" on a section.</span>}
            {current.passes.some((p) => p.verse !== null) && <button className="quiet" onClick={numberVerses}>number the verses</button>}
          </div>
          <div className="row">
            <span className="label">In words</span>
            <input className="line" value={line ?? summary} spellCheck={false} aria-label="The form as one line"
              placeholder="Verse 1 · Chorus ×2 · Verse 2"
              onChange={(e) => { setLine(e.target.value); setLineError(null); }}
              onKeyDown={(e) => { if (e.key === "Enter") applyLine(); if (e.key === "Escape") { setLine(null); setLineError(null); } }} />
            <button onClick={applyLine} disabled={line === null}>Use it</button>
            {line !== null && <button className="quiet" onClick={() => { setLine(null); setLineError(null); }}>Cancel</button>}
          </div>
          {lineError && <div className="row error-text">{lineError}</div>}
          {note && !lineError && <div className="row muted">{note}</div>}
          <div className="muted">
            A pass plays its section once; ×2 plays it twice over. The verse number says which words are sung, the others are
            dimmed while it plays. Measure numbers are the printed ones. The line above names the sections in the order they
            are sung — a section's first letters are enough — and it cannot make a new section.
          </div>
        </div>
      )}
    </div>
  );
}

export type { EventKey };
