import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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

test("an uncited value stands out with a ring and says it has no citation", async () => {
  render(<TraceView target={{ unit: "K-101", prop: "power_W" }} />);
  const svg = await graph();
  // The compressor's power output itself carries no citation in the slice trace.
  const h = await within(svg).findByRole("button", { name: "K-101 power_W (output, uncited)" });
  expect(h.classList.contains("q-uncited")).toBe(true);
  expect(h.querySelector(".tr-ring")).not.toBeNull();
  fireEvent.click(h);
  expect(screen.getByLabelText("Value detail").textContent).toContain("No citation");
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
