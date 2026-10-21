import { useEffect, useState } from "react";
import { api, type Project } from "./api/client";
import { onProjectChanged } from "./api/refresh";
import { Rail, type GlobalPage } from "./components/Rail";
import { applyPalette, loadPalette, savePalette, type PaletteId } from "./theme/palettes";
import { AgentView } from "./views/AgentView";
import { DrawingsView } from "./views/DrawingsView";
import { EquipmentView } from "./views/EquipmentView";
import { FlowsheetView } from "./views/FlowsheetView";
import { HomeView } from "./views/HomeView";
import { ResultsView } from "./views/ResultsView";
import { SheetView } from "./views/SheetView";

// Project tabs, shown once a project is open. Add a view by adding an entry here plus a
// file in src/views/. Drawings (PFD, P&ID, plot plan, isometrics) are sub-tabs, see
// DrawingsView.tsx. Equipment, Sheet and Agent are global pages on the left rail.
const TABS = [
  { id: "flowsheet", label: "Flowsheet", layer: "L1" },
  { id: "results", label: "Results", layer: "L2" },
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

  useEffect(() => {
    api.getProject().then(setProject).catch((e: Error) => setError(e.message));
  }, [refresh]);

  useEffect(() => onProjectChanged(() => setRefresh((k) => k + 1)), []);

  useEffect(() => applyPalette(palette), [palette]);

  const choosePalette = (id: PaletteId) => {
    setPalette(id);
    savePalette(id);
  };
  const importProject = async (p: Project) => {
    setProject(await api.putProject(p));
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
        {page === "home" && <HomeView project={project} onOpen={() => setPage("project")} onImport={importProject} />}
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
                <button type="button" className="btn ob" onClick={() => setPage("home")}>
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
                <FlowsheetView project={project} />
              </section>
            )}
            {tab === "results" && (
              <section className="page panel ob">
                <ResultsView key={refresh} />
              </section>
            )}
            {tab === "drawings" && <DrawingsView key={refresh} project={project} />}
          </>
        )}
      </main>
    </div>
  );
}
