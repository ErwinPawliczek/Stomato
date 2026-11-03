// The real HTTP paths (mocks off): with no project open the client uses the legacy
// unscoped routes; once Home opens a project every project call goes to its
// /api/projects/{id}/... twin.
import { afterEach, beforeEach, expect, test, vi } from "vitest";

type Call = { url: string; method: string; body?: string };
let calls: Call[] = [];

const project = { name: "P", flowsheet: { name: "P", units: [], streams: [] }, layout: { pfd: {}, pid: {}, plot: {} } };
const info = { id: "a b", name: "P", owner: "local", version: 1, created_at: "t", updated_at: "t", project };

beforeEach(() => {
  calls = [];
  vi.stubEnv("MODE", "development");
  vi.stubEnv("VITE_MOCK", "0");
  vi.resetModules();
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      calls.push({ url, method: init?.method ?? "GET", body: init?.body as string | undefined });
      const json = url.endsWith("/api/templates") ? { templates: [] } : url.endsWith("/api/projects") && !init?.method ? { projects: [info] } : info;
      return Promise.resolve(new Response(url.endsWith(".svg") ? "<svg/>" : JSON.stringify(json), { status: 200 }));
    }),
  );
});
afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

const load = async () => (await import("./client")).api;

test("project calls switch from legacy routes to the open project's scoped routes", async () => {
  const api = await load();
  await api.getProject();
  await api.solve();
  expect(calls.map((c) => c.url)).toEqual(["/api/project", "/api/solve"]);

  calls = [];
  const opened = await api.openProject("a b");
  expect(opened.project.name).toBe("P");
  expect(api.openProjectId()).toBe("a b");
  const base = "/api/projects/a%20b";
  expect(await api.getProject()).toEqual(project);
  await api.putProject(project as never);
  await api.solve();
  await api.pfdSvg();
  await api.pidSvg();
  await api.plotSvg();
  await api.route();
  await api.place("pid", "V-101", { x: 1, y: 2 });
  await api.placePlot("V-101", { x: 1, y: 2, z: 0 });
  expect(calls.map((c) => `${c.method} ${c.url}`)).toEqual([
    `POST ${base}/open`,
    `GET ${base}`,
    `PUT ${base}`,
    `POST ${base}/solve`,
    `GET ${base}/views/pfd.svg`,
    `GET ${base}/views/pid.svg`,
    `GET ${base}/views/plot.svg`,
    `POST ${base}/route`,
    `PUT ${base}/layout/pid/V-101`,
    `PUT ${base}/layout/plot/V-101`,
  ]);

  api.closeProject();
  calls = [];
  await api.solve();
  expect(calls.map((c) => c.url)).toEqual(["/api/solve"]);
});

test("project management calls hit the multi-project endpoints", async () => {
  const api = await load();
  expect(await api.listProjects()).toHaveLength(1);
  await api.listTemplates();
  await api.createProject("New", { template: "slice" });
  await api.createProject("Copy", { from_project: "x" });
  await api.renameProject("x", "Renamed");
  await api.deleteProject("x");
  expect(calls.map((c) => `${c.method} ${c.url} ${c.body ?? ""}`.trim())).toEqual([
    "GET /api/projects",
    "GET /api/templates",
    'POST /api/projects {"name":"New","template":"slice"}',
    'POST /api/projects {"name":"Copy","from_project":"x"}',
    'PATCH /api/projects/x {"name":"Renamed"}',
    "DELETE /api/projects/x",
  ]);
});

test("deleting the open project closes it", async () => {
  const api = await load();
  await api.openProject("a b");
  await api.deleteProject("a b");
  expect(api.openProjectId()).toBeNull();
});

test("trace, audit and agent conversations follow the open project, not the default one", async () => {
  const api = await load();
  await api.openProject("a b");
  calls = [];
  await api.trace();
  await api.trace({ stream: "S-1", prop: "T" });
  await api.traceAudit();
  await api.agent.conversations();
  await api.agent.transcript("c 1");
  const base = "/api/projects/a%20b";
  expect(calls.map((c) => `${c.method} ${c.url}`)).toEqual([
    `GET ${base}/trace`,
    `GET ${base}/trace?stream=S-1&prop=T`,
    `GET ${base}/trace/audit`,
    `GET ${base}/agent`,
    `GET ${base}/agent/c%201`,
  ]);
  // An explicit project still wins.
  calls = [];
  await api.trace(undefined, "other");
  expect(calls.map((c) => c.url)).toEqual(["/api/projects/other/trace"]);
});
