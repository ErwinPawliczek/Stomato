import { useEffect, useMemo, useRef, useState } from "react";
import { api, type Meta, type Project, type XY } from "../api/client";
import { FlowsheetCanvas, type CanvasLink, type CanvasUnit } from "../components/FlowsheetCanvas";
import { UnitPalette } from "../components/UnitPalette";
import { nearestFreeCell, snapToHex } from "../hexGrid";
import { defaultParamsFor } from "../unitDefaults";
import { catalogueEntry, nextTag, paletteItems } from "../unitPalette";
import {
  celsiusToKelvin,
  formatNumber,
  kelvinToCelsius,
  kmolPerHToMolS,
  kpaGaugeToPa,
  molPerSToKmolPerH,
  paToKpaGauge,
  parseFiniteNumber,
} from "../units";

// Every editable value is one field with a stable key, the user-facing value it
// starts from, and how to convert the parsed number back to SI.
type Field = {
  key: string;
  label: string;
  initial: number; // user-facing (converted) value
  toSi: (n: number) => number;
};

type Drafts = Record<string, string>;

function unitFields(project: Project): Field[] {
  const fields: Field[] = [];
  for (const u of project.flowsheet.units) {
    for (const [name, value] of Object.entries(u.params ?? {})) {
      if (typeof value === "number") {
        // Unit params are already SI; edited as plain numbers.
        fields.push({
          key: `unit:${u.tag}:${name}`,
          label: `${u.tag} ${name}`,
          initial: value,
          toSi: (n) => n,
        });
      }
    }
  }
  return fields;
}

function feedFields(project: Project): Field[] {
  const fields: Field[] = [];
  for (const s of project.flowsheet.streams) {
    if (!s.feed) continue;
    fields.push({
      key: `feed:${s.id}:T`,
      label: `${s.id} feed T (degC)`,
      initial: kelvinToCelsius(s.feed.T),
      toSi: celsiusToKelvin,
    });
    fields.push({
      key: `feed:${s.id}:P`,
      label: `${s.id} feed P (kPa(g))`,
      initial: paToKpaGauge(s.feed.P),
      toSi: kpaGaugeToPa,
    });
    fields.push({
      key: `feed:${s.id}:molar_flow`,
      label: `${s.id} feed flow (kmol/h)`,
      initial: molPerSToKmolPerH(s.feed.molar_flow),
      toSi: kmolPerHToMolS,
    });
  }
  return fields;
}

/** Apply the parsed drafts to the project. Pure: returns a new Project.
 * The thermo selector is a string field outside the numeric Field machinery;
 * its draft rides the same record under `flowsheet:thermo` and is applied as-is. */
export function applyDrafts(project: Project, fields: Field[], drafts: Drafts): Project {
  const parsed = new Map<string, number>();
  for (const f of fields) {
    const text = drafts[f.key];
    if (text === undefined) continue;
    const n = parseFiniteNumber(text);
    if (n !== null) parsed.set(f.key, f.toSi(n));
  }
  const thermo = drafts["flowsheet:thermo"];
  return {
    ...project,
    flowsheet: {
      ...project.flowsheet,
      ...(thermo !== undefined && thermo !== "" && thermo !== project.flowsheet.thermo && { thermo }),
      units: project.flowsheet.units.map((u) => {
        const edits = Object.keys(u.params ?? {})
          .filter((name) => parsed.has(`unit:${u.tag}:${name}`))
          .map((name) => [name, parsed.get(`unit:${u.tag}:${name}`)] as const);
        return edits.length === 0
          ? u
          : { ...u, params: { ...u.params, ...Object.fromEntries(edits) } };
      }),
      streams: project.flowsheet.streams.map((s) => {
        if (!s.feed) return s;
        const t = parsed.get(`feed:${s.id}:T`);
        const p = parsed.get(`feed:${s.id}:P`);
        const flow = parsed.get(`feed:${s.id}:molar_flow`);
        if (t === undefined && p === undefined && flow === undefined) return s;
        return {
          ...s,
          feed: {
            ...s.feed,
            ...(t !== undefined && { T: t }),
            ...(p !== undefined && { P: p }),
            ...(flow !== undefined && { molar_flow: flow }),
          },
        };
      }),
    },
  };
}

/** Where a unit without a stored layout.pfd position is drawn: rows of five,
 *  on the lattice. Display only; dragging it stores a real position. */
export function autoPosition(index: number): XY {
  return snapToHex({ x: 180 * (index % 5), y: 140 * Math.floor(index / 5) });
}

/** Layer 1: edit unit params and stream feed conditions; Save PUTs the whole Project. */
export function FlowsheetView({ project }: { project: Project }) {
  const [current, setCurrent] = useState(project);
  const [drafts, setDrafts] = useState<Drafts>({});
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [metaError, setMetaError] = useState<string | null>(null);
  const [addError, setAddError] = useState<string | null>(null);
  const [added, setAdded] = useState<string | null>(null);
  // Tags the backend knows: their moves go straight to the layout API. Units
  // added since the last save ride in current.layout.pfd until Save PUTs them.
  const [savedTags, setSavedTags] = useState(() => new Set(project.flowsheet.units.map((u) => u.tag)));
  const centreRef = useRef<XY>({ x: 0, y: 0 });

  // Registry inventory for the thermo selector and the add-unit palette.
  useEffect(() => {
    let cancelled = false;
    api
      .getMeta()
      .then((m) => {
        if (!cancelled) setMeta(m);
      })
      .catch((e: Error) => {
        if (!cancelled) setMetaError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const palette = useMemo(() => paletteItems(meta?.unit), [meta]);
  // Always include the flowsheet's current model so the select can never show a
  // value it does not offer (e.g. while /api/meta is loading or mid-refresh).
  const thermoOptions = useMemo(
    () => [...new Set([...(meta?.thermo ?? []), current.flowsheet.thermo])].sort(),
    [meta, current.flowsheet.thermo],
  );

  const fields = useMemo(() => [...unitFields(current), ...feedFields(current)], [current]);
  const fieldByKey = useMemo(
    () => new Map(fields.map((f) => [f.key, f])),
    [fields],
  );

  // Sync when the parent hands us a different (reloaded) project.
  useEffect(() => {
    setCurrent(project);
    setSavedTags(new Set(project.flowsheet.units.map((u) => u.tag)));
  }, [project]);

  const canvasUnits: CanvasUnit[] = useMemo(() => {
    const placed = current.layout?.pfd ?? {};
    return current.flowsheet.units.map((u, i) => ({
      tag: u.tag,
      kind: u.kind,
      name: catalogueEntry(u.kind)?.name ?? u.kind,
      pos: placed[u.tag] ?? autoPosition(i),
    }));
  }, [current]);
  const canvasLinks: CanvasLink[] = useMemo(
    () =>
      current.flowsheet.streams.flatMap((s) =>
        s.source && s.target ? [{ id: s.id, from: s.source.unit, to: s.target.unit }] : [],
      ),
    [current],
  );

  const invalidKeys = new Set(
    fields
      .filter((f) => drafts[f.key] !== undefined && parseFiniteNumber(drafts[f.key]) === null)
      .map((f) => f.key),
  );

  function valueOf(f: Field): string {
    const text = drafts[f.key];
    return text !== undefined ? text : formatNumber(f.initial);
  }

  function edit(key: string, text: string): void {
    setDrafts((d) => ({ ...d, [key]: text }));
  }

  /** Palette insert: append a UnitSpec with the registry kind, example_case()-
   * shaped default params and an auto tag (P&ID symbol + first free number),
   * at `pos` on the canvas. Persisted by Save — one PUT path, like every other
   * edit in this view. */
  function addUnit(kind: string, pos: XY): void {
    const known = palette.find((p) => p.kind === kind);
    if (!known?.available) {
      setAddError(`${kind} is not a registered unit kind.`);
      return;
    }
    const tag = nextTag(known.pidSymbol, current.flowsheet.units.map((u) => u.tag));
    const layout = current.layout ?? { pfd: {}, pid: {}, plot: {} };
    setCurrent({
      ...current,
      flowsheet: {
        ...current.flowsheet,
        units: [...current.flowsheet.units, { tag, kind, params: defaultParamsFor(kind) }],
      },
      layout: { ...layout, pfd: { ...(layout.pfd ?? {}), [tag]: pos } },
    });
    setAddError(null);
    setAdded(`Added ${tag} (${known.name}). Save persists it.`);
  }

  /** Keyboard / click path: nearest free cell to the middle of the view. */
  function addAtCentre(kind: string): void {
    addUnit(kind, nearestFreeCell(centreRef.current, canvasUnits.map((u) => u.pos)));
  }

  function setPfdPosition(tag: string, pos: XY): void {
    setCurrent((c) => {
      const layout = c.layout ?? { pfd: {}, pid: {}, plot: {} };
      return { ...c, layout: { ...layout, pfd: { ...(layout.pfd ?? {}), [tag]: pos } } };
    });
  }

  /** Saved units: store via the layout API, then take its pfd layout (keeping
   *  pending positions of unsaved units). Unsaved ones wait for Save. */
  async function moveUnit(tag: string, pos: XY): Promise<void> {
    setPfdPosition(tag, pos);
    if (!savedTags.has(tag)) return;
    try {
      const layout = await api.place("pfd", tag, pos);
      setCurrent((c) => {
        const pending = Object.fromEntries(
          Object.entries(c.layout?.pfd ?? {}).filter(([t]) => !savedTags.has(t)),
        );
        return { ...c, layout: { ...layout, pfd: { ...(layout.pfd ?? {}), ...pending } } };
      });
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : String(e));
    }
  }

  async function save(): Promise<void> {
    setSaving(true);
    setSaveError(null);
    try {
      const saved = await api.putProject(applyDrafts(current, fields, drafts));
      setDrafts({});
      setCurrent(saved);
      setSavedTags(new Set(saved.flowsheet.units.map((u) => u.tag)));
      setAdded(null);
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  function paramInput(u: { tag: string }, name: string): JSX.Element | null {
    const field = fieldByKey.get(`unit:${u.tag}:${name}`);
    if (!field) return null; // non-numeric params render as text below
    const invalid = invalidKeys.has(field.key);
    return (
      <label key={name} className="field">
        <span>{name}</span>
        <input
          type="text"
          inputMode="decimal"
          aria-label={field.label}
          value={valueOf(field)}
          aria-invalid={invalid || undefined}
          onChange={(e) => edit(field.key, e.target.value)}
        />
      </label>
    );
  }

  function feedInput(s: { id: string }, suffix: "T" | "P" | "molar_flow"): JSX.Element {
    const field = fieldByKey.get(`feed:${s.id}:${suffix}`)!;
    const invalid = invalidKeys.has(field.key);
    return (
      <label className="field">
        <input
          type="text"
          inputMode="decimal"
          aria-label={field.label}
          value={valueOf(field)}
          aria-invalid={invalid || undefined}
          onChange={(e) => edit(field.key, e.target.value)}
        />
      </label>
    );
  }

  return (
    <div className="grid">
      <div className="toolbar">
        <button
          type="button"
          aria-label="Save"
          disabled={saving || invalidKeys.size > 0}
          onClick={() => void save()}
        >
          {saving ? "Saving…" : "Save"}
        </button>
        {saveError && <span role="alert">Save failed: {saveError}</span>}
        <label className="field">
          <span>Thermo model</span>
          <select
            aria-label="Thermo model"
            value={drafts["flowsheet:thermo"] ?? current.flowsheet.thermo}
            onChange={(e) => edit("flowsheet:thermo", e.target.value)}
          >
            {thermoOptions.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="fsgrid">
        <UnitPalette items={palette} onAdd={addAtCentre} />
        <div className="fscol">
          <FlowsheetCanvas
            units={canvasUnits}
            links={canvasLinks}
            onDropUnit={addUnit}
            onMoveUnit={(tag, pos) => void moveUnit(tag, pos)}
            centreRef={centreRef}
          />
          {metaError && <p role="alert">Registry unavailable: {metaError}</p>}
          {addError && <p role="alert">{addError}</p>}
          {added && (
            <p role="status" className="muted small">
              {added}
            </p>
          )}
        </div>
      </div>
      <section>
        <h2>Units</h2>
        <table>
          <thead>
            <tr>
              <th>Tag</th>
              <th>Kind</th>
              <th>Params (SI)</th>
            </tr>
          </thead>
          <tbody>
            {current.flowsheet.units.map((u) => (
              <tr key={u.tag} data-tag={u.tag}>
                <td>{u.tag}</td>
                <td>{u.kind}</td>
                <td>
                  {Object.entries(u.params ?? {}).map(([name, v]) =>
                    typeof v === "number" ? (
                      paramInput(u, name)
                    ) : (
                      <span key={name} className="muted">
                        {name}={JSON.stringify(v)}{" "}
                      </span>
                    ),
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section>
        <h2>Feed conditions</h2>
        <table>
          <thead>
            <tr>
              <th>Stream</th>
              <th>T (degC)</th>
              <th>P (kPa(g))</th>
              <th>Flow (kmol/h)</th>
              <th>Composition</th>
            </tr>
          </thead>
          <tbody>
            {current.flowsheet.streams
              .filter((s) => s.feed)
              .map((s) => (
                <tr key={s.id} data-stream={s.id}>
                  <td>{s.id}</td>
                  <td>{feedInput(s, "T")}</td>
                  <td>{feedInput(s, "P")}</td>
                  <td>{feedInput(s, "molar_flow")}</td>
                  <td>
                    <code>{JSON.stringify(s.feed?.composition ?? {})}</code>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </section>
      <section>
        <h2>Streams</h2>
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>From</th>
              <th>To</th>
              <th>Service</th>
            </tr>
          </thead>
          <tbody>
            {current.flowsheet.streams.map((s) => (
              <tr key={s.id} data-stream={s.id}>
                <td>{s.id}</td>
                <td>{s.source ? `${s.source.unit}.${s.source.port}` : "feed"}</td>
                <td>{s.target ? `${s.target.unit}.${s.target.port}` : "product"}</td>
                <td>{s.service}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
