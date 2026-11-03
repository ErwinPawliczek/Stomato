import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import App from "./App";

test("opens the project from Home and shows every tab and the slice units from the mock", async () => {
  render(<App />);
  const nav = screen.getByRole("navigation", { name: "Main" });
  for (const label of ["Home", "Equipment", "Sheet", "Agent"]) {
    expect(within(nav).getByRole("button", { name: label })).toBeTruthy();
  }
  expect(screen.getByRole("heading", { name: "Projects" })).toBeTruthy();

  fireEvent.click(await screen.findByRole("button", { name: "Open slice" }));
  expect(await screen.findByRole("tab", { name: "Flowsheet" })).toBeTruthy();
  for (const label of ["Flowsheet", "Results", "Drawings"]) {
    expect(screen.getByRole("tab", { name: label })).toBeTruthy();
  }
  // V-101 shows on the flowsheet canvas and in the units table.
  expect(await screen.findByRole("button", { name: /^V-101 / })).toBeTruthy();
  expect(screen.getAllByRole("row").some((r) => r.getAttribute("data-tag") === "V-101")).toBe(true);
  expect(screen.getAllByText("S-001").length).toBeGreaterThan(0);

  fireEvent.click(screen.getByRole("tab", { name: "Drawings" }));
  for (const label of ["PFD", "P&ID", "Plot plan", "Isometrics"]) {
    expect(screen.getByRole("tab", { name: label })).toBeTruthy();
  }

  fireEvent.click(screen.getByRole("button", { name: "Close" }));
  expect(screen.getByRole("heading", { name: "Projects" })).toBeTruthy();
});

test("clicking a number in Results opens the Trace tab focused on that value", async () => {
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "Open slice" }));
  fireEvent.click(await screen.findByRole("tab", { name: "Results" }));
  fireEvent.click(screen.getByRole("button", { name: "Solve" }));
  await screen.findByText("K-101");
  // K-101 power: 1505837 W in mocks/solved.json -> 1505.84 kW.
  fireEvent.click(screen.getByRole("button", { name: "1505.84" }));
  expect(screen.getByRole("tab", { name: "Trace" }).getAttribute("aria-selected")).toBe("true");
  const svg = await screen.findByRole("group", { name: "Trace graph" });
  const focus = await within(svg).findByRole("button", { name: /^K-101 power_W \(output/ });
  expect(focus.classList.contains("focus")).toBe(true);
  expect((screen.getByLabelText("Stream or unit") as HTMLSelectElement).value).toBe("unit:K-101");
  expect((screen.getByLabelText("Property") as HTMLSelectElement).value).toBe("power_W");
});

test("rail switches pages and the palette", () => {
  render(<App />);
  const nav = screen.getByRole("navigation", { name: "Main" });
  fireEvent.click(within(nav).getByRole("button", { name: "Sheet" }));
  expect(screen.getByRole("heading", { name: "Sheet" })).toBeTruthy();
  expect(within(nav).getByRole("button", { name: "Sheet" }).getAttribute("aria-current")).toBe("page");

  fireEvent.click(screen.getByRole("button", { name: "Blueprint palette" }));
  expect(document.documentElement.dataset.palette).toBe("blueprint");
  expect(document.documentElement.style.getPropertyValue("--bg")).toBe("#0F3D6E");
  expect(screen.getByRole("button", { name: "Blueprint palette" }).getAttribute("aria-pressed")).toBe("true");
});

test("saving the flowsheet updates the project header counts", async () => {
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "Open slice" }));
  await screen.findByRole("tab", { name: "Flowsheet" });
  const header = () => document.querySelector(".crumb small")?.textContent ?? "";
  const [units, streams] = (header().match(/\d+/g) ?? []).map(Number);
  // E-102 carries two streams (S-009 in, S-010 out).
  fireEvent.click(screen.getByRole("button", { name: "Delete E-102" }));
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(header()).toBe(`${units - 1} units · ${streams - 2} streams`));
});
