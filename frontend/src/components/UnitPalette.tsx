import { useMemo, useState } from "react";
import { CATEGORIES, groupPalette, type CategoryId, type PaletteItem } from "../unitPalette";

/** DataTransfer type a palette drag carries; the canvas only accepts this. */
export const UNIT_DND_TYPE = "application/x-stomato-unit";

/** Add-equipment palette: search, collapsible engineering categories, one plain
 *  named box per unit. Drag a box onto the canvas, or click / Enter to add it
 *  at the centre of the view (the keyboard path). */
export function UnitPalette({ items, onAdd }: { items: PaletteItem[]; onAdd: (kind: string) => void }) {
  const [query, setQuery] = useState("");
  // Start with the first category open; the rest stay one click away.
  const [open, setOpen] = useState<ReadonlySet<CategoryId>>(() => new Set([CATEGORIES[0].id]));
  const groups = useMemo(() => groupPalette(items, query), [items, query]);
  const searching = query.trim() !== "";

  const toggle = (id: CategoryId) =>
    setOpen((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });

  return (
    <aside className="panel ob upal" aria-label="Unit palette">
      <h2>Add equipment</h2>
      <div className="inp ob">
        <input
          type="search"
          aria-label="Search units"
          placeholder="Search units"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>
      <p className="muted small">Drag onto the canvas, or click to add at the centre.</p>
      {groups.length === 0 && <p className="muted small">No unit matches “{query}”.</p>}
      <div className="ugroups">
        {groups.map((g) => {
          const expanded = searching || open.has(g.id);
          const listId = `upal-${g.id}`;
          return (
            <div key={g.id} className="ugroup">
              <button
                type="button"
                className="ugh"
                aria-expanded={expanded}
                aria-controls={listId}
                onClick={() => toggle(g.id)}
                disabled={searching}
              >
                <span aria-hidden="true" className="caret">{expanded ? "▾" : "▸"}</span>
                {g.label}
                <span className="num count">{g.items.length}</span>
              </button>
              {expanded && (
                <ul id={listId} aria-label={g.label}>
                  {g.items.map((it) => (
                    <li key={it.kind}>
                      <button
                        type="button"
                        className="ut"
                        draggable={it.available}
                        disabled={!it.available}
                        data-kind={it.kind}
                        title={it.available ? it.summary : `${it.summary} Not registered in this engine.`}
                        onClick={() => onAdd(it.kind)}
                        onDragStart={(e) => {
                          e.dataTransfer.setData(UNIT_DND_TYPE, it.kind);
                          e.dataTransfer.setData("text/plain", it.kind);
                          e.dataTransfer.effectAllowed = "copy";
                        }}
                      >
                        {it.name}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          );
        })}
      </div>
    </aside>
  );
}
