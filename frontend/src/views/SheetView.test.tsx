import { fireEvent, render, screen } from "@testing-library/react";
import { SheetView } from "./SheetView";

test("cells take text, Enter moves down, Tab moves right, Clear empties the grid", () => {
  render(<SheetView />);
  const b3 = screen.getByLabelText("B3") as HTMLInputElement;
  b3.focus();
  fireEvent.focus(b3);
  expect(screen.getByLabelText("Active cell").textContent).toBe("B3");

  fireEvent.change(b3, { target: { value: "Inlet gas" } });
  expect(b3.value).toBe("Inlet gas");

  fireEvent.keyDown(b3, { key: "Enter" });
  expect(document.activeElement).toBe(screen.getByLabelText("B4"));
  fireEvent.keyDown(screen.getByLabelText("B4"), { key: "Tab" });
  expect(document.activeElement).toBe(screen.getByLabelText("C4"));

  fireEvent.click(screen.getByRole("button", { name: "Clear" }));
  expect((screen.getByLabelText("B3") as HTMLInputElement).value).toBe("");
});

test("has 26 columns and 60 rows", () => {
  render(<SheetView />);
  expect(screen.getByLabelText("Z60")).toBeTruthy();
  expect(screen.queryByLabelText("Z61")).toBeNull();
});
