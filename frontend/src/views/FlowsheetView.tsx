import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { api, errorReason, type Meta, type Project, type ThermoModel, type UnitKindInfo, type XY } from "../api/client";
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

type Stream = Project["flowsheet"]["streams"][number];
type Feed = NonNullable<Stream["feed"]>;
/** One end of a stream: a unit port. */
export type PortEnd = { unit: string; port: string };

/** Pure: `C1=0.9, C2=0.1` (also `C1: 0.9` or newline separated) as mole fractions;
 * a string saying what is wrong when it is not a composition the backend accepts
 * (finite, non-negative, summing to 1 within the contract's 1e-6). */
export function parseComposition(text: string): Record<string, number> | string {
  const out: Record<string, number> = {};
  const parts = text.split(/[,;\n]+/).map((p) => p.trim()).filter(Boolean);
  if (parts.length === 0) return "enter at least one component, e.g. C1=0.9, C2=0.1";
  for (const part of parts) {
    const m = /^([^=:\s]+)\s*[=:]\s*(.+)$/.exec(part);
    if (!m) return `'${part}' is not component=fraction`;
    const v = parseFiniteNumber(m[2]);
    if (v === null || v < 0) return `${m[1]}: '${m[2]}' is not a non-negative number`;
    if (m[1] in out) return `${m[1]} is given twice`;
    out[m[1]] = v;
  }
  const sum = Object.values(out).reduce((a, b) => a + b, 0);
  if (Math.abs(sum - 1) > 1e-6) return `mole fractions sum to ${formatNumber(sum)}, not 1`;
  return out;
}

/** `C1=0.9, C2=0.1`: the text form parseComposition reads. */
export function formatComposition(c: Record<string, number>): string {
  return Object.entries(c)
    .map(([k, v]) => `${k}=${formatNumber(v)}`)
    .join(", ");
}

/** Pure: the first `S-NNN` id no stream uses (the backend's own numbering). */
export function nextStreamId(project: Project): string {
  const taken = new Set(project.flowsheet.streams.map((s) => s.id));
  let n = taken.size + 1;
  while (taken.has(`S-${String(n).padStart(3, "0")}`)) n++;
  return `S-${String(n).padStart(3, "0")}`;
}

/** Pure: unit ports with no stream on them, inlets or outlets, in flowsheet order.
 * Ports come from the unit catalogue (GET /api/v1/catalogue/units). */
export function freePorts(project: Project, kinds: ReadonlyMap<string, UnitKindInfo>, side: "inlet" | "outlet"): PortEnd[] {
  const used = new Set(
    project.flowsheet.streams.flatMap((s) => [s.source, s.target].filter(Boolean).map((r) => `${r!.unit}.${r!.port}`)),
  );
  return project.flowsheet.units.flatMap((u) => {
    const info = kinds.get(u.kind);
    const ports = (side === "inlet" ? info?.inlet_ports : info?.outlet_ports) ?? [];
    return ports.filter((port) => !used.has(`${u.tag}.${port}`)).map((port) => ({ unit: u.tag, port }));
  });
}

/** Pure: add a stream from an outlet (null = a boundary feed with `feed`) to an
 * inlet (null = a product). A feed's components join the flowsheet slate, which
 * the contract requires. Throws when the stream would have no end or no feed. */
export function addStream(
  project: Project,
  from: PortEnd | null,
  to: PortEnd | null,
  opts: { id?: string; service?: string; feed?: Feed } = {},
): Project {
  if (!from && !to) throw new Error("a stream needs a source unit or a target unit");
  if (!from && !opts.feed) throw new Error("a feed stream needs its feed conditions");
  const stream: Stream = {
    id: opts.id ?? nextStreamId(project),
    ...(from && { source: from }),
    ...(to && { target: to }),
    ...(!from && opts.feed && { feed: opts.feed }),
    service: opts.service?.trim() || "process",
  };
  const fs = project.flowsheet;
  const slate = (fs.components ?? []).map((c) => (typeof c === "string" ? c : c.id));
  const added = Object.keys(stream.feed?.composition ?? {}).filter((c) => !slate.includes(c));
  return {
    ...project,
    flowsheet: {
      ...fs,
      streams: [...fs.streams, stream],
      ...(added.length > 0 && { components: [...(fs.components ?? []), ...added] }),
    },
  };
}

/** Pure: drop a stream. */
export function deleteStream(project: Project, id: string): Project {
  return { ...project, flowsheet: { ...project.flowsheet, streams: project.flowsheet.streams.filter((s) => s.id !== id) } };
}

/** Pure: drop a unit, every stream on its ports and its stored placements — the
 * backend's delete_unit semantics. Returns the dropped stream ids too. */
export function deleteUnit(project: Project, tag: string): { project: Project; dropped: string[] } {
  const on = (s: Stream) => s.source?.unit === tag || s.target?.unit === tag;
  const dropped = project.flowsheet.streams.filter(on).map((s) => s.id);
  const layout = project.layout ?? { pfd: {}, pid: {}, plot: {} };
  const without = <T,>(m: Record<string, T> | undefined) => Object.fromEntries(Object.entries(m ?? {}).filter(([k]) => k !== tag));
  return {
    dropped,
    project: {
      ...project,
      flowsheet: {
        ...project.flowsheet,
        units: project.flowsheet.units.filter((u) => u.tag !== tag),
        streams: project.flowsheet.streams.filter((s) => !on(s)),
      },
      layout: { ...layout, pfd: without(layout.pfd), pid: without(layout.pid), plot: without(layout.plot) },
    },
  };
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
  const compositions = new Map<string, Record<string, number>>();
  for (const [key, text] of Object.entries(drafts)) {
    const m = /^feed:(.+):composition$/.exec(key);
    if (!m) continue;
    const c = parseComposition(text);
    if (typeof c !== "string") compositions.set(m[1], c);
  }
  const slate = (project.flowsheet.components ?? []).map((c) => (typeof c === "string" ? c : c.id));
  const added = [...new Set([...compositions.values()].flatMap((c) => Object.keys(c)))].filter((c) => !slate.includes(c));
  return {
    ...project,
    flowsheet: {
      ...project.flowsheet,
      ...(thermo !== undefined && thermo !== "" && thermo !== project.flowsheet.thermo && { thermo }),
      ...(added.length > 0 && { components: [...(project.flowsheet.components ?? []), ...added] }),
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
        const composition = compositions.get(s.id);
        if (t === undefined && p === undefined && flow === undefined && !composition) return s;
        return {
          ...s,
          feed: {
            ...s.feed,
            ...(t !== undefined && { T: t }),
            ...(p !== undefined && { P: p }),
            ...(flow !== undefined && { molar_flow: flow }),
            ...(composition && { composition }),
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
export function FlowsheetView({ project, onSaved }: { project: Project; onSaved?: (saved: Project) => void }) {
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
  // Ports per kind (connect form) and which thermo models may be chosen.
  const [kinds, setKinds] = useState<ReadonlyMap<string, UnitKindInfo>>(new Map());
  const [thermoModels, setThermoModels] = useState<ThermoModel[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [connect, setConnect] = useState<{ from: string; to: string } | null>(null);

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
    api
      .unitKinds()
      .then((rows) => {
        if (!cancelled) setKinds(new Map(rows.map((r) => [r.kind, r])));
      })
      .catch((e: unknown) => {
        if (!cancelled) setMetaError(errorReason(e));
      });
    api
      .thermoModels()
      .then((rows) => {
        if (!cancelled) setThermoModels(rows);
      })
      .catch(() => undefined); // the selector falls back to /api/meta's names
    return () => {
      cancelled = true;
    };
  }, []);

  const palette = useMemo(() => paletteItems(meta?.unit), [meta]);
  // Always include the flowsheet's current model so the select can never show a
  // value it does not offer (e.g. while /api/meta is loading or mid-refresh).
  // GET /api/thermo/models marks experimental models not selectable (the solve
  // refuses them): they show disabled with the reason.
  const thermoOptions = useMemo(() => {
    const rows: { id: string; label: string; disabled: boolean; title?: string }[] = thermoModels
      ? thermoModels.map((m) => ({
          id: m.id,
          label: m.name && m.name !== m.id ? `${m.id} — ${m.name}` : m.id,
          disabled: !m.selectable,
          title: m.selectable ? m.status : `Not selectable: ${m.refusal_reason ?? m.status}`,
        }))
      : (meta?.thermo ?? []).map((id) => ({ id, label: id, disabled: false }));
    if (!rows.some((r) => r.id === current.flowsheet.thermo))
      rows.push({ id: current.flowsheet.thermo, label: current.flowsheet.thermo, disabled: false });
    return rows.sort((a, b) => a.id.localeCompare(b.id));
  }, [thermoModels, meta, current.flowsheet.thermo]);

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

  const compositionErrors = new Map(
    Object.entries(drafts).flatMap(([key, text]) => {
      if (!key.endsWith(":composition")) return [];
      const c = parseComposition(text);
      return typeof c === "string" ? [[key, c] as const] : [];
    }),
  );
  const invalidKeys = new Set([
    ...fields.filter((f) => drafts[f.key] !== undefined && parseFiniteNumber(drafts[f.key]) === null).map((f) => f.key),
    ...compositionErrors.keys(),
  ]);

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

  /** Remove a unit with the streams on its ports (Save persists it). */
  function removeUnit(tag: string): void {
    const { project: next, dropped } = deleteUnit(current, tag);
    setCurrent(next);
    if (selected === tag) setSelected(null);
    setAddError(null);
    setAdded(`Deleted ${tag}${dropped.length ? ` and streams ${dropped.join(", ")}` : ""}. Save persists it.`);
  }

  function removeStream(id: string): void {
    setCurrent((c) => deleteStream(c, id));
    setAdded(`Deleted stream ${id}. Save persists it.`);
  }

  /** Connect form result: add the stream locally (Save persists it). */
  function addConnection(from: PortEnd | null, to: PortEnd | null, opts: { service: string; feed?: Feed }): string | null {
    try {
      const id = nextStreamId(current);
      setCurrent(addStream(current, from, to, { ...opts, id }));
      const end = (e: PortEnd | null, boundary: string) => (e ? `${e.unit}.${e.port}` : boundary);
      setAdded(`Added ${id}: ${end(from, "feed")} → ${end(to, "product")}. Save persists it.`);
      setConnect(null);
      return null;
    } catch (e) {
      return errorReason(e);
    }
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
      onSaved?.(saved);
    } catch (e) {
      setSaveError(errorReason(e));
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

  function compositionInput(s: Stream): JSX.Element {
    const key = `feed:${s.id}:composition`;
    const problem = compositionErrors.get(key);
    return (
      <label className="field">
        <input
          type="text"
          aria-label={`${s.id} feed composition (mole fractions)`}
          value={drafts[key] ?? formatComposition(s.feed?.composition ?? {})}
          aria-invalid={problem ? true : undefined}
          title={problem}
          onChange={(e) => edit(key, e.target.value)}
        />
        {problem && <small role="alert">{problem}</small>}
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
              <option key={t.id} value={t.id} disabled={t.disabled} title={t.title}>
                {t.label}
                {t.disabled ? " (not selectable)" : ""}
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
            onSelectUnit={(tag) => setSelected((t) => (t === tag ? null : tag))}
            selected={selected}
            centreRef={centreRef}
          />
          {selected && current.flowsheet.units.some((u) => u.tag === selected) && (
            <SelectedUnit
              tag={selected}
              project={current}
              kinds={kinds}
              onConnectFrom={(from) => setConnect({ from, to: "" })}
              onConnectTo={(to) => setConnect({ from: "", to })}
              onDelete={() => removeUnit(selected)}
              onClose={() => setSelected(null)}
            />
          )}
          <div className="row">
            <button type="button" className="btn ob" aria-expanded={connect !== null} onClick={() => setConnect((c) => (c ? null : { from: "", to: "" }))}>
              Connect stream
            </button>
          </div>
          {connect && (
            <ConnectForm
              key={`${connect.from}>${connect.to}`}
              project={current}
              kinds={kinds}
              initial={connect}
              onAdd={addConnection}
              onCancel={() => setConnect(null)}
            />
          )}
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
              <th />
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
                <td>
                  <button type="button" className="btn ob" aria-label={`Delete ${u.tag}`} onClick={() => removeUnit(u.tag)}>
                    Delete
                  </button>
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
                  <td>{compositionInput(s)}</td>
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
              <th />
            </tr>
          </thead>
          <tbody>
            {current.flowsheet.streams.map((s) => (
              <tr key={s.id} data-stream={s.id}>
                <td>{s.id}</td>
                <td>{s.source ? `${s.source.unit}.${s.source.port}` : "feed"}</td>
                <td>{s.target ? `${s.target.unit}.${s.target.port}` : "product"}</td>
                <td>{s.service}</td>
                <td>
                  <button type="button" className="btn ob" aria-label={`Delete stream ${s.id}`} onClick={() => removeStream(s.id)}>
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

/** The clicked unit: its ports and what is on them, plus connect and delete. */
function SelectedUnit({
  tag,
  project,
  kinds,
  onConnectFrom,
  onConnectTo,
  onDelete,
  onClose,
}: {
  tag: string;
  project: Project;
  kinds: ReadonlyMap<string, UnitKindInfo>;
  onConnectFrom: (from: string) => void;
  onConnectTo: (to: string) => void;
  onDelete: () => void;
  onClose: () => void;
}) {
  const unit = project.flowsheet.units.find((u) => u.tag === tag)!;
  const info = kinds.get(unit.kind);
  const on = (port: string) => project.flowsheet.streams.find((s) => (s.source?.unit === tag && s.source.port === port) || (s.target?.unit === tag && s.target.port === port));
  const row = (port: string, side: "in" | "out") => {
    const s = on(port);
    const key = `${tag}|${port}`;
    return (
      <li key={`${side}:${port}`}>
        <code>{port}</code>{" "}
        {s ? (
          <span className="muted">{s.id}</span>
        ) : (
          <button type="button" className="btn ob" onClick={() => (side === "in" ? onConnectTo(key) : onConnectFrom(key))}>
            {side === "in" ? "Connect into" : "Connect from"}
          </button>
        )}
      </li>
    );
  };
  return (
    <section className="panel ob selunit" aria-label={`Selected unit ${tag}`}>
      <div className="row">
        <strong>{tag}</strong> <span className="muted">{info?.name ?? unit.kind}</span>
        <span className="grow" />
        <button type="button" className="btn ob" onClick={onDelete}>
          Delete {tag}
        </button>
        <button type="button" className="btn ob" aria-label="Deselect" onClick={onClose}>
          ×
        </button>
      </div>
      {info ? (
        <div className="ports">
          <div>
            <span className="small muted">Inlets</span>
            <ul>{info.inlet_ports.map((p) => row(p, "in"))}</ul>
          </div>
          <div>
            <span className="small muted">Outlets</span>
            <ul>{info.outlet_ports.map((p) => row(p, "out"))}</ul>
          </div>
        </div>
      ) : (
        <p className="small muted">Loading ports…</p>
      )}
    </section>
  );
}

const SERVICES = ["process", "PG", "PL", "GL", "W", "HC", "CW", "ST"];
const BOUNDARY = "";

/** Add one stream: from an outlet port or a boundary feed, to an inlet port or a
 * product. A feed takes T, P, flow and composition (user units; SI on add). */
function ConnectForm({
  project,
  kinds,
  initial,
  onAdd,
  onCancel,
}: {
  project: Project;
  kinds: ReadonlyMap<string, UnitKindInfo>;
  initial: { from: string; to: string };
  onAdd: (from: PortEnd | null, to: PortEnd | null, opts: { service: string; feed?: Feed }) => string | null;
  onCancel: () => void;
}) {
  const outlets = freePorts(project, kinds, "outlet");
  const inlets = freePorts(project, kinds, "inlet");
  const firstFeed = project.flowsheet.streams.find((s) => s.feed)?.feed;
  const [from, setFrom] = useState(initial.from);
  const [to, setTo] = useState(initial.to);
  const [service, setService] = useState("process");
  const [T, setT] = useState(firstFeed ? formatNumber(kelvinToCelsius(firstFeed.T)) : "25");
  const [P, setP] = useState(firstFeed ? formatNumber(paToKpaGauge(firstFeed.P)) : "0");
  const [flow, setFlow] = useState(firstFeed ? formatNumber(molPerSToKmolPerH(firstFeed.molar_flow)) : "100");
  const [comp, setComp] = useState(firstFeed ? formatComposition(firstFeed.composition) : "");
  const [error, setError] = useState<string | null>(null);
  const end = (v: string): PortEnd | null => {
    if (v === BOUNDARY) return null;
    const [unit, port] = v.split("|");
    return { unit, port };
  };
  const isFeed = from === BOUNDARY;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    let feed: Feed | undefined;
    if (isFeed) {
      const nums = [parseFiniteNumber(T), parseFiniteNumber(P), parseFiniteNumber(flow)];
      if (nums.some((n) => n === null)) return setError("feed T, P and flow must be numbers");
      const c = parseComposition(comp);
      if (typeof c === "string") return setError(`composition: ${c}`);
      feed = { T: celsiusToKelvin(nums[0]!), P: kpaGaugeToPa(nums[1]!), molar_flow: kmolPerHToMolS(nums[2]!), composition: c };
    }
    setError(onAdd(end(from), end(to), { service, feed }));
  };
  const opt = (e: PortEnd) => (
    <option key={`${e.unit}|${e.port}`} value={`${e.unit}|${e.port}`}>
      {e.unit}.{e.port}
    </option>
  );
  return (
    <form className="panel ob connect" aria-label="Connect stream" onSubmit={submit} onKeyDown={(e) => e.key === "Escape" && onCancel()}>
      <div className="row">
        <label className="field">
          <span>From</span>
          <select aria-label="From" value={from} onChange={(e) => setFrom(e.target.value)}>
            <option value={BOUNDARY}>Feed (battery limit)</option>
            {outlets.map(opt)}
          </select>
        </label>
        <label className="field">
          <span>To</span>
          <select aria-label="To" value={to} onChange={(e) => setTo(e.target.value)}>
            <option value={BOUNDARY}>Product (battery limit)</option>
            {inlets.map(opt)}
          </select>
        </label>
        <label className="field">
          <span>Service</span>
          <select aria-label="Service" value={service} onChange={(e) => setService(e.target.value)}>
            {SERVICES.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </label>
      </div>
      {isFeed && (
        <div className="row">
          <label className="field">
            <span>T (degC)</span>
            <input aria-label="Feed T (degC)" inputMode="decimal" value={T} onChange={(e) => setT(e.target.value)} />
          </label>
          <label className="field">
            <span>P (kPa(g))</span>
            <input aria-label="Feed P (kPa(g))" inputMode="decimal" value={P} onChange={(e) => setP(e.target.value)} />
          </label>
          <label className="field">
            <span>Flow (kmol/h)</span>
            <input aria-label="Feed flow (kmol/h)" inputMode="decimal" value={flow} onChange={(e) => setFlow(e.target.value)} />
          </label>
          <label className="field grow">
            <span>Composition (mole fractions)</span>
            <input aria-label="Feed composition" placeholder="C1=0.9, C2=0.1" value={comp} onChange={(e) => setComp(e.target.value)} />
          </label>
        </div>
      )}
      {kinds.size === 0 && <p className="small muted">Loading unit ports…</p>}
      {error && <p role="alert">{error}</p>}
      <div className="row">
        <button type="submit" className="btn ob primary" disabled={isFeed && to === BOUNDARY}>
          Add stream
        </button>
        <button type="button" className="btn ob" onClick={onCancel}>
          Cancel
        </button>
        {isFeed && to === BOUNDARY && <span className="small muted">Pick a unit for one end.</span>}
      </div>
    </form>
  );
}
