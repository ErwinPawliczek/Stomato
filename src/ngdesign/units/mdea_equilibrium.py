"""Kent-Eisenberg electrolyte equilibrium for the CO2 + H2S + MDEA + H2O system.

Joint acid-gas speciation used by the amine units (absorber ``mdea_absorber``,
future regenerator). Chemistry lives at unit level -- the TEG-precedent shape
(``teg_activity.py``): the thermodynamic package never sees the ionic species,
the unit owns the equilibrium solve.

Model (Kent-Eisenberg: thermodynamic equilibria where known, apparent constants
fitted to published VLE):

    CO2(aq) + H2O  <=> H+ + HCO3-            K1  (Edwards et al., 1978)
    HCO3-          <=> H+ + CO3--            K2  (Edwards et al., 1978)
    H2O            <=> H+ + OH-              Kw  (Edwards et al., 1978)
    H2S(aq)        <=> H+ + HS-              K3  (standard aqueous chemistry)
    HS-            <=> H+ + S--              K4  (standard aqueous chemistry)
    MDEA + H2O     <=> MDEAH+ + OH-          Kam (apparent, NeqSim)
    CO2(aq)        -> p_CO2                  H_CO2 (Versteeg & van Swaaij, 1988)
    H2S(aq)        -> p_H2S                  Lambda (apparent lumped constant,
                                             fitted to Jou-Mather-Otto 1982)

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
solubility data set NeqSim uses for its MDEA model.)

Kam (apparent MDEA dissociation, mol/L): exp(-6.40 - 4210/T), the form NeqSim
fits to the Jou-Mather-Otto 1982 CO2 solubility data (NeqSim
``MDEA-amine-thermo`` documentation, "apparent MDEA dissociation constant").
CO2 regression anchors reproduced with this constant set (NeqSim's own):
313.15 K, 50 wt% MDEA (~4.36 mol/L): p_CO2 ~ 0.0093 bara at loading 0.10 and
~0.229 bara at loading 0.40 -- the module lands within 3% of both (tests).

K3/K4 (T-independent): pK1(H2S) = 7.05, pK2(H2S) = 12.92 -- GPSA Data Book /
Kohl & Nielsen standard aqueous H2S chemistry.  Their only role is the
molecular/bound split at fixed total sulfide, which is insensitive at amine
pH (a factor-2 shift in K3 moves the split <1%); the VLE-relevant temperature
dependence is carried entirely by the lumped sulfide constant below.

Lambda (apparent lumped H2S constant, Pa.m3/mol): the H2S chemistry reduces
to the proton transfer H2S + MDEA <=> MDEAH+ + HS- with K_eq = K3/Kam, so
p_H2S = (Lambda/Kam) [H+][HS-] and [H2S(aq)] = p Kam/(Lambda K3), where
Lambda = H_H2S/K_eq is the single fitted lumped constant (the ideal-chemistry
limit reads p = (H/K_eq) alpha^2 C/(1-alpha)).  Fitting Lambda at the
Jou-Mather-Otto 1982, 40 degC isotherm (4.28 kmol/m3 MDEA; points 0.0108 kPa at loading 0.01, 3.31 kPa at
0.165, 36.9 kPa at 0.453 -- as tabulated in the GASWORKS h2s-mdea-absorber
precedent, tests/test_equilibrium.py::test_jou_mather_anchors) gives

    Lambda(313.15 K) = 24.37 Pa.m3/mol      (minimax over the three anchors)
    Lambda(T) = Lambda(313.15) exp(4570 (1/313.15 - 1/T))

with B = 4570 K the van 't Hoff temperature coefficient (heat of H2S absorption
in MDEA ~ 38 kJ/mol, Jou et al. / NeqSim ``AmineHeatOfAbsorption``).  The fitted
constant reproduces all three anchors within 2%; the apparent-constant route is
the Kent-Eisenberg method itself (fit apparent constants to measured VLE), so
no water-value Henry is claimed for the amine solution.

Validity window: absorber/regenerator service, ~290-400 K, amine molarity
~1-6 mol/L, loadings 0-1.5 mol acid gas/mol MDEA (the Jou data end at 1.08).
The linear-in-amine ideal-solution structure carries no loading- or
composition-dependent activity corrections beyond the fitted constants.

Solve method: the charge balance is monotone in the hydrogen-ion activity
everywhere on the bracket, so both directions reduce to a 1-D root find on
log([H+]) with a hand-rolled Brent solver (no scipy -- dependency-light per
B-07 precedent).

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
    "Speciation",
    "amine_molarity",
    "equilibrium_loadings",
    "equilibrium_partial_pressures",
]

_MAX_LOADING = 1.5
_LN_H_LO = -34.0
_LN_H_HI = 16.0


@dataclass(frozen=True)
class Speciation:
    """Liquid-phase speciation in mol/L plus the gas partial pressures in Pa."""

    h: float
    mdea: float
    mdeah: float
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


def _mdea_kam(T: float) -> float:
    """Apparent MDEA dissociation constant, mol/L (NeqSim fit to Jou 1982 CO2)."""
    return math.exp(-6.40 - 4210.0 / T)


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
_LAMBDA_REF = 24.37  # Pa.m3/mol, minimax fit to Jou-Mather-Otto 1982 anchors
_H2S_VANTHOFF_B = 4570.0  # K


def _h2s_apparent_lambda(T: float) -> float:
    """Lumped apparent H2S constant H/K_eq, Pa.m3/mol (fitted, see module doc)."""
    return _LAMBDA_REF * math.exp(_H2S_VANTHOFF_B * (1.0 / _LAMBDA_REF_T - 1.0 / T))


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


def _charge_residual_ln_h(ln_h: float, T: float, C_A: float, C_co2: float, C_h2s: float) -> float:
    """Forward residual (loadings fixed): cations - anions, mol/L.

    ``C_A``/``C_co2``/``C_h2s`` are the total amine/CO2/H2S liquid-phase
    molarities in mol/L.  Strictly increasing in [H+].
    """
    h = math.exp(ln_h)
    a1, a2, aw, aam = _co2_k1(T), _co2_k2(T), _water_kw(T), _mdea_kam(T)
    a3, a4 = _h2s_k3(T), _h2s_k4(T)
    oh = aw / h
    denom = 1.0 + a1 / h + a1 * a2 / (h * h)
    co2_free = C_co2 / denom
    hco3 = a1 * co2_free / h
    co3 = a2 * hco3 / h
    hs = C_h2s * a3 * h / (h * h + a3 * h + a3 * a4)
    s2 = a4 * hs / h
    mdeah = C_A * h / (h + aam)
    return mdeah + h - (oh + hco3 + 2.0 * co3 + hs + 2.0 * s2)


def _pressure_residual_ln_h(ln_h: float, T: float, C_A: float, co2_free: float, h2s_free: float) -> float:
    """Inverse residual (partial pressures fixed): cations - anions, mol/L.

    ``co2_free``/``h2s_free`` are fixed by Henry's law at the given partial
    pressures.  Strictly increasing in [H+].
    """
    h = math.exp(ln_h)
    a1, a2, aw, aam = _co2_k1(T), _co2_k2(T), _water_kw(T), _mdea_kam(T)
    a3, a4 = _h2s_k3(T), _h2s_k4(T)
    hco3 = a1 * co2_free / h
    co3 = a2 * hco3 / h
    hs = a3 * h2s_free / h
    s2 = a4 * hs / h
    oh = aw / h
    mdeah = C_A * h / (h + aam)
    return mdeah + h - (oh + hco3 + 2.0 * co3 + hs + 2.0 * s2)


def _speciate_from_loadings(T: float, C_A: float, C_co2: float, C_h2s: float) -> Speciation:
    a1, a2, aam = _co2_k1(T), _co2_k2(T), _mdea_kam(T)
    a3, a4 = _h2s_k3(T), _h2s_k4(T)
    fn: Callable[[float], float] = partial(_charge_residual_ln_h, T=T, C_A=C_A, C_co2=C_co2, C_h2s=C_h2s)
    ln_h = _brent_root(fn, _LN_H_LO, _LN_H_HI)
    h = math.exp(ln_h)
    denom = 1.0 + a1 / h + a1 * a2 / (h * h)
    co2_free = C_co2 / denom
    hco3 = a1 * co2_free / h
    co3 = a2 * hco3 / h
    hs = C_h2s * a3 * h / (h * h + a3 * h + a3 * a4)
    s2 = a4 * hs / h
    h2s_free = C_h2s - hs - s2
    mdeah = C_A * h / (h + aam)
    return Speciation(
        h=h,
        mdea=C_A - mdeah,
        mdeah=mdeah,
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
        p_h2s=_h2s_apparent_lambda(T) / aam * h * hs * 1000.0,
    )


def _speciate_from_pressures(T: float, C_A: float, p_co2: float, p_h2s: float) -> Speciation:
    a1, a2, aam = _co2_k1(T), _co2_k2(T), _mdea_kam(T)
    a3, a4 = _h2s_k3(T), _h2s_k4(T)
    # Inverse Henry/lumped laws: p [Pa] / H [Pa.m3/mol] gives mol/m3; the
    # speciation balance works in mol/L, hence the 1000.
    co2_free = p_co2 / _henry_co2(T) / 1000.0
    h2s_free = p_h2s * aam / (_h2s_apparent_lambda(T) * a3) / 1000.0
    fn: Callable[[float], float] = partial(
        _pressure_residual_ln_h, T=T, C_A=C_A, co2_free=co2_free, h2s_free=h2s_free
    )
    ln_h = _brent_root(fn, _LN_H_LO, _LN_H_HI)
    h = math.exp(ln_h)
    hco3 = a1 * co2_free / h
    co3 = a2 * hco3 / h
    hs = a3 * h2s_free / h
    s2 = a4 * hs / h
    mdeah = C_A * h / (h + aam)
    return Speciation(
        h=h,
        mdea=C_A - mdeah,
        mdeah=mdeah,
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
    T: float, amine_molarity_mol_m3: float, co2_loading: float, h2s_loading: float
) -> tuple[float, float]:
    """Equilibrium (p_CO2, p_H2S) in Pa over MDEA solution at fixed loadings.

    Args:
        T: temperature in K.
        amine_molarity_mol_m3: total MDEA molarity of the liquid phase, mol/m3.
        co2_loading: total CO2 loading (mol CO2 per mol MDEA, free + bound).
        h2s_loading: total H2S loading, same basis.
    """
    _validate_common(T, amine_molarity_mol_m3)
    _validate_loadings(co2_loading, h2s_loading)
    C_A = amine_molarity_mol_m3 / 1000.0
    sp = _speciate_from_loadings(T, C_A, co2_loading * C_A, h2s_loading * C_A)
    return sp.p_co2, sp.p_h2s


def equilibrium_loadings(
    T: float, amine_molarity_mol_m3: float, p_co2: float, p_h2s: float
) -> tuple[float, float]:
    """Equilibrium (CO2, H2S) loadings (mol/mol MDEA) at fixed partial pressures.

    Args:
        T: temperature in K.
        amine_molarity_mol_m3: total MDEA molarity of the liquid phase, mol/m3.
        p_co2: CO2 partial pressure over the solution, Pa absolute.
        p_h2s: H2S partial pressure over the solution, Pa absolute.
    """
    _validate_common(T, amine_molarity_mol_m3)
    if p_co2 < 0.0 or p_h2s < 0.0:
        raise ValueError(f"partial pressures must be non-negative, got p_co2={p_co2}, p_h2s={p_h2s}")
    C_A = amine_molarity_mol_m3 / 1000.0
    sp = _speciate_from_pressures(T, C_A, p_co2, p_h2s)
    total_co2 = sp.co2_free + sp.hco3 + sp.co3
    total_h2s = sp.h2s_free + sp.hs + sp.s2
    return total_co2 / C_A, total_h2s / C_A


def amine_molarity(x_mdea: float, phase_mw_g_mol: float, phase_density_kg_m3: float) -> float:
    """MDEA molarity of a liquid phase, mol/m3, from its flashed composition.

    Args:
        x_mdea: MDEA mole fraction within the liquid phase.
        phase_mw_g_mol: mole-fraction-weighted molecular weight of the phase, g/mol.
        phase_density_kg_m3: mass density of the phase, kg/m3.
    """
    if x_mdea <= 0.0:
        raise ValueError(f"no MDEA in the liquid phase (x_mdea={x_mdea}); not an amine solvent")
    if phase_density_kg_m3 <= 0.0 or phase_mw_g_mol <= 0.0:
        raise ValueError(
            f"non-positive phase density ({phase_density_kg_m3} kg/m3) or MW ({phase_mw_g_mol} g/mol)"
        )
    return x_mdea * phase_density_kg_m3 / phase_mw_g_mol * 1000.0


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
                "the Jou-Mather-Otto data end at 1.08)"
            )
