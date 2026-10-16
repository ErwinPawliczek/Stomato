import { useRef, useState } from "react";
import type { Project } from "../api/client";
import { Dropdown } from "../components/Dropdown";

const IMPORTS = [
  { value: "json", label: "Stomato project", meta: ".json" },
  { value: "hsc", label: "Aspen HYSYS case", meta: ".hsc · planned", disabled: true },
  { value: "bkp", label: "Aspen Plus", meta: ".bkp · planned", disabled: true },
  { value: "dwsim", label: "DWSIM", meta: ".dwxmz · planned", disabled: true },
];

/** Projects. The backend holds one project today, so the list has one card; New project
 * waits for a multi-project endpoint. */
export function HomeView({
  project,
  onOpen,
  onImport,
}: {
  project: Project | null;
  onOpen: () => void;
  onImport: (p: Project) => Promise<void>;
}) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const file = useRef<HTMLInputElement>(null);

  const readFile = async (f: File) => {
    try {
      const p = JSON.parse(await f.text()) as Project;
      if (!p || typeof p.name !== "string" || !p.flowsheet) throw new Error("not a Stomato project file");
      await onImport(p);
      setStatus(`Imported ${p.name}.`);
    } catch (e) {
      setStatus(`Could not import ${f.name}: ${(e as Error).message}`);
    }
  };

  const shown = project && project.name.toLowerCase().includes(query.trim().toLowerCase());
  const units = project?.flowsheet.units.length ?? 0;
  const streams = project?.flowsheet.streams.length ?? 0;

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
      <div className="inp ob search">
        <input type="search" name="psearch" aria-label="Search projects" placeholder="Search projects" value={query} onChange={(e) => setQuery(e.target.value)} />
      </div>
      <div className="g3">
        <button type="button" className="proj ob new" disabled title="Needs a multi-project endpoint in the backend">
          <span className="plus">+</span>
          <h3>New project</h3>
          <span className="muted small">Blank flowsheet, or start from a template</span>
        </button>
        {shown && (
          <button type="button" className="proj ob" onClick={onOpen}>
            <span className="thumb" aria-hidden="true">
              <svg viewBox="0 0 160 70">
                <path d="M10 35h30M70 35h30M130 35h20" />
                <rect x="40" y="20" width="30" height="30" rx="15" />
                <polygon points="100,22 130,28 130,42 100,48" />
              </svg>
            </span>
            <h3>{project.name}</h3>
            <span className="stats">
              <span className="stat">
                <b>{units}</b> units
              </span>
              <span className="stat">
                <b>{streams}</b> streams
              </span>
            </span>
          </button>
        )}
      </div>
      {!project && <p className="muted">Loading…</p>}
    </section>
  );
}
