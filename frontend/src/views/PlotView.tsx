import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, api, type Project, type Vec3, type XY } from "../api/client";

/** Client pixels → SVG user units; 1:1 when the drawing is not CSS-scaled. */
export function userUnitsPerClientPx(viewBoxWidth: number, renderedWidth: number): number {
  return viewBoxWidth > 0 && renderedWidth > 0 ? viewBoxWidth / renderedWidth : 1;
}

/** The plot plan snaps to a 500 mm grid (spec F-05). Keyboard nudges move one
 *  grid cell for the same reason — finer steps would snap back to zero. */
export const PLOT_GRID_MM = 500;

/** Pure: the grid crossing closest to v. */
export function snapToGrid(v: number, grid: number = PLOT_GRID_MM): number {
  return Math.round(v / grid) * grid;
}

/** Pure: where a dragged equipment's stored origin lands. The plan view is a
 *  pure translate + y flip of model space (routes_plot.render_plot_svg: north
 *  up), so an SVG drag delta (dx, dy) maps exactly to model delta (dx, -dy);
 *  anchoring on the STORED origin means no geometry parsing and no offset
 *  guessing. x/y snap to the plot grid; the elevation is unchanged by a drag. */
export function plotAfterDrag(origin: Vec3, dxSvg: number, dySvg: number): Vec3 {
  return {
    x: snapToGrid(origin.x + dxSvg),
    y: snapToGrid(origin.y - dySvg), // SVG y grows downwards; north is up
    z: origin.z,
  };
}

/** Pure: where the equipment sits after setting its elevation (mm). */
export function plotAtElevation(origin: Vec3, z: number): Vec3 {
  return { x: origin.x, y: origin.y, z };
}

/** Mirrors the router's auto-placement (router_orthogonal._layout): a tag with
 *  no stored plot position sits at (12 000 mm · i, 0, 0), where i counts the
 *  UNPLACED equipment in P&ID order — and the P&ID builder emits equipment in
 *  flowsheet order, so the flowsheet's unit list is that order. First drags of
 *  never-placed equipment need this to compute an absolute PUT position. */
export function defaultPlotOrigins(units: Array<{ tag: string }>, stored: Record<string, Vec3>): Record<string, Vec3> {
  const SPACING_MM = 12_000;
  const out: Record<string, Vec3> = { ...stored };
  let unplaced = 0;
  for (const u of units) {
    if (stored[u.tag] !== undefined) continue;
    unplaced += 1;
    out[u.tag] = { x: SPACING_MM * unplaced, y: 0, z: 0 };
  }
  return out;
}

const NUDGE = PLOT_GRID_MM; // keyboard nudge step, SVG user units (mm)

type Drag = {
  tag: string;
  group: SVGGElement;
  startX: number;
  startY: number;
  scale: number;
  dx: number;
  dy: number;
};

function viewBoxWidth(svg: Element | null | undefined): number {
  const vb = (svg?.getAttribute("viewBox") ?? "").split(/\s+/).map(Number);
  return Number.isFinite(vb[2]) ? vb[2] : 0;
}

/** Pure: the placeable equipment element under a client point, if any — the
 *  smallest unit-tagged element containing the point wins. Routed lines are
 *  drawn OVER the footprints, so the element a pointer lands on is often a
 *  line polyline whose tagged group is not equipment; finding equipment needs
 *  coordinates, not the target (same pattern as the P&ID view). */
export function placeableTagAt(
  root: Element | null | undefined,
  unitTags: Set<string>,
  x: number,
  y: number,
): Element | null {
  let best: Element | null = null;
  let bestArea = Infinity;
  for (const el of root?.querySelectorAll<Element>("g[data-tag]") ?? []) {
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

/** Layer 5: the plot plan (top view). Drag an equipment footprint (or nudge
 *  with arrow keys) to move it; the drop PUTs the grid-snapped position and
 *  re-fetches the view — GET /api/views/plot.svg re-routes on every fetch
 *  (spec B-05), so the updated routing is visible without leaving the view.
 *  A Re-route button forces the same cycle explicitly; a per-equipment
 *  elevation input saves z. */
export function PlotView({ project }: { project: Project }) {
  const [svg, setSvg] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [routing, setRouting] = useState(false);
  const [unavailable, setUnavailable] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [placements, setPlacements] = useState<Record<string, Vec3>>(() =>
    defaultPlotOrigins(project.flowsheet.units, project.layout?.plot ?? {}),
  );
  const containerRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<Drag | null>(null);
  // Drag feedback transforms the live <g>; keep a ref to roll back on failure
  // even though a re-render has replaced the DOM node.
  const draggedRef = useRef<SVGGElement | null>(null);

  const unitTags = useMemo(() => new Set(project.flowsheet.units.map((u) => u.tag)), [project]);

  const load = useCallback(async () => {
    setLoading(true);
    setUnavailable(false);
    setError(null);
    try {
      setSvg(await api.plotSvg());
    } catch (e) {
      if (e instanceof ApiError && e.status === 501) setUnavailable(true);
      else setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => void load(), [load]);

  /** Place an equipment item and re-render: the PUT persists the position and
   *  the re-fetch re-routes server-side, so the fresh routing shows up here.
   *  Returns whether the save succeeded so callers can roll back visuals. */
  const savePlacement = useCallback(async (tag: string, pos: Vec3): Promise<boolean> => {
    setSaving(true);
    setUnavailable(false);
    setError(null);
    try {
      const layout = await api.placePlot(tag, pos);
      setPlacements((prev) => ({ ...prev, ...layout.plot }));
      setSvg(await api.plotSvg()); // re-render from the re-routed plan
      return true;
    } catch (e) {
      if (e instanceof ApiError && e.status === 501) setUnavailable(true);
      else setError(e instanceof Error ? e.message : String(e));
      return false;
    } finally {
      setSaving(false);
    }
  }, []);

  /** Explicit re-route: POST /api/route (surfaces routing failures as alerts)
   *  then refresh the plan, which re-renders the new routing. */
  const reroute = useCallback(async () => {
    setRouting(true);
    setUnavailable(false);
    setError(null);
    try {
      await api.route();
      setSvg(await api.plotSvg());
    } catch (e) {
      if (e instanceof ApiError && e.status === 501) setUnavailable(true);
      else setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRouting(false);
    }
  }, []);

  // Drag is pointer-event delegation on the injected SVG: visual feedback via
  // a transform on the dragged <g data-tag>, persistence on release. Only
  // equipment moves; line groups are tagged too but stay put — mirroring the
  // backend, which applies layout.plot to equipment only.
  function onPointerDown(e: React.PointerEvent<HTMLDivElement>): void {
    if (saving || routing || e.button > 0) return;
    // Hit-test coordinates: routed lines draw over the footprints, so the
    // event target is often a line polyline, not the equipment underneath.
    const group = placeableTagAt(containerRef.current, unitTags, e.clientX, e.clientY) as SVGGElement | null;
    const tag = group?.getAttribute("data-tag") ?? "";
    if (!group || !tag) return;
    setSelected(tag);
    const svgEl = containerRef.current?.querySelector("svg");
    dragRef.current = {
      tag,
      group,
      startX: e.clientX,
      startY: e.clientY,
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
    draggedRef.current = d.group;
  }

  async function onPointerUp(): Promise<void> {
    const d = dragRef.current;
    if (!d) return;
    dragRef.current = null;
    const origin = placements[d.tag];
    if (!origin) return; // never rendered from a stored layout: nothing to anchor
    const pos = plotAfterDrag(origin, d.dx, d.dy);
    const ok = await savePlacement(d.tag, pos);
    // The visual position holds until the re-fetch replaces the DOM; roll it
    // back only when the save failed and no re-routed plan is coming.
    if (!ok) draggedRef.current?.removeAttribute("transform");
  }

  const saveElevation = useCallback(
    (tag: string, z: number): void => {
      const origin = placements[tag];
      if (!origin || !Number.isFinite(z)) return;
      void savePlacement(tag, plotAtElevation(origin, z));
    },
    [placements, savePlacement],
  );

  // Keyboard access: equipment is focusable and arrow keys nudge it one grid
  // cell, saving the same way a drag does. Re-runs whenever the plan changes.
  useEffect(() => {
    const root = containerRef.current;
    if (!root || !svg) return;
    const groups = Array.from(root.querySelectorAll<SVGGElement>("g[data-tag]")).filter((g) =>
      unitTags.has(g.getAttribute("data-tag") ?? ""),
    );
    const cleanups: Array<() => void> = [];
    for (const g of groups) {
      const tag = g.getAttribute("data-tag") ?? "";
      g.setAttribute("tabindex", "0");
      g.setAttribute("role", "button");
      g.setAttribute("aria-label", `Equipment ${tag}: move with arrow keys, the routing updates`);
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
        setSelected(tag);
        const origin = placements[tag];
        if (!origin) return;
        // A nudge is already grid-sized; the snap keeps it exact anyway.
        void savePlacement(tag, plotAfterDrag(origin, step.x, step.y));
      };
      g.addEventListener("keydown", onKey);
      cleanups.push(() => g.removeEventListener("keydown", onKey));
    }
    return () => cleanups.forEach((fn) => fn());
  }, [svg, unitTags, savePlacement, placements]);

  const selectedOrigin = selected ? placements[selected] : undefined;
  const busy = loading || saving || routing;

  return (
    <div>
      <div className="toolbar">
        <button
          type="button"
          aria-label="Re-route plot"
          disabled={busy}
          onClick={() => void reroute()}
        >
          {routing ? "Routing…" : "Re-route"}
        </button>
        <button
          type="button"
          aria-label="Refresh plot"
          disabled={busy}
          onClick={() => void load()}
        >
          {loading ? "Loading…" : "Refresh"}
        </button>
        {saving && <span role="status">Saving position…</span>}
        {selected && selectedOrigin && (
          <label className="field">
            Elevation of {selected} (mm)
            <input
              type="number"
              aria-label={`Elevation of ${selected} in mm`}
              value={selectedOrigin.z}
              step={PLOT_GRID_MM}
              onChange={(e) => saveElevation(selected, e.target.valueAsNumber)}
            />
          </label>
        )}
        <span role="status" className="muted">
          {PLOT_GRID_MM} mm grid
        </span>
      </div>
      {loading && !svg && <p>Loading plot plan…</p>}
      {unavailable && <p role="alert">Plot routing not available yet</p>}
      {error && <p role="alert">Plot plan failed: {error}</p>}
      <div
        ref={containerRef}
        className="pfd plot"
        // SVG comes from our own backend renderer; data-tag groups drive drag.
        dangerouslySetInnerHTML={svg ? { __html: svg } : undefined}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={() => void onPointerUp()}
      />
    </div>
  );
}
