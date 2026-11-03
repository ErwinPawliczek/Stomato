import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { api, ApiError, type Project, type ProjectInfo, type ProjectSource, type TemplateInfo } from "../api/client";
import { Dropdown } from "../components/Dropdown";
import { autoPosition } from "./FlowsheetView";

const IMPORTS = [
  { value: "json", label: "Stomato project", meta: ".json" },
  { value: "hsc", label: "Aspen HYSYS case", meta: ".hsc · planned", disabled: true },
  { value: "bkp", label: "Aspen Plus", meta: ".bkp · planned", disabled: true },
  { value: "dwsim", label: "DWSIM", meta: ".dwxmz · planned", disabled: true },
];

/** `base`, or `base (2)`, `base (3)`, ... — the first name no project uses. */
export function uniqueName(base: string, taken: Iterable<string>): string {
  const names = new Set(taken);
  if (!names.has(base)) return base;
  for (let n = 2; ; n++) if (!names.has(`${base} (${n})`)) return `${base} (${n})`;
}

/** Most recently opened (else edited) first. */
const recency = (p: ProjectInfo) => p.opened_at ?? p.updated_at;
const byRecency = (a: ProjectInfo, b: ProjectInfo) => recency(b).localeCompare(recency(a));

const message = (e: unknown) => {
  if (e instanceof ApiError) {
    const m = /"detail":\s*"([^"]*)"/.exec(e.message);
    return m ? m[1] : e.message;
  }
  return e instanceof Error ? e.message : String(e);
};

const day = (iso: string) => iso.slice(0, 10);

/** Pure: the project's flowsheet as thumbnail geometry in a 160 x 70 box — unit
 * boxes at their stored PFD positions (else the canvas auto-layout) and one line
 * per connected stream. Empty flowsheet: no shapes. */
export function thumbnail(project: Project): { boxes: { tag: string; x: number; y: number }[]; links: [number, number, number, number][] } {
  const placed = project.layout?.pfd ?? {};
  const pos = new Map(project.flowsheet.units.map((u, i) => [u.tag, placed[u.tag] ?? autoPosition(i)]));
  if (pos.size === 0) return { boxes: [], links: [] };
  const xs = [...pos.values()].map((p) => p.x);
  const ys = [...pos.values()].map((p) => p.y);
  const [x0, y0] = [Math.min(...xs), Math.min(...ys)];
  const w = Math.max(...xs) - x0 || 1;
  const h = Math.max(...ys) - y0 || 1;
  // Fit into the 140 x 50 inner box, keeping the aspect ratio; centre a single row/column.
  const k = Math.min(140 / w, 50 / h);
  const ox = 10 + (140 - w * k) / 2;
  const oy = 10 + (50 - h * k) / 2;
  const at = (p: { x: number; y: number }) => ({ x: ox + (p.x - x0) * k, y: oy + (p.y - y0) * k });
  const boxes = [...pos.entries()].map(([tag, p]) => ({ tag, ...at(p) }));
  const links: [number, number, number, number][] = [];
  for (const st of project.flowsheet.streams) {
    const a = st.source && pos.get(st.source.unit);
    const b = st.target && pos.get(st.target.unit);
    if (a && b) {
      const [pa, pb] = [at(a), at(b)];
      links.push([pa.x, pa.y, pb.x, pb.y]);
    }
  }
  return { boxes, links };
}

function Thumb({ project }: { project: Project }) {
  const { boxes, links } = thumbnail(project);
  return (
    <svg viewBox="0 0 160 70">
      {links.map(([x1, y1, x2, y2], i) => (
        <path key={i} d={`M${x1} ${y1}L${x2} ${y2}`} />
      ))}
      {boxes.map((b) => (
        <rect key={b.tag} x={b.x - 5} y={b.y - 4} width="10" height="8" rx="1.5" />
      ))}
      {boxes.length === 0 && (
        <text x="80" y="39" textAnchor="middle" className="thumb-empty">
          empty flowsheet
        </text>
      )}
    </svg>
  );
}

/** Save a project body as `<name>.json` — the file Import reads back. */
function download(name: string, project: Project): void {
  const url = URL.createObjectURL(new Blob([JSON.stringify(project, null, 2)], { type: "application/json" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = `${name.replace(/[^\w.-]+/g, "_")}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

/** Projects: every project of the caller, newest first, plus New project (blank or
 * from a template), Import, and per-card Open / Rename / Duplicate / Delete. */
export function HomeView({ onOpen, onDeleted }: { onOpen: (id: string) => void; onDeleted?: (id: string) => void }) {
  const [projects, setProjects] = useState<ProjectInfo[] | null>(null);
  const [templates, setTemplates] = useState<TemplateInfo[]>([]);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const [renaming, setRenaming] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const file = useRef<HTMLInputElement>(null);

  const reload = useCallback(async () => {
    try {
      setProjects(await api.listProjects());
    } catch (e) {
      setError(`Could not load projects: ${message(e)}`);
    }
  }, []);
  useEffect(() => {
    void reload();
    api
      .listTemplates()
      .then(setTemplates)
      .catch((e: unknown) => setError(`Could not load templates: ${message(e)}`));
  }, [reload]);

  const taken = (projects ?? []).map((p) => p.name);

  /** Run one project action: status on success, the backend's reason on failure. */
  const act = async (work: () => Promise<string>): Promise<boolean> => {
    setError("");
    try {
      setStatus(await work());
      await reload();
      return true;
    } catch (e) {
      setStatus("");
      setError(message(e));
      return false;
    }
  };

  const readFile = async (f: File) => {
    let p: Project;
    try {
      p = JSON.parse(await f.text()) as Project;
      if (!p || typeof p.name !== "string" || !p.flowsheet) throw new Error("not a Stomato project file");
    } catch (e) {
      setStatus("");
      setError(`Could not import ${f.name}: ${message(e)}`);
      return;
    }
    const name = uniqueName(p.name.trim() || "Imported project", taken);
    await act(async () => {
      await api.createProject(name, { project: { ...p, name } });
      return `Imported ${name}.`;
    });
  };

  const create = async (name: string, source: ProjectSource) => {
    const ok = await act(async () => {
      const info = await api.createProject(name, source);
      onOpen(info.id);
      return `Created ${info.name}.`;
    });
    if (ok) setCreating(false);
  };

  const q = query.trim().toLowerCase();
  const shown = (projects ?? []).filter((p) => p.name.toLowerCase().includes(q)).sort(byRecency);
  const titleOf = (id: string | null | undefined) => templates.find((t) => t.id === id)?.title;

  return (
    <section className="page">
      <div className="pagehead">
        <div>
          <h1>Projects</h1>
        </div>
        <div className="row">
          <Dropdown
            label="Import"
            className="importdd"
            options={IMPORTS}
            trigger={<span>Import</span>}
            onChange={() => file.current?.click()}
          />
          <input
            ref={file}
            type="file"
            accept=".json,application/json"
            hidden
            aria-label="Project file"
            onChange={(e) => {
              const f = e.target.files?.[0];
              e.target.value = "";
              if (f) void readFile(f);
            }}
          />
        </div>
      </div>
      {status && (
        <p className="small muted" role="status">
          {status}
        </p>
      )}
      {error && (
        <p className="chip bad" role="alert">
          {error}
        </p>
      )}
      <div className="inp ob search">
        <input type="search" name="psearch" aria-label="Search projects" placeholder="Search projects" value={query} onChange={(e) => setQuery(e.target.value)} />
      </div>
      {creating && (
        <NewProjectForm
          templates={templates}
          defaultName={uniqueName("Untitled project", taken)}
          onCancel={() => setCreating(false)}
          onCreate={(name, source) => void create(name, source)}
        />
      )}
      <div className="g3">
        <button type="button" className="proj ob new" onClick={() => setCreating(true)} aria-expanded={creating}>
          <span className="plus">+</span>
          <h3>New project</h3>
          <span className="muted small">Blank flowsheet, or start from a template</span>
        </button>
        {shown.map((p) => (
          <article key={p.id} className="proj ob" aria-label={p.name}>
            <button type="button" className="open" aria-label={`Open ${p.name}`} onClick={() => onOpen(p.id)}>
              <span className="thumb" aria-hidden="true">
                <Thumb project={p.project} />
              </span>
              <h3>{p.name}</h3>
              <span className="stats">
                <span className="stat">
                  <b>{p.project.flowsheet.units.length}</b> units
                </span>
                <span className="stat">
                  <b>{p.project.flowsheet.streams.length}</b> streams
                </span>
              </span>
              <span className="muted small">
                {titleOf(p.template) ? `${titleOf(p.template)} · ` : ""}edited {day(p.updated_at)}
              </span>
            </button>
            {renaming === p.id ? (
              <RenameForm
                current={p.name}
                onCancel={() => setRenaming(null)}
                onSave={(name) =>
                  void act(async () => {
                    const info = await api.renameProject(p.id, name);
                    setRenaming(null);
                    return `Renamed to ${info.name}.`;
                  })
                }
              />
            ) : deleting === p.id ? (
              <div className="acts" role="group" aria-label={`Confirm delete ${p.name}`}>
                <span className="small">Delete {p.name}? This cannot be undone.</span>
                <button
                  type="button"
                  className="btn ob"
                  onClick={() =>
                    void act(async () => {
                      await api.deleteProject(p.id);
                      setDeleting(null);
                      onDeleted?.(p.id);
                      return `Deleted ${p.name}.`;
                    })
                  }
                >
                  Delete
                </button>
                <button type="button" className="btn ob" onClick={() => setDeleting(null)}>
                  Cancel
                </button>
              </div>
            ) : (
              <div className="acts">
                <button type="button" className="btn ob" aria-label={`Rename ${p.name}`} onClick={() => setRenaming(p.id)}>
                  Rename
                </button>
                <button
                  type="button"
                  className="btn ob"
                  aria-label={`Duplicate ${p.name}`}
                  onClick={() =>
                    void act(async () => {
                      const info = await api.createProject(uniqueName(`${p.name} copy`, taken), { from_project: p.id });
                      return `Created ${info.name}.`;
                    })
                  }
                >
                  Duplicate
                </button>
                <button type="button" className="btn ob" aria-label={`Export ${p.name}`} onClick={() => download(p.name, p.project)}>
                  Export
                </button>
                <button type="button" className="btn ob" aria-label={`Delete ${p.name}`} onClick={() => setDeleting(p.id)}>
                  Delete
                </button>
              </div>
            )}
          </article>
        ))}
      </div>
      {projects === null && !error && <p className="muted">Loading…</p>}
      {projects?.length === 0 && <p className="muted">No projects yet. Start one with New project, or import a file.</p>}
    </section>
  );
}

/** New project: a name and what to start from (blank flowsheet or a template). */
function NewProjectForm({
  templates,
  defaultName,
  onCreate,
  onCancel,
}: {
  templates: TemplateInfo[];
  defaultName: string;
  onCreate: (name: string, source: ProjectSource) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState(defaultName);
  const [choice, setChoice] = useState("blank");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (name.trim()) onCreate(name.trim(), { template: choice });
  };
  return (
    <form className="panel ob newproj" aria-label="New project" onSubmit={submit} onKeyDown={(e) => e.key === "Escape" && onCancel()}>
      <h2>New project</h2>
      <label className="pfield">
        <span>Name</span>
        <span className="inp ob">
          <input name="pname" value={name} onChange={(e) => setName(e.target.value)} autoFocus />
        </span>
      </label>
      <fieldset>
        <legend>Start from</legend>
        {templates.length === 0 && (
          <p className="small muted" role="status">
            Loading templates… (Create now starts a blank flowsheet.)
          </p>
        )}
        {templates.map((t) => (
          <label key={t.id} className="tpl">
            <input type="radio" name="template" value={t.id} checked={choice === t.id} onChange={() => setChoice(t.id)} />
            <span>
              <b>{t.title}</b>
              <span className="muted small">
                {" "}
                {t.description}
                {t.units > 0 && ` · ${t.units} units, ${t.streams} streams`}
              </span>
            </span>
          </label>
        ))}
      </fieldset>
      <div className="row">
        <button type="submit" className="btn ob primary" disabled={!name.trim()}>
          Create
        </button>
        <button type="button" className="btn ob" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}

function RenameForm({ current, onSave, onCancel }: { current: string; onSave: (name: string) => void; onCancel: () => void }) {
  const [name, setName] = useState(current);
  return (
    <form
      className="acts"
      aria-label={`Rename ${current}`}
      onSubmit={(e) => {
        e.preventDefault();
        if (name.trim()) onSave(name.trim());
      }}
      onKeyDown={(e) => e.key === "Escape" && onCancel()}
    >
      <span className="inp ob">
        <input aria-label="New name" value={name} onChange={(e) => setName(e.target.value)} autoFocus />
      </span>
      <button type="submit" className="btn ob" disabled={!name.trim()}>
        Save
      </button>
      <button type="button" className="btn ob" onClick={onCancel}>
        Cancel
      </button>
    </form>
  );
}
