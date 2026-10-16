import { useState } from "react";
import type { Project } from "../api/client";
import { PfdView } from "./PfdView";
import { PidView } from "./PidView";
import { PlotView } from "./PlotView";
import { Placeholder } from "./Placeholder";

// One sub-tab per drawing. Add a drawing by adding an entry here plus a view file.
export const DRAWINGS = [
  { id: "pfd", label: "PFD", layer: "L3" },
  { id: "pid", label: "P&ID", layer: "L4" },
  { id: "plot", label: "Plot plan", layer: "L5" },
  { id: "iso", label: "Isometrics", layer: "L6" },
] as const;
type DrawingId = (typeof DRAWINGS)[number]["id"];

/** Every drawing generated from the solved model, one at a time. */
export function DrawingsView({ project }: { project: Project }) {
  const [d, setD] = useState<DrawingId>("pfd");
  return (
    <section className="page">
      <div className="pagehead">
        <div>
          <h1>Drawings</h1>
        </div>
        <div className="seg" role="tablist" aria-label="Drawing">
          {DRAWINGS.map((x) => (
            <button key={x.id} type="button" role="tab" className="stab ob" aria-selected={d === x.id} onClick={() => setD(x.id)}>
              {x.label}
            </button>
          ))}
        </div>
      </div>
      <section className="panel ob" role="tabpanel">
        {d === "pfd" && <PfdView project={project} />}
        {d === "pid" && <PidView project={project} />}
        {d === "plot" && <PlotView project={project} />}
        {d === "iso" && <Placeholder layer="L6" what="Isometrics" />}
      </section>
    </section>
  );
}
