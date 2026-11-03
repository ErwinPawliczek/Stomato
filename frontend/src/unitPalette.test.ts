import { UNIT_CATALOGUE } from "./unitCatalogue";
import { CATEGORIES, categoryOf, groupPalette, matchesQuery, nextTag, paletteItems } from "./unitPalette";

// The catalogue YAML is the source the mirror was generated from. Rows start
// with "- id:" at column 0; name, family and pid_symbol are 2-space keys.
function yamlRows(): { id: string; name: string; family: string; pidSymbol: string }[] {
  const files = import.meta.glob<string>("../../data/unit_models/*.yaml", { query: "?raw", import: "default", eager: true });
  const rows: { id: string; name: string; family: string; pidSymbol: string }[] = [];
  for (const [path, text] of Object.entries(files)) {
    if (path.endsWith("/_schema.yaml")) continue;
    for (const chunk of text.split(/^- id: /m).slice(1)) {
      const key = (k: string) => (chunk.match(new RegExp(`^  ${k}: (.*)$`, "m"))?.[1] ?? "").trim().replace(/^(['"])(.*)\1$/, "$2");
      rows.push({ id: chunk.split("\n")[0].trim(), name: key("name"), family: key("family"), pidSymbol: key("pid_symbol") });
    }
  }
  return rows;
}

test("the catalogue mirror matches data/unit_models (84 units)", () => {
  const yaml = yamlRows();
  expect(yaml).toHaveLength(84);
  const mirror = UNIT_CATALOGUE.map(({ id, name, family, pidSymbol }) => ({ id, name, family, pidSymbol }));
  expect(new Set(mirror.map((u) => u.id)).size).toBe(84);
  expect([...mirror].sort((a, b) => a.id.localeCompare(b.id))).toEqual([...yaml].sort((a, b) => a.id.localeCompare(b.id)));
  for (const u of UNIT_CATALOGUE) expect(u.summary.length).toBeGreaterThan(10);
});

test("every catalogue unit is in exactly one category", () => {
  const groups = groupPalette(paletteItems(undefined));
  const placed = groups.flatMap((g) => g.items.map((i) => i.kind));
  expect(placed).toHaveLength(UNIT_CATALOGUE.length);
  expect(new Set(placed)).toEqual(new Set(UNIT_CATALOGUE.map((u) => u.id)));
  const ids = CATEGORIES.map((c) => c.id) as string[];
  for (const u of UNIT_CATALOGUE) expect(ids).toContain(categoryOf(u));
  // The catalogue fills every engineering category; only "Other" stays empty.
  expect(groups.map((g) => g.id)).toEqual(ids.filter((c) => c !== "other"));
});

test("engineering categories put units where an engineer looks for them", () => {
  const cat = (id: string) => categoryOf(UNIT_CATALOGUE.find((u) => u.id === id)!);
  expect(cat("mixer")).toBe("streams");
  expect(cat("compressor")).toBe("pressure");
  expect(cat("jt_valve")).toBe("pressure");
  expect(cat("shell_tube")).toBe("heat");
  expect(cat("separator_3phase")).toBe("separators");
  expect(cat("column")).toBe("columns");
  expect(cat("gibbs_reactor")).toBe("reactors");
  expect(cat("mdea_absorber")).toBe("treating");
  expect(cat("membrane")).toBe("treating");
  expect(cat("filter")).toBe("solids");
  expect(cat("recycle_block")).toBe("utilities");
});

test("search matches name, kind id and category; unknown registered kinds land in Other", () => {
  const items = paletteItems([...UNIT_CATALOGUE.map((u) => u.id), "brand_new_unit"]);
  expect(groupPalette(items, "jt").flatMap((g) => g.items.map((i) => i.kind))).toEqual(["jt_valve"]);
  expect(groupPalette(items, "heat transfer")[0].id).toBe("heat");
  const pump = items.find((i) => i.kind === "pump")!;
  expect(matchesQuery(pump, "PUMP")).toBe(true);
  expect(matchesQuery(pump, "pump compressor")).toBe(false);
  const other = groupPalette(items).find((g) => g.id === "other");
  expect(other?.items.map((i) => i.kind)).toEqual(["brand_new_unit"]);
  expect(paletteItems(["pump"]).find((i) => i.kind === "compressor")?.available).toBe(false);
});

test("nextTag takes the P&ID symbol and the first free number", () => {
  expect(nextTag("K", [])).toBe("K-101");
  expect(nextTag("T", ["T-101", "T-102", "V-103"])).toBe("T-103");
});
