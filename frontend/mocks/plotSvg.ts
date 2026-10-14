// Sample plot plan the mock API serves instead of GET /api/views/plot.svg. It
// honours the same contract as the real S-21-backed renderer (spec B-05):
// every equipment item and line sits in a <g data-tag=...> group, and a stored
// layout.plot position is the equipment envelope's CENTRE in model
// millimetres (x east, y north, z elevation) — the drawing applies the same
// y flip (north up) and margin as routes_plot.render_plot_svg, so a saved
// placement survives re-fetch. Tags mirror the sample flowsheet: 6 equipment,
// 5 routed lines between neighbours.

type Vec3 = { x: number; y: number; z: number };

// Mirrors the router's auto-placement for tags with no stored plot position
// (router_orthogonal: unplaced equipment along x at 12 000 mm spacing, z 0).
const EQUIPMENT: Array<[string, number]> = [
  ["V-101", 12_000],
  ["K-101", 24_000],
  ["E-101", 36_000],
  ["T-101", 48_000],
  ["P-101", 60_000],
  ["E-102", 72_000],
];

const ENVELOPE_HALF = 1_000; // 2 m cube around each origin, like the router
const MARGIN = 3_000; // drawing margin, like routes_plot.MARGIN_MM

// HTML-escaped pipe line numbers, like the real renderer's output.
const LINE_NUMBERS = ["8&quot;-PG-1001-B1", "8&quot;-PG-1002-D1", "6&quot;-FL-1003-B1", "6&quot;-FL-1004-D1", "4&quot;-FU-1005-B1"];

const fmt = (v: number): string => String(Math.round(v));

export function mockPlotSvg(placed: Record<string, Vec3>): string {
  const origins: Record<string, Vec3> = {};
  for (const [tag, x] of EQUIPMENT) origins[tag] = placed[tag] ?? { x, y: 0, z: 0 };

  // Neighbour-to-neighbour runs, the plan projection of a simple routed chain.
  const runs: Array<[string, string]> = [];
  for (let i = 0; i < EQUIPMENT.length - 1; i++) runs.push([EQUIPMENT[i][0], EQUIPMENT[i + 1][0]]);

  // Extent over envelopes and line vertices, like routes_plot._extent.
  const xs: number[] = [];
  const ys: number[] = [];
  for (const o of Object.values(origins)) {
    xs.push(o.x - ENVELOPE_HALF, o.x + ENVELOPE_HALF);
    ys.push(o.y - ENVELOPE_HALF, o.y + ENVELOPE_HALF);
  }
  for (const [a, b] of runs) {
    xs.push(origins[a].x, origins[b].x);
    ys.push(origins[a].y, origins[b].y);
  }
  const minX = Math.min(...xs);
  const maxY = Math.max(...ys);
  const w = Math.max(...xs) - minX + 2 * MARGIN;
  const h = maxY - Math.min(...ys) + 2 * MARGIN;
  const px = (v: number): number => v - minX + MARGIN;
  const py = (v: number): number => maxY + MARGIN - v; // flip: north up

  const parts: string[] = [
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${fmt(w)} ${fmt(h)}" width="${fmt(w)}" height="${fmt(h)}">`,
  ];
  for (const [i, [a, b]] of runs.entries()) {
    const pts = `${fmt(px(origins[a].x))},${fmt(py(origins[a].y))} ${fmt(px(origins[b].x))},${fmt(py(origins[b].y))}`;
    parts.push(
      `<g data-tag="${LINE_NUMBERS[i]}"><polyline points="${pts}" fill="none" stroke="black" stroke-width="300"/>` +
        `<text x="${fmt(px((origins[a].x + origins[b].x) / 2))}" y="${fmt(py((origins[a].y + origins[b].y) / 2) - 700)}" font-size="700" text-anchor="middle">${LINE_NUMBERS[i]}</text></g>`,
    );
  }
  for (const [tag] of EQUIPMENT) {
    const o = origins[tag];
    parts.push(
      `<g data-tag="${tag}">` +
        `<rect x="${fmt(px(o.x - ENVELOPE_HALF))}" y="${fmt(py(o.y + ENVELOPE_HALF))}" width="${fmt(2 * ENVELOPE_HALF)}" height="${fmt(2 * ENVELOPE_HALF)}" fill="none" stroke="black" stroke-width="300"/>` +
        `<text x="${fmt(px(o.x))}" y="${fmt(py(o.y))}" font-size="700" text-anchor="middle" dominant-baseline="middle">${tag}</text></g>`,
    );
  }
  parts.push("</svg>");
  return parts.join("");
}
