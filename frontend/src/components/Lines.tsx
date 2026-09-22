/**
 * The Lines panel (plan 0011, step 6): which instrument each staff of the page plays, and which
 * staff goes on playing a stretch of measures underneath the form.
 *
 * It is built like the form panel and wears its clothes — a summary line that says what you would
 * hear, and a body that opens when you want to change it. Everything here is playback: nothing it
 * writes touches the document, and a page where it is never opened sounds exactly as it always has,
 * which is a piano.
 */
import { useState } from "react";
import type { Line } from "../lines";
import { VOICES, outsideRange, voiceSet, type Voicing } from "../voices";
import type { Under } from "../form";

interface Range { low: number; high: number }

function Picker({ value, onChange, range, id }: { value: string; onChange: (v: string) => void; range: Range | null; id?: string }) {
  const set = voiceSet(value);
  const under = range ? outsideRange(set, range.low) : 0;
  const over = range ? outsideRange(set, range.high) : 0;
  return (
    <>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)} aria-label="Instrument">
        {VOICES.map((v) => <option key={v.id} value={v.id}>{v.label}</option>)}
      </select>
      {(under > 0 || over > 0) && (
        <span className="muted" title={`This line goes outside the range ${set.label.toLowerCase()} samples cover; the notes outside it are stretched from the nearest sample and sound duller.`}>
          {under > 0 ? `${under} semitone${under > 1 ? "s" : ""} below its range` : `${over} semitone${over > 1 ? "s" : ""} above its range`}
        </span>
      )}
    </>
  );
}

/** What the head says: the instruments in play, and what goes on underneath. */
function summarize(lines: Line[], voicings: Voicing[], unders: Under[]): string {
  const said = lines.map((line) => {
    const mine = voicings.filter((v) => v.line === line.index);
    if (mine.length === 0) return `${line.name}: piano`;
    const names = [...new Set(mine.map((v) => voiceSet(v.instrument).label.toLowerCase()))];
    return `${line.name}: ${names.join(", then ")}`;
  });
  for (const under of unders) {
    const line = lines.find((l) => l.index === under.line);
    said.push(`${voiceSet(under.instrument).label.toLowerCase()} goes on under m. ${under.startAt + 1}${line ? ` (${line.name})` : ""}`);
  }
  return said.join(" · ");
}

export function LinesPanel({ lines, voicings, unders, measureCount, rangeOf, heard, onHeard, onChange }: {
  lines: Line[];
  voicings: Voicing[];
  unders: Under[];
  measureCount: number;
  rangeOf: (line: number) => Range | null;
  heard: (line: number) => boolean;
  onHeard: (line: number, on: boolean) => void;
  onChange: (voicings: Voicing[], unders: Under[]) => void;
}) {
  const [open, setOpen] = useState(false);
  if (lines.length === 0 || measureCount === 0) return null;
  const last = measureCount - 1;

  const forLine = (line: number) => voicings.filter((v) => v.line === line).sort((a, b) => a.from - b.from);
  const replace = (line: number, list: Voicing[]) => onChange([...voicings.filter((v) => v.line !== line), ...list], unders);
  const setRange = (line: number, i: number, patch: Partial<Voicing>) => {
    const list = forLine(line).map((v, k) => (k === i ? { ...v, ...patch } : v));
    const v = list[i];
    v.from = Math.max(0, Math.min(v.from, last));
    v.to = Math.max(v.from, Math.min(v.to, last));
    replace(line, list);
  };
  /** The first choice for a line writes one range over the whole page; the next splits the last one. */
  const split = (line: number) => {
    const list = forLine(line);
    const previous = list[list.length - 1];
    if (!previous) return replace(line, [{ line, from: 0, to: last, instrument: "piano" }]);
    const at = Math.min(previous.to, Math.max(previous.from + 1, Math.floor((previous.from + previous.to) / 2) + 1));
    if (at > previous.to) return;
    replace(line, [...list.slice(0, -1), { ...previous, to: at - 1 }, { line, from: at, to: previous.to, instrument: previous.instrument }]);
  };
  const addUnder = () => onChange(voicings, [...unders, {
    line: lines[0].index, from: 0, to: Math.min(7, last), startAt: Math.min(8, last), instrument: "flute",
  }]);
  const setUnder = (i: number, patch: Partial<Under>) => {
    const list = unders.map((u, k) => (k === i ? { ...u, ...patch } : u));
    const u = list[i];
    u.from = Math.max(0, Math.min(u.from, last));
    u.to = Math.max(u.from, Math.min(u.to, last));
    u.startAt = Math.max(0, Math.min(u.startAt, last));
    onChange(voicings, list);
  };

  return (
    <div className={"form lines" + (open ? " open" : "")}>
      <div className="form-head">
        <span className="label">Played on</span>
        <span className="summary"><span className="pass">{summarize(lines, voicings, unders)}</span></span>
        <button className="quiet" onClick={() => setOpen(!open)}>{open ? "Close" : "Change"}</button>
      </div>
      {open && (
        <div className="form-body">
          {lines.map((line) => {
            const list = forLine(line.index);
            const range = rangeOf(line.index);
            return (
              <div className="row" key={line.index}>
                <label title="Switch this line off to hear the others alone; it stays on the sheet and under the cursor.">
                  <input type="checkbox" checked={heard(line.index)} onChange={(e) => onHeard(line.index, e.target.checked)} />
                  {line.name}
                </label>
                {list.length === 0 && (
                  <span className="section">
                    <span className="muted">whole page</span>
                    <Picker value="piano" range={range} onChange={(id) => replace(line.index, [{ line: line.index, from: 0, to: last, instrument: id }])} />
                  </span>
                )}
                {list.map((v, i) => (
                  <span className="section" key={i}>
                    <label>m. <input type="number" min={1} max={measureCount} value={v.from + 1}
                      onChange={(e) => setRange(line.index, i, { from: Number(e.target.value) - 1 })} /></label>
                    <label>to <input type="number" min={1} max={measureCount} value={v.to + 1}
                      onChange={(e) => setRange(line.index, i, { to: Number(e.target.value) - 1 })} /></label>
                    <Picker value={v.instrument} range={range} onChange={(id) => setRange(line.index, i, { instrument: id })} />
                    {list.length > 1 && (
                      <button className="quiet" title="Remove this range" onClick={() => replace(line.index, list.filter((_, k) => k !== i))}>×</button>
                    )}
                  </span>
                ))}
                <button className="quiet" onClick={() => split(line.index)}
                  title="The same line can change instrument part way down the page: a staff printed as a flute for eight measures and sung after it.">
                  + change at a measure
                </button>
              </div>
            );
          })}
          <div className="row">
            <span className="label">Goes on underneath</span>
            {unders.length === 0 && <span className="muted">nothing; the page plays as it is written.</span>}
            <button className="quiet" onClick={addUnder}>+ a line that goes on playing</button>
          </div>
          {unders.map((u, i) => (
            <div className="row" key={i}>
              <span className="section">
                <select value={u.line} onChange={(e) => setUnder(i, { line: Number(e.target.value) })} aria-label="Line">
                  {lines.map((l) => <option key={l.index} value={l.index}>{l.name}</option>)}
                </select>
                <span className="muted">goes on playing</span>
                <label>m. <input type="number" min={1} max={measureCount} value={u.from + 1} onChange={(e) => setUnder(i, { from: Number(e.target.value) - 1 })} /></label>
                <label>to <input type="number" min={1} max={measureCount} value={u.to + 1} onChange={(e) => setUnder(i, { to: Number(e.target.value) - 1 })} /></label>
                <label title="Where it starts on the timeline: the first time the form reaches this measure.">from m. <input type="number" min={1} max={measureCount} value={u.startAt + 1}
                  onChange={(e) => setUnder(i, { startAt: Number(e.target.value) - 1 })} /></label>
                <Picker value={u.instrument} range={rangeOf(u.line)} onChange={(id) => setUnder(i, { instrument: id })} />
                <button className="quiet" title="Remove" onClick={() => onChange(voicings, unders.filter((_, k) => k !== i))}>×</button>
              </span>
              <span className="muted">
                It repeats to the end of the form, and a practice loop replays whatever falls in its window.
              </span>
            </div>
          ))}
          <div className="row">
            <span className="muted">
              Sounds: Salamander Grand Piano (Alexander Holm) and the tonejs-instruments sample sets, both CC-BY 3.0.
              A set is fetched the first time you choose it.
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
