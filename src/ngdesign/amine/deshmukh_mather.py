"""CO2 + H2S over MDEA + sulfolane + water: MacGregor's modified Deshmukh-Mather model.

Source: MacGregor, R. J., "Equilibrium solubility of hydrogen sulphide and carbon dioxide in
a mixed solvent", MSc thesis, University of Alberta, 1988 (constants and provenance in
``data/thermo_params/amine/sulfinol_macgregor1988.yaml``). Sulfolane + water are lumped as
the solvent (pp. 52-53); MDEA is a solute. Molalities m are mol per kg (water + sulfolane).

Reactions (molality-scale K, activities a = gamma m; water activity = its mole fraction,
Deshmukh & Mather's assumption, thesis p. 19):

    MDEA + H2O      = MDEAH+ + OH-     K_mdea   ("K(MDEA prot.)", Table 6.4; see below)
    H2S             = H+ + HS-         K_h2s    (6.6, Table 6.4)
    CO2 + H2O       = HCO3- + H+       K_co2    (6.7, Table 6.4)
    HCO3-           = CO3-- + H+       K_hco3   (6.8, Table 6.4)
    H2O             = H+ + OH-         K_w      (aqueous; Edwards et al. 1978, kent_eisenberg)
    HS-             = H+ + S--         K_hs     (aqueous; kent_eisenberg's pK2 12.92)

K(MDEA prot.) is read as the protonation (base) constant of MDEA, a_MDEAH+ a_OH- /
(a_MDEA a_w). The thesis writes reaction 6.5 as MDEAH+ = MDEA + H+, but read that way the
printed 1.387e-6 (pKa 5.9) leaves MDEA almost unprotonated at the solution pH and the model
overpredicts the thesis's own fitted single-gas data (Tables 5.3 and 5.5, 40 C) by factors of
2.6 to 105 (CO2) and 1.25 to 35 (H2S), measured 2026-11-09. Read as a base constant it gives
K_w/K = 2.1e-8 (pKa 7.7, below aqueous MDEA's ~8.2 at 40 C as a lower-permittivity solvent
should) and reproduces those fitted tables to a mean |ln p| of 0.55 (CO2, 30 points, biased
high) and 0.29 (H2S, 21 points). The thesis's own aqueous-MDEA fits ran at a mean |ln p|
of about 0.5 for CO2 (Table 6.3, objective 27-37 over 58 runs).

"The remaining ionic equilibria were described using aqueous system equilibrium constants"
(p. 65): K_w and K_hs are the repo's cited aqueous values, reused from
:mod:`ngdesign.amine.kent_eisenberg`.

Activity coefficients, extended Debye-Hueckel (eq. 6.2, p. 57; ion size term 1):

    ln gamma_i = -A z_i^2 sqrt(I) / (1 + sqrt(I)) + sum_k beta_ik m_k,   I = 1/2 sum m_i z_i^2

with beta from Table 6.2's Chakravarty (1985) column (the set the thesis adopts, p. 61). A is
the ln-base Debye-Hueckel slope A = 3 A_phi(T, d, eps) (:func:`ngdesign.amine.enrtl.debye_huckel_a_phi`)
on the mixed-solvent dielectric constant of eq. 6.3 (p. 58):

    eps = x_s eps_s + x_w eps_w - 4.341 x_w - 70.940 x_w^2 + 74.683 x_w^3

(x on the water + sulfolane basis; eps_w IAPWS via the thermo databank, eps_s cited per
isotherm in the parameter file). The density in A is pure water's: the thesis names the
dielectric constant as the solvent property modified for the mixed solvent (pp. 20, 57), and
its pages defining A (nomenclature, pp. 78-79) are absent from the scan.

Fugacity (eq. 2.6 with the Poynting factor dropped, p. 56): f_i = gamma_i m_i H_i, H the
mixed-solvent Henry constant (MPa kg/mol, Table 6.4).

The constants exist at 40 and 100 C only and the model is never evaluated between them:
:func:`fugacities` accepts T within :data:`T_MATCH_K` of 313.15 K or 373.15 K and refuses
anything else; the 100 C isotherm also refuses until a cited sulfolane permittivity at
373.15 K is on file. The Henry constant of H2S (0.5035 MPa kg/mol at 40 C) was raised by
hand by the author to fit the high-loading H2S data (p. 66).

Solve: at fixed gammas every species is explicit in [H+] (carbon and sulfur balances are
linear in the free molecular gas), so the charge balance is one bracketed root in ln[H+]
(:func:`ngdesign.amine.roots.brent_root`); the gammas are a damped outer fixed point.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import cache
from typing import Any, cast

import numpy as np
import yaml

from ngdesign.amine.enrtl import debye_huckel_a_phi, water_density_permittivity
from ngdesign.amine.kent_eisenberg import _h2s_k4, _water_kw
from ngdesign.amine.roots import brent_root
from ngdesign.data import DATA_DIR

__all__ = [
    "T_MATCH_K",
    "DeshmukhMatherError",
    "Speciation",
    "dielectric_constant",
    "fugacities",
    "isotherms",
    "thesis_solvent",
]

#: Temperatures (K) whose constants exist, and the match band around them, K. The thesis
#: isotherms are 40 and 100 C; 0.01 K only absorbs the C -> K rounding of a caller.
T_MATCH_K = 0.01

_LN_H_LO = -60.0
_LN_H_HI = 5.0
_FD_STEP = 1e-7
_MAX_LN_GAMMA_STEP = 2.0
_GAMMA_TOL = 1e-10
#: Brent xtol on ln[H+]: the gamma map inherits the root noise times dm/dln h, so it sits
#: below the gamma tolerance at the stripped-solvent molalities a saturation scan visits.
_LN_H_XTOL = 1e-15
_GAMMA_MAX_ITER = 100

#: Charges of the true species.
_CHARGE = {
    "H+": 1,
    "MDEAH+": 1,
    "OH-": -1,
    "HCO3-": -1,
    "CO3--": -2,
    "HS-": -1,
    "S--": -2,
    "MDEA": 0,
    "CO2": 0,
    "H2S": 0,
}


class DeshmukhMatherError(ValueError):
    """The state lies outside the model's constants (temperature or missing constant)."""


@dataclass(frozen=True)
class Speciation:
    """Converged true-species molalities (mol/kg solvent), ln gammas and fugacities (Pa)."""

    molality: dict[str, float]
    ln_gamma: dict[str, float]
    f_co2: float
    f_h2s: float


@cache
def _table() -> dict[str, Any]:
    path = DATA_DIR / "thermo_params" / "amine" / "sulfinol_macgregor1988.yaml"
    return cast(dict[str, Any], yaml.safe_load(path.read_text()))


def thesis_solvent() -> dict[str, float]:
    """The thesis solvent (Table 1.1): sulfolane:water mass ratio and MDEA molality, mol/kg."""
    wt = _table()["solvent"]["wt_percent"]
    return {
        "sulfolane_water_mass_ratio": float(wt["sulfolane"]) / float(wt["water"]),
        "mdea_molality_mol_kg": float(_table()["solvent"]["mdea_molality_mol_kg"]),
    }


def isotherms() -> tuple[float, ...]:
    """The temperatures (K) the thesis gives constants for."""
    return tuple(float(t) for t in _table()["isotherms"])


def _constants(T: float) -> dict[str, float]:
    for t_iso, consts in _table()["isotherms"].items():
        if abs(T - float(t_iso)) <= T_MATCH_K:
            if consts.get("eps_sulfolane") is None:
                raise DeshmukhMatherError(
                    f"no cited sulfolane permittivity at {float(t_iso)} K: the {float(t_iso)} K isotherm "
                    "of MacGregor 1988 cannot be evaluated (eq. 6.3 needs it)"
                )
            return {k: float(v) for k, v in consts.items()}
    raise DeshmukhMatherError(
        f"T={T} K: MacGregor 1988 gives constants at {', '.join(f'{t:g}' for t in isotherms())} K only "
        f"(match band +/-{T_MATCH_K} K); the model does not interpolate between isotherms"
    )


@cache
def _beta() -> dict[tuple[str, str], float]:
    out: dict[tuple[str, str], float] = {}
    for a, b, value in _table()["beta"]:
        out[(a, b)] = out[(b, a)] = float(value)
    return out


def dielectric_constant(T: float, x_water: float) -> float:
    """Mixed-solvent relative permittivity, eq. 6.3 (p. 58); x_water on the water + sulfolane basis."""
    eps_s = _constants(T)["eps_sulfolane"]
    _d, eps_w = water_density_permittivity(T)
    c1, c2, c3 = (float(c) for c in _table()["dielectric_excess"])
    excess = c1 * x_water + c2 * x_water**2 + c3 * x_water**3
    return (1.0 - x_water) * eps_s + x_water * eps_w + excess


def fugacities(
    T: float, m_mdea: float, alpha_co2: float, alpha_h2s: float, x_water_solvent: float, a_water: float
) -> Speciation:
    """Speciate the loaded solvent and return the acid-gas fugacities (Pa).

    ``m_mdea``: MDEA molality, mol/kg (water + sulfolane); ``alpha_*``: loadings, mol gas per
    mol MDEA; ``x_water_solvent``: water mole fraction on the water + sulfolane basis (for
    eq. 6.3); ``a_water``: water activity (its liquid mole fraction, p. 19).
    """
    k = _constants(T)
    if m_mdea <= 0.0:
        raise DeshmukhMatherError("the model needs MDEA: its constants were regressed on the amine solvent")
    d_w, _eps_w = water_density_permittivity(T)
    a_dh = 3.0 * debye_huckel_a_phi(T, d_w, dielectric_constant(T, x_water_solvent))
    k_w, k_hs = _water_kw(T), _h2s_k4(T)
    m_c, m_s = alpha_co2 * m_mdea, alpha_h2s * m_mdea
    beta = _beta()

    def species(h: float, g: dict[str, float]) -> dict[str, float]:
        oh = k_w * a_water / (g["H+"] * g["OH-"] * h)
        # MDEA + H2O = MDEAH+ + OH-: K_mdea = a_MDEAH+ a_OH- / (a_MDEA a_w) (module docstring).
        r_a = k["k_mdea"] * g["MDEA"] * a_water / (g["MDEAH+"] * g["OH-"] * oh)
        r1 = k["k_co2"] * a_water * g["CO2"] / (g["H+"] * g["HCO3-"] * h)
        r2 = k["k_hco3"] * g["HCO3-"] / (g["H+"] * g["CO3--"] * h)
        s1 = k["k_h2s"] * g["H2S"] / (g["H+"] * g["HS-"] * h)
        s2 = k_hs * g["HS-"] / (g["H+"] * g["S--"] * h)
        co2 = m_c / (1.0 + r1 + r1 * r2)
        h2s = m_s / (1.0 + s1 + s1 * s2)
        return {
            "H+": h,
            "MDEAH+": m_mdea * r_a / (1.0 + r_a),
            "MDEA": m_mdea / (1.0 + r_a),
            "OH-": oh,
            "CO2": co2,
            "HCO3-": co2 * r1,
            "CO3--": co2 * r1 * r2,
            "H2S": h2s,
            "HS-": h2s * s1,
            "S--": h2s * s1 * s2,
        }

    def solve(g: dict[str, float]) -> dict[str, float]:
        def charge(ln_h: float) -> float:
            m = species(math.exp(ln_h), g)
            return sum(_CHARGE[s] * v for s, v in m.items())

        return species(math.exp(brent_root(charge, _LN_H_LO, _LN_H_HI, xtol=_LN_H_XTOL)), g)

    names = tuple(_CHARGE)

    def gmap(x: list[float]) -> tuple[list[float], dict[str, float]]:
        """G(ln gamma): eq. 6.2 evaluated at the speciation solved with ln gamma = x."""
        m = solve({sp: math.exp(v) for sp, v in zip(names, x, strict=True)})
        root_i = math.sqrt(0.5 * sum(v * _CHARGE[sp] ** 2 for sp, v in m.items()))
        dh = a_dh * root_i / (1.0 + root_i)
        return [-dh * _CHARGE[sp] ** 2 + sum(beta.get((sp, o), 0.0) * m[o] for o in m) for sp in names], m

    # Newton on F(x) = G(x) - x with a forward-difference Jacobian and step halving on |F|:
    # plain substitution stalls or cycles on the strongly coupled beta terms of a
    # solvent-stripped liquid (the molalities a saturation scan visits).
    x = [0.0] * len(names)
    g, m = gmap(x)
    f = [gi - xi for gi, xi in zip(g, x, strict=True)]
    norm = max(abs(v) for v in f)
    for _ in range(_GAMMA_MAX_ITER):
        if norm < _GAMMA_TOL:
            break
        jac = np.empty((len(names), len(names)))
        for j in range(len(names)):
            xp = list(x)
            xp[j] += _FD_STEP
            gp, _m = gmap(xp)
            for i in range(len(names)):
                jac[i, j] = (gp[i] - xp[i] - f[i]) / _FD_STEP
        dx = np.linalg.solve(jac, -np.asarray(f))
        lam = min(1.0, _MAX_LN_GAMMA_STEP / max(float(np.max(np.abs(dx))), 1e-300))
        while True:
            xt = [xi + lam * float(d) for xi, d in zip(x, dx, strict=True)]
            try:
                gt, mt = gmap(xt)
            except ValueError:  # charge balance unbracketed at the trial gammas: shorten
                nt = math.inf
            else:
                ft = [gi - xi for gi, xi in zip(gt, xt, strict=True)]
                nt = max(abs(v) for v in ft)
            if nt < norm:
                break
            lam *= 0.5
            if lam < 1e-8:
                raise DeshmukhMatherError(f"activity-coefficient Newton step failed at T={T} K")
        x, f, norm, m = xt, ft, nt, mt
    else:
        raise DeshmukhMatherError(f"activity-coefficient fixed point did not converge at T={T} K")
    ln_g = dict(zip(names, x, strict=True))
    mpa = 1e6
    f_co2 = k["h_co2_mpa_kg_mol"] * mpa * math.exp(ln_g["CO2"]) * m["CO2"]
    f_h2s = k["h_h2s_mpa_kg_mol"] * mpa * math.exp(ln_g["H2S"]) * m["H2S"]
    return Speciation(molality=m, ln_gamma=ln_g, f_co2=f_co2, f_h2s=f_h2s)
