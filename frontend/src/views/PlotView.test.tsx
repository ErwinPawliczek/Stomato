import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ApiError, api, type Layout, type Project, type Vec3 } from "../api/client";
import mockProject from "../../mocks/project.json";
import { PLOT_GRID_MM, PlotView, defaultPlotOrigins, plotAfterDrag, snapToGrid } from "./PlotView";

// jsdom has no PointerEvent and no SVG geometry; the view's coordinate
// hit-test needs both.
beforeAll(() => {
  // Every element reports the V-101 box (45,70)-(155,130): the hit-test at a
  // point inside it finds the FIRST unit-tagged group in document order.
  Object.defineProperty(Element.prototype, "getBoundingClientRect", {
    configurable: true,
    value() {
      return { x: 45, y: 70, left: 45, top: 70, right: 155, bottom: 130, width: 110, height: 60 };
    },
  });
  if (!("PointerEvent" in window)) {
    (window as unknown as { PointerEvent?: unknown }).PointerEvent = MouseEvent;
  }
});

const V = (x: number, y: number, z: number): Vec3 => ({ x, y, z });

// The plan's own geometry does not matter to the view (placements come from
// the project layout, deltas from pointer events) — only the group structure:
// equipment tags match the flowsheet's units, line groups are tagged too.
const SVG_BEFORE =
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 120" width="300" height="120">' +
  '<g data-tag="PG-1001"><polyline points="0,60 300,60"/></g>' +
  '<g data-tag="V-101"><rect x="45" y="40" width="110" height="60"/><text>V-101</text></g>' +
  '<g data-tag="K-101"><rect x="190" y="40" width="80" height="60"/><text>K-101</text></g>' +
  "</svg>";
// Distinguishable content so the re-fetch after a save (the re-routed plan)
// is visible in the DOM.
const SVG_AFTER = SVG_BEFORE.replace("</svg>", "<!--rerouted--></svg>");

const layout: Layout = { pfd: {}, pid: {}, plot: { "V-101": V(1_000, 2_000, 0) } };

const project = structuredClone(mockProject) as unknown as Project;
project.layout = layout; // V-101 is stored at (1000, 2000, 0) on the plot plan

async function findGroup(container: HTMLElement, tag: string): Promise<Element> {
  return waitFor(() => {
    const g = container.querySelector(`g[data-tag="${tag}"]`);
    if (!g) throw new Error(`no <g data-tag="${tag}"> rendered yet`);
    return g;
  });
}

test("snapToGrid picks the nearest 500 mm crossing", () => {
  expect(snapToGrid(1_700)).toBe(1_500);
  expect(snapToGrid(1_300)).toBe(1_500);
  expect(snapToGrid(1_249)).toBe(1_000);
  expect(snapToGrid(0)).toBe(0);
  expect(snapToGrid(120, 100)).toBe(100);
});

test("plotAfterDrag maps the SVG drag delta to model space and snaps", () => {
  // SVG y grows downwards and the plan is north up: dragging DOWN (dy > 0)
  // moves the equipment SOUTH (model y decreases). x/y snap, z is untouched.
  expect(plotAfterDrag(V(1_000, 2_000, 6_000), 500, 0)).toEqual(V(1_500, 2_000, 6_000));
  expect(plotAfterDrag(V(1_000, 2_000, 6_000), 0, 300)).toEqual(V(1_000, 1_500, 6_000));
  expect(plotAfterDrag(V(1_000, 2_000, 6_000), 700, -230)).toEqual(V(1_500, 2_000, 6_000));
});

test("defaultPlotOrigins mirrors the router's auto-placement for unplaced tags", () => {
  const units = [{ tag: "V-101" }, { tag: "K-101" }, { tag: "E-101" }];
  // Empty layout: every tag at 12 000 mm spacing along x, grade, counting only
  // unplaced equipment.
  expect(defaultPlotOrigins(units, {})).toEqual({
    "V-101": V(12_000, 0, 0),
    "K-101": V(24_000, 0, 0),
    "E-101": V(36_000, 0, 0),
  });
  // Stored placements survive verbatim and do not consume a default slot.
  expect(defaultPlotOrigins(units, { "K-101": V(5_000, 5_000, 8_000) })).toEqual({
    "V-101": V(12_000, 0, 0),
    "K-101": V(5_000, 5_000, 8_000),
    "E-101": V(24_000, 0, 0),
  });
});

test("renders the plot SVG with equipment and line groups", async () => {
  vi.spyOn(api, "plotSvg").mockResolvedValue(SVG_BEFORE);
  const { container } = render(<PlotView project={project} />);
  await waitFor(() => expect(container.querySelector('g[data-tag="V-101"]')).toBeTruthy());
  expect(container.querySelector('g[data-tag="PG-1001"]')).toBeTruthy();
  // Equipment is keyboard-reachable; line groups are not interactive. The
  // attributes are set in an effect after the SVG is injected, so poll.
  await waitFor(() =>
    expect(container.querySelector('g[data-tag="V-101"]')?.getAttribute("role")).toBe("button"),
  );
  expect(container.querySelector('g[data-tag="PG-1001"]')?.getAttribute("role")).toBeNull();
});

test("dropping a drag PUTs the snapped position and re-renders the re-routed plan", async () => {
  const plotSvg = vi.spyOn(api, "plotSvg").mockResolvedValueOnce(SVG_BEFORE).mockResolvedValueOnce(SVG_AFTER);
  const placePlot = vi.spyOn(api, "placePlot").mockResolvedValue(layout);
  const { container } = render(<PlotView project={project} />);
  const group = (await findGroup(container, "V-101")) as SVGGElement;

  // Drag V-101 by (700, 600) client px; jsdom reports no rendered width, so
  // 1 px = 1 user unit (mm). Stored origin (1000, 2000): model (1700, 1400),
  // snapped to (1500, 1500) — dragged DOWN, so model y DECREASES (north up).
  fireEvent.pointerDown(group, { clientX: 100, clientY: 100, pointerId: 1, button: 0 });
  fireEvent.pointerMove(group, { clientX: 800, clientY: 700, pointerId: 1 });
  expect(group.getAttribute("transform")).toBe("translate(700 600)");
  fireEvent.pointerUp(group, { clientX: 800, clientY: 700, pointerId: 1 });

  await waitFor(() => expect(placePlot).toHaveBeenCalledWith("V-101", V(1_500, 1_500, 0)));
  // The move-to-reroute loop: the plan is re-fetched after the save, and the
  // re-routed drawing replaces the dragged transform.
  await waitFor(() => expect(plotSvg).toHaveBeenCalledTimes(2));
  await waitFor(() => expect(container.innerHTML).toContain("<!--rerouted-->"));
  expect(container.querySelector("g")?.getAttribute("transform")).toBeNull();
});

test("a drag starting on a routed line still moves the equipment underneath", async () => {
  // Regression: routed lines draw OVER the footprints, so pointer events land
  // on a line polyline; the hit-test must find the equipment below it anyway.
  vi.spyOn(api, "plotSvg").mockResolvedValue(SVG_BEFORE);
  const placePlot = vi.spyOn(api, "placePlot").mockResolvedValue(layout);
  const { container } = render(<PlotView project={project} />);
  await findGroup(container, "V-101");
  const plotPane = container.querySelector(".plot") as HTMLElement;
  fireEvent.pointerDown(plotPane, { clientX: 100, clientY: 100, pointerId: 1, button: 0 });
  fireEvent.pointerMove(plotPane, { clientX: 100, clientY: 100, pointerId: 1 });
  fireEvent.pointerUp(plotPane, { clientX: 100, clientY: 100, pointerId: 1 });
  await waitFor(() => expect(placePlot).toHaveBeenCalledWith("V-101", V(1_000, 2_000, 0)));
});

test("a dragged line group never saves a placement", async () => {
  vi.spyOn(api, "plotSvg").mockResolvedValue(SVG_BEFORE);
  const placePlot = vi.spyOn(api, "placePlot").mockResolvedValue(layout);
  const { container } = render(<PlotView project={project} />);
  const line = await findGroup(container, "PG-1001");
  fireEvent.pointerDown(line, { clientX: 0, clientY: 0, pointerId: 1, button: 0 });
  fireEvent.pointerMove(line, { clientX: 50, clientY: 50, pointerId: 1 });
  fireEvent.pointerUp(line, { clientX: 50, clientY: 50, pointerId: 1 });
  expect(placePlot).not.toHaveBeenCalled();
});

test("dropping with no movement still saves the snapped stored position", async () => {
  // A click (no move) must not corrupt anything: the stored origin snaps to
  // itself. Confirms the anchor is the stored position, not parsed geometry.
  vi.spyOn(api, "plotSvg").mockResolvedValue(SVG_BEFORE);
  const placePlot = vi.spyOn(api, "placePlot").mockResolvedValue(layout);
  const { container } = render(<PlotView project={project} />);
  const group = (await findGroup(container, "V-101")) as SVGGElement;
  fireEvent.pointerDown(group, { clientX: 100, clientY: 100, pointerId: 1, button: 0 });
  fireEvent.pointerUp(group, { clientX: 100, clientY: 100, pointerId: 1 });
  await waitFor(() => expect(placePlot).toHaveBeenCalledWith("V-101", V(1_000, 2_000, 0)));
});

test("the elevation input saves z and keeps the plan position", async () => {
  vi.spyOn(api, "plotSvg").mockResolvedValue(SVG_BEFORE);
  const placePlot = vi.spyOn(api, "placePlot").mockResolvedValue(layout);
  const { container } = render(<PlotView project={project} />);
  const group = await findGroup(container, "V-101");
  // Selection happens on pointer down — the same interaction as a drag start.
  fireEvent.pointerDown(group, { clientX: 100, clientY: 100, pointerId: 1, button: 0 });
  const input = await screen.findByLabelText("Elevation of V-101 in mm");
  fireEvent.change(input, { target: { value: "8000" } });
  await waitFor(() => expect(placePlot).toHaveBeenCalledWith("V-101", V(1_000, 2_000, 8_000)));
});

test("Re-route triggers the backend route and refreshes the plan", async () => {
  vi.spyOn(api, "plotSvg").mockResolvedValue(SVG_BEFORE);
  const route = vi.spyOn(api, "route").mockResolvedValue({ equipment: [], lines: [], rack_elevation_mm: 6_000 });
  render(<PlotView project={project} />);
  await screen.findByLabelText("Re-route plot");
  fireEvent.click(screen.getByLabelText("Re-route plot"));
  await waitFor(() => expect(route).toHaveBeenCalledTimes(1));
  await waitFor(() => expect(screen.queryByText("Routing…")).toBeNull());
});

test("a first drag of never-placed equipment anchors on the mirrored default origin", async () => {
  const emptyProject = structuredClone(mockProject) as unknown as Project;
  emptyProject.layout = { pfd: {}, pid: {}, plot: {} };
  vi.spyOn(api, "plotSvg").mockResolvedValue(SVG_BEFORE);
  const placePlot = vi.spyOn(api, "placePlot").mockResolvedValue(emptyProject.layout);
  const { container } = render(<PlotView project={emptyProject} />);
  const group = (await findGroup(container, "V-101")) as SVGGElement;
  // V-101 is the first unplaced unit: default origin 12 000. Drag 500 west —
  // one grid cell; a sub-grid drag would snap back to 12 000.
  fireEvent.pointerDown(group, { clientX: 100, clientY: 100, pointerId: 1, button: 0 });
  fireEvent.pointerMove(group, { clientX: -400, clientY: 100, pointerId: 1 });
  fireEvent.pointerUp(group, { clientX: -400, clientY: 100, pointerId: 1 });
  await waitFor(() => expect(placePlot).toHaveBeenCalledWith("V-101", V(11_500, 0, 0)));
});

test("arrow keys nudge a focused item one grid cell and save", async () => {
  vi.spyOn(api, "plotSvg").mockResolvedValue(SVG_BEFORE);
  const placePlot = vi.spyOn(api, "placePlot").mockResolvedValue(layout);
  const { container } = render(<PlotView project={project} />);
  const group = await findGroup(container, "V-101");
  fireEvent.keyDown(group, { key: "ArrowUp" });
  // Nudge is one PLOT_GRID_MM step; model y DECREASES northward... ArrowUp in
  // SVG space is -y, which is model +y (north).
  await waitFor(() =>
    expect(placePlot).toHaveBeenCalledWith("V-101", V(1_000, 2_000 + PLOT_GRID_MM, 0)),
  );
});

test("a 501 shows the not-available alert instead of crashing", async () => {
  vi.spyOn(api, "plotSvg").mockRejectedValue(new ApiError("GET /api/views/plot.svg: 501", 501));
  render(<PlotView project={project} />);
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toContain("Plot routing not available yet");
});

test("a failed save shows an alert and rolls the footprint back", async () => {
  vi.spyOn(api, "plotSvg").mockResolvedValue(SVG_BEFORE);
  vi.spyOn(api, "placePlot").mockRejectedValue(
    new ApiError("PUT /api/project/layout/plot/V-101: 422", 422),
  );
  const { container } = render(<PlotView project={project} />);
  const group = (await findGroup(container, "V-101")) as SVGGElement;
  fireEvent.pointerDown(group, { clientX: 100, clientY: 100, pointerId: 1, button: 0 });
  fireEvent.pointerMove(group, { clientX: 400, clientY: 100, pointerId: 1 });
  fireEvent.pointerUp(group, { clientX: 400, clientY: 100, pointerId: 1 });
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toContain("Plot plan failed:");
  await waitFor(() => expect(group.hasAttribute("transform")).toBe(false));
});
