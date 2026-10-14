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
  el: Element; // the placeable element carrying data-tag
  transformEl: Element; // the group a visual drag transform applies to
  startX: number;
  startY: number;
  topLeft: XY; // bbox top-left before the drag (the SVG-space position the backend stores)
  scale: number;
  dx: number;
  dy: number;
};

function viewBoxWidth(svg: Element | null | undefined): number {
  const vb = (svg?.getAttribute("viewBox") ?? "").split(/\s+/).map(Number);
  return Number.isFinite(vb[2]) ? vb[2] : 0;
}

/** Client pixels → SVG user units; 1:1 when the drawing is not CSS-scaled. */
export function userUnitsPerClientPx(viewBoxWidth: number, renderedWidth: number): number {
  return viewBoxWidth > 0 && renderedWidth > 0 ? viewBoxWidth / renderedWidth : 1;
}

/** Pure: the placeable equipment element under a client point, if any — the
 *  smallest tagged box containing the point wins. The P&ID renderer tags
 *  equipment as an invisible .equipment-bbox rect that is a SIBLING of the
 *  symbol shapes inside a plain group, so no ancestor of the hit element
 *  carries the tag; finding equipment needs coordinates, not the target. */
export function placeableTagAt(
  root: Element | null | undefined,
  unitTags: Set<string>,
  x: number,
  y: number,
): Element | null {
  let best: Element | null = null;
  let bestArea = Infinity;
  for (const el of root?.querySelectorAll<Element>("[data-tag]") ?? []) {
    if (!unitTags.has(el.getAttribute("data-tag") ?? "")) continue;
    const r = el.getBoundingClientRect();
    if (x < r.left || x > r.right || y < r.top || y > r.bottom) continue;
    const area = r.width * r.height;
    if (area < bestArea) {
      best = el;
      bestArea = area;
    }
  }
  return best;
}

/** The position the backend stores for a placeable element: the bbox rect
 *  carries the top-left as absolute x/y attributes; a tagged group fallback
 *  (the PFD's structure) reports its own user-space bbox. */
export function storedTopLeft(el: Element): XY {
  if (el.classList.contains("equipment-bbox")) {
    return { x: Number(el.getAttribute("x") ?? 0), y: Number(el.getAttribute("y") ?? 0) };
  }
  const g = el as SVGGElement;
  if (typeof g.getBBox !== "function") return { x: 0, y: 0 };
  const b = g.getBBox();
  return { x: b.x, y: b.y };
}

/** The element a drag transform applies to: the bbox rect's parent group
 *  carries the symbol shapes and label, so shifting the group moves the
 *  whole equipment item; a tagged group transforms itself. */
function transformTarget(el: Element): Element {
  return el.classList.contains("equipment-bbox") ? (el.parentElement ?? el) : el;
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
  // transform on the dragged equipment's group, persistence on release. Only
  // equipment is placeable; lines, valves and instruments are tagged too but
  // stay put — mirroring the backend, which applies layout.pid to equipment.
  // The placeable element is found by hit-testing coordinates because the
  // P&ID renderer tags equipment with an invisible bbox rect sibling, not on
  // the symbol shapes a pointer lands on.
  function onPointerDown(e: React.PointerEvent<HTMLDivElement>): void {
    if (saving || e.button > 0) return;
    const el = placeableTagAt(pidRef.current, unitTags, e.clientX, e.clientY);
    const tag = el?.getAttribute("data-tag") ?? "";
    if (!el || !tag) return;
    const transformEl = transformTarget(el);
    const svgEl = pidRef.current?.querySelector("svg");
    dragRef.current = {
      tag,
      el,
      transformEl,
      startX: e.clientX,
      startY: e.clientY,
      topLeft: storedTopLeft(el),
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
    d.transformEl.setAttribute("transform", `translate(${d.dx} ${d.dy})`);
  }

  async function onPointerUp(): Promise<void> {
    const d = dragRef.current;
    if (!d) return;
    dragRef.current = null;
    const topLeft = placedTopLeft(d.topLeft, { x: d.dx, y: d.dy });
    const ok = await savePlacement(d.tag, topLeft);
    // The visual position holds until the re-fetch replaces the DOM; roll it
    // back only when the save failed and no fresh SVG is coming.
    if (!ok) d.transformEl.removeAttribute("transform");
  }

  // Keyboard access: equipment is focusable and arrow keys nudge it, saving
  // the same way a drag does. Re-runs whenever the injected SVG is replaced.
  useEffect(() => {
    const root = pidRef.current;
    if (!root || !pidSvg) return;
    const placeables = Array.from(root.querySelectorAll<Element>("[data-tag]")).filter((el) =>
      unitTags.has(el.getAttribute("data-tag") ?? ""),
    );
    const cleanups: Array<() => void> = [];
    for (const el of placeables) {
      const tag = el.getAttribute("data-tag") ?? "";
      el.setAttribute("tabindex", "0");
      el.setAttribute("role", "button");
      el.setAttribute("aria-label", `Equipment ${tag}: move with arrow keys, position is saved`);
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
        void savePlacement(tag, placedTopLeft(storedTopLeft(el), step));
      };
      el.addEventListener("keydown", onKey);
      cleanups.push(() => el.removeEventListener("keydown", onKey));
    }
    return () => cleanups.forEach((fn) => fn());
  }, [pidSvg, unitTags, savePlacement]);

  // Search highlighting: every element whose tag matches the query (in EITHER
  // drawing) gets .tag-hit. getAttribute already decodes entities, matching
  // the decoded inventory tags. Both tagging styles are covered: the PFD's
  // tagged groups and the P&ID's bbox rects.
  useEffect(() => {
    for (const ref of [pidRef, pfdRef]) {
      const root = ref.current;
      if (!root) continue;
      for (const el of root.querySelectorAll<Element>("[data-tag]")) {
        el.classList.toggle("tag-hit", matched.has(el.getAttribute("data-tag") ?? ""));
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
            // SVG comes from our own backend renderer; data-tag bbox rects drive drag.
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
