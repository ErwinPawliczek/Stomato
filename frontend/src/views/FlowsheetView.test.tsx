import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ApiError, api, type Project } from "../api/client";
import mockProject from "../../mocks/project.json";
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

test("add-unit palette inserts a UnitSpec with example_case-shaped params; Save persists it", async () => {
  api._resetMock();
  const initial = await api.getProject();
  render(<FlowsheetView project={initial} />);

  // The palette renders once /api/meta resolves.
  fireEvent.change(await screen.findByRole("combobox", { name: "New unit kind" }), {
    target: { value: "expander" },
  });
  fireEvent.change(screen.getByRole("textbox", { name: "New unit tag" }), {
    target: { value: "X-201" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Add unit" }));

  // Row appears immediately with the registry kind and the plugin's
  // example_case() defaults (X-201 P_out editable at the expander's 2.0 MPa).
  const row = screen.getAllByRole("row").find((r) => r.getAttribute("data-tag") === "X-201");
  expect(row?.textContent).toContain("expander");
  expect((screen.getByRole("textbox", { name: "X-201 P_out" }) as HTMLInputElement).value).toBe(
    "2000000",
  );

  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(async () => {
    const p = await api.getProject();
    const unit = p.flowsheet.units.find((u) => u.tag === "X-201");
    expect(unit?.kind).toBe("expander");
    expect(unit?.params).toEqual({ P_out: 2000000, eta_isentropic: 0.8 });
  });
});

test("add-unit palette rejects a duplicate tag without adding a unit", async () => {
  api._resetMock();
  render(<FlowsheetView project={structuredClone(mockProject) as Project} />);
  fireEvent.change(await screen.findByRole("combobox", { name: "New unit kind" }), {
    target: { value: "pump" },
  });
  fireEvent.change(screen.getByRole("textbox", { name: "New unit tag" }), {
    target: { value: "K-101" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Add unit" }));
  expect(screen.getByRole("alert").textContent).toContain("already exists");
  expect(
    screen.getAllByRole("row").filter((r) => r.getAttribute("data-tag") === "K-101"),
  ).toHaveLength(1);
});

test("a failed /api/meta fetch shows a registry alert instead of breaking the view", async () => {
  api._resetMock();
  const spy = vi.spyOn(api, "getMeta").mockRejectedValueOnce(new ApiError("GET /api/meta: 503", 503));
  render(<FlowsheetView project={structuredClone(mockProject) as Project} />);
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toContain("Registry unavailable");
  spy.mockRestore();
});

