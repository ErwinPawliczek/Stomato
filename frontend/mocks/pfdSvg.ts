// Sample PFD the mock API serves instead of GET /api/views/pfd.svg. It honours
// the same contract as the real S-22 renderer (spec B-03): every unit is a
// <g data-tag=...> group, and a stored layout.pfd position is the unit box's
// centre — unplaced units keep their fixed sample positions.

type Pos = { x: number; y: number };

// tag, auto centre x/y, box w/h — left to right like the real layout.
const UNITS: Array<[string, number, number, number, number]> = [
  ["V-101", 120, 100, 110, 90],
  ["K-101", 300, 100, 80, 60],
  ["E-101", 470, 100, 70, 70],
  ["T-101", 640, 100, 60, 140],
];

const STREAMS: Array<[string, number, number, number, number]> = [
  ["S-001", 175, 100, 260, 100], // V-101 -> K-101
  ["S-002", 340, 100, 435, 100], // K-101 -> E-101
];

export function mockPfdSvg(placed: Record<string, Pos>): string {
  const parts: string[] = [
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 300" width="800" height="300">',
  ];
  for (const [id, x1, y1, x2, y2] of STREAMS) {
    parts.push(
      `<g data-tag="${id}"><polyline points="${x1},${y1} ${x2},${y2}" fill="none" stroke="black"/><polygon points="${x2 - 7},${y2 - 4} ${x2 - 7},${y2 + 4} ${x2},${y2}"/></g>`,
    );
  }
  for (const [tag, ax, ay, w, h] of UNITS) {
    const cx = placed[tag]?.x ?? ax;
    const cy = placed[tag]?.y ?? ay;
    parts.push(
      `<g data-tag="${tag}"><rect x="${cx - w / 2}" y="${cy - h / 2}" width="${w}" height="${h}" fill="none" stroke="black"/>` +
        `<text x="${cx}" y="${cy - h / 2 - 5}" text-anchor="middle" font-size="9">${tag}</text></g>`,
    );
  }
  parts.push("</svg>");
  return parts.join("");
}
