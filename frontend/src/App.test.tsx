import { render, screen } from "@testing-library/react";
import App from "./App";

test("shows every tab and the slice units from the mock", async () => {
  render(<App />);
  for (const label of ["Flowsheet", "PFD", "P&ID", "Isometrics", "Sheet"]) {
    expect(screen.getByRole("tab", { name: label })).toBeTruthy();
  }
  expect(await screen.findByText("V-101")).toBeTruthy();
  expect(screen.getByText("S-001")).toBeTruthy();
});
