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
