import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties } from "react";
import { api } from "../api/client";
import { catalogFor, type EquipmentInfo } from "../equipmentCatalog";

type Cell = { i: number; j: number };
type Placed = Cell & { x: number; y: number; size: number };
export type DiagLayout = { W: number; cols: number; tiles: Placed[]; ghosts: Placed[]; width: number; height: number };

const S2 = Math.SQRT2;
// Octagon "norm": two same-orientation regular octagons with apothems r1, r2 overlap
// exactly when the norm of their centre offset is below r1 + r2.
const octNorm = (dx: number, dy: number) => Math.max(Math.abs(dx), Math.abs(dy), (Math.abs(dx) + Math.abs(dy)) / S2);

/** Diagonal octagon stacking: octagons sit on a 45° checkerboard with pitch p = W/√2
 * (cells where i + j is even), so each one shares its slanted edges with its diagonal
 * neighbours. Tiles fill row by row; an open tile becomes one big octagon whose slanted
 * edges touch the neighbours k steps away, and the others flow around it. */
export function diagLayout(n: number, avail: number, open: number | null, anchor: Cell | null): DiagLayout {
  const target = Math.min(230, Math.max(150, avail / 6));
  const cols = Math.max(3, Math.floor((avail - target) / (target / S2)) + 1);
  const W = Math.floor(avail / ((cols - 1) / S2 + 1)), p = W / S2, R = W / 2;
  const span = (cols - 1) * p + W;
  let big: (Cell & { Rb: number }) | null = null;
  if (open !== null) {
    const maxBig = Math.min(span, Math.max(3 * W + 1, 580, avail * 0.5));
    let k = 3;
    while (k > 1.5 && (2 * k - 1) * W > maxBig) k -= 0.5;
    const Rb = k * W - R, lo = Math.ceil((Rb - R) / p - 1e-6), hi = Math.floor(((cols - 1) * p - (Rb - R)) / p + 1e-6);
    const i = Math.min(Math.max(anchor?.i ?? lo, lo), Math.max(lo, hi));
    let j = Math.max(anchor?.j ?? lo, lo);
    if ((i + j) % 2) j += 1;
    big = { i, j, Rb };
  }
  const blocked = (i: number, j: number) => big !== null && octNorm((i - big.i) * p, (j - big.j) * p) < big.Rb + R - 1;
  const at = (c: Cell, size: number): Placed => ({ ...c, x: c.i * p + R - size / 2, y: c.j * p + R - size / 2, size });
  const tiles: Placed[] = [];
  let i = 0, j = 0, maxJ = 0;
  const next = (): Cell => {
    for (;;) {
      if (i >= cols) { i = 0; j += 1; }
      const c = { i, j };
      i += 1;
      if ((c.i + c.j) % 2 === 0 && !blocked(c.i, c.j)) return c;
    }
  };
  for (let t = 0; t < n; t++) {
    if (t === open && big) {
      tiles.push(at(big, 2 * big.Rb));
      maxJ = Math.max(maxJ, big.j + Math.ceil((big.Rb - R) / p));
      continue;
    }
    const c = next();
    tiles.push(at(c, W));
    maxJ = Math.max(maxJ, c.j);
  }
  const used = new Set(tiles.filter((_, t) => t !== open).map((c) => `${c.i},${c.j}`));
  const ghosts: Placed[] = [];
  for (let gj = 0; gj <= maxJ; gj++)
    for (let gi = gj % 2; gi < cols; gi += 2)
      if (!used.has(`${gi},${gj}`) && !blocked(gi, gj)) ghosts.push(at({ i: gi, j: gj }, W));
  return { W, cols, tiles, ghosts, width: Math.round(span), height: Math.round(maxJ * p + W) };
}

function Symbol({ info, className }: { info: EquipmentInfo; className?: string }) {
  // Catalog symbols are static strings from equipmentCatalog.ts, never user input.
  return <svg viewBox="-6 -6 172 116" className={className} aria-hidden="true" dangerouslySetInnerHTML={{ __html: info.symbol }} />;
}

function Detail({ e, onClose }: { e: EquipmentInfo; onClose: () => void }) {
  return (
    <div className="odet">
      <button type="button" className="tclose" aria-label="Close" onClick={onClose}>
        ×
      </button>
      <div className="ohead">
        <div className="eqart">
          <Symbol info={e} />
        </div>
        <div>
          <span className="tg">{e.group}</span>
          <h2>{e.name}</h2>
          <code className="kindchip">{e.kind}</code>
        </div>
      </div>
      <p>{e.description}</p>
      <div className="ocols">
        <dl className="kv">
          <dt>Ports</dt>
          <dd className="num">
            {e.inlets.join(", ")} → {e.outlets.join(", ")}
          </dd>
          <dt>Calculates</dt>
          <dd>{e.calculates}</dd>
        </dl>
        <dl className="kv">
          <dt>Sizing</dt>
          <dd>{e.sizer ?? "No sizer yet"}</dd>
        </dl>
      </div>
      <dl className="kv">
        <dt>Inputs</dt>
        <dd>
          {e.inputs.length ? (
            e.inputs.map(([k, l, note]) => (
              <span key={k} className="oin">
                <code>{k}</code> {l} <span className="muted">· {note}</span>
              </span>
            ))
          ) : (
            <span className="muted">None. It only needs its inlet streams.</span>
          )}
        </dd>
      </dl>
      {e.pid.length > 0 && (
        <div className="chips">
          {e.pid.map((r) => (
            <span key={r} className="chip ok">
              <span className="dot" />
              {r}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

/** Catalog of every unit operation the engine registers, as diagonally stacked octagons. */
export function EquipmentView() {
  const [items, setItems] = useState<EquipmentInfo[]>(() => catalogFor(undefined));
  const [open, setOpen] = useState<number | null>(null);
  const [anchor, setAnchor] = useState<Cell | null>(null);
  const [avail, setAvail] = useState(1100);
  const wrap = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let live = true;
    api
      .getMeta()
      .then((m) => live && m.unit && setItems(catalogFor(m.unit)))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);

  useLayoutEffect(() => {
    const el = wrap.current!;
    const measure = () => el.clientWidth > 0 && setAvail(el.clientWidth);
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    if (open === null) return;
    const onKey = (ev: KeyboardEvent) => ev.key === "Escape" && setOpen(null);
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  const L = diagLayout(items.length, avail, open, anchor);
  const pos = (c: Placed): CSSProperties => ({ left: c.x, top: c.y, width: c.size, height: c.size });

  return (
    <section className="page">
      <div className="pagehead">
        <div>
          <h1>Equipment</h1>
          <p>Every unit operation our simulation engine currently supports.</p>
        </div>
      </div>
      <div className="octwrap" ref={wrap}>
        <div className="octgrid" style={{ width: L.width, height: L.height, "--w": `${L.W}px` } as CSSProperties}>
          {L.ghosts.map((g) => (
            <span key={`g${g.i},${g.j}`} className="otile ghost" style={pos(g)} aria-hidden="true" />
          ))}
          {items.map((e, t) => {
            const c = L.tiles[t], isOpen = t === open;
            return (
              <div key={e.kind} className={"otile" + (isOpen ? " open" : "")} style={pos(c)} data-kind={e.kind}>
                {isOpen ? (
                  <Detail e={e} onClose={() => setOpen(null)} />
                ) : (
                  <button
                    type="button"
                    className="osum"
                    aria-expanded="false"
                    onClick={() => {
                      setAnchor({ i: c.i, j: c.j });
                      setOpen(t);
                    }}
                  >
                    <Symbol info={e} className="tsym" />
                    <span className="oname">{e.name}</span>
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
