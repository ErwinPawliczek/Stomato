import { HEX_SIZE, hexAt, hexCentre, hexPatternTile, nearestFreeCell, snapToHex } from "./hexGrid";

const S = HEX_SIZE;
const H = (Math.sqrt(3) / 2) * S; // half the cell height (flat-top)

test("snap returns the centre of the cell that contains the point", () => {
  expect(snapToHex({ x: 0, y: 0 })).toEqual({ x: 0, y: 0 });
  expect(snapToHex({ x: 3, y: -4 })).toEqual({ x: 0, y: 0 });
  // Neighbour to the lower right sits at (1.5 s, h).
  const c = hexCentre({ q: 1, r: 0 });
  expect(c.x).toBeCloseTo(1.5 * S);
  expect(c.y).toBeCloseTo(H);
  const s = snapToHex({ x: 1.5 * S + 5, y: H - 6 });
  expect(s.x).toBeCloseTo(1.5 * S);
  expect(s.y).toBeCloseTo(H);
  // Straight below: one full cell height.
  expect(snapToHex({ x: 2, y: 2 * H - 3 }).y).toBeCloseTo(2 * H);
});

test("snap is idempotent and never moves a point further than the circumradius", () => {
  for (let i = 0; i < 500; i++) {
    const p = { x: (i * 37.3) % 900 - 450, y: (i * 91.7) % 700 - 350 };
    const s = snapToHex(p);
    expect(Math.hypot(s.x - p.x, s.y - p.y)).toBeLessThanOrEqual(S + 1e-9);
    const again = snapToHex(s);
    expect(again.x).toBeCloseTo(s.x, 9);
    expect(again.y).toBeCloseTo(s.y, 9);
    expect(hexAt(s)).toEqual(hexAt(p));
  }
});

test("nearestFreeCell skips occupied cells and stays adjacent", () => {
  expect(nearestFreeCell({ x: 0, y: 0 }, [])).toEqual({ x: 0, y: 0 });
  const p = nearestFreeCell({ x: 0, y: 0 }, [{ x: 1, y: 1 }]);
  expect(Math.hypot(p.x, p.y)).toBeCloseTo(2 * H); // one neighbour step away
});

test("pattern tile spans 3s by sqrt(3)s", () => {
  const t = hexPatternTile();
  expect(t.width).toBeCloseTo(3 * S, 3);
  expect(t.height).toBeCloseTo(2 * H, 3);
  expect(t.d.startsWith("M")).toBe(true);
});
