import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ApiError, api, type Layout, type Project } from "../api/client";
import mockProject from "../../mocks/project.json";
import { mockPfdSvg } from "../../mocks/pfdSvg";
import { mockPidSvg } from "../../mocks/pidSvg";
import { PidView, extractTags, placedTopLeft, tagParity } from "./PidView";

// jsdom has no PointerEvent and reports no element geometry; the view needs
// both. The geometry stub models V-101's .equipment-bbox rect in the P&ID
// panel: top-left (45, 70), 110×60 — matching the SVG below.
beforeAll(() => {
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

const SVG_PID_BEFORE =
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 120" width="300" height="120">' +
  '<g data-tag="8&quot;-PG-1001-B1"><polyline points="0,0 10,10"/></g>' +
  // Equipment mirrors the real P&ID renderer: an invisible .equipment-bbox
  // rect tagged at the stored top-left inside a plain, untagged group.
  '<g><rect x="45" y="70" width="110" height="60" class="equipment-bbox" data-tag="V-101" fill="none" stroke="none"/>' +
  '<text x="100" y="65" font-size="9">V-101</text></g>' +
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
 *  Matches ANY tagged element — the P&ID's bbox rects and the PFD's tagged
 *  groups alike. CSS attribute selectors see the DECODED attribute value
 *  (jsdom decoded &quot; when parsing the SVG), so escape embedded quotes. */
async function findTagged(container: HTMLElement, tag: string): Promise<Element> {
  return waitFor(() => {
    const el = container.querySelector(`[data-tag="${tag.replace(/"/g, '\\"')}"]`);
    if (!el) throw new Error(`no [data-tag="${tag}"] rendered yet`);
    return el;
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
  await findTagged(container, "V-101");
  await findTagged(container, "PSV-1001");
  // Equipment is keyboard-reachable; valves and line numbers are not placeable.
  await waitFor(() =>
    expect(container.querySelector('[data-tag="V-101"]')?.getAttribute("role")).toBe("button"),
  );
  expect(container.querySelector('[data-tag="PSV-1001"]')?.getAttribute("role")).toBeNull();
  await findTagged(container, '8"-PG-1001-B1'); // decoded line number matches
  // The inventory unites both drawings' tags with per-diagram presence.
  expect(screen.getByRole("button", { name: "Find tag PSV-1001" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "Find tag S-001" })).toBeTruthy();
});

test("searching 'PSV' highlights the matching elements in both diagrams", async () => {
  vi.spyOn(api, "pidSvg").mockResolvedValue(SVG_PID_BEFORE);
  vi.spyOn(api, "pfdSvg").mockResolvedValue(SVG_PFD);
  const { container } = render(<PidView project={project} />);
  await findTagged(container, "PSV-1001");
  fireEvent.change(screen.getByLabelText("Search tags"), { target: { value: "PSV" } });
  await waitFor(() =>
    expect(container.querySelector('[data-tag="PSV-1001"]')?.classList.contains("tag-hit")).toBe(true),
  );
  expect(container.querySelector('[data-tag="PSV-1002"]')?.classList.contains("tag-hit")).toBe(true);
  expect(container.querySelector('[data-tag="V-101"]')?.classList.contains("tag-hit")).toBe(false);
});

test("dragging equipment saves its new top-left corner and re-renders from the re-fetched SVG", async () => {
  const pidSvg = vi.spyOn(api, "pidSvg").mockResolvedValueOnce(SVG_PID_BEFORE).mockResolvedValueOnce(SVG_PID_AFTER);
  vi.spyOn(api, "pfdSvg").mockResolvedValue(SVG_PFD);
  const place = vi.spyOn(api, "place").mockResolvedValue(layout);
  const { container } = render(<PidView project={project} />);
  const box = await findTagged(container, "V-101");
  // The pointer lands on the untagged equipment group (as on the real
  // renderer, where the bbox rect is an invisible sibling); the hit-test
  // must still resolve it to V-101 by coordinates.
  const equipGroup = box.parentElement as Element;

  // Drag by (30, 20) client px; jsdom reports no rendered width, so 1 px = 1 unit.
  fireEvent.pointerDown(equipGroup, { clientX: 100, clientY: 100, pointerId: 1, button: 0 });
  fireEvent.pointerMove(equipGroup, { clientX: 130, clientY: 120, pointerId: 1 });
  expect(equipGroup.getAttribute("transform")).toBe("translate(30 20)");
  fireEvent.pointerUp(equipGroup, { clientX: 130, clientY: 120, pointerId: 1 });

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
  const valve = await findTagged(container, "PSV-1001");
  fireEvent.pointerDown(valve, { clientX: 0, clientY: 0, pointerId: 1, button: 0 });
  fireEvent.pointerMove(valve, { clientX: 50, clientY: 50, pointerId: 1 });
  fireEvent.pointerUp(valve, { clientX: 50, clientY: 50, pointerId: 1 });
  const line = await findTagged(container, '8"-PG-1001-B1');
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
  const box = await findTagged(container, "V-101");
  const equipGroup = box.parentElement as Element;
  fireEvent.pointerDown(equipGroup, { clientX: 100, clientY: 100, pointerId: 1, button: 0 });
  fireEvent.pointerMove(equipGroup, { clientX: 140, clientY: 110, pointerId: 1 });
  fireEvent.pointerUp(equipGroup, { clientX: 140, clientY: 110, pointerId: 1 });
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toContain("P&ID failed:");
  await waitFor(() => expect(equipGroup.hasAttribute("transform")).toBe(false));
});

test("arrow keys nudge a focused equipment item and save the moved position", async () => {
  vi.spyOn(api, "pidSvg").mockResolvedValue(SVG_PID_BEFORE);
  vi.spyOn(api, "pfdSvg").mockResolvedValue(SVG_PFD);
  const place = vi.spyOn(api, "place").mockResolvedValue(layout);
  const { container } = render(<PidView project={project} />);
  const box = await findTagged(container, "V-101");
  fireEvent.keyDown(box, { key: "ArrowRight" });
  await waitFor(() => expect(place).toHaveBeenCalledWith("pid", "V-101", { x: 55, y: 70 }));
});
