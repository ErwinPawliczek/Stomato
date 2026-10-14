import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, api, type Project, type XY } from "../api/client";

/** Client pixels → SVG user units; 1:1 when the drawing is not CSS-scaled. */
export function userUnitsPerClientPx(viewBoxWidth: number, renderedWidth: number): number {
  return viewBoxWidth > 0 && renderedWidth > 0 ? viewBoxWidth / renderedWidth : 1;
}

/** Pure: where the unit box's centre lands after dragging delta from original. */
export function placedCenter(original: XY, delta: XY): XY {
  return { x: original.x + delta.x, y: original.y + delta.y };
}

const NUDGE = 10; // keyboard nudge step, SVG user units

type Drag = {
  tag: string;
  group: SVGGElement;
  startX: number;
  startY: number;
  centre: XY; // bbox centre before the drag (the SVG-space position the backend stores)
  scale: number;
  dx: number;
  dy: number;
};

function bboxCentre(g: SVGGElement): XY {
  const b = g.getBBox();
  return { x: b.x + b.width / 2, y: b.y + b.height / 2 };
}

function viewBoxWidth(svg: Element | null | undefined): number {
  const vb = (svg?.getAttribute("viewBox") ?? "").split(/\s+/).map(Number);
  return Number.isFinite(vb[2]) ? vb[2] : 0;
}

/** Layer 3: the PFD. Drag a unit (or nudge with arrow keys) to place it; the
 *  position goes to the layout API and the SVG is re-fetched from the response
 *  so what you see is what the backend rendered from the stored placement. */
export function PfdView({ project }: { project: Project }) {
  const [svg, setSvg] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [unavailable, setUnavailable] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<Drag | null>(null);

  const unitTags = useMemo(() => new Set(project.flowsheet.units.map((u) => u.tag)), [project]);

  const load = useCallback(async () => {
    setLoading(true);
    setUnavailable(false);
    setError(null);
    try {
      setSvg(await api.pfdSvg());
    } catch (e) {
      if (e instanceof ApiError && e.status === 501) setUnavailable(true);
      else setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => void load(), [load]);

  /** Place a unit and re-render from the backend's response. Returns whether
   *  the save succeeded so callers can roll back optimistic visuals. */
  const savePlacement = useCallback(async (tag: string, centre: XY): Promise<boolean> => {
    setSaving(true);
    setUnavailable(false);
    setError(null);
    try {
      await api.place("pfd", tag, centre);
      setSvg(await api.pfdSvg()); // re-render from the backend's response
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
  // transform on the dragged <g data-tag>, persistence on release.
  function onPointerDown(e: React.PointerEvent<HTMLDivElement>): void {
    if (saving || e.button > 0) return;
    const group = (e.target as Element | null)?.closest("g[data-tag]") as SVGGElement | null;
    const tag = group?.getAttribute("data-tag") ?? "";
    // Only units are placeable; stream groups are tagged too but stay put.
    if (!group || !tag || !unitTags.has(tag)) return;
    // getBBox is missing outside real browsers; tests polyfill it. Without a
    // bbox centre we cannot compute the stored position, so don't drag at all.
    if (typeof group.getBBox !== "function") return;
    const svgEl = containerRef.current?.querySelector("svg");
    dragRef.current = {
      tag,
      group,
      startX: e.clientX,
      startY: e.clientY,
      centre: bboxCentre(group),
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
    const centre = placedCenter(d.centre, { x: d.dx, y: d.dy });
    const ok = await savePlacement(d.tag, centre);
    // The visual position holds until the re-fetch replaces the DOM; roll it
    // back only when the save failed and no fresh SVG is coming.
    if (!ok) d.group.removeAttribute("transform");
  }

  // Keyboard access: units are focusable and arrow keys nudge them, saving the
  // same way a drag does. Re-runs whenever the injected SVG is replaced.
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
      g.setAttribute("aria-label", `Unit ${tag}: move with arrow keys, position is saved`);
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
        void savePlacement(tag, placedCenter(bboxCentre(g), step));
      };
      g.addEventListener("keydown", onKey);
      cleanups.push(() => g.removeEventListener("keydown", onKey));
    }
    return () => cleanups.forEach((fn) => fn());
  }, [svg, unitTags, savePlacement]);

  return (
    <div>
      <div className="toolbar">
        <button
          type="button"
          aria-label="Refresh PFD"
          disabled={loading || saving}
          onClick={() => void load()}
        >
          {loading ? "Loading…" : "Refresh"}
        </button>
        {saving && <span role="status">Saving position…</span>}
      </div>
      {loading && !svg && <p>Loading PFD…</p>}
      {unavailable && <p role="alert">PFD renderer not available yet</p>}
      {error && <p role="alert">PFD failed: {error}</p>}
      <div
        ref={containerRef}
        className="pfd"
        // SVG comes from our own backend renderer; data-tag groups drive drag.
        dangerouslySetInnerHTML={svg ? { __html: svg } : undefined}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={() => void onPointerUp()}
      />
    </div>
  );
}
