import { useEffect, useState } from "react";
import { api, type Project, type TraceTarget } from "./api/client";
import { followProjectChanges, onProjectChanged } from "./api/refresh";
import { Rail, type GlobalPage } from "./components/Rail";
import { applyPalette, loadPalette, savePalette, type PaletteId } from "./theme/palettes";
import { AgentView } from "./views/AgentView";
import { DrawingsView } from "./views/DrawingsView";
import { EquipmentView } from "./views/EquipmentView";
import { FlowsheetView } from "./views/FlowsheetView";
import { HomeView } from "./views/HomeView";
import { ResultsView } from "./views/ResultsView";
import { SheetView } from "./views/SheetView";
import { TraceView } from "./views/TraceView";

// Project tabs, shown once a project is open. Add a view by adding an entry here plus a
// file in src/views/. Drawings (PFD, P&ID, plot plan, isometrics) are sub-tabs, see
// DrawingsView.tsx. Equipment, Sheet and Agent are global pages on the left rail.
const TABS = [
  { id: "flowsheet", label: "Flowsheet", layer: "L1" },
  { id: "results", label: "Results", layer: "L2" },
  { id: "trace", label: "Trace", layer: "L2" },
  { id: "drawings", label: "Drawings", layer: "L3" },
] as const;
type TabId = (typeof TABS)[number]["id"];
type Page = GlobalPage | "project";

export default function App() {
  const [page, setPage] = useState<Page>("home");
  const [tab, setTab] = useState<TabId>("flowsheet");
  const [project, setProject] = useState<Project | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [palette, setPalette] = useState<PaletteId>(loadPalette);
  // Bumped when the agent raises the shared project-changed signal: Results and
  // Drawings remount (re-fetching their data); Flowsheet re-renders from the
  // fresh project state fetched here.
  const [refresh, setRefresh] = useState(0);
  // The value the Trace tab focuses; set by clicking a number in Results.
  const [traceTarget, setTraceTarget] = useState<TraceTarget | null>(null);
  const openTrace = (t: TraceTarget) => {
    setTraceTarget(t);
    setTab("trace");
  };

  // Re-fetch the open project when the agent signals a change (Home owns the list).
  useEffect(() => {
    if (refresh === 0 || api.openProjectId() === null) return;
    api.getProject().then(setProject).catch((e: Error) => setError(e.message));
  }, [refresh]);

  useEffect(() => onProjectChanged(() => setRefresh((k) => k + 1)), []);

  // Live edits: while a project is open, follow its change stream so changes
  // made elsewhere (MCP clients, scripts, another tab) refresh every tab.
  const openId = page === "project" && project ? api.openProjectId() : null;
  useEffect(() => (openId === null ? undefined : followProjectChanges()), [openId]);

  useEffect(() => applyPalette(palette), [palette]);

  const choosePalette = (id: PaletteId) => {
    setPalette(id);
    savePalette(id);
  };
  const openProject = (id: string) => {
    setError(null);
    api
      .openProject(id)
      .then((info) => {
        setProject(info.project);
        setTab("flowsheet");
        setPage("project");
      })
      .catch((e: Error) => setError(e.message));
  };
  const closeProject = () => {
    api.closeProject();
    setProject(null);
    setPage("home");
  };
  const projectDeleted = () => {
    // Deleting the open project closes it (the client already dropped its id).
    if (api.openProjectId() === null) setProject(null);
  };

  return (
    <div className="shell">
      <Rail current={page === "project" ? "home" : page} onNavigate={setPage} palette={palette} onPalette={choosePalette} />
      <main className="main">
        {error && (
          <p role="alert" className="chip bad">
            Backend error: {error}
          </p>
        )}
        {page === "home" && <HomeView onOpen={openProject} onDeleted={projectDeleted} />}
        {page === "equipment" && <EquipmentView />}
        {page === "sheet" && <SheetView />}
        {page === "agent" && <AgentView />}
        {page === "project" && project && (
          <>
            <header className="topbar ob">
              <div className="tb-row">
                <div className="crumb">
                  <strong>{project.name}</strong>
                  <small>
                    {project.flowsheet.units.length} units · {project.flowsheet.streams.length} streams
                  </small>
                </div>
                <span className="grow" />
                <button type="button" className="btn ob" onClick={closeProject}>
                  Close
                </button>
              </div>
              <nav className="ptabs" role="tablist" aria-label="Project">
                {TABS.map((t) => (
                  <button key={t.id} type="button" role="tab" className="stab ob" aria-selected={t.id === tab} onClick={() => setTab(t.id)}>
                    {t.label}
                  </button>
                ))}
              </nav>
            </header>
            {tab === "flowsheet" && (
              <section className="page panel ob">
                <FlowsheetView project={project} onSaved={setProject} />
              </section>
            )}
            {tab === "results" && (
              <section className="page panel ob">
                <ResultsView key={refresh} onTrace={openTrace} />
              </section>
            )}
            {tab === "trace" && (
              <section className="page panel ob">
                <TraceView key={refresh} target={traceTarget} />
              </section>
            )}
            {tab === "drawings" && <DrawingsView key={refresh} project={project} />}
          </>
        )}
      </main>
    </div>
  );
}
