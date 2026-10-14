// The one place backend SI base units become user units, per frontend/AGENTS.md:
// backend carries K, Pa absolute, mol/s and W; users see degC, kPa(g), kmol/h and kW.

function round(v: number, digits: number): number {
  const f = 10 ** digits;
  return Math.round(v * f) / f;
}

/** K -> degC */
export function toDegC(T_K: number): number {
  return round(T_K - 273.15, 1);
}

/** Pa absolute -> kPa(g) */
export function toKPaG(P_Pa: number): number {
  return round(P_Pa / 1000 - 101.325, 1);
}

/** mol/s -> kmol/h */
export function toKmolH(mol_per_s: number): number {
  return round(mol_per_s * 3.6, 3);
}

/** W -> kW */
export function toKw(W: number): number {
  return round(W / 1000, 2);
}

/** Vapor fraction is dimensionless; rounded only for display. */
export function toVaporFraction(v: number): number {
  return round(v, 3);
}

// --- Round-trip conversions (F-01 editor) ---
// Display converters above round for presentation; editable fields need exact
// conversions so a saved value re-reads identically.

const KELVIN_OFFSET = 273.15;
const ATMOSPHERE_KPA = 101.325;
const SECONDS_PER_HOUR = 3600;

export function kelvinToCelsius(k: number): number {
  return k - KELVIN_OFFSET;
}

export function celsiusToKelvin(c: number): number {
  return c + KELVIN_OFFSET;
}

export function paToKpaGauge(pa: number): number {
  return pa / 1000 - ATMOSPHERE_KPA;
}

export function kpaGaugeToPa(kpaGauge: number): number {
  return (kpaGauge + ATMOSPHERE_KPA) * 1000;
}

export function molPerSToKmolPerH(molPerS: number): number {
  return (molPerS * SECONDS_PER_HOUR) / 1000;
}

export function kmolPerHToMolS(kmolPerH: number): number {
  return (kmolPerH * 1000) / SECONDS_PER_HOUR;
}

/** Parse user text as a finite number; null when blank or non-numeric. */
export function parseFiniteNumber(text: string): number | null {
  if (text.trim() === "") return null;
  const n = Number(text);
  return Number.isFinite(n) ? n : null;
}

/** Display form of a number without float noise (e.g. 20.000000000000018 → "20"). */
export function formatNumber(n: number): string {
  return String(Number(n.toPrecision(10)));
}
