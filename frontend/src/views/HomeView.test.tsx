import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import App from "../App";
import { api } from "../api/client";
import { HomeView, thumbnail, uniqueName } from "./HomeView";

beforeEach(() => api._resetMock());

test("uniqueName suffixes taken names", () => {
  expect(uniqueName("A", [])).toBe("A");
  expect(uniqueName("A", ["A", "A (2)"])).toBe("A (3)");
});

test("lists every project and the New project card is enabled", async () => {
  await api.createProject("Second", { template: "blank" });
  render(<HomeView onOpen={() => {}} />);
  expect(await screen.findByRole("button", { name: "Open slice" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "Open Second" })).toBeTruthy();
  const card = screen.getByRole("button", { name: /New project/ }) as HTMLButtonElement;
  expect(card.disabled).toBe(false);
});

test("New project offers blank and templates, creates the chosen one and opens it", async () => {
  const onOpen = vi.fn();
  render(<HomeView onOpen={onOpen} />);
  await screen.findByRole("button", { name: "Open slice" });
  fireEvent.click(screen.getByRole("button", { name: /New project/ }));
  const form = screen.getByRole("form", { name: "New project" });
  const blank = (await within(form).findByRole("radio", { name: /Blank flowsheet/ })) as HTMLInputElement;
  expect(blank.checked).toBe(true);
  fireEvent.click(within(form).getByRole("radio", { name: /Gas dehydration slice/ }));
  fireEvent.change(within(form).getByRole("textbox"), { target: { value: "Dehy 2" } });
  fireEvent.click(within(form).getByRole("button", { name: "Create" }));

  expect(await screen.findByRole("button", { name: "Open Dehy 2" })).toBeTruthy();
  const created = (await api.listProjects()).find((p) => p.name === "Dehy 2");
  expect(created?.template).toBe("slice");
  expect(created?.project.flowsheet.units.length).toBeGreaterThan(0);
  expect(onOpen).toHaveBeenCalledWith(created?.id);
  expect(screen.queryByRole("form", { name: "New project" })).toBeNull();
});

test("a blank project has no units; a taken name shows the backend's reason", async () => {
  render(<HomeView onOpen={() => {}} />);
  await screen.findByRole("button", { name: "Open slice" });
  fireEvent.click(screen.getByRole("button", { name: /New project/ }));
  const form = screen.getByRole("form", { name: "New project" });
  expect((within(form).getByRole("textbox") as HTMLInputElement).value).toBe("Untitled project");
  fireEvent.click(within(form).getByRole("button", { name: "Create" }));
  const card = await screen.findByRole("article", { name: "Untitled project" });
  expect(card.textContent).toMatch(/0 units/);
  expect(card.textContent).toMatch(/0 streams/);

  fireEvent.click(screen.getByRole("button", { name: /New project/ }));
  const again = screen.getByRole("form", { name: "New project" });
  fireEvent.change(within(again).getByRole("textbox"), { target: { value: "slice" } });
  fireEvent.click(within(again).getByRole("button", { name: "Create" }));
  expect((await screen.findByRole("alert")).textContent).toMatch(/already exists/);
});

test("rename, duplicate and delete a project", async () => {
  const onDeleted = vi.fn();
  render(<HomeView onOpen={() => {}} onDeleted={onDeleted} />);
  fireEvent.click(await screen.findByRole("button", { name: "Rename slice" }));
  const rename = screen.getByRole("form", { name: "Rename slice" });
  fireEvent.change(within(rename).getByRole("textbox", { name: "New name" }), { target: { value: "Dehydration" } });
  fireEvent.click(within(rename).getByRole("button", { name: "Save" }));
  expect(await screen.findByRole("button", { name: "Open Dehydration" })).toBeTruthy();
  expect((await api.listProjects()).map((p) => p.project.name)).toEqual(["Dehydration"]);

  fireEvent.click(screen.getByRole("button", { name: "Duplicate Dehydration" }));
  expect(await screen.findByRole("button", { name: "Open Dehydration copy" })).toBeTruthy();

  fireEvent.click(screen.getByRole("button", { name: "Delete Dehydration copy" }));
  const confirm = screen.getByRole("group", { name: "Confirm delete Dehydration copy" });
  fireEvent.click(within(confirm).getByRole("button", { name: "Delete" }));
  await waitFor(() => expect(screen.queryByRole("button", { name: "Open Dehydration copy" })).toBeNull());
  expect(onDeleted).toHaveBeenCalled();
  expect((await api.listProjects()).map((p) => p.name)).toEqual(["Dehydration"]);
});

test("import creates a new project under a free name", async () => {
  render(<HomeView onOpen={() => {}} />);
  await screen.findByRole("button", { name: "Open slice" });
  const body = JSON.stringify((await api.listProjects())[0].project);
  const input = screen.getByLabelText("Project file");
  const f = new File([body], "slice.json", { type: "application/json" });
  // jsdom's File has no text(); browsers do.
  Object.defineProperty(f, "text", { value: () => Promise.resolve(body) });
  fireEvent.change(input, { target: { files: [f] } });
  expect(await screen.findByRole("button", { name: "Open slice (2)" })).toBeTruthy();
  expect((await screen.findByRole("status")).textContent).toBe("Imported slice (2).");
});

test("opening a project from Home scopes the project and Close returns to the list", async () => {
  await api.createProject("Blank one", { template: "blank" });
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "Open Blank one" }));
  expect(await screen.findByRole("tab", { name: "Flowsheet" })).toBeTruthy();
  expect(screen.getByText("0 units · 0 streams")).toBeTruthy();
  expect(api.openProjectId()).not.toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Close" }));
  expect(api.openProjectId()).toBeNull();
  expect(await screen.findByRole("button", { name: "Open Blank one" })).toBeTruthy();
});

test("thumbnail draws each project's own units and connected streams", async () => {
  const [slice] = await api.listProjects();
  const t = thumbnail(slice.project);
  expect(t.boxes.map((b) => b.tag).sort()).toEqual(slice.project.flowsheet.units.map((u) => u.tag).sort());
  const connected = slice.project.flowsheet.streams.filter((s) => s.source && s.target).length;
  expect(t.links).toHaveLength(connected);
  for (const b of t.boxes) {
    expect(b.x).toBeGreaterThanOrEqual(10);
    expect(b.x).toBeLessThanOrEqual(150);
    expect(b.y).toBeGreaterThanOrEqual(10);
    expect(b.y).toBeLessThanOrEqual(60);
  }
  const blank = await api.createProject("Empty", { template: "blank" });
  expect(thumbnail(blank.project)).toEqual({ boxes: [], links: [] });
  render(<HomeView onOpen={() => {}} />);
  const card = await screen.findByRole("article", { name: "Empty" });
  expect(card.textContent).toContain("empty flowsheet");
});

test("Export downloads the project body that Import reads back", async () => {
  const created = vi.fn(() => "blob:x");
  const revoked = vi.fn();
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: created, revokeObjectURL: revoked }));
  const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  render(<HomeView onOpen={() => {}} />);
  fireEvent.click(await screen.findByRole("button", { name: "Export slice" }));
  expect(click).toHaveBeenCalledOnce();
  const blob = (created.mock.calls[0] as unknown as [Blob])[0];
  const text = await new Promise<string>((resolve) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result as string);
    r.readAsText(blob);
  });
  const body = JSON.parse(text) as { name: string; flowsheet: { units: unknown[] } };
  expect(body.name).toBe("slice");
  expect(body.flowsheet.units.length).toBeGreaterThan(0);
  expect(revoked).toHaveBeenCalledWith("blob:x");
  click.mockRestore();
  vi.unstubAllGlobals();
});

test("New project form says templates are loading and still creates a blank project", async () => {
  vi.spyOn(api, "listTemplates").mockReturnValue(new Promise(() => {}));
  const onOpen = vi.fn();
  render(<HomeView onOpen={onOpen} />);
  await screen.findByRole("button", { name: "Open slice" });
  fireEvent.click(screen.getByRole("button", { name: /New project/ }));
  const form = screen.getByRole("form", { name: "New project" });
  expect(within(form).getByRole("status").textContent).toMatch(/Loading templates/);
  fireEvent.click(within(form).getByRole("button", { name: "Create" }));
  await waitFor(() => expect(onOpen).toHaveBeenCalled());
  const made = (await api.listProjects()).find((p) => p.name === "Untitled project");
  expect(made?.template).toBe("blank");
  vi.restoreAllMocks();
});
