import { useState } from "react";
import type { ReactNode } from "react";
import { ApiError, api, errorReason, type SolvedFlowsheet, type TraceTarget } from "../api/client";
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

/** Layer 2: solve the open project and show stream states plus unit duty/power, the
 * solve status with each failed unit's reason, and design-spec outcomes. Clicking a
 * number calls `onTrace` with the value it shows (stream + prop, or unit + prop).
 * `result`/`onResult` let the parent keep the last solve across tab switches. */
export function ResultsView({
  onTrace,
  result: kept,
  onResult,
}: {
  onTrace?: (t: TraceTarget) => void;
  result?: SolvedFlowsheet | null;
  onResult?: (r: SolvedFlowsheet | null) => void;
} = {}) {
  const [own, setOwn] = useState<SolvedFlowsheet | null>(null);
  const result = kept !== undefined ? kept : own;
  const setResult = onResult ?? setOwn;
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
      else setError(errorReason(e));
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
          <span className={result.status === "converged" ? "" : "chip bad"} role="status">
            {" "}
            {result.status === "failed"
              ? `Solve failed: ${result.errors?.length ?? 0} unit${result.errors?.length === 1 ? "" : "s"} could not be calculated`
              : `${result.converged ? "Converged" : "Did not converge"} in ${result.iterations} iteration${result.iterations === 1 ? "" : "s"}`}
          </span>
        )}
      </p>
      {result && result.flowsheet.units.length === 0 && (
        <p className="muted">Nothing to solve yet: add units and connect streams on the Flowsheet tab.</p>
      )}
      {result && (result.errors?.length ?? 0) > 0 && (
        <section aria-label="Solve errors">
          <h2>Errors</h2>
          <table>
            <thead>
              <tr>
                <th>Unit</th>
                <th>Kind</th>
                <th>Stage</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {result.errors!.map((e) => (
                <tr key={`${e.tag}:${e.stage}`} data-error-tag={e.tag}>
                  <td>{e.tag}</td>
                  <td>{e.kind}</td>
                  <td>{e.stage}</td>
                  <td>
                    {e.upstream ? <span className="muted">(upstream failure) </span> : null}
                    {e.error_type}: {e.message}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
      {result && (result.design_spec_results?.length ?? 0) > 0 && (
        <section aria-label="Design specs">
          <h2>Design specs</h2>
          <table>
            <thead>
              <tr>
                <th>Spec</th>
                <th>Status</th>
                <th>Achieved</th>
                <th>Manipulated value</th>
                <th>Iterations</th>
              </tr>
            </thead>
            <tbody>
              {result.design_spec_results!.map((d) => (
                <tr key={d.id} data-spec={d.id}>
                  <td>{d.id}</td>
                  <td>{d.converged ? "met" : "not met"}</td>
                  <td>{formatNumber(d.achieved)}</td>
                  <td>{formatNumber(d.manipulated_value)}</td>
                  <td>{d.iterations}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
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
