// Flowsheet editing beyond params: connect streams (unit to unit, boundary feeds),
// delete units and streams, edit feed compositions, thermo models the backend refuses.
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { api, type Project, type UnitKindInfo } from "../api/client";
import mockProject from "../../mocks/project.json";
import mockKinds from "../../mocks/unit-catalogue.json";
import { addStream, deleteUnit, freePorts, FlowsheetView, nextStreamId, parseComposition } from "./FlowsheetView";

const slice = () => structuredClone(mockProject) as Project;
const kinds = new Map((mockKinds.units as UnitKindInfo[]).map((k) => [k.kind, k]));

beforeAll(() => {
  const w = window as unknown as Record<string, unknown>;
  if (!("PointerEvent" in window)) w.PointerEvent = MouseEvent;
});
beforeEach(() => api._resetMock());

test("parseComposition reads fractions and says what is wrong", () => {
  expect(parseComposition("C1=0.9, C2: 0.1")).toEqual({ C1: 0.9, C2: 0.1 });
  expect(parseComposition("C1=0.9\nC2=0.1")).toEqual({ C1: 0.9, C2: 0.1 });
  expect(parseComposition("C1=0.8, C2=0.1")).toMatch(/sum to 0.9/);
  expect(parseComposition("C1=x")).toMatch(/not a non-negative number/);
  expect(parseComposition("C1")).toMatch(/component=fraction/);
  expect(parseComposition("")).toMatch(/at least one/);
});

test("nextStreamId, freePorts, addStream and deleteUnit follow the backend's rules", () => {
  const p = slice();
  expect(nextStreamId(p)).toBe("S-012");
  // A new unit brings free ports; wired ports are never offered.
  const withPump: Project = { ...p, flowsheet: { ...p.flowsheet, units: [...p.flowsheet.units, { tag: "P-102", kind: "pump", params: {} }] } };
  const inlets = freePorts(withPump, kinds, "inlet");
  expect(inlets).toContainEqual({ unit: "P-102", port: "inlet" });
  expect(freePorts(withPump, kinds, "outlet")).toContainEqual({ unit: "P-102", port: "outlet" });
  const wired = new Set(p.flowsheet.streams.flatMap((x) => [x.source, x.target]).filter(Boolean).map((r) => `${r!.unit}.${r!.port}`));
  expect(inlets.filter((e) => wired.has(`${e.unit}.${e.port}`))).toEqual([]);

  const fed = addStream(withPump, null, { unit: "P-102", port: "inlet" }, {
    feed: { T: 300, P: 2e5, molar_flow: 1, composition: { H2O: 1 } },
    service: "W",
  });
  const s = fed.flowsheet.streams.at(-1)!;
  expect(s).toMatchObject({ id: "S-012", target: { unit: "P-102", port: "inlet" }, service: "W" });
  expect(s.source).toBeUndefined();
  // The feed's components join the slate (the contract rejects a feed outside it).
  expect(fed.flowsheet.components).toContain("H2O");
  expect(() => addStream(withPump, null, null, {})).toThrow(/source unit or a target/);
  expect(() => addStream(withPump, null, { unit: "P-102", port: "inlet" })).toThrow(/feed conditions/);

  const { project: gone, dropped } = deleteUnit(fed, "K-101");
  expect(gone.flowsheet.units.map((u) => u.tag)).not.toContain("K-101");
  expect(dropped.sort()).toEqual(["S-002", "S-003"]);
  expect(gone.flowsheet.streams.some((x) => x.source?.unit === "K-101" || x.target?.unit === "K-101")).toBe(false);
});

test("add a unit, feed it from the battery limit, connect it to a product, Save persists", async () => {
  const p0 = { ...slice(), layout: { pfd: {}, pid: {}, plot: {} } };
  await api.putProject(p0);
  render(<FlowsheetView project={await api.getProject()} />);
  const pal = screen.getByRole("complementary", { name: "Unit palette" });
  fireEvent.change(within(pal).getByRole("searchbox", { name: "Search units" }), { target: { value: "pump" } });
  fireEvent.click(await within(pal).findByRole("button", { name: "Pump" }));

  // Wait for ports, then select the new unit on the canvas (click without moving).
  const box = await waitFor(() => {
    const g = document.querySelector('g[data-tag="P-102"]');
    expect(g).not.toBeNull();
    return g as SVGGElement;
  });
  fireEvent.pointerDown(box, { clientX: 5, clientY: 5, pointerId: 1, button: 0 });
  fireEvent.pointerUp(box, { clientX: 5, clientY: 5, pointerId: 1 });
  const panel = await screen.findByRole("region", { name: "Selected unit P-102" });
  fireEvent.click(await within(panel).findByRole("button", { name: "Connect into" }));

  const form = screen.getByRole("form", { name: "Connect stream" });
  expect((within(form).getByRole("combobox", { name: "To" }) as HTMLSelectElement).value).toBe("P-102|inlet");
  expect((within(form).getByRole("combobox", { name: "From" }) as HTMLSelectElement).value).toBe("");
  fireEvent.change(within(form).getByRole("textbox", { name: "Feed composition" }), { target: { value: "H2O=1" } });
  fireEvent.change(within(form).getByRole("textbox", { name: "Feed T (degC)" }), { target: { value: "30" } });
  fireEvent.click(within(form).getByRole("button", { name: "Add stream" }));
  expect(screen.queryByRole("form", { name: "Connect stream" })).toBeNull();

  // Outlet to a product, from the Connect stream button.
  fireEvent.click(screen.getByRole("button", { name: "Connect stream" }));
  const form2 = screen.getByRole("form", { name: "Connect stream" });
  fireEvent.change(within(form2).getByRole("combobox", { name: "From" }), { target: { value: "P-102|outlet" } });
  fireEvent.click(within(form2).getByRole("button", { name: "Add stream" }));

  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(async () => {
    const saved = await api.getProject();
    const feed = saved.flowsheet.streams.find((s) => s.target?.unit === "P-102");
    const product = saved.flowsheet.streams.find((s) => s.source?.unit === "P-102");
    expect(feed?.feed?.composition).toEqual({ H2O: 1 });
    expect(feed?.feed?.T).toBeCloseTo(303.15);
    expect(product?.target).toBeUndefined();
    expect(saved.flowsheet.components).toContain("H2O");
  });
});

test("a stream with no unit end cannot be added; a bad feed composition is explained", async () => {
  render(<FlowsheetView project={slice()} />);
  fireEvent.click(screen.getByRole("button", { name: "Connect stream" }));
  const form = screen.getByRole("form", { name: "Connect stream" });
  expect((within(form).getByRole("button", { name: "Add stream" }) as HTMLButtonElement).disabled).toBe(true);
  // Wired ports are not offered: V-101.gas_out carries S-002.
  await waitFor(() => expect(within(form).queryByText("Loading unit ports…")).toBeNull());
  expect(within(form).queryByRole("option", { name: "V-101.gas_out" })).toBeNull();
  const to = within(form).getByRole("combobox", { name: "To" }) as HTMLSelectElement;
  const free = [...to.options].find((o) => o.value !== "");
  expect(free).toBeTruthy();
  fireEvent.change(to, { target: { value: free!.value } });
  fireEvent.change(within(form).getByRole("textbox", { name: "Feed composition" }), { target: { value: "C1=0.5" } });
  fireEvent.click(within(form).getByRole("button", { name: "Add stream" }));
  expect(within(form).getByRole("alert").textContent).toMatch(/composition: mole fractions sum to 0.5/);
});

test("Delete removes a unit with its streams, and a stream on its own; Save persists both", async () => {
  render(<FlowsheetView project={await api.getProject()} />);
  fireEvent.click(screen.getByRole("button", { name: "Delete E-102" }));
  expect(screen.getByRole("status").textContent).toMatch(/Deleted E-102 and streams S-009, S-010/);
  fireEvent.click(screen.getByRole("button", { name: "Delete stream S-011" }));
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(async () => {
    const saved = await api.getProject();
    expect(saved.flowsheet.units.map((u) => u.tag)).not.toContain("E-102");
    expect(saved.flowsheet.streams.map((s) => s.id)).not.toEqual(expect.arrayContaining(["S-009"]));
    expect(saved.flowsheet.streams.map((s) => s.id)).not.toContain("S-010");
    expect(saved.flowsheet.streams.map((s) => s.id)).not.toContain("S-011");
  });
});

test("feed composition is editable; an invalid one blocks Save with the reason", async () => {
  render(<FlowsheetView project={await api.getProject()} />);
  const input = screen.getByRole("textbox", { name: "S-006 feed composition (mole fractions)" }) as HTMLInputElement;
  expect(input.value).toMatch(/=/);
  fireEvent.change(input, { target: { value: "TEG=0.5, H2O=0.4" } });
  expect((screen.getByRole("button", { name: "Save" }) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByText(/sum to 0.9/)).toBeTruthy();
  fireEvent.change(input, { target: { value: "TEG=0.5, H2O=0.5" } });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(async () => {
    const s6 = (await api.getProject()).flowsheet.streams.find((s) => s.id === "S-006");
    expect(s6?.feed?.composition).toEqual({ TEG: 0.5, H2O: 0.5 });
  });
});

test("thermo models the backend refuses are listed but disabled", async () => {
  render(<FlowsheetView project={slice()} />);
  const select = screen.getByRole("combobox", { name: "Thermo model" }) as HTMLSelectElement;
  await waitFor(() => expect(select.querySelector('option[value="flory_huggins"]')).not.toBeNull());
  const refused = select.querySelector('option[value="flory_huggins"]') as HTMLOptionElement;
  expect(refused.disabled).toBe(true);
  expect(refused.title).toMatch(/experimental/);
  expect((select.querySelector('option[value="pr"]') as HTMLOptionElement).disabled).toBe(false);
});
