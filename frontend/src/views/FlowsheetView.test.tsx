import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { ApiError, api, type Project } from "../api/client";
import mockProject from "../../mocks/project.json";
import { clientToWorld } from "../components/FlowsheetCanvas";
import { UNIT_DND_TYPE } from "../components/UnitPalette";
import { HEX_SIZE, snapToHex } from "../hexGrid";
import { FlowsheetView } from "./FlowsheetView";

function k101Param(p: Project, name: string): unknown {
  const unit = p.flowsheet.units.find((u) => u.tag === "K-101");
  return unit?.params?.[name];
}

test("edit K-101 P_out, save, reload from mock, value persists", async () => {
  api._resetMock();
  const initial = await api.getProject();
  const { rerender } = render(<FlowsheetView project={initial} />);

  const input = screen.getByRole("textbox", { name: "K-101 P_out" }) as HTMLInputElement;
  expect(input.value).toBe("7000000");
  fireEvent.change(input, { target: { value: "8000000" } });

  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(async () => {
    const p = await api.getProject(); // mock branch is synchronous
    expect(k101Param(p, "P_out")).toBe(8000000);
  });

  const reloaded = await api.getProject();
  rerender(<FlowsheetView project={reloaded} />);
  expect(
    (screen.getByRole("textbox", { name: "K-101 P_out" }) as HTMLInputElement).value,
  ).toBe("8000000");
});

test("non-numeric input disables Save and marks the field invalid", () => {
  api._resetMock();
  render(<FlowsheetView project={structuredClone(mockProject) as Project} />);
  const save = screen.getByRole("button", { name: "Save" }) as HTMLButtonElement;
  expect(save.disabled).toBe(false);

  const input = screen.getByRole("textbox", { name: "K-101 P_out" }) as HTMLInputElement;
  fireEvent.change(input, { target: { value: "not-a-number" } });
  expect(save.disabled).toBe(true);
  expect(input.getAttribute("aria-invalid")).toBe("true");

  // Recovery: a valid value re-enables Save.
  fireEvent.change(input, { target: { value: "7250000" } });
  expect(save.disabled).toBe(false);
  expect(input.getAttribute("aria-invalid")).not.toBe("true");
});

test("feed conditions are shown in degC, kPa(g) and kmol/h", () => {
  api._resetMock();
  render(<FlowsheetView project={structuredClone(mockProject) as Project} />);
  expect(
    (screen.getByRole("textbox", { name: "S-001 feed T (degC)" }) as HTMLInputElement).value,
  ).toBe("20");
  expect(
    (screen.getByRole("textbox", { name: "S-001 feed P (kPa(g))" }) as HTMLInputElement).value,
  ).toBe("3345.675");
  expect(
    Number(
      (screen.getByRole("textbox", { name: "S-001 feed flow (kmol/h)" }) as HTMLInputElement)
        .value,
    ),
  ).toBeCloseTo(2490.1423072194, 4);
});

test("edited feed T, P and flow are saved in SI units", async () => {
  api._resetMock();
  render(<FlowsheetView project={structuredClone(mockProject) as Project} />);

  fireEvent.change(screen.getByRole("textbox", { name: "S-001 feed T (degC)" }), {
    target: { value: "25" },
  });
  fireEvent.change(screen.getByRole("textbox", { name: "S-001 feed P (kPa(g))" }), {
    target: { value: "3500" },
  });
  fireEvent.change(screen.getByRole("textbox", { name: "S-001 feed flow (kmol/h)" }), {
    target: { value: "3600" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));

  await waitFor(async () => {
    const p = await api.getProject();
    const feed = p.flowsheet.streams.find((s) => s.id === "S-001")?.feed;
    expect(feed?.T).toBeCloseTo(298.15, 9);
    expect(feed?.P).toBeCloseTo(3601325, 6);
    expect(feed?.molar_flow).toBeCloseTo(1000, 9);
  });
});

test("thermo selector lists registry models and persists a change through Save", async () => {
  api._resetMock();
  const initial = await api.getProject();
  render(<FlowsheetView project={initial} />);

  const select = screen.getByRole("combobox", { name: "Thermo model" }) as HTMLSelectElement;
  expect(select.value).toBe("pr");
  // Options come from GET /api/meta (the mock mirrors the registered thermo plugins).
  await waitFor(() =>
    expect([...select.options].map((o) => o.value)).toEqual(
      expect.arrayContaining(["nrtl", "pr", "pr78", "srk"]),
    ),
  );

  fireEvent.change(select, { target: { value: "nrtl" } });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(async () => {
    const p = await api.getProject(); // mock branch is synchronous
    expect(p.flowsheet.thermo).toBe("nrtl");
  });
});

// jsdom has no PointerEvent or DragEvent; MouseEvent carries clientX/Y for both.
beforeAll(() => {
  const w = window as unknown as Record<string, unknown>;
  if (!("PointerEvent" in window)) w.PointerEvent = MouseEvent;
  if (!("DragEvent" in window)) w.DragEvent = MouseEvent;
});

function canvas(): SVGSVGElement {
  const svg = screen.getByRole("application", { name: /Flowsheet canvas/ }) as unknown as SVGSVGElement;
  svg.getBoundingClientRect = () => ({ left: 10, top: 20, right: 810, bottom: 500, width: 800, height: 480, x: 10, y: 20, toJSON: () => ({}) });
  return svg;
}

/** World point under client (cx, cy), from the canvas's current viewBox and zoom. */
function worldAt(svg: SVGSVGElement, cx: number, cy: number) {
  const [vx, vy] = (svg.getAttribute("viewBox") ?? "").split(" ").map(Number);
  const k = Number(svg.getAttribute("data-zoom"));
  return clientToWorld({ x: vx, y: vy, k }, { left: 10, top: 20 }, cx, cy);
}

function unitBox(tag: string): SVGGElement | null {
  return document.querySelector(`g[data-tag="${tag}"]`);
}

function dataTransfer(kind?: string) {
  const store: Record<string, string> = kind ? { [UNIT_DND_TYPE]: kind } : {};
  return {
    types: Object.keys(store),
    getData: (t: string) => store[t] ?? "",
    setData: (t: string, v: string) => void (store[t] = v),
    dropEffect: "none",
    effectAllowed: "all",
  };
}

test("palette: categories collapse and expand; search filters across all of them", async () => {
  api._resetMock();
  render(<FlowsheetView project={structuredClone(mockProject) as Project} />);
  const pal = screen.getByRole("complementary", { name: "Unit palette" });
  const streams = within(pal).getByRole("button", { name: /Streams & Mixing/ });
  const heat = within(pal).getByRole("button", { name: /Heat Transfer/ });
  expect(streams.getAttribute("aria-expanded")).toBe("true");
  expect(heat.getAttribute("aria-expanded")).toBe("false");
  expect(within(pal).queryByRole("button", { name: "Air cooler" })).toBeNull();

  fireEvent.click(heat);
  expect(heat.getAttribute("aria-expanded")).toBe("true");
  const air = within(pal).getByRole("button", { name: "Air cooler" });
  expect(air.getAttribute("title")).toMatch(/Fin-fan cooler/); // one-line tooltip
  fireEvent.click(streams);
  expect(within(pal).queryByRole("button", { name: "Mixer" })).toBeNull();

  fireEvent.change(within(pal).getByRole("searchbox", { name: "Search units" }), { target: { value: "compressor" } });
  const hits = within(pal).getAllByRole("button").filter((b) => b.classList.contains("ut")).map((b) => b.textContent);
  expect(hits).toEqual(["Centrifugal compressor", "Reciprocating compressor"]);
  await screen.findByRole("button", { name: "Centrifugal compressor" }); // registry loaded, still listed
});

test("click-to-add inserts a UnitSpec with example_case params and an auto tag; Save persists unit and position", async () => {
  api._resetMock();
  const initial = await api.getProject();
  render(<FlowsheetView project={initial} />);
  const pal = screen.getByRole("complementary", { name: "Unit palette" });
  fireEvent.change(within(pal).getByRole("searchbox", { name: "Search units" }), { target: { value: "expander" } });
  // Keyboard path: the palette box is a plain button (Enter/Space click it).
  fireEvent.click(await within(pal).findByRole("button", { name: "Expander / turbine" }));

  // P&ID symbol T; T-101 is taken by the TEG contactor, so T-102.
  const row = screen.getAllByRole("row").find((r) => r.getAttribute("data-tag") === "T-102");
  expect(row?.textContent).toContain("expander");
  expect((screen.getByRole("textbox", { name: "T-102 P_out" }) as HTMLInputElement).value).toBe("2000000");
  expect(unitBox("T-102")).not.toBeNull();
  expect(screen.getByRole("status").textContent).toContain("Added T-102");

  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(async () => {
    const p = await api.getProject();
    const unit = p.flowsheet.units.find((u) => u.tag === "T-102");
    expect(unit?.kind).toBe("expander");
    expect(unit?.params).toEqual({ P_out: 2000000, eta_isentropic: 0.8 });
    expect(p.layout?.pfd?.["T-102"]).toEqual({ x: Number(unitBox("T-102")!.getAttribute("data-x")), y: Number(unitBox("T-102")!.getAttribute("data-y")) });
  });
});

test("dropping a palette unit on the canvas creates it at the drop point, snapped to the hex cell", async () => {
  api._resetMock();
  render(<FlowsheetView project={structuredClone(mockProject) as Project} />);
  await screen.findByRole("button", { name: "Mixer" }); // registry loaded
  const svg = canvas();

  const dt = dataTransfer();
  fireEvent.dragStart(screen.getByRole("button", { name: "Mixer" }), { dataTransfer: dt });
  expect(dt.getData(UNIT_DND_TYPE)).toBe("mixer");
  fireEvent.dragOver(svg, { dataTransfer: dataTransfer("mixer"), clientX: 333, clientY: 222 });
  fireEvent.drop(svg, { dataTransfer: dataTransfer("mixer"), clientX: 333, clientY: 222 });

  const box = unitBox("MIX-101");
  expect(box).not.toBeNull();
  const want = snapToHex(worldAt(svg, 333, 222));
  expect(Number(box!.getAttribute("data-x"))).toBeCloseTo(want.x, 9);
  expect(Number(box!.getAttribute("data-y"))).toBeCloseTo(want.y, 9);
  expect(screen.getAllByRole("row").some((r) => r.getAttribute("data-tag") === "MIX-101")).toBe(true);

  // A drag that is not a palette unit (e.g. a file) creates nothing.
  fireEvent.drop(svg, { dataTransfer: dataTransfer(), clientX: 50, clientY: 50 });
  expect(document.querySelectorAll("g[data-tag]")).toHaveLength(9);
});

test("dragging a saved unit snaps it to a cell and stores it through the layout API; grid off = no snap", async () => {
  api._resetMock();
  const place = vi.spyOn(api, "place");
  render(<FlowsheetView project={structuredClone(mockProject) as Project} />);
  const svg = canvas();
  const k = Number(svg.getAttribute("data-zoom"));
  const box = unitBox("K-101")!;
  const x0 = Number(box.getAttribute("data-x"));
  const y0 = Number(box.getAttribute("data-y"));

  fireEvent.pointerDown(box, { clientX: 100, clientY: 100, button: 0 });
  fireEvent.pointerMove(svg, { clientX: 100 + 77 * k, clientY: 100 + 31 * k });
  fireEvent.pointerUp(svg, { clientX: 100 + 77 * k, clientY: 100 + 31 * k });
  const snapped = snapToHex({ x: x0 + 77, y: y0 + 31 });
  await waitFor(() => expect(place).toHaveBeenCalledWith("pfd", "K-101", snapped));
  await waitFor(() => expect(Number(unitBox("K-101")!.getAttribute("data-x"))).toBeCloseTo(snapped.x, 9));

  // Grid off: the lattice disappears and positions are free (rounded only).
  const toggle = screen.getByRole("button", { name: "Grid & snap" });
  expect(toggle.getAttribute("aria-pressed")).toBe("true");
  expect(svg.querySelector("pattern")).not.toBeNull();
  fireEvent.click(toggle);
  expect(toggle.getAttribute("aria-pressed")).toBe("false");
  expect(svg.querySelector("pattern")).toBeNull();
  const b2 = unitBox("K-101")!;
  fireEvent.pointerDown(b2, { clientX: 100, clientY: 100, button: 0 });
  fireEvent.pointerMove(svg, { clientX: 100 + 13 * k, clientY: 100 + 7 * k });
  fireEvent.pointerUp(svg, { clientX: 100 + 13 * k, clientY: 100 + 7 * k });
  await waitFor(() =>
    expect(place).toHaveBeenLastCalledWith("pfd", "K-101", { x: Math.round(snapped.x + 13), y: Math.round(snapped.y + 7) }),
  );
  place.mockRestore();
});

test("arrow keys move a focused unit one hex cell", async () => {
  api._resetMock();
  const place = vi.spyOn(api, "place");
  render(<FlowsheetView project={structuredClone(mockProject) as Project} />);
  const box = unitBox("V-101")!;
  const y0 = Number(box.getAttribute("data-y"));
  fireEvent.keyDown(box, { key: "ArrowDown" });
  await waitFor(() => expect(place).toHaveBeenCalled());
  const [, tag, pos] = place.mock.calls[0];
  expect(tag).toBe("V-101");
  expect(pos.y - y0).toBeCloseTo(HEX_SIZE * Math.sqrt(3), 9);
  place.mockRestore();
});

test("a failed /api/meta fetch shows a registry alert instead of breaking the view", async () => {
  api._resetMock();
  const spy = vi.spyOn(api, "getMeta").mockRejectedValueOnce(new ApiError("GET /api/meta: 503", 503));
  render(<FlowsheetView project={structuredClone(mockProject) as Project} />);
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toContain("Registry unavailable");
  spy.mockRestore();
});

