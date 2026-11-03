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

test("a failed solve names each failed unit with its reason", async () => {
  const failed = {
    ...structuredClone(mockSolved),
    converged: false,
    status: "failed",
    errors: [
      { tag: "K-101", kind: "compressor", error_type: "ValueError", message: "P_out below inlet pressure", stage: "unit", upstream: false },
      { tag: "E-101", kind: "air_cooler", error_type: "UpstreamFailure", message: "inlet from K-101 not available", stage: "unit", upstream: true },
    ],
  };
  const spy = vi.spyOn(api, "solve").mockResolvedValueOnce(failed as never);
  render(<ResultsView />);
  fireEvent.click(screen.getByRole("button", { name: "Solve" }));
  expect((await screen.findByRole("status")).textContent).toMatch(/Solve failed: 2 units could not be calculated/);
  const errors = screen.getByRole("region", { name: "Solve errors" });
  expect(errors.textContent).toContain("P_out below inlet pressure");
  expect(errors.textContent).toContain("(upstream failure)");
  spy.mockRestore();
});

test("design spec outcomes are listed", async () => {
  const withSpecs = {
    ...structuredClone(mockSolved),
    design_spec_results: [{ id: "dew", converged: true, achieved: 7.0, manipulated_value: 51.4, iterations: 4, history: [] }],
  };
  const spy = vi.spyOn(api, "solve").mockResolvedValueOnce(withSpecs as never);
  render(<ResultsView />);
  fireEvent.click(screen.getByRole("button", { name: "Solve" }));
  const specs = await screen.findByRole("region", { name: "Design specs" });
  expect(specs.textContent).toContain("dew");
  expect(specs.textContent).toContain("met");
  expect(specs.textContent).toContain("51.4");
  spy.mockRestore();
});

test("a kept result renders without solving again (parent-owned across tab switches)", () => {
  const spy = vi.spyOn(api, "solve");
  render(<ResultsView result={structuredClone(mockSolved) as never} onResult={() => {}} />);
  expect(screen.getByText("S-011")).toBeTruthy();
  expect(spy).not.toHaveBeenCalled();
  spy.mockRestore();
});
