import { useState, type KeyboardEvent } from "react";
import { OctScroll } from "../components/OctScroll";

export const SHEET_COLS = 26;
export const SHEET_ROWS = 60;
const colName = (c: number) => String.fromCharCode(65 + c);

/** A plain spreadsheet grid: type into any cell, move with Enter, Tab and the arrow keys.
 * Values live in memory only; formulas and saving come with the sheet engine (F-07). */
export function SheetView() {
  const [cells, setCells] = useState<Record<string, string>>({});
  const [active, setActive] = useState("A1");

  const focusCell = (id: string) => {
    const el = document.querySelector<HTMLInputElement>(`[data-cell="${id}"]`);
    el?.focus();
    el?.select();
  };

  const onKey = (e: KeyboardEvent<HTMLInputElement>, c: number, r: number) => {
    const el = e.currentTarget;
    const atStart = el.selectionStart === 0 && el.selectionEnd === 0;
    const atEnd = el.selectionStart === el.value.length;
    const moves: Record<string, [number, number] | null> = {
      Enter: [0, e.shiftKey ? -1 : 1],
      ArrowDown: [0, 1],
      ArrowUp: [0, -1],
      Tab: [e.shiftKey ? -1 : 1, 0],
      ArrowRight: atEnd ? [1, 0] : null,
      ArrowLeft: atStart ? [-1, 0] : null,
    };
    const mv = moves[e.key];
    if (!mv) return;
    const nc = c + mv[0], nr = r + mv[1];
    if (nc < 0 || nc >= SHEET_COLS || nr < 1 || nr > SHEET_ROWS) return;
    e.preventDefault();
    focusCell(colName(nc) + nr);
  };

  return (
    <section className="page">
      <div className="pagehead">
        <div>
          <h1>Sheet</h1>
        </div>
        <div className="row">
          <span className="namebox ob num" aria-label="Active cell">
            {active}
          </span>
          <button type="button" className="btn ob" onClick={() => setCells({})}>
            Clear
          </button>
        </div>
      </div>
      <OctScroll label="Sheet" className="xsheet" maxHeight="calc(100dvh - 150px)">
        <table className="xgrid">
          <thead>
            <tr>
              <th className="corner" />
              {Array.from({ length: SHEET_COLS }, (_, c) => (
                <th key={c} scope="col">
                  {colName(c)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: SHEET_ROWS }, (_, i) => {
              const r = i + 1;
              return (
                <tr key={r}>
                  <th scope="row">{r}</th>
                  {Array.from({ length: SHEET_COLS }, (_, c) => {
                    const id = colName(c) + r;
                    return (
                      <td key={id}>
                        <input
                          data-cell={id}
                          name={id}
                          aria-label={id}
                          autoComplete="off"
                          spellCheck={false}
                          value={cells[id] ?? ""}
                          onFocus={() => setActive(id)}
                          onKeyDown={(e) => onKey(e, c, r)}
                          onChange={(e) => {
                            const v = e.target.value;
                            setCells((prev) => {
                              const next = { ...prev };
                              if (v) next[id] = v;
                              else delete next[id];
                              return next;
                            });
                          }}
                        />
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </OctScroll>
    </section>
  );
}
