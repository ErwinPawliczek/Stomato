import { fireEvent, render, screen, within } from "@testing-library/react";
import App from "./App";

test("opens the project from Home and shows every tab and the slice units from the mock", async () => {
  render(<App />);
  const nav = screen.getByRole("navigation", { name: "Main" });
  for (const label of ["Home", "Equipment", "Sheet", "Agent"]) {
    expect(within(nav).getByRole("button", { name: label })).toBeTruthy();
  }
  expect(screen.getByRole("heading", { name: "Projects" })).toBeTruthy();

  fireEvent.click(await screen.findByRole("button", { name: /slice/i }));
  for (const label of ["Flowsheet", "Results", "Drawings"]) {
    expect(screen.getByRole("tab", { name: label })).toBeTruthy();
  }
  expect(await screen.findByText("V-101")).toBeTruthy();
  expect(screen.getAllByText("S-001").length).toBeGreaterThan(0);

  fireEvent.click(screen.getByRole("tab", { name: "Drawings" }));
  for (const label of ["PFD", "P&ID", "Plot plan", "Isometrics"]) {
    expect(screen.getByRole("tab", { name: label })).toBeTruthy();
  }

  fireEvent.click(screen.getByRole("button", { name: "Close" }));
  expect(screen.getByRole("heading", { name: "Projects" })).toBeTruthy();
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
