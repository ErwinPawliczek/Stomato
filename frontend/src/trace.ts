// Pure helpers for the provenance trace graph (docs/provenance.md section 2): finding a
// reported value, cutting its upstream subgraph, the picker's choices, and the layered
// left-to-right layout the Trace view draws. No React, no I/O.
import type { components } from "./api/schema";

export type TraceGraph = components["schemas"]["TraceGraph"];
export type ValueNode = components["schemas"]["ValueNode"];
export type OpNode = components["schemas"]["OpNode"];
export type TraceEdge = components["schemas"]["Edge"];

/** One reported value: a stream property (`?stream=&prop=`) or a unit result (`?unit=&prop=`). */
export type TraceTarget = { stream: string; prop: string } | { unit: string; prop: string };

/** The output node for a target, mirroring the backend's `TraceGraph.find`. */
export function findOutput(graph: TraceGraph, target: TraceTarget): ValueNode | undefined {
  return graph.values.find((v) => {
    if (v.kind !== "output" || v.prop !== target.prop) return false;
    if ("stream" in target) return v.stream === target.stream;
    return v.stream == null && v.unit_tag === target.unit;
  });
}

/** The target an output node answers, or null for nodes that are not stream/unit results. */
export function targetOf(v: ValueNode): TraceTarget | null {
  if (v.kind !== "output" || !v.prop) return null;
  if (v.stream) return { stream: v.stream, prop: v.prop };
  if (v.unit_tag) return { unit: v.unit_tag, prop: v.prop };
  return null;
}

/** Everything `nodeId` depends on (itself included), mirroring the backend's
 * `TraceGraph.upstream`: walk edges backwards, keep meta, set meta.focus. */
export function upstream(graph: TraceGraph, nodeId: string): TraceGraph {
  const into = new Map<string, TraceEdge[]>();
  for (const e of graph.edges) {
    const list = into.get(e.target);
    if (list) list.push(e);
    else into.set(e.target, [e]);
  }
  const seen = new Set([nodeId]);
  const stack = [nodeId];
  const edges: TraceEdge[] = [];
  while (stack.length) {
    const id = stack.pop()!;
    for (const e of into.get(id) ?? []) {
      edges.push(e);
      if (!seen.has(e.source)) {
        seen.add(e.source);
        stack.push(e.source);
      }
    }
  }
  return {
    values: graph.values.filter((v) => seen.has(v.id)),
    ops: graph.ops.filter((o) => seen.has(o.id)),
    edges,
    meta: { ...graph.meta, focus: nodeId },
  };
}

/** Picker choices: every source (stream or unit) with the props it reports, sorted. */
export interface TraceSource {
  key: string; // "stream:S-001" | "unit:K-101"
  kind: "stream" | "unit";
  id: string;
  props: string[];
}

export function sourceKey(t: TraceTarget): string {
  return "stream" in t ? `stream:${t.stream}` : `unit:${t.unit}`;
}

export function makeTarget(source: TraceSource, prop: string): TraceTarget {
  return source.kind === "stream" ? { stream: source.id, prop } : { unit: source.id, prop };
}

export function traceSources(graph: TraceGraph): TraceSource[] {
  const byKey = new Map<string, TraceSource>();
  for (const v of graph.values) {
    const t = targetOf(v);
    if (!t) continue;
    const key = sourceKey(t);
    let s = byKey.get(key);
    if (!s) {
      s = "stream" in t ? { key, kind: "stream", id: t.stream, props: [] } : { key, kind: "unit", id: t.unit, props: [] };
      byKey.set(key, s);
    }
    if (!s.props.includes(t.prop)) s.props.push(t.prop);
  }
  // Base state first (T, P, flow, ...), then phase/info props alphabetically.
  const rank = (p: string) => {
    const i = ["T", "P", "molar_flow", "vapor_fraction", "enthalpy", "entropy", "composition", "duty_W", "power_W"].indexOf(p);
    return i < 0 ? 100 : i;
  };
  const out = [...byKey.values()];
  for (const s of out) s.props.sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));
  return out.sort((a, b) => a.kind.localeCompare(b.kind) || a.id.localeCompare(b.id));
}

// --- Layout -------------------------------------------------------------------------

export interface LaidNode {
  id: string;
  type: "value" | "op";
  layer: number;
  order: number;
  /** Centre. */
  x: number;
  y: number;
  /** Box size (a value's circle fits in w x h). */
  w: number;
  h: number;
}

export interface LaidEdge extends TraceEdge {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

export interface TraceLayout {
  nodes: LaidNode[];
  edges: LaidEdge[];
  width: number;
  height: number;
}

export const VALUE_R = 13;
/** Characters of a value label drawn under its circle (the rest is in the tooltip). */
export const VALUE_LABEL_CHARS = 30;
/** Characters of an operation name drawn in its box. */
export const OP_LABEL_CHARS = 32;
const OP_H = 30;
const COL_GAP = 110;
const SUB_GAP = 24;
const ROW_H = 58;
const PAD = 40;
/** A layer taller than this wraps into side-by-side sub-columns (leaf constants can be 60+). */
const MAX_ROWS = 18;

/** Width of an operation box for its label (text ~6.4 px/char at 11 px, clamped). */
export function opWidth(label: string): number {
  return Math.min(220, Math.max(90, Math.round(Math.min(label.length, OP_LABEL_CHARS) * 6.4 + 22)));
}

/** Width a value's label needs under its circle (~5.8 px/char at 10.5 px). */
function valueLabelWidth(label: string): number {
  return Math.round(Math.min(label.length, VALUE_LABEL_CHARS) * 5.8);
}

/**
 * Layer of every node = longest path from a leaf (a node without non-feedback inputs),
 * ignoring `feedback` edges so recycle loops do not create cycles. A residual cycle in a
 * malformed graph is broken by taking the stuck node with the fewest unresolved inputs.
 */
export function layerNodes(ids: string[], edges: TraceEdge[]): Map<string, number> {
  const known = new Set(ids);
  const dag = edges.filter((e) => !e.feedback && known.has(e.source) && known.has(e.target) && e.source !== e.target);
  const preds = new Map<string, string[]>(ids.map((id) => [id, []]));
  const succs = new Map<string, string[]>(ids.map((id) => [id, []]));
  for (const e of dag) {
    preds.get(e.target)!.push(e.source);
    succs.get(e.source)!.push(e.target);
  }
  const pending = new Map(ids.map((id) => [id, preds.get(id)!.length]));
  const layer = new Map<string, number>();
  const ready = ids.filter((id) => pending.get(id) === 0);
  while (layer.size < ids.length) {
    if (ready.length === 0) {
      // Cycle without a feedback mark: release the least-blocked remaining node.
      let best: string | null = null;
      for (const id of ids) if (!layer.has(id) && (best === null || pending.get(id)! < pending.get(best)!)) best = id;
      ready.push(best!);
    }
    const id = ready.shift()!;
    if (layer.has(id)) continue;
    const ps = preds.get(id)!.filter((p) => layer.has(p));
    layer.set(id, ps.length ? Math.max(...ps.map((p) => layer.get(p)!)) + 1 : 0);
    for (const s of succs.get(id)!) {
      pending.set(s, pending.get(s)! - 1);
      if (pending.get(s) === 0 && !layer.has(s)) ready.push(s);
    }
  }
  return layer;
}

/**
 * Layered left-to-right layout: columns from `layerNodes`, then a few barycentre sweeps
 * (down using predecessors, up using successors) to reduce edge crossings.
 */
export function layoutTrace(graph: TraceGraph, sweeps = 4): TraceLayout {
  const ids = [...graph.values.map((v) => v.id), ...graph.ops.map((o) => o.id)];
  const opLabel = new Map(graph.ops.map((o) => [o.id, o.name || o.label]));
  const layer = layerNodes(ids, graph.edges);
  const nLayers = ids.length ? Math.max(...ids.map((id) => layer.get(id)!)) + 1 : 0;
  const cols: string[][] = Array.from({ length: nLayers }, () => []);
  for (const id of ids) cols[layer.get(id)!].push(id);

  const dag = graph.edges.filter((e) => !e.feedback && layer.has(e.source) && layer.has(e.target));
  const preds = new Map<string, string[]>();
  const succs = new Map<string, string[]>();
  for (const e of dag) {
    (preds.get(e.target) ?? preds.set(e.target, []).get(e.target)!).push(e.source);
    (succs.get(e.source) ?? succs.set(e.source, []).get(e.source)!).push(e.target);
  }
  const pos = new Map<string, number>();
  const index = () => cols.forEach((col) => col.forEach((id, i) => pos.set(id, col.length > 1 ? i / (col.length - 1) : 0.5)));
  index();
  const reorder = (col: string[], nbrs: Map<string, string[]>) => {
    const bary = new Map<string, number>();
    col.forEach((id, i) => {
      const ns = nbrs.get(id) ?? [];
      bary.set(id, ns.length ? ns.reduce((s, n) => s + pos.get(n)!, 0) / ns.length : col.length > 1 ? i / (col.length - 1) : 0.5);
    });
    col.sort((a, b) => bary.get(a)! - bary.get(b)!);
  };
  for (let s = 0; s < sweeps; s++) {
    for (let l = 1; l < nLayers; l++) {
      reorder(cols[l], preds);
      index();
    }
    for (let l = nLayers - 2; l >= 0; l--) {
      reorder(cols[l], succs);
      index();
    }
  }

  // Shape width (where edges attach) vs. the width the node needs in its column (label).
  const valueLabel = new Map(graph.values.map((v) => [v.id, v.label]));
  const shapeW = (id: string) => (opLabel.has(id) ? opWidth(opLabel.get(id)!) : 2 * VALUE_R);
  const spanW = (id: string) => Math.max(shapeW(id), valueLabelWidth(valueLabel.get(id) ?? ""));
  // A tall layer wraps into k sub-columns of `rows` nodes, keeping the barycentre order
  // top-to-bottom within each; all sub-columns stay in the same layer.
  const wrapped = cols.map((col) => {
    const k = Math.max(1, Math.ceil(col.length / MAX_ROWS));
    const rows = Math.ceil(col.length / k);
    return Array.from({ length: k }, (_, j) => col.slice(j * rows, (j + 1) * rows));
  });
  const tallest = Math.max(0, ...wrapped.flatMap((subs) => subs.map((c) => c.length)));
  const height = Math.max(1, tallest) * ROW_H + 2 * PAD;
  const nodes: LaidNode[] = [];
  const byId = new Map<string, LaidNode>();
  let x = PAD;
  wrapped.forEach((subs, l) => {
    let order = 0;
    subs.forEach((col, j) => {
      const w = Math.max(2 * VALUE_R, ...col.map(spanW));
      const cx = x + w / 2;
      const top = PAD + ((tallest - col.length) * ROW_H) / 2;
      col.forEach((id, i) => {
        const isOp = opLabel.has(id);
        const n: LaidNode = {
          id,
          type: isOp ? "op" : "value",
          layer: l,
          order: order++,
          x: cx,
          y: top + i * ROW_H + ROW_H / 2,
          w: shapeW(id),
          h: isOp ? OP_H : 2 * VALUE_R,
        };
        nodes.push(n);
        byId.set(id, n);
      });
      x += w + (j < subs.length - 1 ? SUB_GAP : COL_GAP);
    });
  });
  const width = Math.max(x - COL_GAP + PAD, 2 * PAD);
  const edges: LaidEdge[] = graph.edges
    .filter((e) => byId.has(e.source) && byId.has(e.target))
    .map((e) => {
      const a = byId.get(e.source)!;
      const b = byId.get(e.target)!;
      return { ...e, x1: a.x + a.w / 2, y1: a.y, x2: b.x - b.w / 2, y2: b.y };
    });
  return { nodes, edges, width, height };
}
