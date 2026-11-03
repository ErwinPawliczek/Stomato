import mockTrace from "../mocks/trace.json";
import { findOutput, layerNodes, layoutTrace, traceSources, upstream, type TraceGraph } from "./trace";

const full = mockTrace as TraceGraph;

function value(id: string, extra: Partial<TraceGraph["values"][number]> = {}): TraceGraph["values"][number] {
  return { id, label: id, value: 1, unit: "1", kind: "intermediate", quality: "derived", ...extra };
}
function op(id: string): TraceGraph["ops"][number] {
  return { id, label: id, method: "m", name: id, references: [] };
}
const edge = (source: string, target: string, feedback = false) => ({ source, target, role: "x", feedback });

test("layers are the longest path from the leaves and respect every edge's direction", () => {
  // a -> o1 -> b -> o2 -> c, plus a shortcut a -> o2: o2 must sit after b, not after a.
  const layer = layerNodes(["a", "b", "c", "o1", "o2"], [edge("a", "o1"), edge("o1", "b"), edge("b", "o2"), edge("a", "o2"), edge("o2", "c")]);
  expect(Object.fromEntries(layer)).toEqual({ a: 0, o1: 1, b: 2, o2: 3, c: 4 });
});

test("feedback edges are ignored for layering, so a recycle loop still lays out as a DAG", () => {
  // feed -> mix -> s1 -> split -> s2, and s2 -> mix closes the loop as feedback.
  const edges = [edge("feed", "mix"), edge("mix", "s1"), edge("s1", "split"), edge("split", "s2"), edge("s2", "mix", true)];
  const layer = layerNodes(["feed", "mix", "s1", "split", "s2"], edges);
  expect(Object.fromEntries(layer)).toEqual({ feed: 0, mix: 1, s1: 2, split: 3, s2: 4 });
});

test("layout places every node, puts sources left of targets, and keeps the feedback edge drawn", () => {
  const g: TraceGraph = {
    values: [value("feed", { kind: "input", quality: "user" }), value("s1"), value("s2", { kind: "output" })],
    ops: [op("mix"), op("split")],
    edges: [edge("feed", "mix"), edge("mix", "s1"), edge("s1", "split"), edge("split", "s2"), edge("s2", "mix", true)],
    meta: {},
  };
  const lay = layoutTrace(g);
  expect(lay.nodes).toHaveLength(5);
  const at = new Map(lay.nodes.map((n) => [n.id, n]));
  for (const e of g.edges.filter((e) => !e.feedback)) expect(at.get(e.source)!.x).toBeLessThan(at.get(e.target)!.x);
  expect(lay.edges).toHaveLength(5);
  expect(at.get("mix")!.type).toBe("op");
  expect(at.get("feed")!.type).toBe("value");
});

test("the barycentre pass removes an avoidable crossing", () => {
  // Leaves a, b feed ops in crossed order: a -> o2, b -> o1. After ordering, o2 sits beside a.
  const g: TraceGraph = {
    values: [value("a"), value("b")],
    ops: [op("o1"), op("o2")],
    edges: [edge("a", "o2"), edge("b", "o1")],
    meta: {},
  };
  const at = new Map(layoutTrace(g).nodes.map((n) => [n.id, n]));
  expect(Math.sign(at.get("a")!.y - at.get("b")!.y)).toBe(Math.sign(at.get("o2")!.y - at.get("o1")!.y));
});

test("on the real slice graph every non-feedback edge points left to right", () => {
  const sub = upstream(full, findOutput(full, { unit: "T-101", prop: "info.water_removed_kg_h" })!.id);
  const lay = layoutTrace(sub);
  const at = new Map(lay.nodes.map((n) => [n.id, n]));
  expect(lay.nodes.length).toBe(sub.values.length + sub.ops.length);
  for (const e of sub.edges.filter((e) => !e.feedback)) expect(at.get(e.source)!.layer).toBeLessThan(at.get(e.target)!.layer);
});

test("upstream mirrors the backend: focus set, only ancestors kept", () => {
  const node = findOutput(full, { stream: "S-001", prop: "T" })!;
  const sub = upstream(full, node.id);
  expect(sub.meta.focus).toBe(node.id);
  expect(sub.values.some((v) => v.id === node.id)).toBe(true);
  const ids = new Set([...sub.values, ...sub.ops].map((n) => n.id));
  for (const e of sub.edges) expect(ids.has(e.source) && ids.has(e.target)).toBe(true);
  // A downstream stream never appears in S-001's trace.
  expect(sub.values.some((v) => v.stream === "S-006")).toBe(false);
});

test("picker sources list streams and units with base props first", () => {
  const sources = traceSources(full);
  const s1 = sources.find((s) => s.key === "stream:S-001")!;
  expect(s1.props.slice(0, 4)).toEqual(["T", "P", "molar_flow", "vapor_fraction"]);
  const k = sources.find((s) => s.key === "unit:K-101")!;
  expect(k.props).toContain("power_W");
  expect(k.props).toContain("info.pressure_ratio");
});
