import { useEffect, useMemo, useState } from "react";
import { api, type Meta, type Project } from "../api/client";
import { defaultParamsFor } from "../unitDefaults";
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

/** Layer 1: edit unit params and stream feed conditions; Save PUTs the whole Project. */
export function FlowsheetView({ project }: { project: Project }) {
  const [current, setCurrent] = useState(project);
  const [drafts, setDrafts] = useState<Drafts>({});
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [metaError, setMetaError] = useState<string | null>(null);
  const [newKind, setNewKind] = useState("");
  const [newTag, setNewTag] = useState("");
  const [addError, setAddError] = useState<string | null>(null);

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

  const unitKinds = useMemo(() => [...(meta?.unit ?? [])].sort(), [meta]);
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
  useEffect(() => setCurrent(project), [project]);

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

  /** Palette insert: append a UnitSpec with the registry kind and
   * example_case()-shaped default params. Persisted by the existing Save
   * button — one PUT path, like every other edit in this view. */
  function addUnit(): void {
    const tag = newTag.trim();
    if (tag === "") {
      setAddError("Enter a tag for the new unit.");
      return;
    }
    if (current.flowsheet.units.some((u) => u.tag === tag)) {
      setAddError(`Tag ${tag} already exists in the flowsheet.`);
      return;
    }
    if (newKind === "") {
      setAddError("Pick a unit kind first.");
      return;
    }
    setCurrent({
      ...current,
      flowsheet: {
        ...current.flowsheet,
        units: [...current.flowsheet.units, { tag, kind: newKind, params: defaultParamsFor(newKind) }],
      },
    });
    setNewTag("");
    setAddError(null);
  }

  async function save(): Promise<void> {
    setSaving(true);
    setSaveError(null);
    try {
      const saved = await api.putProject(applyDrafts(current, fields, drafts));
      setDrafts({});
      setCurrent(saved);
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
        <h2>Add unit</h2>
        {metaError && <p role="alert">Registry unavailable: {metaError}</p>}
        {meta && (
          <div className="toolbar">
            <label className="field">
              <span>Kind</span>
              <select
                aria-label="New unit kind"
                value={newKind}
                onChange={(e) => {
                  setNewKind(e.target.value);
                  setAddError(null);
                }}
              >
                <option value="" disabled>
                  Pick a kind…
                </option>
                {unitKinds.map((k) => (
                  <option key={k} value={k}>
                    {k}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Tag</span>
              <input
                type="text"
                aria-label="New unit tag"
                value={newTag}
                onChange={(e) => {
                  setNewTag(e.target.value);
                  setAddError(null);
                }}
              />
            </label>
            <button type="button" disabled={newKind === ""} onClick={addUnit}>
              Add unit
            </button>
            {addError && <span role="alert">{addError}</span>}
            <span className="muted">Inserted with example params (SI); Save persists it.</span>
          </div>
        )}
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
