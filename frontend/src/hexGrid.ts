// Flat-top hexagonal lattice for the flowsheet canvas. Pure geometry: cell
// centres, snapping a point to the nearest centre, and the SVG pattern tile.
// Axial coordinates (q, r) and cube rounding after Red Blob Games, "Hexagonal
// Grids" (redblobgames.com/grids/hexagons), flat-top orientation.
import type { XY } from "./api/client";

export type Hex = { q: number; r: number };

/** Circumradius of one cell, canvas user units (= PFD layout units). */
export const HEX_SIZE = 40;
const SQRT3 = Math.sqrt(3);

export function hexCentre({ q, r }: Hex, size = HEX_SIZE): XY {
  return { x: size * 1.5 * q, y: size * SQRT3 * (r + q / 2) };
}

/** Cube rounding of fractional axial coordinates to the cell that contains them. */
function roundHex(qf: number, rf: number): Hex {
  const sf = -qf - rf;
  let q = Math.round(qf);
  let r = Math.round(rf);
  const s = Math.round(sf);
  const dq = Math.abs(q - qf);
  const dr = Math.abs(r - rf);
  const ds = Math.abs(s - sf);
  if (dq > dr && dq > ds) q = -r - s;
  else if (dr > ds) r = -q - s;
  return { q: q + 0, r: r + 0 }; // +0 turns -0 into 0
}

export function hexAt(p: XY, size = HEX_SIZE): Hex {
  const qf = ((2 / 3) * p.x) / size;
  const rf = ((-1 / 3) * p.x + (SQRT3 / 3) * p.y) / size;
  return roundHex(qf, rf);
}

/** The centre of the cell containing p: where a dropped or dragged unit rests. */
export function snapToHex(p: XY, size = HEX_SIZE): XY {
  return hexCentre(hexAt(p, size), size);
}

const NEIGHBOURS: readonly Hex[] = [
  { q: 1, r: 0 }, { q: 1, r: -1 }, { q: 0, r: -1 }, { q: -1, r: 0 }, { q: -1, r: 1 }, { q: 0, r: 1 },
];

/** Nearest cell centre to p (ring by ring) that no occupied point snaps to. */
export function nearestFreeCell(p: XY, occupied: readonly XY[], size = HEX_SIZE): XY {
  const key = (h: Hex) => `${h.q},${h.r}`;
  const taken = new Set(occupied.map((o) => key(hexAt(o, size))));
  const start = hexAt(p, size);
  const seen = new Set([key(start)]);
  let frontier = [start];
  for (let ring = 0; ring < 64; ring++) {
    const free = frontier.filter((h) => !taken.has(key(h)));
    if (free.length > 0) {
      const d = (h: Hex) => Math.hypot(hexCentre(h, size).x - p.x, hexCentre(h, size).y - p.y);
      return hexCentre(free.reduce((a, b) => (d(b) < d(a) ? b : a)), size);
    }
    const next: Hex[] = [];
    for (const h of frontier)
      for (const n of NEIGHBOURS) {
        const c = { q: h.q + n.q, r: h.r + n.r };
        if (!seen.has(key(c))) {
          seen.add(key(c));
          next.push(c);
        }
      }
    frontier = next;
  }
  return hexCentre(start, size);
}

/** Pattern tile (3·size × √3·size) holding each lattice edge exactly once, so a
 *  semi-transparent stroke never doubles up. Origin sits on a cell centre. */
export function hexPatternTile(size = HEX_SIZE): { width: number; height: number; d: string } {
  const s = size;
  const h = (SQRT3 / 2) * s;
  const f = (n: number) => +n.toFixed(3);
  return {
    width: f(3 * s),
    height: f(2 * h),
    d:
      `M0 ${f(h)}H${f(s / 2)}L${f(s)} 0H${f(2 * s)}L${f(2.5 * s)} ${f(h)}H${f(3 * s)}` +
      `M${f(s / 2)} ${f(h)}L${f(s)} ${f(2 * h)}H${f(2 * s)}L${f(2.5 * s)} ${f(h)}`,
  };
}
