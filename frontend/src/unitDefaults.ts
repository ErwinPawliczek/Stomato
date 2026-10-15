// Default params per registered unit kind, mirroring each plugin's example_case()
// (src/ngdesign/units/*.py). GET /api/meta lists kind names only — until it drops
// param defaults, the add-unit palette sources them here (frontend/AGENTS.md:
// sample data lives frontend-side). All values SI, exactly as the plugins read them.
export const unitDefaultParams: Readonly<Record<string, Record<string, unknown>>> = {
  air_cooler: { T_out: 313.15, dP: 35000 },
  compression_train: { P_discharge: 15000000, eta_isentropic: 0.75, T_interstage_out: 322.15 },
  compressor: { P_out: 7000000, eta_isentropic: 0.75 },
  cooler: { T_out: 313.15, dP: 35000 },
  expander: { P_out: 2000000, eta_isentropic: 0.8 },
  heater: { T_out: 313.15, dP: 35000 },
  jt_valve: { P_out: 3000000 },
  mdea_absorber: {},
  mdea_regenerator: {},
  mixer: {},
  pump: { P_out: 1500000, eta: 0.65 },
  scrubber: {},
  separator_3phase: {},
  shell_tube: { T_out: 313.15, dP: 35000 },
  splitter: { fractions: [0.6, 0.4] },
  teg_contactor: {},
};

/** example_case()-shaped params for a kind, cloned so callers cannot mutate the
 * table. Unknown kinds add no params (plugins read params with defaults), so a
 * newly registered backend kind stays addable before this map catches up. */
export function defaultParamsFor(kind: string): Record<string, unknown> {
  return structuredClone(unitDefaultParams[kind] ?? {});
}
