import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { ApiError, api, errorReason } from "../api/client";
import { IsoView } from "./IsoView";

afterEach(() => vi.restoreAllMocks());

test("lists the routed lines, shows the first sheet, and switches on pick", async () => {
  const { container } = render(<IsoView />);
  const picker = (await screen.findByLabelText("Line number")) as HTMLSelectElement;
  await waitFor(() => expect(picker.value).toBe('8"-PG-1001-B1'));
  expect(Array.from(picker.options).map((o) => o.value)).toEqual(['8"-PG-1001-B1', '1"-GL-1006-D1', '6"-FL-1012-B1']);
  // The first line's drawing and tables arrive without a pick.
  await waitFor(() => expect(container.querySelector('.iso g[data-tag="title-block"]')).toBeTruthy());
  expect(within(screen.getByRole("table", { name: "Title block" })).getByText('8"-PG-1001-B1')).toBeTruthy();

  fireEvent.change(picker, { target: { value: '1"-GL-1006-D1' } });
  await waitFor(() => expect(container.querySelector(".iso")?.textContent).toContain('1"-GL-1006-D1'));
  const title = screen.getByRole("table", { name: "Title block" });
  expect(within(title).getByText('1"-GL-1006-D1')).toBeTruthy();
  expect(title.textContent).toContain("7708.7 kPa(g) / 77 degC");
  expect(title.textContent).toContain("50.61 m"); // total pipe length, mm -> m
  const bom = screen.getByRole("table", { name: "Bill of materials" });
  expect(within(bom).getByText('1" WN flange cl600 RTJ')).toBeTruthy();
  const cuts = screen.getByRole("table", { name: "Cut list" });
  expect(within(cuts).getAllByRole("row")).toHaveLength(5); // header + 4 pieces
  expect(within(cuts).getByText("38064")).toBeTruthy();
});

test("a 422 shows the backend's reason instead of the raw error", async () => {
  vi.spyOn(api, "isoLines").mockRejectedValue(
    new ApiError(
      'GET /api/projects/p-1/views/iso: 422 {"detail":"unit P-999 has no connected streams to size from"}',
      422,
    ),
  );
  render(<IsoView />);
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toBe("Isometrics cannot be drawn: unit P-999 has no connected streams to size from");
});

test("no routed lines shows the empty state", async () => {
  vi.spyOn(api, "isoLines").mockResolvedValue([]);
  render(<IsoView />);
  expect(await screen.findByText(/No routed lines yet/)).toBeTruthy();
  expect((screen.getByLabelText("Line number") as HTMLSelectElement).disabled).toBe(true);
});

test("errorReason reads detail strings, validation lists and the v1 envelope", () => {
  expect(errorReason(new ApiError('GET x: 404 {"detail":"no routed line \'8\\"-PG\'"}', 404))).toBe(
    "no routed line '8\"-PG'",
  );
  expect(errorReason(new ApiError('PUT x: 422 {"detail":[{"msg":"field required"}]}', 422))).toBe("field required");
  expect(errorReason(new ApiError('GET x: 422 {"error":{"code":"undrawable","message":"why"}}', 422))).toBe("why");
  expect(errorReason(new ApiError("GET x: 500 Internal Server Error", 500))).toBe("GET x: 500 Internal Server Error");
});
