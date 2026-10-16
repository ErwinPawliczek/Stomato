import { fireEvent, render, screen } from "@testing-library/react";
import { CATALOG, catalogFor } from "../equipmentCatalog";
import { diagLayout, EquipmentView } from "./EquipmentView";

test("lists every registered unit and opens one into its detail octagon", async () => {
  render(<EquipmentView />);
  expect(await screen.findByRole("button", { name: /TEG contactor/ })).toBeTruthy();
  expect(screen.getByRole("button", { name: /Compression train/ })).toBeTruthy();

  fireEvent.click(screen.getByRole("button", { name: /TEG contactor/ }));
  expect(screen.getByRole("heading", { name: "TEG contactor" })).toBeTruthy();
  expect(screen.getByText("water_out_lb_per_mmscf")).toBeTruthy();
  expect(screen.getByText("gas_in, lean_teg_in → gas_out, rich_teg_out")).toBeTruthy();

  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.queryByRole("heading", { name: "TEG contactor" })).toBeNull();
});

test("unknown and alias kinds from the registry still get a tile", () => {
  const items = catalogFor(["compressor", "mea_absorber", "brand_new_unit"]);
  expect(items.map((e) => e.kind)).toEqual(["compressor", "mea_absorber", "brand_new_unit"]);
  expect(items[1].name).toBe("Amine absorber, MEA");
  expect(items[2].name).toBe("Brand new unit");
});

test("diagonal layout: tiles never overlap, the row fills the width, the big octagon pushes others aside", () => {
  const n = CATALOG.length;
  const octNorm = (dx: number, dy: number) => Math.max(Math.abs(dx), Math.abs(dy), (Math.abs(dx) + Math.abs(dy)) / Math.SQRT2);
  for (const [avail, open] of [
    [1270, null],
    [1270, 3],
    [900, 0],
    [520, null],
  ] as const) {
    const L = diagLayout(n, avail, open, open === null ? null : { i: 2, j: 1 });
    expect(L.width).toBeLessThanOrEqual(avail);
    expect(L.width).toBeGreaterThan(avail - L.cols);
    const all = [...L.tiles, ...L.ghosts];
    for (let a = 0; a < all.length; a++)
      for (let b = a + 1; b < all.length; b++) {
        const A = all[a], B = all[b];
        const d = octNorm(A.x + A.size / 2 - (B.x + B.size / 2), A.y + A.size / 2 - (B.y + B.size / 2));
        expect(d).toBeGreaterThanOrEqual((A.size + B.size) / 2 - 1.5);
      }
    if (open !== null) expect(L.tiles[open].size).toBeGreaterThanOrEqual(3 * L.W - 1);
  }
});
