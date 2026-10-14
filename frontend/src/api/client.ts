// The ONLY place the frontend talks to the backend. Types come from src/api/schema.d.ts,
// generated from ../openapi.json (`npm run gen:api`). Never hand-edit schema.d.ts.
import type { components } from "./schema";
import mockProject from "../../mocks/project.json";
import mockSolved from "../../mocks/solved.json";

export type Project = components["schemas"]["Project"];
export type XY = components["schemas"]["XY"];
export type Layout = components["schemas"]["Layout"];
export type SolvedFlowsheet = components["schemas"]["SolvedFlowsheet"];

/** HTTP failure with its status, so callers can react to codes like 501. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const MOCK = import.meta.env.VITE_MOCK === "1" || import.meta.env.MODE === "test";

let mockState: Project = structuredClone(mockProject) as Project;

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...init });
  if (!r.ok) throw new ApiError(`${init?.method ?? "GET"} ${path}: ${r.status} ${await r.text()}`, r.status);
  return r.json() as Promise<T>;
}

export const api = {
  async getProject(): Promise<Project> {
    return MOCK ? structuredClone(mockState) : http<Project>("/api/project");
  },
  async place(view: "pfd" | "pid", tag: string, pos: XY): Promise<Layout> {
    if (MOCK) {
      const layout = (mockState.layout ??= { pfd: {}, pid: {}, plot: {} });
      (layout[view] ??= {})[tag] = pos;
      return structuredClone(layout);
    }
    return http<Layout>(`/api/project/layout/${view}/${encodeURIComponent(tag)}`, {
      method: "PUT",
      body: JSON.stringify(pos),
    });
  },
  async putProject(project: Project): Promise<Project> {
    if (MOCK) {
      mockState = structuredClone(project);
      return structuredClone(mockState);
    }
    return http<Project>("/api/project", {
      method: "PUT",
      body: JSON.stringify(project),
    });
  },
  async solve(): Promise<SolvedFlowsheet> {
    if (MOCK) return structuredClone(mockSolved) as SolvedFlowsheet;
    return http<SolvedFlowsheet>("/api/solve", { method: "POST" });
  },
  _resetMock() {
    mockState = structuredClone(mockProject) as Project;
  },
};
