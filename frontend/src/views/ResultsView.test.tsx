import { fireEvent, render, screen } from "@testing-library/react";
import { ApiError, api } from "../api/client";
import mockSolved from "../../mocks/solved.json";
import { ResultsView } from "./ResultsView";

test("solve renders one row per stream in mocks/solved.json, sorted by id", async () => {
  render(<ResultsView />);
  fireEvent.click(screen.getByRole("button", { name: "Solve" }));
  await screen.findByText("S-011");
  const rows = screen.getAllByRole("row").filter((r) => r.hasAttribute("data-stream"));
  expect(rows).toHaveLength(Object.keys(mockSolved.streams).length);
  expect(rows[0].getAttribute("data-stream")).toBe("S-001");
  expect(rows[rows.length - 1].getAttribute("data-stream")).toBe("S-011");
  // Real solver output for S-001: 293.15 K -> 20 degC, 3447000 Pa -> 3345.7 kPa(g),
  // 691.7062 mol/s -> 2490.142 kmol/h.
  expect(rows[0].textContent).toContain("2490.142");
  expect(rows[0].textContent).toContain("3345.7");
  expect(rows[0].textContent).toContain("0.987");
});

test("solve renders one row per unit with duty and power", async () => {
  render(<ResultsView />);
  fireEvent.click(screen.getByRole("button", { name: "Solve" }));
  await screen.findByText("K-101");
  // K-101 power is 1505837 W in the real solver output -> 1505.84 kW.
  expect(screen.getByText("1505.84")).toBeTruthy();
});

test("a 501 from the backend shows 'Solver not available yet' instead of crashing", async () => {
  const spy = vi.spyOn(api, "solve").mockRejectedValueOnce(new ApiError("POST /api/solve: 501", 501));
  render(<ResultsView />);
  fireEvent.click(screen.getByRole("button", { name: "Solve" }));
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toContain("Solver not available yet");
  expect(screen.queryByText(/Solve failed/)).toBeNull();
  spy.mockRestore();
});


test("unit info keys render generically as key=value readouts", async () => {
  render(<ResultsView />);
  fireEvent.click(screen.getByRole("button", { name: "Solve" }));
  await screen.findByText("K-101");
  // Real solver info from mocks/solved.json — whatever keys the plugins emit,
  // each renders as key=value (pressure_ratio on K-101, water removal on T-101).
  expect(screen.getByText(/pressure_ratio=2\.030751/)).toBeTruthy();
  expect(screen.getByText(/water_removed_kg_h=33\.94117/)).toBeTruthy();
});
