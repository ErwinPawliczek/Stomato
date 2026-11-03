import { useState } from "react";
import type { ReactNode } from "react";
import { ApiError, api, type SolvedFlowsheet, type TraceTarget } from "../api/client";
import { formatNumber, toDegC, toKPaG, toKmolH, toKw, toVaporFraction } from "../units";

/** A result number; with `onTrace` it is a button that opens the Trace view on that value. */
function Traced({ target, onTrace, children }: { target: TraceTarget; onTrace?: (t: TraceTarget) => void; children: ReactNode }) {
  if (!onTrace) return <>{children}</>;
  const of = "stream" in target ? target.stream : target.unit;
  return (
    <button type="button" className="tracelink" title={`Trace ${of} ${target.prop}`} onClick={() => onTrace(target)}>
      {children}
    </button>
  );
}

/** Layer 2: solve the slice and show stream states plus unit duty/power. Clicking a number
 * calls `onTrace` with the value it shows (stream + prop, or unit + prop). */
export function ResultsView({ onTrace }: { onTrace?: (t: TraceTarget) => void } = {}) {
  const [result, setResult] = useState<SolvedFlowsheet | null>(null);
  const [solving, setSolving] = useState(false);
  const [solverUnavailable, setSolverUnavailable] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function solve() {
    setSolving(true);
    setSolverUnavailable(false);
    setError(null);
    try {
      setResult(await api.solve());
    } catch (e) {
      if (e instanceof ApiError && e.status === 501) setSolverUnavailable(true);
      else if (e instanceof Error) setError(e.message);
      else setError(String(e));
    } finally {
      setSolving(false);
    }
  }

  const streams = result ? Object.entries(result.streams).sort(([a], [b]) => a.localeCompare(b)) : [];
  const units = result ? Object.entries(result.units).sort(([a], [b]) => a.localeCompare(b)) : [];

  return (
    <div>
      <p>
        <button onClick={solve} disabled={solving}>
          {solving ? "Solving…" : "Solve"}
        </button>
        {result && (
          <span className={result.converged ? "" : "muted"}>
            {" "}
            {result.converged ? "Converged" : "Did not converge"} in {result.iterations} iteration
            {result.iterations === 1 ? "" : "s"}
          </span>
        )}
      </p>
      {solverUnavailable && (
        <p role="alert">
          Solver not available yet
        </p>
      )}
      {error && <p role="alert">Solve failed: {error}</p>}
      {result && (
        <div className="grid">
          <section>
            <h2>Streams</h2>
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>T (degC)</th>
                  <th>P (kPa(g))</th>
                  <th>Flow (kmol/h)</th>
                  <th>Vapor fraction</th>
                </tr>
              </thead>
              <tbody>
                {streams.map(([id, st]) => (
                  <tr key={id} data-stream={id}>
                    <td>{id}</td>
                    <td>
                      <Traced target={{ stream: id, prop: "T" }} onTrace={onTrace}>
                        {toDegC(st.T)}
                      </Traced>
                    </td>
                    <td>
                      <Traced target={{ stream: id, prop: "P" }} onTrace={onTrace}>
                        {toKPaG(st.P)}
                      </Traced>
                    </td>
                    <td>
                      <Traced target={{ stream: id, prop: "molar_flow" }} onTrace={onTrace}>
                        {toKmolH(st.molar_flow)}
                      </Traced>
                    </td>
                    <td>
                      <Traced target={{ stream: id, prop: "vapor_fraction" }} onTrace={onTrace}>
                        {toVaporFraction(st.vapor_fraction)}
                      </Traced>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
          <section>
            <h2>Units</h2>
            <table>
              <thead>
                <tr>
                  <th>Tag</th>
                  <th>Duty (kW)</th>
                  <th>Power (kW)</th>
                  <th>Info</th>
                </tr>
              </thead>
              <tbody>
                {units.map(([tag, ur]) => (
                  <tr key={tag} data-tag={tag}>
                    <td>{tag}</td>
                    <td>
                      <Traced target={{ unit: tag, prop: "duty_W" }} onTrace={onTrace}>
                        {toKw(ur.duty_W)}
                      </Traced>
                    </td>
                    <td>
                      <Traced target={{ unit: tag, prop: "power_W" }} onTrace={onTrace}>
                        {toKw(ur.power_W)}
                      </Traced>
                    </td>
                    <td>
                      {/* Plugin-authored readouts (hydrate margins, MDEA loadings,
                          per-stage pressures) rendered generically: key=value. */}
                      {Object.entries(ur.info).length === 0 ? (
                        <span className="muted">—</span>
                      ) : (
                        Object.entries(ur.info).map(([k, v]) => (
                          <span key={k} className="muted" data-info-key={k}>
                            <Traced target={{ unit: tag, prop: `info.${k}` }} onTrace={onTrace}>
                              {k}={formatNumber(v)}
                            </Traced>{" "}
                          </span>
                        ))
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </div>
      )}
    </div>
  );
}
