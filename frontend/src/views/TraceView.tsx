import katex from "katex";
import "katex/dist/katex.min.css";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type RefObject } from "react";
import { api, type AuditFinding, type AuditReport, type Citation, type OpNode, type TraceGraph, type TraceTarget, type ValueNode } from "../api/client";
import { layoutTrace, makeTarget, sourceKey, targetOf, traceSources, OP_LABEL_CHARS, VALUE_LABEL_CHARS, VALUE_R, type LaidEdge, type LaidNode } from "../trace";
import { formatNumber, toDegC, toKmolH, toKPaG, toKw } from "../units";

const QUALITIES = ["cited", "user", "estimated", "derived", "uncited"] as const;
const NO_IDS: ReadonlySet<string> = new Set();

const clip = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

/** A number in user units (frontend/AGENTS.md) when the SI unit and property say what it is:
 * absolute temperatures and pressures, molar flows, powers. Otherwise null (shown in SI). */
function inUserUnits(value: number, unit: string, prop: string | null | undefined): string | null {
  const leaf = (prop ?? "").split(".").pop() ?? "";
  if (unit === "K" && (leaf === "T" || leaf.startsWith("T_"))) return `${toDegC(value)} degC`;
  if (unit === "Pa" && leaf === "P") return `${toKPaG(value)} kPa(g)`;
  if (unit === "mol/s") return `${toKmolH(value)} kmol/h`;
  if (unit === "W") return `${toKw(value)} kW`;
  return null;
}

/** One-line form of a value node's value, e.g. "20 degC (293.15 K)". */
export function formatTraceValue(v: ValueNode): string {
  const x = v.value;
  if (x === null || x === undefined) return "—";
  if (typeof x === "string") return x;
  if (typeof x === "number") {
    const si = `${formatNumber(x)}${v.unit && v.unit !== "1" ? ` ${v.unit}` : ""}`;
    const user = inUserUnits(x, v.unit, v.prop);
    return user ? `${user} (${si})` : si;
  }
  if (Array.isArray(x)) return `${x.length} × ${x[0]?.length ?? 0} matrix`;
  return `${Object.keys(x).length} components`;
}

function ValueTable({ value }: { value: ValueNode["value"] }) {
  if (Array.isArray(value)) {
    return (
      <div className="tr-scroll">
        <table className="mini-t">
          <tbody>
            {value.map((row, i) => (
              <tr key={i}>
                {row.map((c, j) => (
                  <td key={j}>{formatNumber(c)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  if (value && typeof value === "object") {
    return (
      <div className="tr-scroll">
        <table className="mini-t">
          <tbody>
            {Object.entries(value).map(([k, c]) => (
              <tr key={k}>
                <th scope="row">{k}</th>
                <td>{formatNumber(c)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  return null;
}

function CitationBlock({ c }: { c: Citation }) {
  return (
    <div className="tr-cite">
      <p>{c.citation}</p>
      <dl className="kv">
        <dt>Source</dt>
        <dd>
          <code>{c.source}</code>
        </dd>
        {c.doi && (
          <>
            <dt>DOI</dt>
            <dd>
              <a href={`https://doi.org/${c.doi}`} target="_blank" rel="noreferrer">
                {c.doi}
              </a>
            </dd>
          </>
        )}
        {c.url && (
          <>
            <dt>URL</dt>
            <dd>
              <a href={c.url} target="_blank" rel="noreferrer">
                {c.url}
              </a>
            </dd>
          </>
        )}
        {c.table && (
          <>
            <dt>Table</dt>
            <dd>{c.table}</dd>
          </>
        )}
        {c.reference && (
          <>
            <dt>Reference</dt>
            <dd>{c.reference}</dd>
          </>
        )}
        {c.grade && (
          <>
            <dt>Grade</dt>
            <dd>{c.grade}</dd>
          </>
        )}
      </dl>
    </div>
  );
}

function ValueDetail({ v }: { v: ValueNode }) {
  return (
    <div className="tr-detail" aria-label="Value detail">
      <span className="tg">value · {v.kind}</span>
      <h3>{v.label}</h3>
      <p className="tr-big">{formatTraceValue(v)}</p>
      <ValueTable value={v.value} />
      <div className="chips">
        <span className={`chip tr-q q-${v.quality}`}>
          <span className="dot" />
          {v.quality}
        </span>
        {v.stream && <span className="chip">{v.stream}</span>}
        {v.unit_tag && <span className="chip">{v.unit_tag}</span>}
        {v.prop && <span className="chip">{v.prop}</span>}
      </div>
      <h4>Citation</h4>
      {v.citation ? (
        <CitationBlock c={v.citation} />
      ) : v.quality === "derived" ? (
        <p className="muted">Computed: its sources are the inputs upstream in the graph.</p>
      ) : (
        <p className="chip bad">No citation</p>
      )}
      {v.note && (
        <>
          <h4>Note</h4>
          <p>{v.note}</p>
        </>
      )}
    </div>
  );
}

function Equation({ latex }: { latex: string }) {
  // KaTeX escapes its input; throwOnError:false renders a bad formula in red instead of throwing.
  const html = useMemo(() => katex.renderToString(latex, { throwOnError: false, displayMode: true }), [latex]);
  return <div className="tr-eq" data-latex={latex} dangerouslySetInnerHTML={{ __html: html }} />;
}

function OpDetail({ o }: { o: OpNode }) {
  return (
    <div className="tr-detail" aria-label="Operation detail">
      <span className="tg">operation · {o.method}</span>
      <h3>{o.name}</h3>
      <p className="muted">{o.label}</p>
      {o.latex ? <Equation latex={o.latex} /> : <p className="muted">No equation recorded.</p>}
      <dl className="kv ocols">
        {o.unit_tag && (
          <>
            <dt>Unit</dt>
            <dd>{o.unit_tag}</dd>
          </>
        )}
        {o.iterations != null && (
          <>
            <dt>Iterations</dt>
            <dd>{o.iterations}</dd>
          </>
        )}
        {o.residual != null && (
          <>
            <dt>Residual</dt>
            <dd>{o.residual.toExponential(3)}</dd>
          </>
        )}
        {o.converged != null && (
          <>
            <dt>Converged</dt>
            <dd>{o.converged ? "yes" : "no"}</dd>
          </>
        )}
        {o.calls != null && (
          <>
            <dt>Calls</dt>
            <dd>{o.calls}</dd>
          </>
        )}
      </dl>
      <h4>References</h4>
      {o.references.length ? (
        o.references.map((c, i) => <CitationBlock key={`${c.source}-${i}`} c={c} />)
      ) : (
        <p className="chip bad">No reference</p>
      )}
      {o.note && (
        <>
          <h4>Note</h4>
          <p>{o.note}</p>
        </>
      )}
    </div>
  );
}

// --- Export --------------------------------------------------------------------------

/** Presentation properties copied from computed style, so the file renders without our CSS. */
const INLINE_PROPS = [
  "fill",
  "fill-opacity",
  "stroke",
  "stroke-width",
  "stroke-dasharray",
  "stroke-opacity",
  "opacity",
  "font-family",
  "font-size",
  "font-weight",
  "paint-order",
];

/** Standalone SVG text of a rendered SVG element, with computed styles inlined. */
export function serializeSvg(svg: SVGSVGElement): string {
  const clone = svg.cloneNode(true) as SVGSVGElement;
  const src = [svg, ...Array.from(svg.querySelectorAll("*"))];
  const dst = [clone, ...Array.from(clone.querySelectorAll("*"))];
  const computed = new Map<Element, CSSStyleDeclaration>();
  src.forEach((el, i) => {
    const cs = getComputedStyle(el);
    computed.set(el, cs);
    // Inherited values repeat down the tree; write only what differs from the parent.
    const parent = el === svg ? undefined : computed.get(el.parentElement!);
    const decl = INLINE_PROPS.map((p) => [p, cs.getPropertyValue(p)] as const)
      .filter(([p, v]) => v !== "" && (p === "opacity" ? v !== "1" : v !== parent?.getPropertyValue(p)))
      .map(([p, v]) => `${p}:${v}`)
      .join(";");
    if (decl) dst[i].setAttribute("style", decl);
    dst[i].removeAttribute("tabindex");
  });
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  const bg = getComputedStyle(svg.parentElement ?? svg).getPropertyValue("background-color");
  if (bg) {
    const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    rect.setAttribute("width", "100%");
    rect.setAttribute("height", "100%");
    rect.setAttribute("fill", bg);
    clone.insertBefore(rect, clone.firstChild);
  }
  return `<?xml version="1.0" encoding="UTF-8"?>\n${new XMLSerializer().serializeToString(clone)}`;
}

function download(filename: string, type: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// --- Graph ---------------------------------------------------------------------------

type Pt = [number, number];

/** Cubic Bezier control points of an edge (left to right; a feedback edge dips below). */
function edgeCurve(e: LaidEdge): [Pt, Pt, Pt, Pt] {
  if (e.feedback) {
    const dip = Math.max(e.y1, e.y2) + 60;
    return [[e.x1, e.y1], [e.x1 + 60, dip], [e.x2 - 60, dip], [e.x2, e.y2]];
  }
  const mx = (e.x1 + e.x2) / 2;
  return [[e.x1, e.y1], [mx, e.y1], [mx, e.y2], [e.x2, e.y2]];
}

function bezierAt([p0, p1, p2, p3]: [Pt, Pt, Pt, Pt], t: number): Pt {
  const u = 1 - t;
  const f = (i: 0 | 1) => u * u * u * p0[i] + 3 * u * u * t * p1[i] + 3 * u * t * t * p2[i] + t * t * t * p3[i];
  return [f(0), f(1)];
}

interface GraphProps {
  graph: TraceGraph;
  svgRef: RefObject<SVGSVGElement>;
  zoom: number;
  selected: string | null;
  culprits: ReadonlySet<string>;
  onSelect: (id: string) => void;
  onHover: (id: string | null) => void;
}

function TraceSvg({ graph, svgRef, zoom, selected, culprits, onSelect, onHover }: GraphProps) {
  const lay = useMemo(() => layoutTrace(graph), [graph]);
  const values = useMemo(() => new Map(graph.values.map((v) => [v.id, v])), [graph]);
  const ops = useMemo(() => new Map(graph.ops.map((o) => [o.id, o])), [graph]);
  const focus = graph.meta.focus;
  const key = (id: string) => (e: KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onSelect(id);
    }
  };
  const nodeProps = (n: LaidNode, name: string) => ({
    "data-node": n.id,
    role: "button",
    tabIndex: 0,
    "aria-label": name,
    "aria-pressed": n.id === selected,
    transform: `translate(${n.x},${n.y})`,
    onClick: () => onSelect(n.id),
    onKeyDown: key(n.id),
    onMouseEnter: () => onHover(n.id),
    onMouseLeave: () => onHover(null),
    onFocus: () => onHover(n.id),
    onBlur: () => onHover(null),
  });
  const flags = (id: string) => `${id === focus ? " focus" : ""}${id === selected ? " sel" : ""}${culprits.has(id) ? " culprit" : ""}`;
  return (
    <svg
      ref={svgRef}
      className="tr-svg"
      width={Math.round(lay.width * zoom)}
      height={Math.round(lay.height * zoom)}
      viewBox={`0 0 ${lay.width} ${lay.height}`}
      role="group"
      aria-label="Trace graph"
    >
      <defs>
        <marker id="tr-arrow" viewBox="0 0 8 8" refX="8" refY="4" markerWidth="7" markerHeight="7" orient="auto">
          <path d="M0,0 L8,4 L0,8 z" className="tr-arrowhead" />
        </marker>
      </defs>
      <g className="tr-edges">
        {lay.edges.map((e, i) => {
          const c = edgeCurve(e);
          // Label by the end that is not shared: next to the input value (role = its symbol
          // in the formula) or next to the produced value; many edges meet at an operation.
          const [lx, ly] = bezierAt(c, ops.has(e.source) ? 0.8 : 0.2);
          return (
            <g key={i} className={`tr-edge${e.feedback ? " feedback" : ""}${e.source === selected || e.target === selected ? " on" : ""}`}>
              <path d={`M${c[0]} C${c[1]} ${c[2]} ${c[3]}`} markerEnd="url(#tr-arrow)" />
              {e.role && (
                <text x={lx} y={ly - 4} textAnchor="middle">
                  {clip(e.role, 22)}
                </text>
              )}
            </g>
          );
        })}
      </g>
      <g className="tr-nodes">
        {lay.nodes.map((n) => {
          const v = values.get(n.id);
          if (v) {
            return (
              <g key={n.id} className={`tr-node tr-value q-${v.quality}${flags(n.id)}`} {...nodeProps(n, `${v.label} (${v.kind}, ${v.quality})`)}>
                <title>{`${v.label}\n${formatTraceValue(v)}\n${v.kind} · ${v.quality}`}</title>
                {(v.quality === "uncited" || culprits.has(n.id) || n.id === focus) && <circle className="tr-ring" r={VALUE_R + 5} />}
                <circle className="tr-dot" r={VALUE_R} />
                <text className="tr-kind" textAnchor="middle" dy="0.35em">
                  {v.quality === "uncited" ? "!" : v.kind[0].toUpperCase()}
                </text>
                <text className="tr-label" textAnchor="middle" y={VALUE_R + 14}>
                  {clip(v.label, VALUE_LABEL_CHARS)}
                </text>
              </g>
            );
          }
          const o = ops.get(n.id)!;
          return (
            <g key={n.id} className={`tr-node tr-op${o.references.length ? "" : " noref"}${flags(n.id)}`} {...nodeProps(n, `operation ${o.name}`)}>
              <title>{`${o.name}\n${o.label}`}</title>
              <rect x={-n.w / 2} y={-n.h / 2} width={n.w} height={n.h} rx={9} />
              <text textAnchor="middle" dy="0.35em">
                {clip(o.name || o.label, OP_LABEL_CHARS)}
              </text>
            </g>
          );
        })}
      </g>
    </svg>
  );
}

// --- View ----------------------------------------------------------------------------

function AuditPanel({ audit, active, onPick }: { audit: AuditReport; active: string | null; onPick: (f: AuditFinding) => void }) {
  const errors = audit.findings.filter((f) => f.severity === "error").length;
  return (
    <section className="tr-audit" aria-label="Audit">
      <h2>Audit</h2>
      <div className="stats">
        <span className="stat">
          <b>{audit.outputs}</b> outputs
        </span>
        <span className="stat">
          <b>{audit.clean}</b> clean
        </span>
        <span className="stat">
          <b>{errors}</b> errors
        </span>
        <span className="stat">
          <b>{audit.findings.length - errors}</b> warnings
        </span>
      </div>
      <ul className="tr-findings">
        {audit.findings.map((f) => (
          <li key={f.node}>
            <button type="button" className="tr-finding" aria-pressed={f.node === active} onClick={() => onPick(f)}>
              <span className={`chip ${f.severity === "error" ? "bad" : "warn"}`}>{f.severity}</span> <strong>{f.label}</strong>
              <small>{f.reasons.join("; ")}</small>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Calculation provenance (docs/provenance.md section 8): pick a reported value, see the
 * upstream graph of everything it depends on, inspect citations and equations, audit. */
export function TraceView({ target: requested = null }: { target?: TraceTarget | null }) {
  const [full, setFull] = useState<TraceGraph | null>(null);
  const [audit, setAudit] = useState<AuditReport | null>(null);
  const [target, setTarget] = useState<TraceTarget | null>(requested);
  const [graph, setGraph] = useState<TraceGraph | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);
  const [finding, setFinding] = useState<AuditFinding | null>(null);
  const [zoom, setZoom] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  // A click-through from another view (Results) re-targets an open Trace view.
  useEffect(() => {
    if (requested) {
      setTarget(requested);
      setFinding(null);
    }
  }, [requested]);

  useEffect(() => {
    let live = true;
    Promise.all([api.trace(), api.traceAudit()])
      .then(([g, a]) => {
        if (!live) return;
        setFull(g);
        setAudit(a);
        setTarget((t) => {
          if (t) return t;
          const first = traceSources(g)[0];
          return first ? makeTarget(first, first.props[0]) : null;
        });
      })
      .catch((e: Error) => live && setError(e.message));
    return () => {
      live = false;
    };
  }, []);

  useEffect(() => {
    if (!target) return;
    let live = true;
    setError(null);
    api
      .trace(target)
      .then((g) => {
        if (!live) return;
        setGraph(g);
        setSelected(g.meta.focus ?? null);
      })
      .catch((e: Error) => {
        if (!live) return;
        setGraph(null);
        setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [target]);

  const sources = useMemo(() => (full ? traceSources(full) : []), [full]);
  const source = target ? sources.find((s) => s.key === sourceKey(target)) : undefined;
  const nodes = useMemo(() => {
    const m = new Map<string, { value?: ValueNode; op?: OpNode }>();
    for (const v of graph?.values ?? []) m.set(v.id, { value: v });
    for (const o of graph?.ops ?? []) m.set(o.id, { op: o });
    return m;
  }, [graph]);
  const shown = nodes.get(hovered ?? "") ?? nodes.get(selected ?? "");
  const culprits = finding && graph?.meta.focus === finding.node ? new Set(finding.culprits) : NO_IDS;

  const retarget = (t: TraceTarget) => {
    setFinding(null);
    setTarget(t);
  };
  const pickSource = (key: string) => {
    const s = sources.find((x) => x.key === key);
    if (s) retarget(makeTarget(s, target && s.props.includes(target.prop) ? target.prop : s.props[0]));
  };
  const pickFinding = (f: AuditFinding) => {
    const v = full?.values.find((x) => x.id === f.node);
    const t = v && targetOf(v);
    if (!t) return;
    setFinding(f);
    setTarget(t);
  };

  const focusLabel = graph?.values.find((v) => v.id === graph.meta.focus)?.label ?? "trace";
  const fileBase = `trace-${focusLabel.replace(/[^A-Za-z0-9._-]+/g, "_")}`;

  return (
    <div className="trace">
      <div className="tr-bar" role="group" aria-label="Value to trace">
        <label className="field">
          Stream or unit
          <select value={source?.key ?? ""} onChange={(e) => pickSource(e.target.value)} disabled={!sources.length}>
            {!source && <option value="">—</option>}
            {(["stream", "unit"] as const).map((kind) => (
              <optgroup key={kind} label={kind === "stream" ? "Streams" : "Units"}>
                {sources
                  .filter((s) => s.kind === kind)
                  .map((s) => (
                    <option key={s.key} value={s.key}>
                      {s.id}
                    </option>
                  ))}
              </optgroup>
            ))}
          </select>
        </label>
        <label className="field">
          Property
          <select value={target?.prop ?? ""} onChange={(e) => source && retarget(makeTarget(source, e.target.value))} disabled={!source}>
            {(source?.props ?? []).map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
        <span className="grow" />
        <button type="button" className="btn ob" aria-label="Zoom out" onClick={() => setZoom((z) => Math.max(0.25, z / 1.25))}>
          −
        </button>
        <button type="button" className="btn ob" aria-label="Reset zoom" onClick={() => setZoom(1)}>
          {Math.round(zoom * 100)}%
        </button>
        <button type="button" className="btn ob" aria-label="Zoom in" onClick={() => setZoom((z) => Math.min(4, z * 1.25))}>
          +
        </button>
        <button
          type="button"
          className="btn ob"
          disabled={!graph}
          onClick={() => svgRef.current && download(`${fileBase}.svg`, "image/svg+xml", serializeSvg(svgRef.current))}
        >
          Export SVG
        </button>
        <button type="button" className="btn ob" disabled={!graph} onClick={() => graph && download(`${fileBase}.json`, "application/json", JSON.stringify(graph, null, 2))}>
          Export JSON
        </button>
      </div>
      <div className="tr-legend" aria-label="Quality legend">
        {QUALITIES.map((q) => (
          <span key={q} className={`tr-q q-${q}`}>
            <svg width="14" height="14" aria-hidden="true">
              <circle cx="7" cy="7" r="5.5" className="tr-dot" />
            </svg>
            {q}
          </span>
        ))}
        {graph && (
          <span className="muted">
            {graph.values.length} values · {graph.ops.length} operations
          </span>
        )}
      </div>
      {error && (
        <p role="alert" className="chip bad">
          Trace failed: {error}
        </p>
      )}
      <div className="tr-grid">
        <div className="tr-canvas">
          {graph ? (
            <TraceSvg graph={graph} svgRef={svgRef} zoom={zoom} selected={selected} culprits={culprits} onSelect={setSelected} onHover={setHovered} />
          ) : (
            !error && <p className="placeholder">Loading trace…</p>
          )}
        </div>
        <aside className="tr-side">
          {shown?.value && <ValueDetail v={shown.value} />}
          {shown?.op && <OpDetail o={shown.op} />}
          {!shown && <p className="placeholder">Click a value or an operation for its detail.</p>}
          {audit && <AuditPanel audit={audit} active={finding?.node ?? null} onPick={pickFinding} />}
        </aside>
      </div>
    </div>
  );
}
