import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api } from "../api/client";
import { formatNumber } from "../units";

type IsoSheet = Awaited<ReturnType<typeof api.isoSheet>>;

/** Pure: the backend's reason for a failed call. FastAPI answers
 *  `{"detail": "..."}` (legacy and project routes) and the v1 envelope
 *  `{"error": {"message": "..."}}`; ApiError carries the body after the status.
 *  Falls back to the raw message when the body is not JSON. */
export function errorReason(e: unknown): string {
  if (!(e instanceof Error)) return String(e);
  if (e instanceof ApiError) {
    const at = e.message.indexOf("{");
    if (at >= 0) {
      try {
        const body = JSON.parse(e.message.slice(at)) as { detail?: unknown; error?: { message?: unknown } };
        if (typeof body.detail === "string") return body.detail;
        if (Array.isArray(body.detail))
          return body.detail.map((d: { msg?: string }) => d.msg ?? JSON.stringify(d)).join("; ");
        if (typeof body.error?.message === "string") return body.error.message;
      } catch {
        // not JSON: use the raw message below
      }
    }
  }
  return e.message;
}

/** Display a measured value without float noise, to `digits` decimals at most. */
const num = (v: number, digits = 1) => formatNumber(Number(v.toFixed(digits)));

/** Layer 6: fabrication isometrics, one sheet per routed line (spec B-06).
 *  Pick a line number; the drawing comes from GET .../views/iso/{line}.svg and
 *  the title block, BOM, cut list and weld count from .../{line}.json. A
 *  project the backend cannot draw (422, e.g. an unwired unit) shows its
 *  reason. Read-only: the iso placement PUT is not wired here. */
export function IsoView() {
  const [lines, setLines] = useState<string[] | null>(null);
  const [line, setLine] = useState<string | null>(null);
  const [svg, setSvg] = useState<string | null>(null);
  const [sheet, setSheet] = useState<IsoSheet | null>(null);
  const [loading, setLoading] = useState(true);
  const [sheetLoading, setSheetLoading] = useState(false);
  const [error, setError] = useState<{ status: number | null; reason: string } | null>(null);
  // Only the latest line pick may write state (a slow earlier fetch is dropped).
  const seq = useRef(0);
  const current = useRef<string | null>(null);

  const fail = (e: unknown) => setError({ status: e instanceof ApiError ? e.status : null, reason: errorReason(e) });

  const pick = useCallback(async (next: string) => {
    const mine = ++seq.current;
    current.current = next;
    setLine(next);
    setSheetLoading(true);
    setError(null);
    try {
      const [s, j] = await Promise.all([api.isoSvg(next), api.isoSheet(next)]);
      if (mine !== seq.current) return;
      setSvg(s);
      setSheet(j);
    } catch (e) {
      if (mine !== seq.current) return;
      setSvg(null);
      setSheet(null);
      fail(e);
    } finally {
      if (mine === seq.current) setSheetLoading(false);
    }
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const all = await api.isoLines();
      setLines(all);
      // Keep the current pick across a refresh when it is still routed.
      const was = current.current;
      const keep = was !== null && all.includes(was) ? was : all[0];
      if (keep !== undefined) await pick(keep);
      else {
        current.current = null;
        setLine(null);
        setSvg(null);
        setSheet(null);
      }
    } catch (e) {
      setLines(null);
      setSvg(null);
      setSheet(null);
      fail(e);
    } finally {
      setLoading(false);
    }
  }, [pick]);
  useEffect(() => void load(), [load]);

  const busy = loading || sheetLoading;

  return (
    <div className="iso-view">
      <div className="toolbar">
        <label className="field">
          Line
          <select
            aria-label="Line number"
            value={line ?? ""}
            disabled={busy || !lines || lines.length === 0}
            onChange={(e) => void pick(e.target.value)}
          >
            {(lines ?? []).map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </select>
        </label>
        <button type="button" aria-label="Refresh isometrics" disabled={busy} onClick={() => void load()}>
          {loading ? "Loading…" : "Refresh"}
        </button>
        {lines && (
          <span role="status" className="muted">
            {lines.length} routed line{lines.length === 1 ? "" : "s"}
          </span>
        )}
      </div>

      {loading && !lines && <p>Loading isometrics…</p>}
      {error && (
        <p role="alert">
          {error.status === 422 ? "Isometrics cannot be drawn: " : "Isometric failed: "}
          {error.reason}
        </p>
      )}
      {lines && lines.length === 0 && (
        <p className="placeholder">No routed lines yet: connect units with streams to get isometrics.</p>
      )}
      {sheetLoading && <p role="status">Loading {line}…</p>}

      {svg && (
        <div
          className="pfd iso"
          aria-label={`Isometric of ${line ?? ""}`}
          // SVG comes from our own backend renderer (iso_renderer "svg").
          dangerouslySetInnerHTML={{ __html: svg }}
        />
      )}

      {sheet && <IsoTables sheet={sheet} />}
    </div>
  );
}

function IsoTables({ sheet }: { sheet: IsoSheet }) {
  const t = sheet.title;
  return (
    <div className="iso-tables">
      <table aria-label="Title block">
        <tbody>
          <tr>
            <th scope="row">Line</th>
            <td>{t.line_number}</td>
            <th scope="row">Pipe class</th>
            <td>{t.pipe_class}</td>
            <th scope="row">Sheet</th>
            <td>{t.sheet}</td>
          </tr>
          <tr>
            <th scope="row">Design</th>
            <td>
              {num(t.design_pressure_kPag)} kPa(g) / {num(t.design_temperature_C)} degC
            </td>
            <th scope="row">Test</th>
            <td>{num(t.test_pressure_kPag)} kPa(g)</td>
            <th scope="row">Insulation</th>
            <td>{t.insulation}</td>
          </tr>
          <tr>
            <th scope="row">Total pipe</th>
            <td>{num(sheet.total_pipe_length_mm / 1000, 2)} m</td>
            <th scope="row">Welds</th>
            <td>{sheet.weld_count}</td>
            <td colSpan={2} />
          </tr>
        </tbody>
      </table>

      <h2>Bill of materials</h2>
      <table aria-label="Bill of materials">
        <thead>
          <tr>
            <th>Item</th>
            <th>Qty</th>
            <th>Unit</th>
            <th>NPS (in)</th>
            <th>Description</th>
            <th>Material</th>
          </tr>
        </thead>
        <tbody>
          {sheet.bom.map((b) => (
            <tr key={b.item}>
              <td>{b.item}</td>
              <td>{num(b.qty, 2)}</td>
              <td>{b.unit}</td>
              <td>{num(b.nps_in, 2)}</td>
              <td>{b.description}</td>
              <td>{b.material}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2>Cut list</h2>
      <table aria-label="Cut list">
        <thead>
          <tr>
            <th>Piece</th>
            <th>Spool</th>
            <th>NPS (in)</th>
            <th>Length (mm)</th>
          </tr>
        </thead>
        <tbody>
          {sheet.cut_list.map((c) => (
            <tr key={c.piece}>
              <td>{c.piece}</td>
              <td>{c.spool}</td>
              <td>{num(c.nps_in, 2)}</td>
              <td>{num(c.length_mm, 0)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
