import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ApiError, api, type Layout, type Project } from "../api/client";
import mockProject from "../../mocks/project.json";
import { mockPfdSvg } from "../../mocks/pfdSvg";
import { mockPidSvg } from "../../mocks/pidSvg";
import { PidView, extractTags, placedTopLeft, tagParity } from "./PidView";

// jsdom has no SVG geometry and no PointerEvent; the view needs both.
beforeAll(() => {
  // getBBox: jsdom parses <g> into plain elements and defines no SVGGElement,
  // so the polyfill goes on Element.prototype. V-101's box: top-left (45, 70).
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

const SVG_PID_BEFORE =
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 120" width="300" height="120">' +
  '<g data-tag="8&quot;-PG-1001-B1"><polyline points="0,0 10,10"/></g>' +
  '<g data-tag="V-101"><rect x="45" y="70" width="110" height="60"/></g>' +
  '<g data-tag="PSV-1001"><circle cx="20" cy="20" r="8"/></g>' +
  '<g data-tag="PSV-1002"><circle cx="60" cy="20" r="8"/></g></svg>';
const SVG_PID_AFTER = SVG_PID_BEFORE.replace("</svg>", "<!--placed--></svg>");
// Distinguishable PFD content: shares V-101, adds a stream the P&ID lacks.
const SVG_PFD =
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 120" width="300" height="120">' +
  '<g data-tag="V-101"><rect x="45" y="70" width="110" height="60"/></g>' +
  '<g data-tag="S-001"><polyline points="0,0 10,10"/></g></svg>';

const project = structuredClone(mockProject) as unknown as Project;
const layout: Layout = { pfd: {}, pid: { "V-101": { x: 75, y: 90 } }, plot: {} };

/** waitFor polls only while the callback throws; querySelector returns null
 *  before the mocked fetch resolves, so poll on that condition explicitly.
 *  CSS attribute selectors see the DECODED attribute value (jsdom decoded
 *  &quot; when parsing the SVG), so escape embedded quotes for the selector. */
async function findGroup(container: HTMLElement, tag: string): Promise<Element> {
  return waitFor(() => {
    const g = container.querySelector(`g[data-tag="${tag.replace(/"/g, '\\"')}"]`);
    if (!g) throw new Error(`no <g data-tag="${tag}"> rendered yet`);
    return g;
  });
}

test("extractTags decodes entities and keeps first-occurrence order", () => {
  expect(
    extractTags('<svg><g data-tag="V-101"/><g data-tag="8&quot;-PG-1001-B1"/><g data-tag="V-101"/></svg>'),
  ).toEqual(["V-101", '8"-PG-1001-B1']);
});

test("placedTopLeft moves the box corner by the drag delta", () => {
  expect(placedTopLeft({ x: 45, y: 70 }, { x: 30, y: 20 })).toEqual({ x: 75, y: 90 });
});

test("tagParity surfaces one-diagram gaps first, then shared tags", () => {
  const rows = tagParity(
    '<g data-tag="V-101"/><g data-tag="S-001"/>',
    '<g data-tag="V-101"/><g data-tag="PSV-1001"/>',
  );
  expect(rows[0]).toEqual({ tag: "PSV-1001", inPfd: false, inPid: true });
  expect(rows[1]).toEqual({ tag: "S-001", inPfd: true, inPid: false });
  expect(rows[2]).toEqual({ tag: "V-101", inPfd: true, inPid: true });
});

test("tag parity: every sample unit tag appears in BOTH mock diagrams", () => {
  const unitTags = mockProject.flowsheet.units.map((u) => u.tag);
  const pfdTags = new Set(extractTags(mockPfdSvg({})));
  const pidTags = new Set(extractTags(mockPidSvg({})));
  expect(unitTags.length).toBeGreaterThan(0);
  for (const tag of unitTags) {
    expect(pfdTags.has(tag)).toBe(true);
    expect(pidTags.has(tag)).toBe(true);
  }
});

test("renders the P&ID and PFD side by side with the shared tag inventory", async () => {
  vi.spyOn(api, "pidSvg").mockResolvedValue(SVG_PID_BEFORE);
  vi.spyOn(api, "pfdSvg").mockResolvedValue(SVG_PFD);
  const { container } = render(<PidView project={project} />);
  await findGroup(container, "V-101");
  await findGroup(container, "PSV-1001");
  // Equipment is keyboard-reachable; valves and line numbers are not placeable.
  await waitFor(() =>
    expect(container.querySelector('g[data-tag="V-101"]')?.getAttribute("role")).toBe("button"),
  );
  expect(container.querySelector('g[data-tag="PSV-1001"]')?.getAttribute("role")).toBeNull();
  await findGroup(container, '8"-PG-1001-B1'); // decoded line number matches
  // The inventory unites both drawings' tags with per-diagram presence.
  expect(screen.getByRole("button", { name: "Find tag PSV-1001" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "Find tag S-001" })).toBeTruthy();
});

test("searching 'PSV' highlights the matching elements in both diagrams", async () => {
  vi.spyOn(api, "pidSvg").mockResolvedValue(SVG_PID_BEFORE);
  vi.spyOn(api, "pfdSvg").mockResolvedValue(SVG_PFD);
  const { container } = render(<PidView project={project} />);
  await findGroup(container, "PSV-1001");
  fireEvent.change(screen.getByLabelText("Search tags"), { target: { value: "PSV" } });
  await waitFor(() =>
    expect(container.querySelector('g[data-tag="PSV-1001"]')?.classList.contains("tag-hit")).toBe(true),
  );
  expect(container.querySelector('g[data-tag="PSV-1002"]')?.classList.contains("tag-hit")).toBe(true);
  expect(container.querySelector('g[data-tag="V-101"]')?.classList.contains("tag-hit")).toBe(false);
});

test("dragging equipment saves its new top-left corner and re-renders from the re-fetched SVG", async () => {
  const pidSvg = vi.spyOn(api, "pidSvg").mockResolvedValueOnce(SVG_PID_BEFORE).mockResolvedValueOnce(SVG_PID_AFTER);
  vi.spyOn(api, "pfdSvg").mockResolvedValue(SVG_PFD);
  const place = vi.spyOn(api, "place").mockResolvedValue(layout);
  const { container } = render(<PidView project={project} />);
  const group = await findGroup(container, "V-101");

  // Drag by (30, 20) client px; jsdom reports no rendered width, so 1 px = 1 unit.
  fireEvent.pointerDown(group, { clientX: 100, clientY: 100, pointerId: 1, button: 0 });
  fireEvent.pointerMove(group, { clientX: 130, clientY: 120, pointerId: 1 });
  expect(group.getAttribute("transform")).toBe("translate(30 20)");
  fireEvent.pointerUp(group, { clientX: 130, clientY: 120, pointerId: 1 });

  // New top-left = old bbox top-left (45, 70) + delta (30, 20).
  await waitFor(() => expect(place).toHaveBeenCalledWith("pid", "V-101", { x: 75, y: 90 }));
  await waitFor(() => expect(pidSvg).toHaveBeenCalledTimes(2));
  await waitFor(() => expect(container.innerHTML).toContain("<!--placed-->"));
  // The re-rendered SVG is server layout, not our drag transform.
  expect(container.querySelector("g")?.getAttribute("transform")).toBeNull();
});

test("valve and line groups are not draggable", async () => {
  vi.spyOn(api, "pidSvg").mockResolvedValue(SVG_PID_BEFORE);
  vi.spyOn(api, "pfdSvg").mockResolvedValue(SVG_PFD);
  const place = vi.spyOn(api, "place").mockResolvedValue(layout);
  const { container } = render(<PidView project={project} />);
  const valve = await findGroup(container, "PSV-1001");
  fireEvent.pointerDown(valve, { clientX: 0, clientY: 0, pointerId: 1, button: 0 });
  fireEvent.pointerMove(valve, { clientX: 50, clientY: 50, pointerId: 1 });
  fireEvent.pointerUp(valve, { clientX: 50, clientY: 50, pointerId: 1 });
  const line = await findGroup(container, '8"-PG-1001-B1');
  fireEvent.pointerDown(line, { clientX: 0, clientY: 0, pointerId: 1, button: 0 });
  fireEvent.pointerMove(line, { clientX: 50, clientY: 50, pointerId: 1 });
  fireEvent.pointerUp(line, { clientX: 50, clientY: 50, pointerId: 1 });
  expect(place).not.toHaveBeenCalled();
});

test("a 501 shows the not-available alert instead of crashing", async () => {
  vi.spyOn(api, "pidSvg").mockRejectedValue(new ApiError("GET /api/views/pid.svg: 501", 501));
  render(<PidView project={project} />);
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toContain("P&ID renderer not available yet");
});

test("a failed save shows an alert and rolls the unit back to its rendered spot", async () => {
  vi.spyOn(api, "pidSvg").mockResolvedValue(SVG_PID_BEFORE);
  vi.spyOn(api, "pfdSvg").mockResolvedValue(SVG_PFD);
  vi.spyOn(api, "place").mockRejectedValue(new ApiError("PUT /api/project/layout/pid/V-101: 500", 500));
  const { container } = render(<PidView project={project} />);
  const group = await findGroup(container, "V-101");
  fireEvent.pointerDown(group, { clientX: 100, clientY: 100, pointerId: 1, button: 0 });
  fireEvent.pointerMove(group, { clientX: 140, clientY: 110, pointerId: 1 });
  fireEvent.pointerUp(group, { clientX: 140, clientY: 110, pointerId: 1 });
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toContain("P&ID failed:");
  await waitFor(() => expect(group.hasAttribute("transform")).toBe(false));
});

test("arrow keys nudge a focused equipment item and save the moved position", async () => {
  vi.spyOn(api, "pidSvg").mockResolvedValue(SVG_PID_BEFORE);
  vi.spyOn(api, "pfdSvg").mockResolvedValue(SVG_PFD);
  const place = vi.spyOn(api, "place").mockResolvedValue(layout);
  const { container } = render(<PidView project={project} />);
  const group = await findGroup(container, "V-101");
  fireEvent.keyDown(group, { key: "ArrowRight" });
  await waitFor(() => expect(place).toHaveBeenCalledWith("pid", "V-101", { x: 55, y: 70 }));
});
