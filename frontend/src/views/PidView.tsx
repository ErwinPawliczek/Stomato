import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, api, type Project, type XY } from "../api/client";

/** Pure: where the equipment box's top-left corner lands after dragging delta
 *  from original. layout.pid stores the TOP-LEFT (spec B-04), unlike the PFD's
 *  box centre — hence a separate helper from PfdView's placedCenter. */
export function placedTopLeft(original: XY, delta: XY): XY {
  return { x: original.x + delta.x, y: original.y + delta.y };
}

const ENTITIES: Record<string, string> = {
  "&quot;": '"',
  "&apos;": "'",
  "&lt;": "<",
  "&gt;": ">",
  "&amp;": "&",
};

function decodeEntities(s: string): string {
  return s.replace(/&(?:quot|apos|lt|gt|amp);/g, (m) => ENTITIES[m] ?? m);
}

/** Pure: every data-tag value in an SVG document, in first-occurrence order.
 *  Works on the raw text so tests need no DOM; the backend HTML-escapes
 *  attribute values (line numbers like 8&quot;-PG-1001-B1), so decode them. */
export function extractTags(svg: string): string[] {
  const seen = new Set<string>();
  const tags: string[] = [];
  for (const m of svg.matchAll(/data-tag="([^"]*)"/g)) {
    const tag = decodeEntities(m[1]);
    if (tag && !seen.has(tag)) {
      seen.add(tag);
      tags.push(tag);
    }
  }
  return tags;
}

export type TagParityRow = { tag: string; inPfd: boolean; inPid: boolean };

/** Pure: the union of both diagrams' tags with per-diagram presence. Tags that
 *  appear in only ONE diagram (parity gaps) sort first — nothing can hide. */
export function tagParity(pfdSvg: string, pidSvg: string): TagParityRow[] {
  const pfd = new Set(extractTags(pfdSvg));
  const pid = new Set(extractTags(pidSvg));
  return [...new Set([...pfd, ...pid])]
    .map((tag) => ({ tag, inPfd: pfd.has(tag), inPid: pid.has(tag) }))
    .sort((a, b) => {
      const gapA = a.inPfd !== a.inPid ? 0 : 1;
      const gapB = b.inPfd !== b.inPid ? 0 : 1;
      return gapA - gapB || a.tag.localeCompare(b.tag);
    });
}

const NUDGE = 10; // keyboard nudge step, SVG user units

type Drag = {
  tag: string;
  group: SVGGElement;
  startX: number;
  startY: number;
  topLeft: XY; // bbox top-left before the drag (the SVG-space position the backend stores)
  scale: number;
  dx: number;
  dy: number;
};

function bboxTopLeft(g: SVGGElement): XY {
  const b = g.getBBox();
  return { x: b.x, y: b.y };
}

function viewBoxWidth(svg: Element | null | undefined): number {
  const vb = (svg?.getAttribute("viewBox") ?? "").split(/\s+/).map(Number);
  return Number.isFinite(vb[2]) ? vb[2] : 0;
}

/** Client pixels → SVG user units; 1:1 when the drawing is not CSS-scaled. */
export function userUnitsPerClientPx(viewBoxWidth: number, renderedWidth: number): number {
  return viewBoxWidth > 0 && renderedWidth > 0 ? viewBoxWidth / renderedWidth : 1;
}

/** Layer 4: the P&ID, shown alongside the PFD so every tag is findable in
 *  BOTH diagrams. Same placement machinery as the PFD (drag or arrow-key nudge
 *  → api.place → re-render from the backend's response), plus a search box and
 *  a shared tag inventory: one row per tag in either drawing with its presence
 *  in each, parity gaps first. */
export function PidView({ project }: { project: Project }) {
  const [pidSvg, setPidSvg] = useState<string | null>(null);
  const [pfdSvg, setPfdSvg] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [unavailable, setUnavailable] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const pidRef = useRef<HTMLDivElement>(null);
  const pfdRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<Drag | null>(null);

  const unitTags = useMemo(() => new Set(project.flowsheet.units.map((u) => u.tag)), [project]);

  const rows = useMemo(
    () => (pidSvg !== null && pfdSvg !== null ? tagParity(pfdSvg, pidSvg) : []),
    [pfdSvg, pidSvg],
  );

  const q = query.trim().toLowerCase();
  const matched = useMemo(
    () => new Set(q ? rows.filter((r) => r.tag.toLowerCase().includes(q)).map((r) => r.tag) : []),
    [rows, q],
  );
  const gapCount = rows.filter((r) => r.inPfd !== r.inPid).length;

  const load = useCallback(async () => {
    setLoading(true);
    setUnavailable(false);
    setError(null);
    try {
      const [pid, pfd] = await Promise.all([api.pidSvg(), api.pfdSvg()]);
      setPidSvg(pid);
      setPfdSvg(pfd);
    } catch (e) {
      if (e instanceof ApiError && e.status === 501) setUnavailable(true);
      else setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => void load(), [load]);

  /** Place a P&ID equipment item and re-render from the backend's response.
   *  Returns whether the save succeeded so callers can roll back visuals. */
  const savePlacement = useCallback(async (tag: string, topLeft: XY): Promise<boolean> => {
    setSaving(true);
    setUnavailable(false);
    setError(null);
    try {
      await api.place("pid", tag, topLeft);
      setPidSvg(await api.pidSvg()); // re-render from the backend's response
      return true;
    } catch (e) {
      if (e instanceof ApiError && e.status === 501) setUnavailable(true);
      else setError(e instanceof Error ? e.message : String(e));
      return false;
    } finally {
      setSaving(false);
    }
  }, []);

  // Drag is pointer-event delegation on the injected SVG: visual feedback via a
  // transform on the dragged <g data-tag>, persistence on release. Only
  // equipment is placeable; lines, valves and instruments are tagged too but
  // stay put — mirroring the backend, which applies layout.pid to equipment.
  function onPointerDown(e: React.PointerEvent<HTMLDivElement>): void {
    if (saving || e.button > 0) return;
    const group = (e.target as Element | null)?.closest("g[data-tag]") as SVGGElement | null;
    const tag = group?.getAttribute("data-tag") ?? "";
    if (!group || !tag || !unitTags.has(tag)) return;
    // getBBox is missing outside real browsers; tests polyfill it. Without a
    // bbox we cannot compute the stored position, so don't drag at all.
    if (typeof group.getBBox !== "function") return;
    const svgEl = pidRef.current?.querySelector("svg");
    dragRef.current = {
      tag,
      group,
      startX: e.clientX,
      startY: e.clientY,
      topLeft: bboxTopLeft(group),
      scale: userUnitsPerClientPx(viewBoxWidth(svgEl), svgEl?.clientWidth ?? 0),
      dx: 0,
      dy: 0,
    };
  }

  function onPointerMove(e: React.PointerEvent<HTMLDivElement>): void {
    const d = dragRef.current;
    if (!d) return;
    d.dx = (e.clientX - d.startX) * d.scale;
    d.dy = (e.clientY - d.startY) * d.scale;
    d.group.setAttribute("transform", `translate(${d.dx} ${d.dy})`);
  }

  async function onPointerUp(): Promise<void> {
    const d = dragRef.current;
    if (!d) return;
    dragRef.current = null;
    const topLeft = placedTopLeft(d.topLeft, { x: d.dx, y: d.dy });
    const ok = await savePlacement(d.tag, topLeft);
    // The visual position holds until the re-fetch replaces the DOM; roll it
    // back only when the save failed and no fresh SVG is coming.
    if (!ok) d.group.removeAttribute("transform");
  }

  // Keyboard access: equipment is focusable and arrow keys nudge it, saving
  // the same way a drag does. Re-runs whenever the injected SVG is replaced.
  useEffect(() => {
    const root = pidRef.current;
    if (!root || !pidSvg) return;
    const groups = Array.from(root.querySelectorAll<SVGGElement>("g[data-tag]")).filter((g) =>
      unitTags.has(g.getAttribute("data-tag") ?? ""),
    );
    const cleanups: Array<() => void> = [];
    for (const g of groups) {
      const tag = g.getAttribute("data-tag") ?? "";
      g.setAttribute("tabindex", "0");
      g.setAttribute("role", "button");
      g.setAttribute("aria-label", `Equipment ${tag}: move with arrow keys, position is saved`);
      const onKey = (ev: Event): void => {
        const ke = ev as KeyboardEvent;
        const step: XY | null =
          ke.key === "ArrowLeft"
            ? { x: -NUDGE, y: 0 }
            : ke.key === "ArrowRight"
              ? { x: NUDGE, y: 0 }
              : ke.key === "ArrowUp"
                ? { x: 0, y: -NUDGE }
                : ke.key === "ArrowDown"
                  ? { x: 0, y: NUDGE }
                  : null;
        if (!step) return;
        ev.preventDefault();
        void savePlacement(tag, placedTopLeft(bboxTopLeft(g), step));
      };
      g.addEventListener("keydown", onKey);
      cleanups.push(() => g.removeEventListener("keydown", onKey));
    }
    return () => cleanups.forEach((fn) => fn());
  }, [pidSvg, unitTags, savePlacement]);

  // Search highlighting: every element whose tag matches the query (in EITHER
  // drawing) gets .tag-hit. getAttribute already decodes entities, matching
  // the decoded inventory tags.
  useEffect(() => {
    for (const ref of [pidRef, pfdRef]) {
      const root = ref.current;
      if (!root) continue;
      for (const g of root.querySelectorAll<SVGGElement>("g[data-tag]")) {
        g.classList.toggle("tag-hit", matched.has(g.getAttribute("data-tag") ?? ""));
      }
    }
  }, [matched, pidSvg, pfdSvg]);

  return (
    <div>
      <div className="toolbar">
        <button
          type="button"
          aria-label="Refresh P&ID"
          disabled={loading || saving}
          onClick={() => void load()}
        >
          {loading ? "Loading…" : "Refresh"}
        </button>
        {saving && <span role="status">Saving position…</span>}
        <label className="field">
          Search tags
          <input
            type="search"
            aria-label="Search tags"
            value={query}
            placeholder="e.g. PSV"
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <span role="status" className="muted">
          {q
            ? `${matched.size} tag(s) match "${query.trim()}"`
            : `${rows.length} tags · ${gapCount} in only one diagram`}
        </span>
      </div>
      {loading && !pidSvg && <p>Loading P&amp;ID…</p>}
      {unavailable && <p role="alert">P&amp;ID renderer not available yet</p>}
      {error && <p role="alert">P&amp;ID failed: {error}</p>}
      <div className="pid-panels">
        <section>
          <h2>P&amp;ID</h2>
          <div
            ref={pidRef}
            className="pfd pid"
            // SVG comes from our own backend renderer; data-tag groups drive drag.
            dangerouslySetInnerHTML={pidSvg ? { __html: pidSvg } : undefined}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={() => void onPointerUp()}
          />
        </section>
        <section>
          <h2>PFD (reference)</h2>
          <div
            ref={pfdRef}
            className="pfd pid-readonly"
            // Read-only: placement happens on the PFD tab; here it is the
            // cross-check that makes every tag findable in both diagrams.
            dangerouslySetInnerHTML={pfdSvg ? { __html: pfdSvg } : undefined}
          />
        </section>
      </div>
      <h2>Tag inventory</h2>
      <p className="muted">
        Every tag in either drawing, gaps first. Select a tag to highlight it in both diagrams.
      </p>
      <ul className="tag-inventory">
        {rows.map((r) => (
          <li key={r.tag} className={matched.has(r.tag) ? "hit" : undefined}>
            <button type="button" aria-label={`Find tag ${r.tag}`} onClick={() => setQuery(r.tag)}>
              {r.tag}
            </button>
            <span className={"badge" + (r.inPfd ? " on" : " off")}>
              PFD{r.inPfd ? "" : " missing"}
            </span>
            <span className={"badge" + (r.inPid ? " on" : " off")}>
              P&amp;ID{r.inPid ? "" : " missing"}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
