import { useState, type FormEvent } from "react";
import type { Project } from "../api/client";
import { formatNumber, parseFiniteNumber } from "../units";

type Spec = NonNullable<Project["flowsheet"]["design_specs"]>[number];

/** Pure: the first `DS-NNN` id no design spec uses. */
export function nextSpecId(project: Project): string {
  const taken = new Set((project.flowsheet.design_specs ?? []).map((s) => s.id));
  let n = taken.size + 1;
  while (taken.has(`DS-${String(n).padStart(3, "0")}`)) n++;
  return `DS-${String(n).padStart(3, "0")}`;
}

/** Pure: writable addresses the manipulated-variable box suggests — every numeric
 * unit param (`K-101.params.P_out`). The backend validates any address on Save. */
export function writableAddresses(project: Project): string[] {
  return project.flowsheet.units.flatMap((u) =>
    Object.entries(u.params ?? {})
      .filter(([, v]) => typeof v === "number")
      .map(([k]) => `${u.tag}.params.${k}`),
  );
}

/** Pure: readable addresses the target box suggests — stream T, P and flow. */
export function readableAddresses(project: Project): string[] {
  return project.flowsheet.streams.flatMap((s) => [`${s.id}.T`, `${s.id}.P`, `${s.id}.molar_flow`]);
}

/** Design specs of the flowsheet: drive a target to a value by moving one
 * variable within bounds (values in SI). Add and Delete edit the project held by
 * the Flowsheet view; Save persists them with every other edit. */
export function DesignSpecs({ project, onChange }: { project: Project; onChange: (p: Project) => void }) {
  const specs = project.flowsheet.design_specs ?? [];
  const [adding, setAdding] = useState(false);
  const set = (next: Spec[]) => onChange({ ...project, flowsheet: { ...project.flowsheet, design_specs: next } });
  return (
    <section aria-label="Design specs">
      <h2>Design specs</h2>
      {specs.length === 0 ? (
        <p className="small muted">None. A design spec drives a target (e.g. S-005.T) to a value by adjusting one variable (e.g. E-101.params.T_out).</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Target</th>
              <th>Value (SI)</th>
              <th>Manipulated</th>
              <th>Bounds (SI)</th>
              <th>Tolerance</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {specs.map((s) => (
              <tr key={s.id} data-spec={s.id}>
                <td>{s.id}</td>
                <td>
                  <code>{s.target}</code>
                </td>
                <td>{formatNumber(s.value)}</td>
                <td>
                  <code>{s.manipulated}</code>
                </td>
                <td>
                  {formatNumber(s.lower)} … {formatNumber(s.upper)}
                </td>
                <td>{formatNumber(s.tolerance ?? 1e-4)}</td>
                <td>
                  <button type="button" className="btn ob" aria-label={`Delete design spec ${s.id}`} onClick={() => set(specs.filter((x) => x.id !== s.id))}>
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {adding ? (
        <SpecForm
          project={project}
          onAdd={(spec) => {
            set([...specs, spec]);
            setAdding(false);
          }}
          onCancel={() => setAdding(false)}
        />
      ) : (
        <button type="button" className="btn ob" onClick={() => setAdding(true)}>
          Add design spec
        </button>
      )}
    </section>
  );
}

function SpecForm({ project, onAdd, onCancel }: { project: Project; onAdd: (s: Spec) => void; onCancel: () => void }) {
  const [f, setF] = useState({ id: nextSpecId(project), target: "", value: "", manipulated: "", lower: "", upper: "", tolerance: "0.0001" });
  const [error, setError] = useState<string | null>(null);
  const field = (key: keyof typeof f, label: string, list?: string) => (
    <label className="field">
      <span>{label}</span>
      <input aria-label={label} list={list} value={f[key]} onChange={(e) => setF({ ...f, [key]: e.target.value })} />
    </label>
  );
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const ids = new Set((project.flowsheet.design_specs ?? []).map((s) => s.id));
    const [value, lower, upper, tolerance] = [f.value, f.lower, f.upper, f.tolerance].map(parseFiniteNumber);
    if (!f.id.trim()) return setError("give the spec an id");
    if (ids.has(f.id.trim())) return setError(`design spec ${f.id.trim()} already exists`);
    if (!f.target.trim() || !f.manipulated.trim()) return setError("target and manipulated variable are required");
    if (value === null || lower === null || upper === null || tolerance === null) return setError("value, bounds and tolerance must be numbers");
    if (!(lower < upper)) return setError("lower bound must be below the upper bound");
    if (!(tolerance > 0)) return setError("tolerance must be positive");
    onAdd({ id: f.id.trim(), target: f.target.trim(), value, manipulated: f.manipulated.trim(), lower, upper, tolerance, max_iterations: 30 });
  };
  return (
    <form className="panel ob connect" aria-label="Add design spec" onSubmit={submit} onKeyDown={(e) => e.key === "Escape" && onCancel()}>
      <datalist id="ds-targets">
        {readableAddresses(project).map((a) => (
          <option key={a} value={a} />
        ))}
      </datalist>
      <datalist id="ds-writable">
        {writableAddresses(project).map((a) => (
          <option key={a} value={a} />
        ))}
      </datalist>
      <div className="row">
        {field("id", "Spec id")}
        {field("target", "Target address", "ds-targets")}
        {field("value", "Target value (SI)")}
      </div>
      <div className="row">
        {field("manipulated", "Manipulated address", "ds-writable")}
        {field("lower", "Lower bound (SI)")}
        {field("upper", "Upper bound (SI)")}
        {field("tolerance", "Relative tolerance")}
      </div>
      {error && <p role="alert">{error}</p>}
      <div className="row">
        <button type="submit" className="btn ob primary">
          Add
        </button>
        <button type="button" className="btn ob" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
