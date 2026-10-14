import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ApiError, api, type Layout, type Project } from "../api/client";
import mockProject from "../../mocks/project.json";
import { PfdView, userUnitsPerClientPx } from "./PfdView";

// jsdom has no SVG geometry and no PointerEvent; the view needs both.
beforeAll(() => {
  // getBBox: jsdom parses <g> into plain elements and defines no SVGGElement,
  // so the polyfill goes on Element.prototype. V-101's box: centre (100, 100).
  const proto = typeof SVGGElement !== "undefined" ? SVGGElement.prototype : Element.prototype;
  Object.defineProperty(proto, "getBBox", {
    configurable: true,
    value() {
      return { x: 45, y: 70, width: 110, height: 60 };
    },
  });
  if (!("PointerEvent" in window)) {
    (window as unknown as { PointerEvent?: unknown }).PointerEvent = MouseEvent;
  }
});

const SVG_BEFORE =
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 120" width="300" height="120">' +
  '<g data-tag="V-101"><rect x="45" y="70" width="110" height="60"/></g>' +
  '<g data-tag="S-001"><polyline points="0,0 10,10"/></g></svg>';
// Distinguishable content so the re-fetch after a save is visible in the DOM.
const SVG_AFTER = SVG_BEFORE.replace("</svg>", "<!--placed--></svg>");

const project = structuredClone(mockProject) as unknown as Project;
const layout: Layout = { pfd: { "V-101": { x: 130, y: 120 } }, pid: {}, plot: {} };

/** waitFor polls only while the callback throws; querySelector returns null
 *  before the mocked fetch resolves, so poll on that condition explicitly. */
async function findGroup(container: HTMLElement, tag: string): Promise<Element> {
  return waitFor(() => {
    const g = container.querySelector(`g[data-tag="${tag}"]`);
    if (!g) throw new Error(`no <g data-tag="${tag}"> rendered yet`);
    return g;
  });
}

test("userUnitsPerClientPx maps client pixels to SVG user units", () => {
  expect(userUnitsPerClientPx(300, 150)).toBe(2);
  expect(userUnitsPerClientPx(300, 300)).toBe(1);
  // Unknown rendered width (jsdom reports 0): assume 1:1 rather than divide by zero.
  expect(userUnitsPerClientPx(300, 0)).toBe(1);
});

test("renders the PFD SVG with unit and stream groups", async () => {
  vi.spyOn(api, "pfdSvg").mockResolvedValue(SVG_BEFORE);
  const { container } = render(<PfdView project={project} />);
  await waitFor(() => expect(container.querySelector('g[data-tag="V-101"]')).toBeTruthy());
  expect(container.querySelector('g[data-tag="S-001"]')).toBeTruthy();
  // Units are keyboard-reachable; stream groups are not interactive. The
  // attributes are set in an effect after the SVG is injected, so poll.
  await waitFor(() =>
    expect(container.querySelector('g[data-tag="V-101"]')?.getAttribute("role")).toBe("button"),
  );
  expect(container.querySelector('g[data-tag="S-001"]')?.getAttribute("role")).toBeNull();
});

test("dragging a unit saves its new centre and re-renders from the re-fetched SVG", async () => {
  const pfdSvg = vi.spyOn(api, "pfdSvg").mockResolvedValueOnce(SVG_BEFORE).mockResolvedValueOnce(SVG_AFTER);
  const place = vi.spyOn(api, "place").mockResolvedValue(layout);
  const { container } = render(<PfdView project={project} />);
  const group = await findGroup(container, "V-101");

  // Drag by (30, 20) client px; jsdom reports no rendered width, so 1 px = 1 unit.
  fireEvent.pointerDown(group, { clientX: 100, clientY: 100, pointerId: 1, button: 0 });
  fireEvent.pointerMove(group, { clientX: 130, clientY: 120, pointerId: 1 });
  expect(group.getAttribute("transform")).toBe("translate(30 20)");
  fireEvent.pointerUp(group, { clientX: 130, clientY: 120, pointerId: 1 });

  // New centre = old bbox centre (100, 100) + delta (30, 20).
  await waitFor(() => expect(place).toHaveBeenCalledWith("pfd", "V-101", { x: 130, y: 120 }));
  await waitFor(() => expect(pfdSvg).toHaveBeenCalledTimes(2));
  await waitFor(() => expect(container.innerHTML).toContain("<!--placed-->"));
  // The re-rendered SVG is server layout, not our drag transform.
  expect(container.querySelector("g")?.getAttribute("transform")).toBeNull();
});

test("stream groups are not draggable", async () => {
  vi.spyOn(api, "pfdSvg").mockResolvedValue(SVG_BEFORE);
  const place = vi.spyOn(api, "place").mockResolvedValue(layout);
  const { container } = render(<PfdView project={project} />);
  const stream = await findGroup(container, "S-001");
  fireEvent.pointerDown(stream, { clientX: 0, clientY: 0, pointerId: 1, button: 0 });
  fireEvent.pointerMove(stream, { clientX: 50, clientY: 50, pointerId: 1 });
  fireEvent.pointerUp(stream, { clientX: 50, clientY: 50, pointerId: 1 });
  expect(place).not.toHaveBeenCalled();
});

test("a 501 shows the not-available alert instead of crashing", async () => {
  vi.spyOn(api, "pfdSvg").mockRejectedValue(new ApiError("GET /api/views/pfd.svg: 501", 501));
  render(<PfdView project={project} />);
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toContain("PFD renderer not available yet");
});

test("a failed save shows an alert and rolls the unit back to its rendered spot", async () => {
  vi.spyOn(api, "pfdSvg").mockResolvedValue(SVG_BEFORE);
  vi.spyOn(api, "place").mockRejectedValue(new ApiError("PUT /api/project/layout/pfd/V-101: 500", 500));
  const { container } = render(<PfdView project={project} />);
  const group = await findGroup(container, "V-101");
  fireEvent.pointerDown(group, { clientX: 100, clientY: 100, pointerId: 1, button: 0 });
  fireEvent.pointerMove(group, { clientX: 140, clientY: 110, pointerId: 1 });
  fireEvent.pointerUp(group, { clientX: 140, clientY: 110, pointerId: 1 });
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toContain("PFD failed:");
  await waitFor(() => expect(group.hasAttribute("transform")).toBe(false));
});

test("arrow keys nudge a focused unit and save the moved position", async () => {
  vi.spyOn(api, "pfdSvg").mockResolvedValue(SVG_BEFORE);
  const place = vi.spyOn(api, "place").mockResolvedValue(layout);
  const { container } = render(<PfdView project={project} />);
  const group = await findGroup(container, "V-101");
  fireEvent.keyDown(group, { key: "ArrowRight" });
  await waitFor(() => expect(place).toHaveBeenCalledWith("pfd", "V-101", { x: 110, y: 100 }));
});
