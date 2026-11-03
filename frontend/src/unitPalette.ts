// The flowsheet's add-equipment palette: every catalogue unit in exactly one
// engineering category. The default comes from the catalogue `family`
// (data/unit_models/_schema.yaml); OVERRIDES moves the units whose family is a
// code-organisation bucket rather than how a process engineer looks for them
// (flow → pressure change, logical → mixing vs. solver utilities, membranes and
// adsorbers → gas treating, cyclones and filters → solids). This is the only
// place the mapping lives; unitPalette.test.ts holds every unit to one category.
import { UNIT_CATALOGUE, type CatalogueFamily, type CatalogueUnit } from "./unitCatalogue";

export const CATEGORIES = [
  { id: "streams", label: "Streams & Mixing" },
  { id: "pressure", label: "Pressure Change" },
  { id: "heat", label: "Heat Transfer" },
  { id: "separators", label: "Separators & Flash" },
  { id: "columns", label: "Columns" },
  { id: "reactors", label: "Reactors" },
  { id: "treating", label: "Amine & Gas Treating" },
  { id: "solids", label: "Solids" },
  { id: "refining", label: "Refining" },
  { id: "utilities", label: "Utilities & Logical" },
  { id: "other", label: "Other" },
] as const;
export type CategoryId = (typeof CATEGORIES)[number]["id"];

const BY_FAMILY: Record<CatalogueFamily, CategoryId> = {
  logical: "utilities",
  flow: "pressure",
  heat: "heat",
  separation: "separators",
  column: "columns",
  reactors: "reactors",
  treating: "treating",
  refining: "refining",
};

const OVERRIDES: Readonly<Record<string, CategoryId>> = {
  mixer: "streams",
  splitter: "streams",
  component_splitter: "streams",
  stream_duplicator: "streams",
  membrane: "treating",
  adsorption_bed: "treating",
  hydrate_check: "treating",
  hydrocyclone: "solids",
  filter: "solids",
};

/** One palette box: a unit kind, whether the running engine registers it. */
export type PaletteItem = {
  kind: string;
  name: string;
  summary: string;
  pidSymbol: string;
  category: CategoryId;
  available: boolean;
};

const CATALOGUE_BY_ID = new Map(UNIT_CATALOGUE.map((u) => [u.id, u]));

export function categoryOf(unit: Pick<CatalogueUnit, "id" | "family">): CategoryId {
  return OVERRIDES[unit.id] ?? BY_FAMILY[unit.family];
}

/** Palette items for the catalogue plus any registered kind the catalogue
 *  mirror does not know yet ("Other"). `registered` undefined = registry not
 *  loaded yet: everything shows as available, the backend validates on solve. */
export function paletteItems(registered: readonly string[] | undefined): PaletteItem[] {
  const reg = registered ? new Set(registered) : null;
  const items: PaletteItem[] = UNIT_CATALOGUE.map((u) => ({
    kind: u.id,
    name: u.name,
    summary: u.summary,
    pidSymbol: u.pidSymbol,
    category: categoryOf(u),
    available: reg ? reg.has(u.id) : true,
  }));
  for (const k of registered ?? []) {
    if (CATALOGUE_BY_ID.has(k)) continue;
    items.push({
      kind: k,
      name: k.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase()),
      summary: "Registered in the engine; not in the unit catalogue yet.",
      pidSymbol: "U",
      category: "other",
      available: true,
    });
  }
  return items;
}

/** Case-insensitive match on name, kind id or category label; every word must hit. */
export function matchesQuery(item: PaletteItem, query: string): boolean {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length === 0) return true;
  const label = CATEGORIES.find((c) => c.id === item.category)?.label ?? "";
  const hay = `${item.name} ${item.kind} ${item.kind.replace(/_/g, " ")} ${label}`.toLowerCase();
  return words.every((w) => hay.includes(w));
}

/** Categories in palette order with their matching items (name-sorted); empty ones dropped. */
export function groupPalette(
  items: readonly PaletteItem[],
  query = "",
): { id: CategoryId; label: string; items: PaletteItem[] }[] {
  return CATEGORIES.map((c) => ({
    id: c.id,
    label: c.label,
    items: items
      .filter((i) => i.category === c.id && matchesQuery(i, query))
      .sort((a, b) => a.name.localeCompare(b.name)),
  })).filter((g) => g.items.length > 0);
}

/** Next free tag for a kind: its P&ID symbol plus the first free number from 101. */
export function nextTag(pidSymbol: string, taken: Iterable<string>): string {
  const used = new Set(taken);
  for (let n = 101; ; n++) {
    const tag = `${pidSymbol}-${n}`;
    if (!used.has(tag)) return tag;
  }
}

export function catalogueEntry(kind: string): CatalogueUnit | undefined {
  return CATALOGUE_BY_ID.get(kind);
}
