/**
 * The other readings of a note (plan 0005): the print at the top, then one card per reading of its
 * measure — the measure engraved on its own with the changed note marked, what changed in words,
 * a listen and a Use. The list comes from `score/alternatives`, regenerated whenever the document
 * changes, so a second correction can follow the first without leaving the dialog.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { OpenSheetMusicDisplay } from "opensheetmusicdisplay";
import { loadScore } from "../score/beaming";
import type { Doubt } from "../api";
import { markNotes } from "../editor/sheet";
import { changeLine } from "../score/draft";
import type { EditorSession } from "../editor/session";
import type { Player } from "../player";
import { previewNotes, readings, type PreviewNote, type Reading } from "../score/alternatives";
import { find, nearest, parse, type EventKey } from "../score/xml";
import { fitZoom, MIN_READING_ZOOM } from "../score/readingFit";
import { Lightbox, PrintedStrip } from "./Editor";

const SHOWN = 6; // the rest of the list waits behind "More"

interface Card { id: string; xml: string; key: EventKey | null; label: string; note: string; fixes: boolean; reading: Reading | null }

/** The gap the pipeline padded this measure with, in quarters; the generator ranks the fixes by it. */
function paddedGap(doubts: Doubt[], measure: number): number | undefined {
  const d = doubts.find((x) => x.measure === measure && (x.kind === "padded" || x.kind === "pickup"));
  const raw = typeof d?.gap === "string" ? d.gap : null;   // a fraction ("5/2") or a decimal ("0.5")
  if (!raw) return undefined;
  const [n, q] = raw.split("/");
  const value = q === undefined ? Number(n) : Number(n) / Number(q);
  return Number.isFinite(value) && value > 0 ? value : undefined;
}

/** The width, in px, the engraved measure wants at the current zoom (OSMD units are 10 px at zoom 1). */
function naturalWidth(osmd: OpenSheetMusicDisplay, host: HTMLElement): number {
  let units = 0;
  try {
    for (const page of osmd.GraphicSheet.MusicPages) for (const sys of page.MusicSystems) units = Math.max(units, sys.PositionAndShape.Size.width);
  } catch { /* fall back to what the drawing says */ }
  if (units > 0) return units * 10 * osmd.Zoom;
  const svg = host.querySelector("svg");
  return svg ? Math.max(svg.scrollWidth, svg.getBoundingClientRect().width) : 0;
}

export function ReadingsDialog({ session, jobId, target, bpm, player, onApply, onClose }: {
  session: EditorSession; jobId: string; target: EventKey; bpm: number; player: Player;
  onApply: (r: Reading) => void; onClose: () => void;
}) {
  const [lightbox, setLightbox] = useState(false);
  const [more, setMore] = useState(false);
  const [playing, setPlaying] = useState<string | null>(null);
  const hosts = useRef<(HTMLDivElement | null)[]>([]);
  const engraved = useRef(new Map<string, OpenSheetMusicDisplay>());
  const [wide, setWide] = useState<Set<string>>(new Set());          // too wide to read in one column
  const [expanded, setExpanded] = useState<Set<string>>(new Set());  // tapped open: the dialog's width
  const expandedNow = useRef(expanded);

  // The event the dialog is about, followed across the edits made from it: gone means the note was
  // replaced (the nearest one of its measure takes over), a measure gone means there is nothing left.
  const key = useMemo(() => {
    if (!session.measures[target.measure]) return null;
    return find(session.measures, target)?.key ?? nearest(session.measures, target)?.key ?? null;
  }, [session.docVersion, target]); // eslint-disable-line react-hooks/exhaustive-deps

  const data = useMemo(() => (key ? readings(session.doc, key, { padGap: paddedGap(session.doubts, key.measure) }) : null),
    [session.docVersion, key]); // eslint-disable-line react-hooks/exhaustive-deps

  const cards: Card[] = useMemo(() => {
    if (!data || !key) return [];
    // A padded measure adds up only thanks to the rest the pipeline put in: the card says so.
    const padded = session.doubts.find((d) => d.measure === key.measure && (d.kind === "padded" || d.kind === "pickup"));
    const current: Card = {
      id: "current", xml: data.current.xml, key, reading: null,
      label: session.canUndo ? "As edited" : "As read", fixes: data.current.status === "ok" && !padded,
      note: data.current.note || (padded ? padded.text : data.current.status === "ok" ? "measure adds up" : ""),
    };
    const rest = (more ? data.list : data.list.slice(0, SHOWN)).map((r) => ({
      id: r.id, xml: r.xml, key: r.key, label: r.label, note: r.note, fixes: r.fixes, reading: r,
    }));
    return [current, ...rest];
  }, [data, key, more, session.canUndo, session.doubts]);

  useEffect(() => { if (!key) onClose(); }, [key, onClose]);

  // Escape and the backdrop leave; the photo, when it is open, takes Escape for itself.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape" && !lightbox) onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [lightbox, onClose]);

  useEffect(() => () => player.stopPreview(), [player]);

  // Engrave one card and fit it: shrunk so the whole measure shows, never below the readable zoom;
  // a card that still does not fit is flagged wide (it takes the full row). An expanded card keeps the
  // normal zoom and scrolls sideways when it is still wider than the dialog.
  const engrave = useMemo(() => async function (osmd: OpenSheetMusicDisplay, host: HTMLElement, card: Card, open: boolean) {
    const base = window.innerWidth < 600 ? 0.55 : 0.7;
    const draw = () => { osmd.render(); if (card.key) markNotes(osmd, [{ ...card.key, measure: 0 }]); };
    osmd.Zoom = base;
    await loadScore(osmd, card.xml);
    draw();
    if (open) return;
    const fit = (available: number) => fitZoom({ natural: naturalWidth(osmd, host), available, zoom: osmd.Zoom, minZoom: MIN_READING_ZOOM });
    let r = fit(host.clientWidth);
    if (r.zoom !== osmd.Zoom) { osmd.Zoom = r.zoom; draw(); }
    if (!r.fits) {
      setWide((w) => (w.has(card.id) ? w : new Set(w).add(card.id)));
      const row = host.closest(".cards")?.clientWidth ?? 0;            // the full row it now takes
      r = fit(row - 18);
      if (r.zoom !== osmd.Zoom) { osmd.Zoom = r.zoom; draw(); }
    }
  }, []);

  // One OSMD per card, engraved one after another so the page stays responsive, and dropped together
  // when the readings are generated again (which also forgets the cards that are gone).
  useEffect(() => {
    const made = engraved.current;
    let cancelled = false;
    const ids = new Set(cards.map((c) => c.id));
    setWide((w) => new Set([...w].filter((id) => ids.has(id))));
    if ([...expandedNow.current].some((id) => !ids.has(id))) {
      expandedNow.current = new Set([...expandedNow.current].filter((id) => ids.has(id)));
      setExpanded(expandedNow.current);
    }
    void (async () => {
      for (let i = 0; i < cards.length; i++) {
        const host = hosts.current[i];
        if (cancelled) return;
        if (!host) continue;
        const osmd = new OpenSheetMusicDisplay(host, {
          autoResize: false, drawTitle: false, drawPartNames: false, drawingParameters: "compacttight",
          followCursor: false, drawMeasureNumbers: false,
        });
        made.set(cards[i].id, osmd);
        try {
          await engrave(osmd, host, cards[i], expandedNow.current.has(cards[i].id));
        } catch {
          host.textContent = "This reading could not be engraved.";
        }
      }
    })();
    return () => {
      cancelled = true;
      for (const osmd of made.values()) { try { osmd.clear(); } catch { /* its card is already off the page */ } }
      made.clear();
      for (let i = 0; i < cards.length; i++) hosts.current[i]?.replaceChildren();
    };
  }, [cards, engrave]);

  // Tapping a card re-engraves that card alone, at the width its new state gives it.
  const toggle = (card: Card, i: number) => {
    const open = !expandedNow.current.has(card.id);
    const next = new Set(expandedNow.current);
    if (open) next.add(card.id); else next.delete(card.id);
    expandedNow.current = next;
    setExpanded(next);
    const host = hosts.current[i];
    const osmd = engraved.current.get(card.id);
    if (!host || !osmd) return;
    requestAnimationFrame(() => { void engrave(osmd, host, card, open).catch(() => { /* keeps what it had */ }); });
  };

  if (!key || !data) return null;
  const measure = key.measure;
  const fromModel = session.modelReadingsAt(measure);

  /** The previous measure as a run-up, then this reading of the measure, with the accompaniment. */
  async function play(card: Card): Promise<void> {
    if (playing === card.id) { player.stopPreview(); return; }
    const notes: PreviewNote[] = [];
    const accomp: { measure: number; at: number }[] = [];
    let at = 0;
    if (measure > 0) {
      const before = previewNotes(session.doc, measure - 1, measure - 1);
      notes.push(...before.notes);
      at = before.lengths[0] ?? 0;
      accomp.push({ measure: measure - 1, at: 0 });
    }
    try {
      const here = previewNotes(parse(card.xml), 0, 0);
      for (const n of here.notes) notes.push({ ...n, time: n.time + at });
    } catch { /* an excerpt that will not parse: the run-up alone still says where we are */ }
    accomp.push({ measure, at });
    setPlaying(card.id);
    player.setBpm(bpm);
    await player.preview(notes, accomp);
    setPlaying((p) => (p === card.id ? null : p));
  }

  return (
    <div className="readings" role="dialog" aria-label={`Other readings of measure ${measure + 1}`}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="panel">
        <div className="head">
          <h2>Other readings of measure {measure + 1}</h2>
          {session.canUndo && <button className="quiet" onClick={() => session.undo()} title="Undo the last change (Ctrl+Z)">Undo</button>}
          <button className="quiet" onClick={onClose}>Close</button>
        </div>
        <p className="muted">The recognition may have misread a note here. Compare each reading with the print, listen, and use the one that matches.</p>
        {session.layout && session.hasImage && (
          <PrintedStrip jobId={jobId} layout={session.layout} measure={measure} zoom="measure" onOpen={() => setLightbox(true)} />
        )}
        <div className="cards">
          {cards.map((card, i) => (
            <div key={card.id + ":" + session.docVersion}
              className={"reading" + (card.reading ? "" : " current") + (wide.has(card.id) || expanded.has(card.id) ? " wide" : "") + (expanded.has(card.id) ? " open" : "")}>
              <div className="mini" ref={(el) => { hosts.current[i] = el; }} onClick={() => toggle(card, i)}
                title={expanded.has(card.id) ? "Tap to shrink" : "Tap to enlarge"} />
              <div className="row"><strong>{card.label}</strong></div>
              {card.note && <div className="row"><span className={card.fixes ? "fixes" : "muted"}>{card.note}</span></div>}
              <div className="row">
                <button className="quiet" onClick={() => void play(card)} title="Play the measure before it and this reading">
                  {playing === card.id ? "■ Stop" : "▶ Play"}
                </button>
                {card.reading && <button className="primary" onClick={() => onApply(card.reading!)} title="Read the measure this way">Use</button>}
              </div>
            </div>
          ))}
        </div>
        {fromModel.length > 0 && (
          <div className="model-readings">
            <h3>From the model</h3>
            {fromModel.map((r) => (
              <div key={r.id} className="reading model">
                <div className="row"><strong>model</strong> <span className="muted">{r.route === "api" ? r.model : r.route}</span></div>
                <div className="row"><span>{changeLine(r)}</span></div>
                <div className="row">
                  <button className="primary" onClick={() => session.acceptModelReading(r.id)} title="Write this syllable under the note">Use</button>
                  <button className="quiet" onClick={() => void session.rejectModelReading(r.id)} title="Hide this reading; it stays on file">Reject</button>
                </div>
              </div>
            ))}
          </div>
        )}
        {!more && data.list.length > SHOWN && (
          <button className="quiet" onClick={() => setMore(true)}>More ({data.list.length - SHOWN} other{data.list.length - SHOWN > 1 ? "s" : ""})</button>
        )}
        {data.list.length === 0 && <p className="muted">No other reading of this measure to compare; correct it with the toolbar.</p>}
      </div>
      {lightbox && <Lightbox jobId={jobId} onClose={() => setLightbox(false)} />}
    </div>
  );
}
