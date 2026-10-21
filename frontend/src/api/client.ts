// The ONLY place the frontend talks to the backend. Types come from src/api/schema.d.ts,
// generated from ../openapi.json (`npm run gen:api`). Never hand-edit schema.d.ts.
import type { components } from "./schema";
import mockProject from "../../mocks/project.json";
import mockSolved from "../../mocks/solved.json";
import { mockPfdSvg } from "../../mocks/pfdSvg";
import { mockPidSvg } from "../../mocks/pidSvg";
import { mockPlotSvg } from "../../mocks/plotSvg";
import mockAgentEvents from "../../mocks/agent-events.json";

export type Project = components["schemas"]["Project"];
export type XY = components["schemas"]["XY"];
export type Layout = components["schemas"]["Layout"];
export type Meta = {
  [kind: string]: string[];
};
export type SolvedFlowsheet = components["schemas"]["SolvedFlowsheet"];
export type Vec3 = components["schemas"]["Vec3"];
export type PipingNetwork = components["schemas"]["PipingNetwork"];

// Mirror of GET /api/meta (routes_meta.py): every @register(kind, name) in
// src/ngdesign, read from source at the current commit. Lets the thermo
// selector and add-unit palette demo without a backend.
const MOCK_META: Meta = {
  correlation: [
    "cv_liquid",
    "darcy_colebrook",
    "erosional_api14e",
    "flange_rating_b165",
    "hammerschmidt_formation",
    "kremser",
    "line_size",
    "lmtd_counter",
    "nielsen_bucklin_suppression",
    "psv_api520_gas",
    "pump_power",
    "souders_brown",
    "wall_thickness_b313",
  ],
  diagram: ["pfd", "pid"],
  iso_renderer: ["svg"],
  pid_builder: ["default"],
  pid_rule: [
    "discharge_check",
    "drains_vents",
    "nozzle_isolation",
    "psv_sizing",
    "pump_instruments",
    "vessel_instruments",
    "vessel_psv",
  ],
  router: ["orthogonal"],
  sizer: ["air_cooler", "compressor", "pump", "scrubber", "separator_3phase", "shell_tube", "teg_contactor"],
  solver: ["sequential_modular"],
  thermo: ["nrtl", "pr", "pr78", "srk"],
  unit: [
    "air_cooler",
    "compression_train",
    "compressor",
    "cooler",
    "expander",
    "heater",
    "jt_valve",
    "mdea_absorber",
    "mdea_regenerator",
    "mixer",
    "pump",
    "scrubber",
    "separator_3phase",
    "shell_tube",
    "splitter",
    "teg_contactor",
  ],
};

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

/** Like http(), for text endpoints (SVG views) instead of JSON. */
async function httpText(path: string): Promise<string> {
  const r = await fetch(path);
  if (!r.ok) throw new ApiError(`GET ${path}: ${r.status} ${await r.text()}`, r.status);
  return r.text();
}

// --- Agent (B-08 SSE) ---
// Typed locally from the event schema in specs/frontend/F-08-l8-agent-chat-panel.md
// because src/api/schema.d.ts does not carry the agent routes yet (generated file —
// never hand-edited). When B-08 merges, these become generated types in a follow-up.
export type AgentEvent =
  | { type: "text_delta"; text: string }
  | { type: "tool_call"; id: string; name: string; input: unknown }
  | { type: "tool_result"; id: string; ok: boolean; summary: string; result?: unknown }
  | { type: "project_changed" }
  | { type: "done"; conversation_id: string; stop_reason: string; usage?: Record<string, number> }
  | { type: "error"; message: string };

/** Parse one SSE frame (the text between blank lines) into events. */
function parseSseFrame(frame: string, onEvent: (e: AgentEvent) => void): void {
  for (const line of frame.split("\n")) {
    if (!line.startsWith("data:")) continue;
    const data = line.slice(5).trim();
    if (data) onEvent(JSON.parse(data) as AgentEvent);
  }
}

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));

const agent = {
  /** Send one message to POST /api/agent and stream the reply as AgentEvents.
   * `conversationId` continues a session (undefined starts one); the `done`
   * event carries the id to pass back on the next send. */
  async send(message: string, conversationId: string | undefined, onEvent: (e: AgentEvent) => void): Promise<void> {
    if (MOCK) {
      // Canned showcase conversation, one event at a time.
      for (const e of mockAgentEvents as AgentEvent[]) {
        onEvent(e);
        await delay(40);
      }
      return;
    }
    const r = await fetch("/api/agent", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, conversation_id: conversationId }),
    });
    if (!r.ok || !r.body) throw new ApiError(`POST /api/agent: ${r.status} ${await r.text()}`, r.status);
    const reader = r.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let sep: number;
      while ((sep = buf.indexOf("\n\n")) !== -1) {
        parseSseFrame(buf.slice(0, sep), onEvent);
        buf = buf.slice(sep + 2);
      }
    }
    buf += decoder.decode();
    if (buf.trim()) parseSseFrame(buf, onEvent);
  },
};

export const api = {
  /** Chat with the engine agent over the B-08 SSE stream. */
  agent,
  /** Registered plugin names per registry kind — feeds the thermo selector and
   * the add-unit palette. The backend validates any choice at solve time. */
  async getMeta(): Promise<Meta> {
    if (MOCK) return structuredClone(MOCK_META);
    return http<Meta>("/api/meta");
  },
  async getProject(): Promise<Project> {
    return MOCK ? structuredClone(mockState) : http<Project>("/api/project");
  },
  async pfdSvg(): Promise<string> {
    // Mock honours the backend contract: a stored layout.pfd position is the
    // unit box's centre (spec B-03), so saved placements survive re-fetch.
    if (MOCK) return mockPfdSvg(mockState.layout?.pfd ?? {});
    return httpText("/api/views/pfd.svg");
  },
  async pidSvg(): Promise<string> {
    // Mock honours the backend contract: a stored layout.pid position is the
    // equipment box's top-left corner (spec B-04), so saved placements survive.
    if (MOCK) return mockPidSvg(mockState.layout?.pid ?? {});
    return httpText("/api/views/pid.svg");
  },
  async plotSvg(): Promise<string> {
    // Mock honours the backend contract: a stored layout.plot position is the
    // equipment envelope's centre in model mm (spec B-05), and every fetch
    // re-routes through the stored placements — so the plot view re-renders
    // the fresh routing after each placement save.
    if (MOCK) return mockPlotSvg(mockState.layout?.plot ?? {});
    return httpText("/api/views/plot.svg");
  },
  async placePlot(tag: string, pos: Vec3): Promise<Layout> {
    // The plot plan has its own PUT taking a full Vec3 (x, y in mm on the
    // plan, z the elevation) — routes_plot.py's shadowed-route 422 is gone.
    if (MOCK) {
      const layout = (mockState.layout ??= { pfd: {}, pid: {}, plot: {} });
      (layout.plot ??= {})[tag] = pos;
      return structuredClone(layout);
    }
    return http<Layout>(`/api/project/layout/plot/${encodeURIComponent(tag)}`, {
      method: "PUT",
      body: JSON.stringify(pos),
    });
  },
  async route(): Promise<PipingNetwork> {
    // Explicit re-route (POST /api/route). The SVG views route implicitly on
    // every fetch; the JSON call surfaces routing problems as a 501/422
    // before the view re-renders.
    if (MOCK) return { equipment: [], lines: [], rack_elevation_mm: 6000 };
    return http<PipingNetwork>("/api/route", { method: "POST" });
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
