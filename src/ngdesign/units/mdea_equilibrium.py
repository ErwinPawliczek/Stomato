"""Kent-Eisenberg electrolyte equilibrium for CO2 + H2S + amine + H2O systems.

Joint acid-gas speciation shared by the amine units (absorber ``mdea_absorber``
and its ``mea_absorber``/``dea_absorber`` aliases, regenerator likewise).
Chemistry lives at unit level -- the TEG-precedent shape (``teg_activity.py``):
the thermodynamic package never sees the ionic species, the unit owns the
equilibrium solve. The amine is selected by name (``amine="MDEA"``, ``"MEA"``,
``"DEA"``); the stream ``z`` stays molecular either way -- ions never leave
this module.

Model (Kent-Eisenberg: thermodynamic equilibria where known, apparent constants
fitted to published VLE):

    CO2(aq) + H2O  <=> H+ + HCO3-            K1  (Edwards et al., 1978)
    HCO3-          <=> H+ + CO3--            K2  (Edwards et al., 1978)
    H2O            <=> H+ + OH-              Kw  (Edwards et al., 1978)
    H2S(aq)        <=> H+ + HS-              K3  (standard aqueous chemistry)
    HS-            <=> H+ + S--              K4  (standard aqueous chemistry)
    Amine + H2O    <=> AmineH+ + OH-         Kam (apparent, per amine)
    CO2(aq)        -> p_CO2                  H_CO2 (Versteeg & van Swaaij, 1988)
    H2S(aq)        -> p_H2S                  Lambda (apparent lumped constant,
                                             fitted per amine to published VLE)
    primary/secondary amines only (MEA, DEA):
    AmineCOO- + H2O <=> Amine + HCO3-        Kc  (carbamate reversion, apparent)

Constant provenance
-------------------
K1/K2/Kw (molality scale, applied to molar concentrations -- the standard
apparent-model convention): Edwards, T.J., Maurer, G., Newman, J. and
Prausnitz, J.M., 1978, "Vapor-liquid equilibria in multicomponent aqueous
solutions of volatile weak electrolytes", AIChE J. 24(6) 966-976, eq. 24
coefficient set ``exp(A/T + B ln T + C)``:

    K1 = exp(-12092.1/T - 36.7816 ln T + 235.482)      mol/L
    K2 = exp(-12431.7/T - 35.4819 ln T + 220.067)      mol/L
    Kw = exp(-13445.9/T - 22.4773 ln T + 140.932)      (mol/L)^2

H_CO2 (Henry, Pa.m3/mol): Versteeg, G.F. and van Swaaij, W.P.M., 1988,
"Solubility and diffusivity of acid gases in aqueous diethanolamine solutions",
J. Chem. Eng. Data 33, 29-34:  H = 2.82e6 exp(-2044/T).  (The same N2O-analogue
solubility data set NeqSim uses for its amine models.)

Amine constants (all retrieved from NeqSim's ``AmineKentEisenberg`` model, the
reference implementation and validation target for the CO2 side):

    MDEA  Kam = exp(-6.40 - 4210/T)                    (tertiary: no carbamate)
    MEA   Kam = exp(-3.10 - 5630/T),  Kc = exp(3.90 - 1800/T)
    DEA   Kam = exp(-3.66 - 5000/T),  Kc = exp(4.80 - 1800/T)

Kam is the apparent amine dissociation (protonation) constant, mol/L; Kc the
apparent carbamate reversion constant, mol/L, for the primary/secondary-amine
reaction AmineCOO- + H2O <=> Amine + HCO3-.  NeqSim tunes these so the model
reproduces the classic VLE data sets of Jou, Mather & Otto (1982, MDEA) and
Jou/Lee/Mather (MEA).  CO2 regression anchors reproduced with the MDEA
constant set (NeqSim's own): 313.15 K, 50 wt% MDEA (~4.36 mol/L): p_CO2 ~
0.0093 bara at loading 0.10 and ~0.229 bara at loading 0.40 -- the module
lands within 3% of both (tests).  For MEA/DEA the CO2 goldens are the same
constants and speciation algebra as NeqSim's carbamate model (tests carry an
independent port of it and require agreement within 2.4%), with NeqSim's
documented MEA engineering band (30 wt%, 313.15 K, loading 0.5: p_CO2 in
5-30 kPa) and MEA-binds-tighter-than-MDEA as external sanity anchors.

K3/K4 (T-independent): pK1(H2S) = 7.05, pK2(H2S) = 12.92 -- GPSA Data Book /
Kohl & Nielsen standard aqueous H2S chemistry.  Their only role is the
molecular/bound split at fixed total sulfide, which is insensitive at amine
pH (a factor-2 shift in K3 moves the split <1%); the VLE-relevant temperature
dependence is carried entirely by the lumped sulfide constant below.

Lambda (apparent lumped H2S constant, Pa.m3/mol): the H2S chemistry reduces
to the proton transfer H2S + Amine <=> AmineH+ + HS-, so
p_H2S = (Lambda/Kam) [H+][HS-] and [H2S(aq)] = p Kam/(Lambda K3), where
Lambda is the single fitted lumped constant (the ideal-chemistry limit reads
p = Lambda alpha^2 C/(1-alpha)).  Fits at the 313.15 K isotherms, minimax
over three published anchors each:

    MDEA  24.37 Pa.m3/mol, B = 4570 K
          anchors: Jou, Mather & Otto 1982 (I&EC Process Des. Dev. 21, 539),
          4.28 kmol/m3: 0.0108 kPa at loading 0.01, 3.31 kPa at 0.165,
          36.9 kPa at 0.453 (GASWORKS h2s-mdea-absorber tabulation).  Fit
          lands within 2% of all three anchors.
    MEA   2.473 Pa.m3/mol, B = 5906 K
          anchors: Jones, Froning & Claytor 1959 (J. Chem. Eng. Data 4, 85),
          15.3 wt% (~2.47 kmol/m3): 0.40 kPa at 0.208, 1.21 kPa at 0.362,
          5.75 kPa at 0.643 (IUPAC Solubility Data Series vol. 32, sec. 1.6).
          Minimax band +/-17%; the Jones hold-out points (0.13 kPa at 0.125,
          7.96 kPa at 0.729, 14.1 kPa at 0.814) land within +/-40%.
    DEA   10.060 Pa.m3/mol, B = 5244 K
          anchors: Lai, Otto & Mather 1985 (Can. J. Chem. Eng. 63, 681),
          2.0 kmol/m3: 0.106 kPa at 0.063, 0.384 kPa at 0.141,
          1.355 kPa at 0.219 (IUPAC SDS vol. 32, sec. 1.6).  Minimax band
          +/-20% (the Lai data carry a stated +/-15% pressure uncertainty).

Honest band note: the tight 2% MDEA fit is data luck, not a property of the
method -- at a single isotherm the one-parameter Kent-Eisenberg H2S form has
its loading shape locked (p proportional to alpha^2/(1-alpha)), and the MEA
and DEA data do not follow that shape as closely as Jou's MDEA points do.
Kent and Eisenberg's own MEA fits claim ~20-30% accuracy.  The tests assert
the achieved bands above, not a borrowed 2%.

B coefficients (van 't Hoff, K): from the heat of H2S absorption -- MDEA
~38 kJ/mol (Jou et al. / NeqSim ``AmineHeatOfAbsorption``), MEA 49.1 kJ/mol
(620 Btu/lb), DEA 43.6 kJ/mol (550 Btu/lb) (GPSA Data Book / Manning &
Thompson tabulation).

    Lambda(T) = Lambda(313.15) exp(B (1/313.15 - 1/T))

The apparent-constant route is the Kent-Eisenberg method itself (fit apparent
constants to measured VLE), so no water-value Henry is claimed for the amine
solution.

Validity window: absorber/regenerator service, ~290-400 K, amine molarity
~1-6 mol/L, loadings 0-1.5 mol acid gas/mol amine (the Jou-MDEA data end at
1.08, the Jones-MEA data at 0.97).  The linear-in-amine ideal-solution
structure carries no loading- or composition-dependent activity corrections
beyond the fitted constants; KE accuracy at high loading is the known
correlation limit.

Solve method: the charge balance is monotone in the hydrogen-ion activity
everywhere on the bracket, so both directions reduce to a 1-D root find on
log([H+]) with a hand-rolled Brent solver (no scipy -- dependency-light per
B-07 precedent).  For primary/secondary amines the carbamate sink takes CO2
out of the molecular pool, so the free CO2 at a given [H+] comes from a second
bracketed root find on the carbon balance (the same balance NeqSim's
``freeCO2AtH`` fixed-point iterates), nested inside the charge-balance root
find.

All public quantities are SI: T in K, molarity in mol/m3, pressures in Pa
absolute.  Internally the chemistry runs on the literature scale (mol/L) and
converts at the API boundary.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial

__all__ = [
    "AMINES",
    "AmineChemistry",
    "Speciation",
    "amine_molarity",
    "equilibrium_loadings",
    "equilibrium_partial_pressures",
]

_MAX_LOADING = 1.5
_LN_H_LO = -34.0
_LN_H_HI = 16.0


@dataclass(frozen=True)
class AmineChemistry:
    """Per-amine Kent-Eisenberg constants (provenance in the module docstring).

    ``carbamate`` is the (a, b) pair of the carbamate reversion constant
    Kc = exp(a + b/T) for primary/secondary amines, or None for tertiary
    amines, which form no carbamate.
    """

    name: str
    kam_a: float
    kam_b: float
    carbamate: tuple[float, float] | None
    lambda_ref: float
    vant_hoff_b: float

    def kam(self, T: float) -> float:
        """Apparent amine dissociation constant, mol/L."""
        return math.exp(self.kam_a - self.kam_b / T)

    def kc(self, T: float) -> float | None:
        """Apparent carbamate reversion constant, mol/L (tertiary amines: None)."""
        if self.carbamate is None:
            return None
        a, b = self.carbamate
        return math.exp(a + b / T)

    def lambda_h2s(self, T: float) -> float:
        """Lumped apparent H2S constant at T, Pa.m3/mol (van 't Hoff shifted)."""
        return self.lambda_ref * math.exp(self.vant_hoff_b * (1.0 / _LAMBDA_REF_T - 1.0 / T))


MDEA_CHEMISTRY = AmineChemistry(
    name="MDEA", kam_a=-6.40, kam_b=4210.0, carbamate=None, lambda_ref=24.37, vant_hoff_b=4570.0
)
MEA_CHEMISTRY = AmineChemistry(
    name="MEA", kam_a=-3.10, kam_b=5630.0, carbamate=(3.90, -1800.0), lambda_ref=2.473, vant_hoff_b=5906.0
)
DEA_CHEMISTRY = AmineChemistry(
    name="DEA", kam_a=-3.66, kam_b=5000.0, carbamate=(4.80, -1800.0), lambda_ref=10.060, vant_hoff_b=5244.0
)

#: The supported amine chemistries, by component name.
AMINES: dict[str, AmineChemistry] = {
    MDEA_CHEMISTRY.name: MDEA_CHEMISTRY,
    MEA_CHEMISTRY.name: MEA_CHEMISTRY,
    DEA_CHEMISTRY.name: DEA_CHEMISTRY,
}


def _chemistry(amine: str) -> AmineChemistry:
    """Look up a supported amine chemistry by component name."""
    chem = AMINES.get(amine)
    if chem is None:
        supported = ", ".join(sorted(AMINES))
        raise ValueError(f"unsupported amine {amine!r}; supported amines: {supported}")
    return chem


@dataclass(frozen=True)
class Speciation:
    """Liquid-phase speciation in mol/L plus the gas partial pressures in Pa."""

    h: float
    amine: float
    amineh: float
    carbamate: float
    co2_free: float
    hco3: float
    co3: float
    h2s_free: float
    hs: float
    s2: float
    oh: float
    p_co2: float
    p_h2s: float


def _co2_k1(T: float) -> float:
    """CO2 + H2O <=> H+ + HCO3-, mol/L (Edwards et al. 1978)."""
    return math.exp(-12092.1 / T - 36.7816 * math.log(T) + 235.482)


def _co2_k2(T: float) -> float:
    """HCO3- <=> H+ + CO3--, mol/L (Edwards et al. 1978)."""
    return math.exp(-12431.7 / T - 35.4819 * math.log(T) + 220.067)


def _water_kw(T: float) -> float:
    """H2O <=> H+ + OH-, (mol/L)^2 (Edwards et al. 1978)."""
    return math.exp(-13445.9 / T - 22.4773 * math.log(T) + 140.932)


def _henry_co2(T: float) -> float:
    """CO2 Henry constant, Pa.m3/mol (Versteeg & van Swaaij 1988)."""
    return 2.82e6 * math.exp(-2044.0 / T)


def _h2s_k3(T: float) -> float:
    """H2S <=> H+ + HS-, mol/L (pK1 = 7.05, GPSA/Kohl-Nielsen)."""
    return math.pow(10.0, -7.05)


def _h2s_k4(T: float) -> float:
    """HS- <=> H+ + S--, mol/L (pK2 = 12.92, GPSA/Kohl-Nielsen)."""
    return math.pow(10.0, -12.92)


_LAMBDA_REF_T = 313.15


def _brent_root(
    fn: Callable[[float], float], lo: float, hi: float, xtol: float = 1e-12, max_iter: int = 100
) -> float:
    """Hand-rolled Brent root finder on [lo, hi] (requires fn(lo)*fn(hi) <= 0).

    Classic bisection/secant/inverse-quadratic hybrid (Brent 1973; the scipy
    ``brentq`` algorithm).  A failing bracket raises -- errors are never
    swallowed.
    """
    a, b = lo, hi
    fa, fb = fn(a), fn(b)
    if fa == 0.0:
        return a
    if fb == 0.0:
        return b
    if fa * fb > 0.0:
        raise ValueError(f"root not bracketed: fn({lo})={fa}, fn({hi})={fb}")
    c, fc = a, fa
    d = e = hi - lo
    for _ in range(max_iter):
        if fb * fc > 0.0:
            c, fc = a, fa
            d = e = b - a
        if abs(fc) < abs(fb):
            a, fa = b, fb
            b, fb = c, fc
            c, fc = a, fa
        tol1 = 2.0 * xtol * abs(b) + 0.5 * xtol
        xm = 0.5 * (c - b)
        if abs(xm) <= tol1 or fb == 0.0:
            return b
        if abs(e) >= tol1 and abs(fa) > abs(fb):
            s = fb / fa
            if a == c:
                p = 2.0 * xm * s
                q = 1.0 - s
            else:
                q = fa / fc
                r = fb / fc
                p = s * (2.0 * xm * q * (q - r) - (b - a) * (r - 1.0))
                q = (q - 1.0) * (r - 1.0) * (s - 1.0)
            if p > 0.0:
                q = -q
            p = abs(p)
            if 2.0 * p < min(3.0 * xm * q - abs(tol1 * q), abs(e * q)):
                e, d = d, p / q
            else:
                d = e = xm
        else:
            d = e = xm
        a, fa = b, fb
        step = d if abs(d) > tol1 else math.copysign(tol1, xm)
        b, fb = b + step, fn(b + step)
    raise ValueError(f"Brent solver did not converge in {max_iter} iterations")


def _carbon_balance_at_h(
    h: float, C_co2: float, C_A: float, a1: float, a2: float, aam: float, kc: float
) -> tuple[float, float, float, float, float]:
    """Solve the carbon balance at a given [H+]: free CO2 given the carbamate sink.

    The carbamate sink takes CO2 out of the molecular pool, so the free CO2 is
    no longer the closed-form ``C_co2/denom`` of the tertiary-amine case.  The
    balance co2 + hco3 + co3 + carbamate = C_co2 is strictly increasing in
    hco3 (every sink grows with it), so it reduces to a bracketed Brent root
    on [0, C_co2] -- NeqSim's ``freeCO2AtH`` solves the same balance with a
    fixed-point iteration, which can two-cycle where the sinks saturate.
    Returns (co2_free, hco3, co3, amine, carbamate).
    """
    h_over_a1 = h / a1
    a2_over_h = a2 / h

    def carbon_residual(hco3: float) -> float:
        amine = C_A / (1.0 + h / aam + hco3 / kc)
        carbamate = amine * hco3 / kc
        return hco3 * h_over_a1 + hco3 + hco3 * a2_over_h + carbamate - C_co2

    hco3 = _brent_root(carbon_residual, 0.0, C_co2)
    co2 = hco3 * h_over_a1
    co3 = hco3 * a2_over_h
    amine = C_A / (1.0 + h / aam + hco3 / kc)
    carbamate = amine * hco3 / kc
    return co2, hco3, co3, amine, carbamate


def _charge_residual_ln_h(
    ln_h: float, T: float, C_A: float, C_co2: float, C_h2s: float, chem: AmineChemistry
) -> float:
    """Forward residual (loadings fixed): cations - anions, mol/L.

    ``C_A``/``C_co2``/``C_h2s`` are the total amine/CO2/H2S liquid-phase
    molarities in mol/L.  Strictly increasing in [H+].
    """
    h = math.exp(ln_h)
    a1, a2, aw = _co2_k1(T), _co2_k2(T), _water_kw(T)
    a3, a4 = _h2s_k3(T), _h2s_k4(T)
    aam = chem.kam(T)
    kc = chem.kc(T)
    oh = aw / h
    hs = C_h2s * a3 * h / (h * h + a3 * h + a3 * a4)
    s2 = a4 * hs / h
    if kc is None:
        denom = 1.0 + a1 / h + a1 * a2 / (h * h)
        co2_free = C_co2 / denom
        hco3 = a1 * co2_free / h
        co3 = a2 * hco3 / h
        carbamate = 0.0
        amine = C_A / (1.0 + h / aam)
    else:
        co2_free, hco3, co3, amine, carbamate = _carbon_balance_at_h(h, C_co2, C_A, a1, a2, aam, kc)
    # Protonation equilibrium amineH = amine h/Kam; the mass balance C_A =
    # amine + amineH + carbamate is already encoded in amine's denominator,
    # so C_A - amine would wrongly fold the carbamate into the cation side.
    amineh = amine * h / aam
    return amineh + h - (oh + hco3 + 2.0 * co3 + carbamate + hs + 2.0 * s2)


def _pressure_residual_ln_h(
    ln_h: float, T: float, C_A: float, co2_free: float, h2s_free: float, chem: AmineChemistry
) -> float:
    """Inverse residual (partial pressures fixed): cations - anions, mol/L.

    ``co2_free``/``h2s_free`` are fixed by Henry's law at the given partial
    pressures.  Strictly increasing in [H+].
    """
    h = math.exp(ln_h)
    a1, a2, aw = _co2_k1(T), _co2_k2(T), _water_kw(T)
    a3, a4 = _h2s_k3(T), _h2s_k4(T)
    aam = chem.kam(T)
    kc = chem.kc(T)
    hco3 = a1 * co2_free / h
    co3 = a2 * hco3 / h
    hs = a3 * h2s_free / h
    s2 = a4 * hs / h
    oh = aw / h
    if kc is None:
        carbamate = 0.0
        amine = C_A / (1.0 + h / aam)
    else:
        amine = C_A / (1.0 + h / aam + hco3 / kc)
        carbamate = amine * hco3 / kc
    amineh = amine * h / aam
    return amineh + h - (oh + hco3 + 2.0 * co3 + carbamate + hs + 2.0 * s2)


def _speciate_from_loadings(
    T: float, C_A: float, C_co2: float, C_h2s: float, chem: AmineChemistry
) -> Speciation:
    a1, a2, aam = _co2_k1(T), _co2_k2(T), chem.kam(T)
    a3, a4 = _h2s_k3(T), _h2s_k4(T)
    fn: Callable[[float], float] = partial(
        _charge_residual_ln_h, T=T, C_A=C_A, C_co2=C_co2, C_h2s=C_h2s, chem=chem
    )
    ln_h = _brent_root(fn, _LN_H_LO, _LN_H_HI)
    h = math.exp(ln_h)
    kc = chem.kc(T)
    if kc is None:
        denom = 1.0 + a1 / h + a1 * a2 / (h * h)
        co2_free = C_co2 / denom
        hco3 = a1 * co2_free / h
        co3 = a2 * hco3 / h
        carbamate = 0.0
        amine = C_A / (1.0 + h / aam)
    else:
        co2_free, hco3, co3, amine, carbamate = _carbon_balance_at_h(h, C_co2, C_A, a1, a2, aam, kc)
    hs = C_h2s * a3 * h / (h * h + a3 * h + a3 * a4)
    s2 = a4 * hs / h
    h2s_free = C_h2s - hs - s2
    amineh = amine * h / aam
    return Speciation(
        h=h,
        amine=amine,
        amineh=amineh,
        carbamate=carbamate,
        co2_free=co2_free,
        hco3=hco3,
        co3=co3,
        h2s_free=h2s_free,
        hs=hs,
        s2=s2,
        oh=_water_kw(T) / h,
        # Forward VLE in SI: H [Pa.m3/mol] x concentration [mol/m3]; the
        # speciation works in mol/L, hence the 1000.
        p_co2=_henry_co2(T) * co2_free * 1000.0,
        p_h2s=chem.lambda_h2s(T) / aam * h * hs * 1000.0,
    )


def _speciate_from_pressures(
    T: float, C_A: float, p_co2: float, p_h2s: float, chem: AmineChemistry
) -> Speciation:
    a1, a2, aam = _co2_k1(T), _co2_k2(T), chem.kam(T)
    a3, a4 = _h2s_k3(T), _h2s_k4(T)
    # Inverse Henry/lumped laws: p [Pa] / H [Pa.m3/mol] gives mol/m3; the
    # speciation balance works in mol/L, hence the 1000.
    co2_free = p_co2 / _henry_co2(T) / 1000.0
    h2s_free = p_h2s * aam / (chem.lambda_h2s(T) * a3) / 1000.0
    fn: Callable[[float], float] = partial(
        _pressure_residual_ln_h, T=T, C_A=C_A, co2_free=co2_free, h2s_free=h2s_free, chem=chem
    )
    ln_h = _brent_root(fn, _LN_H_LO, _LN_H_HI)
    h = math.exp(ln_h)
    hco3 = a1 * co2_free / h
    co3 = a2 * hco3 / h
    hs = a3 * h2s_free / h
    s2 = a4 * hs / h
    kc = chem.kc(T)
    if kc is None:
        carbamate = 0.0
        amine = C_A / (1.0 + h / aam)
    else:
        amine = C_A / (1.0 + h / aam + hco3 / kc)
        carbamate = amine * hco3 / kc
    return Speciation(
        h=h,
        amine=amine,
        amineh=amine * h / aam,
        carbamate=carbamate,
        co2_free=co2_free,
        hco3=hco3,
        co3=co3,
        h2s_free=h2s_free,
        hs=hs,
        s2=s2,
        oh=_water_kw(T) / h,
        p_co2=p_co2,
        p_h2s=p_h2s,
    )


def equilibrium_partial_pressures(
    T: float,
    amine_molarity_mol_m3: float,
    co2_loading: float,
    h2s_loading: float,
    amine: str = "MDEA",
) -> tuple[float, float]:
    """Equilibrium (p_CO2, p_H2S) in Pa over amine solution at fixed loadings.

    Args:
        T: temperature in K.
        amine_molarity_mol_m3: total amine molarity of the liquid phase, mol/m3.
        co2_loading: total CO2 loading (mol CO2 per mol amine, free + bound).
        h2s_loading: total H2S loading, same basis.
        amine: solvent amine, one of ``AMINES`` (default MDEA).
    """
    chem = _chemistry(amine)
    _validate_common(T, amine_molarity_mol_m3)
    _validate_loadings(co2_loading, h2s_loading)
    C_A = amine_molarity_mol_m3 / 1000.0
    sp = _speciate_from_loadings(T, C_A, co2_loading * C_A, h2s_loading * C_A, chem)
    return sp.p_co2, sp.p_h2s


def equilibrium_loadings(
    T: float,
    amine_molarity_mol_m3: float,
    p_co2: float,
    p_h2s: float,
    amine: str = "MDEA",
) -> tuple[float, float]:
    """Equilibrium (CO2, H2S) loadings (mol/mol amine) at fixed partial pressures.

    Args:
        T: temperature in K.
        amine_molarity_mol_m3: total amine molarity of the liquid phase, mol/m3.
        p_co2: CO2 partial pressure over the solution, Pa absolute.
        p_h2s: H2S partial pressure over the solution, Pa absolute.
        amine: solvent amine, one of ``AMINES`` (default MDEA).
    """
    chem = _chemistry(amine)
    _validate_common(T, amine_molarity_mol_m3)
    if p_co2 < 0.0 or p_h2s < 0.0:
        raise ValueError(f"partial pressures must be non-negative, got p_co2={p_co2}, p_h2s={p_h2s}")
    C_A = amine_molarity_mol_m3 / 1000.0
    sp = _speciate_from_pressures(T, C_A, p_co2, p_h2s, chem)
    total_co2 = sp.co2_free + sp.hco3 + sp.co3 + sp.carbamate
    total_h2s = sp.h2s_free + sp.hs + sp.s2
    return total_co2 / C_A, total_h2s / C_A


def amine_molarity(x_amine: float, phase_mw_g_mol: float, phase_density_kg_m3: float) -> float:
    """Amine molarity of a liquid phase, mol/m3, from its flashed composition.

    Args:
        x_amine: amine mole fraction within the liquid phase.
        phase_mw_g_mol: mole-fraction-weighted molecular weight of the phase, g/mol.
        phase_density_kg_m3: mass density of the phase, kg/m3.
    """
    if x_amine <= 0.0:
        raise ValueError(f"no amine in the liquid phase (x_amine={x_amine}); not an amine solvent")
    if phase_density_kg_m3 <= 0.0 or phase_mw_g_mol <= 0.0:
        raise ValueError(
            f"non-positive phase density ({phase_density_kg_m3} kg/m3) or MW ({phase_mw_g_mol} g/mol)"
        )
    return x_amine * phase_density_kg_m3 / phase_mw_g_mol * 1000.0


def _validate_common(T: float, amine_molarity_mol_m3: float) -> None:
    if T <= 0.0:
        raise ValueError(f"temperature must be positive, got {T} K")
    if amine_molarity_mol_m3 <= 0.0:
        raise ValueError(f"amine molarity must be positive, got {amine_molarity_mol_m3} mol/m3")


def _validate_loadings(co2_loading: float, h2s_loading: float) -> None:
    for name, value in (("co2_loading", co2_loading), ("h2s_loading", h2s_loading)):
        if value < 0.0:
            raise ValueError(f"{name} must be non-negative, got {value}")
        if value > _MAX_LOADING:
            raise ValueError(
                f"{name}={value} exceeds the model window (max {_MAX_LOADING} mol/mol; "
                "the fitted isotherm data end near 1.1)"
            )
