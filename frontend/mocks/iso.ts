// Sample isometrics the mock API serves instead of GET /api/views/iso,
// /api/views/iso/{line}.svg and /api/views/iso/{line}.json (spec B-06). The
// sheets are trimmed from the real backend's output for the "slice" template
// (S-19 iso_renderer "svg"); the drawing is a small stand-in with the same
// data-tag groups (title-block, bom, dim-*, component groups).

type IsoSheet = {
  title: {
    line_number: string;
    pipe_class: string;
    design_pressure_kPag: number;
    design_temperature_C: number;
    test_pressure_kPag: number;
    insulation: string;
    sheet: string;
  };
  bom: Array<{ item: number; qty: number; unit: string; nps_in: number; description: string; material: string }>;
  cut_list: Array<{ piece: number; spool: string; nps_in: number; length_mm: number }>;
  weld_count: number;
  total_pipe_length_mm: number;
  svg: string;
};

const MATERIAL = "CS ASTM A106 Gr B (seamless)";

function sheet(
  line: string,
  cls: string,
  nps: number,
  sch: string,
  rating: string,
  p: number,
  t: number,
  cuts: number[],
): IsoSheet {
  const total = cuts.reduce((a, b) => a + b, 0);
  const n = `${nps}"`;
  return {
    title: {
      line_number: line,
      pipe_class: cls,
      design_pressure_kPag: p,
      design_temperature_C: t,
      test_pressure_kPag: p * 1.5,
      insulation: "none",
      sheet: "1 of 1",
    },
    bom: [
      { item: 1, qty: total / 1000, unit: "m", nps_in: nps, description: `${n} pipe SCH${sch}`, material: MATERIAL },
      { item: 2, qty: 3, unit: "ea", nps_in: nps, description: `${n} 90 LR elbow SCH${sch}`, material: MATERIAL },
      { item: 3, qty: 1, unit: "ea", nps_in: nps, description: `${n} WN flange ${rating} RTJ`, material: MATERIAL },
    ],
    cut_list: cuts.map((length_mm, i) => ({ piece: i + 1, spool: "SP-1", nps_in: nps, length_mm })),
    weld_count: 7,
    total_pipe_length_mm: total,
    svg: isoSvg(line),
  };
}

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");

function isoSvg(line: string): string {
  return (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300" width="400" height="300">' +
    '<rect x="0" y="0" width="400" height="300" fill="white" />' +
    `<g data-tag="pipe"><line x1="40" y1="260" x2="40" y2="80" stroke="#1a1a1a" stroke-width="2" />` +
    '<line x1="40" y1="80" x2="200" y2="40" stroke="#1a1a1a" stroke-width="2" />' +
    '<line x1="200" y1="40" x2="360" y2="80" stroke="#1a1a1a" stroke-width="2" /></g>' +
    '<g data-tag="dim-C1"><text x="10" y="170" font-size="10">5695</text></g>' +
    `<g data-tag="title-block"><rect x="220" y="230" width="170" height="60" fill="none" stroke="#1a1a1a" />` +
    `<text x="228" y="250" font-size="11">${esc(line)}</text></g>` +
    "</svg>"
  );
}

/** IsoSheet per routed line number; key order is the GET /api/views/iso order. */
export const MOCK_ISO_SHEETS: Record<string, IsoSheet> = Object.fromEntries(
  [
    sheet('8"-PG-1001-B1', "B1", 8, "30", "cl300", 3690.375, 45, [5695.2, 100.5, 5390.4, 100]),
    sheet('1"-GL-1006-D1', "D1", 1, "XS", "cl600", 7708.675, 77, [5961.9, 38063.7, 6223.8, 361.9]),
    sheet('6"-FL-1012-B1', "B1", 6, "40", "cl300", 3590.0, 60, [4200, 2500.5]),
  ].map((s) => [s.title.line_number, s]),
);
