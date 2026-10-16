// What the Equipment page says about each registered unit kind. Ports, params and
// defaults mirror the plugin sources in src/ngdesign/units/*.py; sizers mirror
// src/ngdesign/sizing/. Kinds GET /api/meta lists that are not here still get a tile.
export type EquipmentInfo = {
  kind: string;
  name: string;
  group: string;
  /** SVG body drawn in a -6 -6 172 116 viewBox. */
  symbol: string;
  description: string;
  inlets: string[];
  outlets: string[];
  inputs: [param: string, label: string, note: string][];
  calculates: string;
  sizer: string | null;
  pid: string[];
};

export const CATALOG: EquipmentInfo[] = [
  {
    kind: "separator_3phase", name: "Three-phase separator", group: "Separation",
    symbol: '<rect x="20" y="30" width="120" height="44" rx="22"/><path d="M45 74v8M95 74v8M60 52h40" style="stroke-dasharray:3 3"/><path d="M4 52h16M120 30V14h36M45 82v14h-30M95 82v14h60"/>',
    description: "Splits a well stream into gas, hydrocarbon liquid and water by flashing it at the inlet conditions. Usually the first vessel in a gas plant.",
    inlets: ["inlet"], outlets: ["gas_out", "hc_out", "water_out"], inputs: [["dP", "Pressure drop", "optional, default 0"]],
    calculates: "Phase split and the state of each outlet",
    sizer: "Diameter, tan-to-tan length, L/D, maximum gas velocity (Souders–Brown) and liquid hold-up",
    pid: ["PSV", "Level, pressure and temperature instruments", "Isolation valves", "Drains and vents"],
  },
  {
    kind: "scrubber", name: "Scrubber", group: "Separation",
    symbol: '<rect x="58" y="8" width="44" height="88" rx="22"/><path d="M58 34h44" style="stroke-dasharray:3 3"/><path d="M30 60h28M80 8V2M80 96v6"/>',
    description: "Two-phase knock-out vessel. Catches liquid droplets ahead of a compressor or after a cooler.",
    inlets: ["inlet"], outlets: ["gas_out", "liquid_out"], inputs: [["dP", "Pressure drop", "optional, default 0"]],
    calculates: "Gas and liquid outlets", sizer: "Diameter and height from the gas load",
    pid: ["PSV", "Level instruments", "Isolation valves", "Drains and vents"],
  },
  {
    kind: "compressor", name: "Compressor", group: "Pressure change",
    symbol: '<polygon points="40,22 120,40 120,64 40,82"/><path d="M8 52h32M120 52h32"/>',
    description: "Raises gas pressure. Modelled with an isentropic efficiency, so the discharge temperature and shaft power both come out of the solve.",
    inlets: ["inlet"], outlets: ["outlet"],
    inputs: [["P_out", "Outlet pressure", "required"], ["eta_isentropic", "Isentropic efficiency", "default 0.75"]],
    calculates: "Shaft power, discharge temperature, pressure ratio",
    sizer: "Power, pressure ratio, number of stages, discharge temperature", pid: ["Check valve on discharge", "Isolation valves"],
  },
  {
    kind: "compression_train", name: "Compression train", group: "Pressure change",
    symbol: '<polygon points="14,30 54,40 54,64 14,74"/><polygon points="96,30 136,40 136,64 96,74"/><circle cx="75" cy="52" r="12"/><path d="M0 52h14M54 52h9M87 52h9M136 52h24M69 58l6-12 6 12"/>',
    description: "Several compressor stages with an intercooler between each, as one unit. The pressure ratio is split evenly over the fewest stages that keep each stage under the limit.",
    inlets: ["gas_in"], outlets: ["gas_out"],
    inputs: [
      ["P_discharge", "Final discharge pressure", "required"],
      ["max_ratio_per_stage", "Largest ratio per stage", "default 3.5"],
      ["eta_isentropic", "Isentropic efficiency", "default 0.75"],
      ["T_interstage_out", "Intercooler outlet temperature", "default 49 °C"],
    ],
    calculates: "Stage count, total shaft power, intercooler duties and each stage's discharge pressure",
    sizer: null, pid: [],
  },
  {
    kind: "expander", name: "Turbo-expander", group: "Pressure change",
    symbol: '<polygon points="40,40 120,22 120,82 40,64"/><path d="M8 52h32M120 52h32"/>',
    description: "Drops gas pressure through a turbine and recovers the work. The gas gets much colder than across a JT valve, and some of it may condense.",
    inlets: ["gas_in"], outlets: ["gas_out"],
    inputs: [["P_out", "Outlet pressure", "required"], ["eta_isentropic", "Isentropic efficiency", "default 0.80"]],
    calculates: "Recovered power, outlet temperature and phase split", sizer: null, pid: [],
  },
  {
    kind: "pump", name: "Centrifugal pump", group: "Pressure change",
    symbol: '<circle cx="80" cy="56" r="30"/><path d="M80 26h52M20 56h30M60 82l-10 14h60l-10-14"/>',
    description: "Raises liquid pressure. Power comes from the hydraulic head and the pump efficiency.",
    inlets: ["inlet"], outlets: ["outlet"],
    inputs: [["P_out", "Outlet pressure", "required"], ["eta", "Pump efficiency", "default 0.65"]],
    calculates: "Hydraulic and shaft power", sizer: "Hydraulic and shaft power, head",
    pid: ["Check valve on discharge", "Pump instruments", "Isolation valves"],
  },
  {
    kind: "jt_valve", name: "JT valve", group: "Pressure change",
    symbol: '<polygon points="40,32 80,52 40,72"/><polygon points="120,32 80,52 120,72"/><path d="M8 52h32M120 52h32M80 52V22M66 22h28"/>',
    description: "Drops pressure at constant enthalpy. Gas cools as it expands (the Joule–Thomson effect), which is how hydrocarbon dew point control works.",
    inlets: ["inlet"], outlets: ["outlet"], inputs: [["P_out", "Outlet pressure", "required"]],
    calculates: "Outlet temperature and vapour fraction", sizer: null, pid: ["Isolation valves"],
  },
  {
    kind: "heater", name: "Heater", group: "Heat transfer",
    symbol: '<circle cx="80" cy="52" r="30"/><path d="M58 60l9-20 9 20 9-20 9 20"/><path d="M8 52h42M110 52h42"/>',
    description: "Heats a stream to a set outlet temperature, or by a set duty. The utility side is not modelled.",
    inlets: ["inlet"], outlets: ["outlet"], inputs: [["T_out", "Outlet temperature", "or duty_W"], ["dP", "Pressure drop", "default 0"]],
    calculates: "Duty", sizer: null, pid: ["Isolation valves"],
  },
  {
    kind: "cooler", name: "Cooler", group: "Heat transfer",
    symbol: '<circle cx="80" cy="52" r="30"/><path d="M58 44l9 20 9-20 9 20 9-20"/><path d="M8 52h42M110 52h42"/>',
    description: "Cools a stream to a set outlet temperature, or by a set duty.",
    inlets: ["inlet"], outlets: ["outlet"], inputs: [["T_out", "Outlet temperature", "or duty_W"], ["dP", "Pressure drop", "default 0"]],
    calculates: "Duty", sizer: null, pid: ["Isolation valves"],
  },
  {
    kind: "air_cooler", name: "Air cooler", group: "Heat transfer",
    symbol: '<rect x="30" y="40" width="100" height="26"/><path d="M40 66l10-18 10 18 10-18 10 18 10-18 10 18 10-18 10 18"/><circle cx="80" cy="24" r="12"/><path d="M68 24h24M80 12v24M8 53h22M130 53h22"/>',
    description: "Fin-fan cooler that rejects heat to ambient air. Typical after a compressor.",
    inlets: ["inlet"], outlets: ["outlet"], inputs: [["T_out", "Outlet temperature", "required"], ["dP", "Pressure drop", "default 0"]],
    calculates: "Duty", sizer: "Area from U and LMTD", pid: ["Isolation valves"],
  },
  {
    kind: "shell_tube", name: "Shell and tube exchanger", group: "Heat transfer",
    symbol: '<rect x="30" y="30" width="100" height="44" rx="6"/><path d="M30 44h100M30 60h100" style="stroke-dasharray:4 3"/><path d="M8 52h22M130 52h22M60 30V14M100 74v16"/>',
    description: "Exchanger against a utility stream. Set the process outlet temperature and the utility in and out temperatures.",
    inlets: ["inlet"], outlets: ["outlet"],
    inputs: [
      ["T_out", "Outlet temperature", "required"], ["dP", "Pressure drop", "default 0"],
      ["utility_T_in", "Utility inlet temperature", "for LMTD"], ["utility_T_out", "Utility outlet temperature", "for LMTD"],
    ],
    calculates: "Duty", sizer: "Area from U and counter-current LMTD", pid: ["Isolation valves"],
  },
  {
    kind: "teg_contactor", name: "TEG contactor", group: "Mass transfer",
    symbol: '<rect x="60" y="6" width="40" height="92" rx="12"/><path d="M60 26h40M60 40h40M60 54h40M60 68h40M60 82h40" style="stroke-dasharray:3 3"/><path d="M30 90h30M100 16h30M80 6V0M100 92h30"/>',
    description: "Dries natural gas by counter-current contact with lean triethylene glycol. You set the water content you want in the dry gas.",
    inlets: ["gas_in", "lean_teg_in"], outlets: ["gas_out", "rich_teg_out"],
    inputs: [["water_out_lb_per_mmscf", "Dry gas water content", "default 7 lb/MMSCF"]],
    calculates: "Water removed, rich TEG flow, stage count (Kremser)", sizer: "Diameter and maximum gas velocity",
    pid: ["PSV", "Level instruments", "Isolation valves"],
  },
  {
    kind: "mdea_absorber", name: "Amine absorber", group: "Mass transfer",
    symbol: '<rect x="60" y="6" width="40" height="92" rx="12"/><path d="M60 30l40 12M60 48l40 12M60 66l40 12"/><path d="M30 90h30M100 16h30M80 6V0M100 92h30"/>',
    description: "Sweetens sour gas with lean amine (MDEA by default, or MEA or DEA). You set the CO₂ and H₂S left in the gas; Kent–Eisenberg equilibrium checks that the solvent can reach them.",
    inlets: ["gas_in", "lean_amine_in"], outlets: ["gas_out", "rich_amine_out"],
    inputs: [
      ["co2_out_molpct", "CO₂ left in the gas", "default 2 mol%"],
      ["h2s_out_ppmv", "H₂S left in the gas", "default 4 ppmv"],
      ["amine", "Solvent", "MDEA, MEA or DEA"],
    ],
    calculates: "Acid gas removed and the rich amine loading", sizer: null, pid: [],
  },
  {
    kind: "mdea_regenerator", name: "Amine regenerator", group: "Mass transfer",
    symbol: '<rect x="60" y="6" width="40" height="80" rx="12"/><path d="M60 30h40M60 48h40M60 66h40" style="stroke-dasharray:3 3"/><circle cx="80" cy="96" r="8"/><path d="M30 20h30M80 6V0M100 76h30"/>',
    description: "Strips the rich amine back to lean loadings with reboiler steam, using the same equilibrium as the absorber.",
    inlets: ["rich_amine_in"], outlets: ["lean_amine_out", "acid_gas_out"],
    inputs: [
      ["lean_co2_loading", "Lean CO₂ loading", "default 0.005"],
      ["lean_h2s_loading", "Lean H₂S loading", "default 0.002"],
      ["regenerator_P", "Regenerator pressure", "default 180 kPa(a)"],
      ["reboiler_T", "Reboiler temperature", "default 121 °C"],
    ],
    calculates: "Stripping duty, steam demand and the acid gas stream", sizer: null, pid: [],
  },
  {
    kind: "column", name: "Distillation column", group: "Mass transfer",
    symbol: '<rect x="62" y="10" width="36" height="84" rx="14"/><path d="M62 30h36M62 44h36M62 58h36M62 72h36" style="stroke-dasharray:3 3"/><path d="M20 52h42M98 18h40M98 86h40M80 10V0"/>',
    description: "Rigorous equilibrium-stage column (inside-out solver, Newton fallback). Set the stage count, feed stage, condenser and reboiler type, and the column specs.",
    inlets: ["feed"], outlets: ["distillate", "bottoms", "side_draw"],
    inputs: [
      ["n_stages", "Equilibrium stages", "required"],
      ["feed_stage", "Feed stage", "default the middle stage"],
      ["condenser", "Condenser", "total, partial or none"],
      ["reboiler", "Reboiler", "kettle or none"],
      ["specs", "Column specs", "e.g. reflux_ratio, product_purity"],
    ],
    calculates: "Stage temperatures, flows and compositions, condenser and reboiler duties", sizer: null, pid: [],
  },
  {
    kind: "mixer", name: "Mixer", group: "Mixing",
    symbol: '<path d="M10 22l60 30-60 30M70 52h80M10 52h60"/>',
    description: "Combines up to three streams adiabatically. Unused inlets can be left empty.",
    inlets: ["inlet_1", "inlet_2", "inlet_3"], outlets: ["outlet"], inputs: [], calculates: "Mixed outlet state", sizer: null, pid: [],
  },
  {
    kind: "splitter", name: "Splitter", group: "Mixing",
    symbol: '<path d="M10 52h60M70 52l70-30M70 52l70 30"/>',
    description: "Divides one stream into two with the same temperature, pressure and composition.",
    inlets: ["inlet"], outlets: ["outlet_1", "outlet_2"], inputs: [["fractions", "Split fractions", "two values summing to 1"]],
    calculates: "Two outlets", sizer: null, pid: [],
  },
];

// The absorber and regenerator also register under the solvent name.
const ALIASES: Record<string, [base: string, name: string]> = {
  mea_absorber: ["mdea_absorber", "Amine absorber, MEA"],
  dea_absorber: ["mdea_absorber", "Amine absorber, DEA"],
  mea_regenerator: ["mdea_regenerator", "Amine regenerator, MEA"],
  dea_regenerator: ["mdea_regenerator", "Amine regenerator, DEA"],
};

const BY_KIND = new Map(CATALOG.map((e) => [e.kind, e]));

/** Catalog entries for the registered unit kinds, in catalog order; unknown kinds last. */
export function catalogFor(kinds: string[] | undefined): EquipmentInfo[] {
  if (!kinds) return CATALOG;
  const known = CATALOG.filter((e) => kinds.includes(e.kind));
  const extra = kinds
    .filter((k) => !BY_KIND.has(k))
    .map((k): EquipmentInfo => {
      const alias = ALIASES[k];
      const base = alias && BY_KIND.get(alias[0]);
      if (base) return { ...base, kind: k, name: alias[1] };
      return {
        kind: k, name: k.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase()), group: "Other",
        symbol: '<rect x="40" y="22" width="80" height="60" rx="8"/><path d="M8 52h32M120 52h32"/>',
        description: "Registered in the engine. No description yet.", inlets: [], outlets: [], inputs: [],
        calculates: "See the plugin source", sizer: null, pid: [],
      };
    });
  return [...known, ...extra];
}
