// Sample P&ID the mock API serves instead of GET /api/views/pid.svg. It honours
// the same contract as the real S-18 renderer (spec B-04): equipment, lines,
// valves and instruments each sit in a <g data-tag=...> group, line groups use
// the pipe line number (HTML-escaped, e.g. 8&quot;-PG-1001-B1), and a stored
// layout.pid position is the equipment box's TOP-LEFT corner in view px —
// unplaced equipment keeps its fixed sample position. Tags mirror the real
// sample: 8 equipment, 13 line numbers, 15 valves (incl. 2 PSVs), 7 instruments.

type Pos = { x: number; y: number };

// tag, auto top-left x/y, box w/h — left to right like the real layout.
const EQUIPMENT: Array<[string, number, number, number, number]> = [
  ["V-101", 40, 60, 110, 90],
  ["K-101", 210, 60, 80, 60],
  ["E-101", 360, 60, 70, 70],
  ["T-101", 510, 60, 90, 140],
  ["P-101", 670, 60, 60, 60],
  ["E-102", 790, 60, 80, 70],
  // Wave-1 amine loop on its own row below the line band.
  ["A-101", 40, 330, 110, 80],
  ["R-101", 210, 330, 90, 80],
];

// Pipe line numbers, size-prefixed and HTML-escaped like the backend's output.
const LINE_NUMBERS = [
  "8&quot;-PG-1001-B1",
  "8&quot;-PG-1002-D1",
  "8&quot;-PG-1003-D1",
  "8&quot;-PG-1004-D1",
  "8&quot;-PG-1005-D1",
  "1&quot;-GL-1006-D1",
  "1&quot;-GL-1007-D1",
  "1&quot;-PL-1008-B1",
  "1.5&quot;-PL-1009-B1",
  "1.5&quot;-PL-1010-B1",
  "1&quot;-W-1011-B1",
  "6&quot;-FL-1012-B1",
  "6&quot;-FL-1013-D1",
];

const VALVES = [
  "HV-1001", "HV-1002", "HV-1003", "HV-1004", "HV-1005", "HV-1006", "HV-1007",
  "HV-1008", "HV-1009", "HV-1010", "HV-1011", "HV-1012", "HV-1013",
];

const PSVS = ["PSV-1001", "PSV-1002"];

const INSTRUMENTS = ["LG-1001", "LIT-1002", "LSHH-1001", "LSLL-1001", "LT-1001", "PT-1003", "PT-1004"];

export function mockPidSvg(placed: Record<string, Pos>): string {
  const parts: string[] = [
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 920 440" width="920" height="440">',
  ];
  // Lines: horizontal runs in a band below the equipment row; valve i sits on
  // line i's midpoint, like the real renderer draws inline valves.
  LINE_NUMBERS.forEach((num, i) => {
    const x1 = 40;
    const x2 = 300 + (i % 3) * 80;
    const y = 210 + (i % 4) * 26;
    parts.push(
      `<g data-tag="${num}"><polyline points="${x1},${y} ${x2},${y}" fill="none" stroke="black"/>` +
        `<polygon points="${x2 - 7},${y - 4} ${x2 - 7},${y + 4} ${x2},${y}"/>` +
        `<text x="${x1}" y="${y - 5}" font-size="8">${num}</text></g>`,
    );
    const valve = VALVES[i];
    if (valve) {
      const vx = (x1 + x2) / 2;
      parts.push(
        `<g data-tag="${valve}"><polygon points="${vx - 8},${y - 6} ${vx - 8},${y + 6} ${vx + 8},${y - 6} ${vx + 8},${y + 6}" fill="none" stroke="black"/>` +
          `<text x="${vx}" y="${y + 18}" text-anchor="middle" font-size="7">${valve}</text></g>`,
      );
    }
  });
  // Relief valves stand alone at the right edge.
  PSVS.forEach((tag, i) => {
    const cx = 870;
    const cy = 230 + i * 40;
    parts.push(
      `<g data-tag="${tag}"><circle cx="${cx}" cy="${cy}" r="12" fill="none" stroke="black"/>` +
        `<text x="${cx}" y="${cy + 24}" text-anchor="middle" font-size="7">${tag}</text></g>`,
    );
  });
  // Instrument bubbles along the top.
  INSTRUMENTS.forEach((tag, i) => {
    const cx = 60 + i * 120;
    parts.push(
      `<g data-tag="${tag}"><circle cx="${cx}" cy="24" r="14" fill="none" stroke="black"/>` +
        `<text x="${cx}" y="27" text-anchor="middle" font-size="6">${tag}</text></g>`,
    );
  });
  // Equipment: placed[tag] is the bbox top-left (spec B-04), so a saved
  // placement survives re-fetch exactly like on the real renderer. Mirror
  // the real renderer's structure — a plain group holding an invisible
  // .equipment-bbox rect tagged at the stored top-left, a symbol outline,
  // and the label — so the mock exercises the same DOM the view must handle.
  for (const [tag, ax, ay, w, h] of EQUIPMENT) {
    const x = placed[tag]?.x ?? ax;
    const y = placed[tag]?.y ?? ay;
    parts.push(
      `<g><rect x="${x}" y="${y}" width="${w}" height="${h}" class="equipment-bbox" data-tag="${tag}" fill="none" stroke="none"/>` +
        `<rect x="${x + 10}" y="${y + 10}" width="${w - 20}" height="${h - 20}" fill="none" stroke="black"/>` +
        `<text x="${x + w / 2}" y="${y - 5}" text-anchor="middle" font-size="9">${tag}</text></g>`,
    );
  }
  parts.push("</svg>");
  return parts.join("");
}
