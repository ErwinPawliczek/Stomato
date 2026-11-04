import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { XY } from "../api/client";
import { HEX_SIZE, hexPatternTile, snapToHex } from "../hexGrid";
import { UNIT_DND_TYPE } from "./UnitPalette";

export type CanvasUnit = { tag: string; kind: string; name: string; pos: XY };
export type CanvasLink = { id: string; from: string; to: string };

/** Pan/zoom state: world point at the top-left of the canvas, and px per world unit. */
export type View = { x: number; y: number; k: number };

const BOX_W = 132;
const BOX_H = 44;
export const MIN_K = 0.2;
export const MAX_K = 5;
const FALLBACK_SIZE = { w: 800, h: 480 };
const NUDGE = 10; // keyboard step with snapping off, world units

/** Client px → world units under the given view (canvas origin at rect.left/top). */
export function clientToWorld(view: View, rect: { left: number; top: number }, cx: number, cy: number): XY {
  return { x: view.x + (cx - rect.left) / view.k, y: view.y + (cy - rect.top) / view.k };
}

/** Zoom by `factor` keeping the world point under (px, py) canvas px fixed. */
export function zoomAt(view: View, factor: number, px: number, py: number): View {
  const k = Math.min(MAX_K, Math.max(MIN_K, view.k * factor));
  const wx = view.x + px / view.k;
  const wy = view.y + py / view.k;
  return { x: wx - px / k, y: wy - py / k, k };
}

/** View that frames every unit with a margin; 1:1 around the origin when empty. */
export function fitView(points: XY[], w: number, h: number): View {
  if (points.length === 0) return { x: -w / 2, y: -h / 2, k: 1 };
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const minX = Math.min(...xs) - BOX_W;
  const maxX = Math.max(...xs) + BOX_W;
  const minY = Math.min(...ys) - BOX_H * 2;
  const maxY = Math.max(...ys) + BOX_H * 2;
  const k = Math.min(MAX_K, Math.max(MIN_K, Math.min(w / (maxX - minX), h / (maxY - minY), 1.5)));
  return { x: (minX + maxX) / 2 - w / 2 / k, y: (minY + maxY) / 2 - h / 2 / k, k };
}

type Gesture =
  | { type: "pan"; id: number; sx: number; sy: number; view: View }
  | { type: "move"; id: number; tag: string; sx: number; sy: number; origin: XY; moved: boolean };

/** The flowsheet canvas: units as plain named boxes resting on a hexagonal
 *  lattice, streams as straight links. Drop a palette unit to create it where it
 *  lands; drag a box to move it; drag the background to pan, wheel to zoom.
 *  With the grid on, positions snap to the nearest cell centre. */
export function FlowsheetCanvas({
  units,
  links,
  onDropUnit,
  onMoveUnit,
  onSelectUnit,
  selected = null,
  centreRef,
}: {
  units: CanvasUnit[];
  links: CanvasLink[];
  onDropUnit: (kind: string, pos: XY) => void;
  onMoveUnit: (tag: string, pos: XY) => void;
  /** A unit was clicked (pressed and released without moving) or Enter/Space on it. */
  onSelectUnit?: (tag: string) => void;
  /** Tag drawn highlighted. */
  selected?: string | null;
  /** Written with the world point at the centre of the view (click-to-add target). */
  centreRef?: { current: XY };
}) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [size, setSize] = useState(FALLBACK_SIZE);
  const [view, setView] = useState<View>(() =>
    fitView(units.map((u) => u.pos), FALLBACK_SIZE.w, FALLBACK_SIZE.h),
  );
  const [grid, setGrid] = useState(true);
  const [drag, setDrag] = useState<{ tag: string; pos: XY } | null>(null);
  const [dropCell, setDropCell] = useState<XY | null>(null);
  const gesture = useRef<Gesture | null>(null);
  // Until the user pans or zooms, keep the view fitted to the measured size.
  const touched = useRef(false);
  const patternId = `hex${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const tile = useMemo(() => hexPatternTile(HEX_SIZE), []);

  const unitsRef = useRef(units);
  unitsRef.current = units;

  const place = (p: XY): XY => (grid ? snapToHex(p) : { x: Math.round(p.x), y: Math.round(p.y) });

  // Track the element size so the viewBox matches it 1:1 (crisp lines, exact hit maths).
  useEffect(() => {
    const el = svgRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([e]) => {
      const { width, height } = e.contentRect;
      if (width <= 0 || height <= 0) return;
      setSize({ w: width, h: height });
      if (!touched.current) setView(fitView(unitsRef.current.map((u) => u.pos), width, height));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  if (centreRef) centreRef.current = { x: view.x + size.w / 2 / view.k, y: view.y + size.h / 2 / view.k };

  // Wheel zoom about the cursor. Native listener: React's wheel handler is passive.
  useEffect(() => {
    const el = svgRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      touched.current = true;
      const r = el.getBoundingClientRect();
      setView((v) => zoomAt(v, Math.exp(-e.deltaY * 0.0015), e.clientX - r.left, e.clientY - r.top));
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  const rect = () => svgRef.current?.getBoundingClientRect() ?? { left: 0, top: 0 };
  const posOf = new Map(units.map((u) => [u.tag, drag?.tag === u.tag ? drag.pos : u.pos]));

  function onPointerDown(e: React.PointerEvent<SVGSVGElement>): void {
    if (e.button > 0) return;
    const g = (e.target as Element).closest("g[data-tag]");
    const tag = g?.getAttribute("data-tag");
    const unit = tag ? units.find((u) => u.tag === tag) : undefined;
    if (!unit) touched.current = true;
    gesture.current = unit
      ? { type: "move", id: e.pointerId, tag: unit.tag, sx: e.clientX, sy: e.clientY, origin: unit.pos, moved: false }
      : { type: "pan", id: e.pointerId, sx: e.clientX, sy: e.clientY, view };
    svgRef.current?.setPointerCapture?.(e.pointerId);
  }

  function onPointerMove(e: React.PointerEvent<SVGSVGElement>): void {
    const g = gesture.current;
    if (!g || g.id !== e.pointerId) return;
    const dx = (e.clientX - g.sx) / view.k;
    const dy = (e.clientY - g.sy) / view.k;
    if (g.type === "pan") {
      setView({ ...g.view, x: g.view.x - dx, y: g.view.y - dy });
    } else {
      if (Math.abs(dx) + Math.abs(dy) < 2 / view.k && !g.moved) return;
      g.moved = true;
      setDrag({ tag: g.tag, pos: { x: g.origin.x + dx, y: g.origin.y + dy } });
    }
  }

  function onPointerUp(e: React.PointerEvent<SVGSVGElement>): void {
    const g = gesture.current;
    if (!g || g.id !== e.pointerId) return;
    gesture.current = null;
    if (g.type === "move" && g.moved && drag) {
      const to = place(drag.pos);
      if (to.x !== g.origin.x || to.y !== g.origin.y) onMoveUnit(g.tag, to);
    } else if (g.type === "move" && !g.moved) onSelectUnit?.(g.tag);
    setDrag(null);
  }

  function onKeyUnit(e: React.KeyboardEvent, u: CanvasUnit): void {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onSelectUnit?.(u.tag);
      return;
    }
    const step = grid ? HEX_SIZE * Math.sqrt(3) : NUDGE; // one cell down/up; ±1.5 s across
    const across = grid ? HEX_SIZE * 1.5 : NUDGE;
    const d: Record<string, XY> = {
      ArrowLeft: { x: -across, y: grid ? -step / 2 : 0 },
      ArrowRight: { x: across, y: grid ? step / 2 : 0 },
      ArrowUp: { x: 0, y: -step },
      ArrowDown: { x: 0, y: step },
    };
    const m = d[e.key];
    if (!m) return;
    e.preventDefault();
    onMoveUnit(u.tag, place({ x: u.pos.x + m.x, y: u.pos.y + m.y }));
  }

  const accepts = (e: React.DragEvent) => Array.from(e.dataTransfer?.types ?? []).includes(UNIT_DND_TYPE);

  function onDragOver(e: React.DragEvent<SVGSVGElement>): void {
    if (!accepts(e)) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
    const p = place(clientToWorld(view, rect(), e.clientX, e.clientY));
    if (!dropCell || dropCell.x !== p.x || dropCell.y !== p.y) setDropCell(p);
  }

  function onDrop(e: React.DragEvent<SVGSVGElement>): void {
    setDropCell(null);
    const kind = e.dataTransfer?.getData(UNIT_DND_TYPE);
    if (!kind) return;
    e.preventDefault();
    onDropUnit(kind, place(clientToWorld(view, rect(), e.clientX, e.clientY)));
  }

  const zoomBy = (f: number) => {
    touched.current = true;
    setViewZoom(f);
  };
  const setViewZoom = (f: number) => setView((v) => zoomAt(v, f, size.w / 2, size.h / 2));
  const vw = size.w / view.k;
  const vh = size.h / view.k;
  const hairline = 1 / view.k; // 1 screen px at any zoom

  return (
    <div className="canvas ob">
      <div className="ctools" role="toolbar" aria-label="Canvas">
        <button
          type="button"
          className="tool ob"
          aria-pressed={grid}
          title="Show the hexagonal grid and snap units to its cells"
          onClick={() => setGrid((g) => !g)}
        >
          Grid &amp; snap
        </button>
        <button type="button" className="tool ob zoom" aria-label="Zoom out" onClick={() => zoomBy(1 / 1.25)}>
          −
        </button>
        <span className="tool ob zoomval num" aria-live="polite">
          {Math.round(view.k * 100)}%
        </span>
        <button type="button" className="tool ob" aria-label="Zoom in" onClick={() => zoomBy(1.25)}>
          +
        </button>
        <button
          type="button"
          className="tool ob"
          onClick={() => setView(fitView(units.map((u) => u.pos), size.w, size.h))}
        >
          Fit
        </button>
      </div>
      <svg
        ref={svgRef}
        className="fscanvas"
        role="application"
        aria-label="Flowsheet canvas: drop units here"
        viewBox={`${view.x} ${view.y} ${vw} ${vh}`}
        data-zoom={view.k}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onDragOver={onDragOver}
        onDragLeave={() => setDropCell(null)}
        onDrop={onDrop}
      >
        {grid && (
          <>
            <defs>
              <pattern id={patternId} patternUnits="userSpaceOnUse" width={tile.width} height={tile.height}>
                <path className="hexline" d={tile.d} strokeWidth={hairline} />
              </pattern>
            </defs>
            <rect className="hexgrid" x={view.x} y={view.y} width={vw} height={vh} fill={`url(#${patternId})`} />
          </>
        )}
        {dropCell && (
          <rect
            className="dropcell"
            x={dropCell.x - BOX_W / 2}
            y={dropCell.y - BOX_H / 2}
            width={BOX_W}
            height={BOX_H}
            strokeWidth={hairline * 1.5}
          />
        )}
        {links.map((l) => {
          const a = posOf.get(l.from);
          const b = posOf.get(l.to);
          if (!a || !b) return null;
          return <line key={l.id} className="link" x1={a.x} y1={a.y} x2={b.x} y2={b.y} strokeWidth={hairline * 1.4} />;
        })}
        {units.map((u) => {
          const p = posOf.get(u.tag) ?? u.pos;
          return (
            <g
              key={u.tag}
              data-tag={u.tag}
              data-x={p.x}
              data-y={p.y}
              className={`unitbox${drag?.tag === u.tag ? " dragging" : ""}${selected === u.tag ? " selected" : ""}`}
              aria-pressed={selected === u.tag}
              transform={`translate(${p.x} ${p.y})`}
              tabIndex={0}
              role="button"
              aria-label={`${u.tag} ${u.name}: Enter selects, arrow keys move it`}
              onKeyDown={(e) => onKeyUnit(e, u)}
            >
              <title>{`${u.tag} · ${u.name}`}</title>
              <rect x={-BOX_W / 2} y={-BOX_H / 2} width={BOX_W} height={BOX_H} strokeWidth={hairline * 1.6} />
              <text className="utag" y={-4}>
                {u.tag}
              </text>
              <text className="ukind" y={12}>
                {u.name.length > 21 ? `${u.name.slice(0, 20)}…` : u.name}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
