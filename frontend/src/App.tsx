import { useEffect, useState } from "react";
import { api, type Project } from "./api/client";
import { FlowsheetView } from "./views/FlowsheetView";
import { ResultsView } from "./views/ResultsView";
import { Placeholder } from "./views/Placeholder";

// One tab per view. Add a view by adding an entry here plus a file in src/views/.
const TABS = [
  { id: "flowsheet", label: "Flowsheet", layer: "L1" },
  { id: "results", label: "Results", layer: "L2" },
  { id: "pfd", label: "PFD", layer: "L3" },
  { id: "pid", label: "P&ID", layer: "L4" },
  { id: "plot", label: "Plot plan", layer: "L5" },
  { id: "iso", label: "Isometrics", layer: "L6" },
  { id: "sheet", label: "Sheet", layer: "L7" },
  { id: "agent", label: "Agent", layer: "L8" },
] as const;
type TabId = (typeof TABS)[number]["id"];

export default function App() {
  const [tab, setTab] = useState<TabId>("flowsheet");
  const [project, setProject] = useState<Project | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getProject().then(setProject).catch((e: Error) => setError(e.message));
  }, []);

  const current = TABS.find((t) => t.id === tab)!;
  return (
    <div className="app">
      <header>
        <strong>ngdesign</strong> <span className="muted">{project?.name ?? ""}</span>
        <nav role="tablist">
          {TABS.map((t) => (
            <button key={t.id} role="tab" aria-selected={t.id === tab} onClick={() => setTab(t.id)}>
              {t.label}
            </button>
          ))}
        </nav>
      </header>
      <main>
        {error && <p role="alert">Backend error: {error}</p>}
        {!project && !error && <p>Loading…</p>}
        {project && tab === "flowsheet" && <FlowsheetView project={project} />}
        {project && tab === "results" && <ResultsView />}
        {project && tab !== "flowsheet" && tab !== "results" && (
          <Placeholder layer={current.layer} what={current.label} />
        )}
      </main>
    </div>
  );
}
