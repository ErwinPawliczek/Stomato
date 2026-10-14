// Sample PFD the mock API serves instead of GET /api/views/pfd.svg. It honours
// the same contract as the real S-22 renderer (spec B-03): every unit and every
// stream of the sample project is a <g data-tag=...> group (full slice fidelity,
// so the shared tag inventory in the P&ID view sees real parity), and a stored
// layout.pfd position is the unit box's centre — unplaced units keep their
// fixed sample positions.

type Pos = { x: number; y: number };

// tag, auto centre x/y, box w/h — left to right like the real layout.
const UNITS: Array<[string, number, number, number, number]> = [
  ["V-101", 120, 100, 110, 90],
  ["K-101", 300, 100, 80, 60],
  ["E-101", 470, 100, 70, 70],
  ["T-101", 640, 100, 60, 140],
  ["P-101", 300, 240, 60, 60],
  ["E-102", 470, 240, 80, 70],
];

const STREAMS: Array<[string, number, number, number, number]> = [
  ["S-001", 40, 100, 65, 100], // feed -> V-101
  ["S-002", 175, 100, 260, 100], // V-101 -> K-101
  ["S-003", 340, 100, 435, 100], // K-101 -> E-101
  ["S-004", 505, 100, 610, 100], // E-101 -> T-101
  ["S-005", 670, 100, 760, 100], // T-101 gas out
  ["S-006", 700, 10, 640, 30], // lean TEG into T-101
  ["S-007", 640, 170, 700, 190], // T-101 rich TEG out
  ["S-008", 120, 145, 270, 240], // V-101 -> P-101
  ["S-009", 330, 240, 430, 240], // P-101 -> E-102
  ["S-010", 510, 240, 560, 240], // E-102 out
  ["S-011", 65, 145, 40, 170], // V-101 water out
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
