import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { vi } from "vitest";
import { api } from "../api/client";
import mockTrace from "../../mocks/trace.json";
import { findOutput, upstream, type TraceGraph } from "../trace";
import mockAudit from "../../mocks/trace-audit.json";
import { ResultsView } from "./ResultsView";
import { TraceView } from "./TraceView";

// jsdom's Blob has no .text(); read it through FileReader instead.
const readBlob = (b: Blob) =>
  new Promise<string>((resolve) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result as string);
    r.readAsText(b);
  });
const graph = () => screen.findByRole("group", { name: "Trace graph" });
const node = (svg: HTMLElement, id: string) => svg.querySelector(`[data-node="${id}"]`);

test("renders the first stream value's upstream graph and the audit counts from the mocks", async () => {
  render(<TraceView />);
  const svg = await graph();
  // Default pick: first stream, first property (S-001 T), drawn as its upstream subgraph.
  const sub = upstream(mockTrace as TraceGraph, findOutput(mockTrace as TraceGraph, { stream: "S-001", prop: "T" })!.id);
  expect((screen.getByLabelText("Stream or unit") as HTMLSelectElement).value).toBe("stream:S-001");
  expect((screen.getByLabelText("Property") as HTMLSelectElement).value).toBe("T");
  expect(within(svg).getByRole("button", { name: "S-001 T (output, derived)" })).toBeTruthy();
  expect(svg.querySelectorAll(".tr-value").length).toBe(sub.values.length);
  expect(svg.querySelectorAll(".tr-op").length).toBe(sub.ops.length);
  expect(sub.ops.length).toBeGreaterThan(0);
  // Edges carry their role symbol.
  expect(within(svg).getAllByText("z").length).toBeGreaterThan(0);
  // The focused value starts selected: its detail is shown in user units (293.15 K -> 20 degC).
  expect(screen.getByLabelText("Value detail").textContent).toContain("20 degC (293.15 K)");

  const audit = screen.getByRole("region", { name: "Audit" });
  expect(audit.textContent).toContain(`${mockAudit.outputs} outputs`);
  expect(audit.textContent).toContain(`${mockAudit.clean} clean`);
  expect(within(audit).getAllByRole("button")).toHaveLength(mockAudit.findings.length);
});

test("picking a unit and a result traces that value", async () => {
  render(<TraceView />);
  await graph();
  fireEvent.change(screen.getByLabelText("Stream or unit"), { target: { value: "unit:K-101" } });
  fireEvent.change(screen.getByLabelText("Property"), { target: { value: "power_W" } });
  const svg = await graph();
  const focus = await within(svg).findByRole("button", { name: /^K-101 power_W \(output/ });
  expect(focus.classList.contains("focus")).toBe(true);
  const sub = upstream(mockTrace as TraceGraph, findOutput(mockTrace as TraceGraph, { unit: "K-101", prop: "power_W" })!.id);
  expect(svg.querySelectorAll(".tr-node").length).toBe(sub.values.length + sub.ops.length);
});

test("clicking a value node shows its quality and full citation with a DOI link", async () => {
  render(<TraceView target={{ stream: "S-001", prop: "T" }} />);
  const svg = await graph();
  fireEvent.click(within(svg).getByRole("button", { name: "C1 Tc (constant, cited)" }));
  const detail = screen.getByLabelText("Value detail");
  expect(within(detail).getByRole("heading", { name: "C1 Tc" })).toBeTruthy();
  expect(detail.textContent).toContain("cited");
  expect(detail.textContent).toContain("Huber, M.L., Lemmon, E.W.");
  const doi = within(detail).getByRole("link", { name: "10.1021/acs.iecr.2c01427" });
  expect(doi.getAttribute("href")).toBe("https://doi.org/10.1021/acs.iecr.2c01427");
});

// A graph with one uncited leaf: the audit flags the output resting on it.
const uncitedGraph: TraceGraph = {
  values: [
    { id: "a", label: "X-1 k (unattributed)", value: 2.5, unit: "1", kind: "intermediate", quality: "uncited" },
    { id: "u", label: "X-1 F (spec)", value: 4, unit: "mol/s", kind: "input", quality: "user", stream: "S-1", prop: "spec.molar_flow",
      citation: { source: "user", citation: "User input: feed S-1 molar_flow" } },
    { id: "y", label: "X-1 duty_W", value: 10, unit: "W", kind: "output", quality: "derived", unit_tag: "X-1", prop: "duty_W" },
  ],
  ops: [{ id: "o", label: "X-1 (demo) model", method: "unit_model:demo", name: "unit_model:demo", references: [] }],
  edges: [
    { source: "a", target: "o", role: "k", feedback: false },
    { source: "u", target: "o", role: "F", feedback: false },
    { source: "o", target: "y", role: "duty_W", feedback: false },
  ],
  meta: {},
} as unknown as TraceGraph;

test("an uncited value stands out with a ring, says it has no citation, and the audit lists it", async () => {
  const trace = vi.spyOn(api, "trace").mockImplementation(async (t) =>
    t ? { ...uncitedGraph, meta: { focus: "y" } } : uncitedGraph,
  );
  const audit = vi.spyOn(api, "traceAudit").mockResolvedValue({
    outputs: 1,
    clean: 0,
    findings: [
      { node: "y", label: "X-1 duty_W", severity: "error", reasons: ["uncited value: X-1 k (unattributed)"], culprits: ["a", "o"] },
    ],
  });
  try {
    render(<TraceView target={{ unit: "X-1", prop: "duty_W" }} />);
    const svg = await graph();
    const h = await within(svg).findByRole("button", { name: "X-1 k (unattributed) (intermediate, uncited)" });
    expect(h.classList.contains("q-uncited")).toBe(true);
    expect(h.querySelector(".tr-ring")).not.toBeNull();
    fireEvent.click(h);
    expect(screen.getByLabelText("Value detail").textContent).toContain("No citation");
    expect((await screen.findByText(/uncited value: X-1 k/)).textContent).toContain("uncited value");
  } finally {
    trace.mockRestore();
    audit.mockRestore();
  }
});

test("a project selector traces another stored project", async () => {
  const list = vi.spyOn(api, "listProjects").mockResolvedValue([
    { id: "p-default", name: "default" },
    { id: "p-demo", name: "Trace demo: gas processing" },
  ]);
  const trace = vi.spyOn(api, "trace");
  const audit = vi.spyOn(api, "traceAudit");
  try {
    render(<TraceView />);
    const select = (await screen.findByLabelText("Project")) as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "p-demo" } });
    await waitFor(() => expect(audit).toHaveBeenCalledWith("p-demo"));
    await waitFor(() => expect(trace.mock.calls.some((c) => c[1] === "p-demo")).toBe(true));
  } finally {
    list.mockRestore();
    trace.mockRestore();
    audit.mockRestore();
  }
});

test("clicking an operation shows its equation rendered with KaTeX and every reference", async () => {
  render(<TraceView target={{ stream: "S-001", prop: "T" }} />);
  const svg = await graph();
  fireEvent.click(within(svg).getByRole("button", { name: "operation PT flash · Peng-Robinson EOS" }));
  const detail = screen.getByLabelText("Operation detail");
  expect(within(detail).getByRole("heading", { name: "PT flash · Peng-Robinson EOS" })).toBeTruthy();
  const eq = detail.querySelector(".tr-eq")!;
  expect(eq.querySelector(".katex")).not.toBeNull();
  expect(eq.getAttribute("data-latex")).toContain("\\frac{RT}{v-b}");
  expect(detail.textContent).toContain("Peng, D.-Y. and Robinson, D.B.");
  expect(detail.textContent).toContain("Rachford, H.H.");
  expect(within(detail).getByRole("link", { name: "10.1021/i160057a011" }).getAttribute("href")).toBe("https://doi.org/10.1021/i160057a011");
  expect(detail.textContent).toContain("Iterations8");
});

test("clicking an audit finding focuses the graph on that output and highlights its culprits", async () => {
  render(<TraceView />);
  await graph();
  const finding = mockAudit.findings.find((f) => f.label === "S-006 T")!;
  const audit = screen.getByRole("region", { name: "Audit" });
  const btn = within(audit).getAllByRole("button").find((b) => b.textContent?.includes(finding.reasons[0]))!;
  fireEvent.click(btn);
  await waitFor(() => expect((screen.getByLabelText("Stream or unit") as HTMLSelectElement).value).toBe("stream:S-006"));
  expect(btn.getAttribute("aria-pressed")).toBe("true");
  const svg = await graph();
  await waitFor(() => expect(node(svg, finding.node)?.classList.contains("focus")).toBe(true));
  for (const c of finding.culprits) expect(node(svg, c)?.classList.contains("culprit")).toBe(true);
});

test("export buttons download the shown graph as standalone SVG and as TraceGraph JSON", async () => {
  const blobs: Blob[] = [];
  const create = vi.fn((b: Blob) => {
    blobs.push(b);
    return `blob:${blobs.length}`;
  });
  Object.assign(URL, { createObjectURL: create, revokeObjectURL: vi.fn() });
  const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  render(<TraceView target={{ unit: "K-101", prop: "power_W" }} />);
  const svg = await graph();
  await within(svg).findByRole("button", { name: /^K-101 power_W \(output/ });

  fireEvent.click(screen.getByRole("button", { name: "Export JSON" }));
  const json = JSON.parse(await readBlob(blobs[0]));
  const expected = await api.trace({ unit: "K-101", prop: "power_W" });
  expect(json).toEqual(expected);
  expect(blobs[0].type).toBe("application/json");

  fireEvent.click(screen.getByRole("button", { name: "Export SVG" }));
  const text = await readBlob(blobs[1]);
  expect(blobs[1].type).toBe("image/svg+xml");
  expect(text.startsWith("<?xml")).toBe(true);
  expect(text).toContain('xmlns="http://www.w3.org/2000/svg"');
  expect(text).toContain(`data-node="${expected.meta.focus}"`);
  expect(text).not.toContain("tabindex");
  expect(click).toHaveBeenCalledTimes(2);
  expect((click.mock.instances[0] as unknown as HTMLAnchorElement).download).toBe("trace-K-101_power_W.json");
  click.mockRestore();
});

test("clicking a number in Results asks to trace exactly that value", async () => {
  const onTrace = vi.fn();
  render(<ResultsView onTrace={onTrace} />);
  fireEvent.click(screen.getByRole("button", { name: "Solve" }));
  await screen.findByText("K-101");
  fireEvent.click(screen.getByRole("button", { name: "1505.84" }));
  expect(onTrace).toHaveBeenLastCalledWith({ unit: "K-101", prop: "power_W" });
  fireEvent.click(screen.getByRole("button", { name: /^pressure_ratio=2\.030751/ }));
  expect(onTrace).toHaveBeenLastCalledWith({ unit: "K-101", prop: "info.pressure_ratio" });
  const s1 = screen.getAllByRole("row").find((r) => r.getAttribute("data-stream") === "S-001")!;
  fireEvent.click(within(s1).getByRole("button", { name: "20" }));
  expect(onTrace).toHaveBeenLastCalledWith({ stream: "S-001", prop: "T" });
});

test("depth limits the drawing and 'Show inputs' opens one hidden branch", async () => {
  render(<TraceView target={{ stream: "S-003", prop: "T" }} />);
  const svg = await graph();
  await within(svg).findByRole("button", { name: /^S-003 T \(output/ });
  const count = () => svg.querySelectorAll("[data-node]").length;
  const atFour = count();
  fireEvent.change(screen.getByLabelText("Depth"), { target: { value: "all" } });
  await waitFor(() => expect(count()).toBeGreaterThanOrEqual(atFour));
  // At two steps some inputs are hidden; selecting such a node offers to show them.
  fireEvent.change(screen.getByLabelText("Depth"), { target: { value: "2" } });
  await waitFor(() => expect(count()).toBeLessThan(atFour));
  const atTwo = count();
  const hidden = svg.querySelector(".tr-node.trunc") as Element;
  expect(hidden).not.toBeNull();
  fireEvent.click(hidden);
  fireEvent.click(screen.getByRole("button", { name: "Show inputs of the selected node" }));
  await waitFor(() => expect(count()).toBeGreaterThan(atTwo));
});

test("an operation's detail lists its inputs; following one selects that value", async () => {
  render(<TraceView target={{ unit: "K-101", prop: "power_W" }} />);
  const svg = await graph();
  fireEvent.click(await within(svg).findByRole("button", { name: "operation Shaft power from enthalpy change" }));
  const inputs = screen.getByRole("list", { name: "Inputs" });
  const links = within(inputs).getAllByRole("button");
  expect(links.map((b) => b.textContent)).toEqual(
    expect.arrayContaining([expect.stringMatching(/^F /), expect.stringMatching(/^h_in /), expect.stringMatching(/^h_out /)]),
  );
  fireEvent.click(links.find((b) => b.textContent!.startsWith("h_in "))!);
  const detail = screen.getByLabelText("Value detail");
  expect(detail.textContent).toContain("enthalpy");
  expect(within(detail).getByRole("list", { name: "Used by" })).toBeTruthy();
});
