import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { api, type Project } from "../api/client";
import mockProject from "../../mocks/project.json";
import { FlowsheetView } from "../views/FlowsheetView";
import { nextSpecId, writableAddresses } from "./DesignSpecs";

beforeEach(() => api._resetMock());

test("nextSpecId and the suggested writable addresses", () => {
  const p = structuredClone(mockProject) as Project;
  expect(nextSpecId(p)).toBe("DS-001");
  expect(writableAddresses(p)).toContain("K-101.params.P_out");
});

test("add a design spec, Save persists it; Delete removes it", async () => {
  render(<FlowsheetView project={await api.getProject()} />);
  const section = screen.getByRole("region", { name: "Design specs" });
  fireEvent.click(within(section).getByRole("button", { name: "Add design spec" }));
  const form = within(section).getByRole("form", { name: "Add design spec" });
  const box = (label: string) => within(form).getByLabelText(label) as HTMLInputElement;
  fireEvent.change(box("Target address"), { target: { value: "S-004.T" } });
  fireEvent.change(box("Target value (SI)"), { target: { value: "320" } });
  fireEvent.change(box("Manipulated address"), { target: { value: "E-101.params.T_out" } });
  fireEvent.change(box("Lower bound (SI)"), { target: { value: "340" } });
  fireEvent.change(box("Upper bound (SI)"), { target: { value: "300" } });
  fireEvent.click(within(form).getByRole("button", { name: "Add" }));
  expect(within(form).getByRole("alert").textContent).toMatch(/lower bound must be below/);
  fireEvent.change(box("Lower bound (SI)"), { target: { value: "300" } });
  fireEvent.change(box("Upper bound (SI)"), { target: { value: "340" } });
  fireEvent.click(within(form).getByRole("button", { name: "Add" }));
  expect(within(section).getByRole("row", { name: /DS-001/ })).toBeTruthy();

  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(async () => {
    const specs = (await api.getProject()).flowsheet.design_specs ?? [];
    expect(specs).toEqual([
      expect.objectContaining({ id: "DS-001", target: "S-004.T", value: 320, manipulated: "E-101.params.T_out", lower: 300, upper: 340 }),
    ]);
  });
  fireEvent.click(within(section).getByRole("button", { name: "Delete design spec DS-001" }));
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(async () => expect((await api.getProject()).flowsheet.design_specs ?? []).toEqual([]));
});
