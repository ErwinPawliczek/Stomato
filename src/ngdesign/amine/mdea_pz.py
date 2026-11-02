"""CO2 equilibrium over aqueous MDEA + piperazine (Bishnoi & Rochelle's reaction set).

Reactions, on the mole-fraction scale, ln K = A + B/T + C ln T (constants in
``data/thermo_params/amine/mdea_pz.yaml``):

    CO2 + 2 H2O      <=> H3O+ + HCO3-        K_hco3
    HCO3- + H2O      <=> H3O+ + CO3--        K_co3
    2 H2O            <=> H3O+ + OH-          K_w
    PZH+ + H2O       <=> PZ + H3O+           K_pzh
    PZ + CO2 + H2O   <=> PZCOO- + H3O+       K_pzcoo
    H+PZCOO- + H2O   <=> PZCOO- + H3O+       K_hpzcoo
    PZCOO- + CO2 + H2O <=> PZ(COO-)2 + H3O+  K_dicarb
    MDEAH+ + H2O     <=> MDEA + H3O+         K_mdea

with p_CO2 = H x_CO2. Bishnoi regressed these on an electrolyte-NRTL liquid; here every
activity coefficient is one, as Kent-Eisenberg treats its apparent constants. That
loses the composition slope: against Bishnoi's own 313 K and 343 K data the pressure
runs from 0.23 to 2.7 times the measurement, which the catalogue row records.

The solve is the Kent-Eisenberg shape: charge balance as a root in ln [H3O+], with the
free CO2 a nested root of the carbon balance.
"""

from __future__ import annotations

import math
from functools import cache
from typing import Any, cast

import yaml

from ngdesign.amine.roots import brent_root
from ngdesign.data import DATA_DIR

_LN_H_LO = -40.0
_LN_H_HI = -5.0
_LN_CO2_LO = -80.0


@cache
def _table() -> dict[str, Any]:
    path = DATA_DIR / "thermo_params" / "amine" / "mdea_pz.yaml"
    return cast(dict[str, Any], yaml.safe_load(path.read_text()))


def _k(name: str, T: float) -> float:
    a, b, c = _table()["reactions"][name]
    return math.exp(float(a) + float(b) / T + float(c) * math.log(T))


def _henry_co2(T: float) -> float:
    """Henry constant of CO2 in water, Pa per mole fraction (Bishnoi Table 5.4b)."""
    a, b, c, d = _table()["henry_co2"]
    return math.exp(float(a) + float(b) / T + float(c) * math.log(T) + float(d) * T)


def mdea_pz_p_co2(T: float, n_water: float, n_mdea: float, n_pz: float, n_co2: float) -> float:
    """Equilibrium CO2 partial pressure (Pa) over a liquid of these mole amounts."""
    if n_co2 <= 0.0:
        return 0.0
    total = n_water + n_mdea + n_pz + n_co2
    x_w, mdea_t, pz_t, carbon_t = n_water / total, n_mdea / total, n_pz / total, n_co2 / total
    k_hco3, k_co3, k_w = _k("hco3", T), _k("co3", T), _k("water", T)
    k_pzh, k_pzcoo, k_hpzcoo = _k("pzh", T), _k("pzcoo", T), _k("hpzcoo", T)
    k_dicarb, k_mdea = _k("dicarbamate", T), _k("mdeah", T)

    def species(h: float, co2: float) -> tuple[float, float, float, float, float, float]:
        """(HCO3-, CO3--, PZ, PZCOO-, H+PZCOO-, PZ(COO-)2) at this H3O+ and free CO2."""
        hco3 = k_hco3 * x_w * x_w * co2 / h
        co3 = k_co3 * x_w * hco3 / h
        ratio = k_pzcoo * x_w * co2 / h
        step = k_dicarb * x_w * co2 / h
        pz = pz_t / (1.0 + h / (k_pzh * x_w) + ratio * (1.0 + h / (k_hpzcoo * x_w) + step))
        pzcoo = ratio * pz
        return hco3, co3, pz, pzcoo, pzcoo * h / (k_hpzcoo * x_w), step * pzcoo

    def free_co2(h: float) -> float:
        def carbon(ln_co2: float) -> float:
            co2 = math.exp(ln_co2)
            hco3, co3, _pz, pzcoo, hpzcoo, dicarb = species(h, co2)
            return co2 + hco3 + co3 + pzcoo + hpzcoo + 2.0 * dicarb - carbon_t

        return math.exp(brent_root(carbon, _LN_CO2_LO, math.log(carbon_t) + 1.0))

    def charge(ln_h: float) -> float:
        h = math.exp(ln_h)
        hco3, co3, pz, pzcoo, _hpzcoo, dicarb = species(h, free_co2(h))
        mdeah = mdea_t - mdea_t / (1.0 + h / (k_mdea * x_w))
        pzh = pz * h / (k_pzh * x_w)
        return h + mdeah + pzh - k_w * x_w * x_w / h - hco3 - 2.0 * co3 - pzcoo - 2.0 * dicarb

    h = math.exp(brent_root(charge, _LN_H_LO, _LN_H_HI))
    return _henry_co2(T) * free_co2(h)
