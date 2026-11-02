"""Fluid catalytic cracker: yield table (R0) and four-lump riser kinetics (R1).

No constant here is a package default.  Published FCC yield correlations are
chart-based (Gary, Handwerk & Kaiser, *Petroleum Refining*, 5th ed., §6.12,
Figs. 6.17-6.28) and lumped rate constants are specific to a feed and catalyst,
so the user supplies both; a missing value is a typed refusal.  The form of the
kinetics is cited, the numbers are the user's:

R0 reads mass yields from a user table against conversion, wt% on feed, where
conversion = 100 - LCO - slurry (the wt basis of the usual FCC definition; the
table is checked against it).  Interpolation is linear, which keeps the yields
summing to 100 between nodes; there is no extrapolation.

R1 is the Weekman & Nace (AIChE J. 16 (1970) 397) gas-oil lump extended to four
lumps by Lee, Chen & Huang (1989), integrated over riser contact time t, with
y1 gas oil, y2 gasoline, y3 gases, y4 coke as mass fractions:

    dy1/dt = -(k12 + k13 + k14)*y1**2*phi
    dy2/dt = (k12*y1**2 - (k23 + k24)*y2)*phi
    dy3/dt = (k13*y1**2 + k23*y2)*phi
    dy4/dt = (k14*y1**2 + k24*y2)*phi

Second order in gas oil, first order in gasoline, k_ij = k0*exp(-Ea/(R*T)), and
Weekman's time-on-stream decay phi = exp(-alpha*t).  With k14 = k24 = 0 this is
the Weekman three-lump model with y3 holding gases plus coke.  The k_ij carry
the catalyst holdup of the operating catalyst-to-oil ratio; a published set on
another basis must be converted by the user.

Heat balance (R1, unless ``isothermal_T_K`` is given): regenerated catalyst at
T_regen meets the feed at T_mix, from (C/O)*cp_cat*(T_regen - T_mix) =
h_feed(T_mix) - h_feed(T_feed), with thermo enthalpies per kg so vaporization is
included; the riser is then adiabatic, dT/dt = dH_c*(dy1/dt)/(C/O*cp_cat + cp_oil),
with dH_c the heat of cracking per kg converted.  As in the pfr, the exact
closure owns T_out: (C/O)*cp_cat*(T_regen - T_out) = sum h_out(T_out) - h_feed +
X*dH_c.  The regenerator is not solved: T_regen is an input, and the coke-burn
heat against the catalyst heat is reported as ``regenerator_residual_W``.

All lumps are mass-only pseudo-components, so the element ledger is empty and
the duty is sensible-only (flagged; issue #222).  Their Tb and sg are nominal
carriers for the flash, not correlation constants.  A feed species with a formula
is refused, because its atoms could not be accounted for.  All SI.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import brentq

from ngdesign.contracts import PhaseKind, StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.data import component_record, register_pseudo
from ngdesign.data.formation import MissingFormationData, atomic_composition
from ngdesign.units._physics.kinetics import R, yield_shift
from ngdesign.units.balance import SENSIBLE_ONLY_FLAG

register_pseudo("fcc_vgo", "FCC gas-oil feed carrier (example)", Tb=700.0, sg=0.90)
register_pseudo("fcc_dry_gas", "FCC dry gas carrier lump", Tb=180.0, sg=0.40)
register_pseudo("fcc_lpg", "FCC LPG carrier lump", Tb=250.0, sg=0.56)
register_pseudo("fcc_gasoline", "FCC gasoline carrier lump", Tb=390.0, sg=0.75)
register_pseudo("fcc_lco", "FCC light cycle oil carrier lump", Tb=560.0, sg=0.93)
register_pseudo("fcc_slurry", "FCC slurry carrier lump", Tb=720.0, sg=1.02)
register_pseudo("fcc_coke", "FCC coke on catalyst, mass only", Tb=1100.0, sg=0.95)

#: Outlet port, its table/yield key and its carrier lump.
_PRODUCTS: tuple[tuple[str, str, str], ...] = (
    ("dry_gas_out", "dry_gas", "fcc_dry_gas"),
    ("lpg_out", "lpg", "fcc_lpg"),
    ("gasoline_out", "gasoline", "fcc_gasoline"),
    ("lco_out", "lco", "fcc_lco"),
    ("slurry_out", "slurry", "fcc_slurry"),
    ("coke_out", "coke", "fcc_coke"),
)

#: The five four-lump rate paths.
_PATHS = (
    "gasoil_to_gasoline",
    "gasoil_to_gases",
    "gasoil_to_coke",
    "gasoline_to_gases",
    "gasoline_to_coke",
)

#: Closure of a table row, wt%.
_TABLE_TOL = 1.0e-6


class FccSpecError(ValueError):
    """Raised when FCC parameters are missing or inconsistent."""


def _number(params: Mapping[str, Any], key: str, *, positive: bool = True) -> float:
    if key not in params:
        raise FccSpecError(f"{key} is required: the FCC has no default for it")
    value = float(params[key])
    if positive and value <= 0.0:
        raise FccSpecError(f"{key} must be > 0")
    return value


def _fraction(params: Mapping[str, Any], key: str) -> float:
    value = _number(params, key, positive=False)
    if not 0.0 <= value <= 1.0:
        raise FccSpecError(f"{key} {value} is outside [0, 1]")
    return value


def _feed_lumps(feed: StreamState) -> dict[str, float]:
    """The feed flows, refusing a species with a formula (its atoms would vanish)."""
    flows = {cid: n for cid, n in feed.component_flows().items() if n > 0.0}
    if not flows:
        raise FccSpecError("feed_in carries no components")
    for cid in flows:
        try:
            atomic_composition(cid)
        except MissingFormationData:
            continue
        raise FccSpecError(
            f"feed species {cid!r} has a formula; FCC lumps are mass-only pseudo-components, "
            "so the feed must be a pseudo slate (elemental characterisation is issue #222)"
        )
    return flows


def _outlets(
    flows: dict[str, float], yields: Mapping[str, float], t_out: float, p_out: float, thermo: Thermo
) -> tuple[dict[str, StreamState], float]:
    """Product streams from mass yields (fractions, sum 1) and their enthalpy flow."""
    keys = [key for _, key, _ in _PRODUCTS]
    lumps = [lump for _, _, lump in _PRODUCTS]
    n_out = yield_shift(flows, list(flows), [yields[k] for k in keys], lumps)
    outlets: dict[str, StreamState] = {}
    total = 0.0
    for port, _, lump in _PRODUCTS:
        state = thermo.flash_pt({lump: 1.0}, t_out, p_out, n_out[lump])
        outlets[port] = state
        total += state.enthalpy * state.molar_flow
    return outlets, total


def _mass_kg_s(flows: Mapping[str, float]) -> float:
    return math.fsum(n * float(component_record(cid)["mw"]) / 1000.0 for cid, n in flows.items())


class FccR0:
    """FCC at R0: user yield table against conversion."""

    inlet_ports: tuple[str, ...] = ("feed_in",)
    outlet_ports: tuple[str, ...] = tuple(port for port, _, _ in _PRODUCTS)

    def solve(
        self,
        inlets: Mapping[str, StreamState],
        params: Mapping[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        feed = inlets["feed_in"]
        flows = _feed_lumps(feed)
        table = params.get("yield_table")
        if table is None:
            raise FccSpecError(
                "yield_table is required: FCC yields are feed- and catalyst-specific and the "
                "published correlations are charts, so the package carries no default table"
            )
        conversion = _number(params, "conversion_wt_pct")
        t_out = _number(params, "T_out")
        p_out = _number(params, "P_out")
        grid = [float(x) for x in table.get("conversion_wt_pct", ())]
        if len(grid) < 2 or any(b <= a for a, b in zip(grid, grid[1:], strict=False)):
            raise FccSpecError("yield_table.conversion_wt_pct needs >= 2 strictly increasing points")
        columns: dict[str, Sequence[float]] = {}
        for _, key, _ in _PRODUCTS:
            name = f"{key}_wt_pct"
            if name not in table:
                raise FccSpecError(f"yield_table.{name} is required")
            columns[key] = [float(x) for x in table[name]]
            if len(columns[key]) != len(grid):
                raise FccSpecError(f"yield_table.{name} must have the same length as conversion_wt_pct")
            if min(columns[key]) < 0.0:
                raise FccSpecError(f"yield_table.{name} has a negative yield")
        for i, conv in enumerate(grid):
            row = math.fsum(columns[key][i] for key in columns)
            if abs(row - 100.0) > _TABLE_TOL:
                raise FccSpecError(f"yield_table row {i} sums to {row} wt%, not 100")
            unconverted = columns["lco"][i] + columns["slurry"][i]
            if abs(unconverted - (100.0 - conv)) > _TABLE_TOL:
                raise FccSpecError(
                    f"yield_table row {i}: LCO + slurry = {unconverted} wt% is not 100 - conversion"
                )
        if not grid[0] <= conversion <= grid[-1]:
            raise FccSpecError(
                f"conversion_wt_pct {conversion} is outside the table [{grid[0]}, {grid[-1]}]: "
                "no extrapolation"
            )
        yields = {key: float(np.interp(conversion, grid, col)) / 100.0 for key, col in columns.items()}
        outlets, h_out = _outlets(flows, yields, t_out, p_out, thermo)
        info = {f"{key}_wt_pct": 100.0 * value for key, value in yields.items()}
        info["conversion_wt_pct"] = conversion
        info[SENSIBLE_ONLY_FLAG] = 1.0
        return UnitResult(outlets=outlets, duty_W=h_out - feed.enthalpy * feed.molar_flow, info=info)

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """A test-only table, internally consistent, NOT published data."""
        feeds = {"feed_in": {"T": 800.0, "P": 3.0e5, "molar_flow": 1.0, "composition": {"fcc_vgo": 1.0}}}
        params: dict[str, Any] = {
            "conversion_wt_pct": 70.0,
            "T_out": 800.0,
            "P_out": 2.5e5,
            "yield_table": {
                "conversion_wt_pct": [60.0, 80.0],
                "dry_gas_wt_pct": [2.0, 4.0],
                "lpg_wt_pct": [10.0, 18.0],
                "gasoline_wt_pct": [44.0, 52.0],
                "lco_wt_pct": [28.0, 16.0],
                "slurry_wt_pct": [12.0, 4.0],
                "coke_wt_pct": [4.0, 6.0],
            },
        }
        return feeds, params


def riser_rhs(
    t: float, y: Sequence[float], k: Mapping[str, float], alpha: float
) -> tuple[float, float, float, float]:
    """The four-lump derivatives at contact time t (module docstring), mass fractions."""
    phi = math.exp(-alpha * t)
    y1, y2 = y[0], y[1]
    second = y1 * y1
    return (
        -(k["gasoil_to_gasoline"] + k["gasoil_to_gases"] + k["gasoil_to_coke"]) * second * phi,
        (k["gasoil_to_gasoline"] * second - (k["gasoline_to_gases"] + k["gasoline_to_coke"]) * y2) * phi,
        (k["gasoil_to_gases"] * second + k["gasoline_to_gases"] * y2) * phi,
        (k["gasoil_to_coke"] * second + k["gasoline_to_coke"] * y2) * phi,
    )


class FccR1:
    """FCC at R1: four-lump riser kinetics with a catalyst heat balance."""

    inlet_ports: tuple[str, ...] = FccR0.inlet_ports
    outlet_ports: tuple[str, ...] = FccR0.outlet_ports

    def solve(
        self,
        inlets: Mapping[str, StreamState],
        params: Mapping[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        feed = inlets["feed_in"]
        flows = _feed_lumps(feed)
        kinetics = params.get("kinetics")
        if kinetics is None:
            raise FccSpecError(
                "kinetics is required: lumped FCC rate constants are feed- and catalyst-specific, "
                "so the package carries none"
            )
        unknown = sorted(set(kinetics) - set(_PATHS))
        if unknown:
            raise FccSpecError(f"kinetics names unknown paths {unknown}; expected {list(_PATHS)}")
        arrhenius: dict[str, tuple[float, float]] = {}
        for path in _PATHS:
            if path not in kinetics:
                raise FccSpecError(f"kinetics.{path} is required (give k0_per_s 0 to switch it off)")
            arrhenius[path] = (
                _number(kinetics[path], "k0_per_s", positive=False),
                _number(kinetics[path], "Ea_J_mol", positive=False),
            )
        contact = _number(params, "contact_time_s")
        alpha = _number(params, "deactivation_alpha_per_s", positive=False)
        p_out = _number(params, "P_out")
        f_dry = _fraction(params, "dry_gas_fraction")
        f_lco = _fraction(params, "lco_fraction")
        isothermal = "isothermal_T_K" in params
        mass = _mass_kg_s(flows)
        z_feed = dict(feed.composition)

        cto = cp_cat = t_regen = d_h = hc = cp_oil = 0.0
        if isothermal:
            t_start = _number(params, "isothermal_T_K")
        else:
            cto = _number(params, "catalyst_to_oil")
            cp_cat = _number(params, "cp_cat_J_kgK")
            t_regen = _number(params, "T_regen_K")
            d_h = _number(params, "heat_of_cracking_J_kg", positive=False)
            hc = _number(params, "coke_heat_of_combustion_J_kg")
            h_feed = feed.enthalpy * feed.molar_flow

            def mix(t: float) -> float:
                state = thermo.flash_pt(z_feed, t, p_out, feed.molar_flow)
                return cto * cp_cat * mass * (t_regen - t) - (state.enthalpy * state.molar_flow - h_feed)

            if float(feed.T) >= t_regen or mix(float(feed.T)) * mix(t_regen) > 0.0:
                raise FccSpecError(f"T_regen_K {t_regen} cannot heat the feed from {feed.T} K")
            t_start = float(brentq(mix, float(feed.T), t_regen, xtol=1.0e-9, maxiter=100))
            props = thermo.phase_props(z_feed, t_start, p_out, PhaseKind.VAPOR)
            cp_oil = float(props.cp) * 1000.0 / float(props.molecular_weight)

        def rhs(t: float, state: np.ndarray) -> np.ndarray:
            temperature = float(state[4])
            k = {path: k0 * math.exp(-ea / (R * temperature)) for path, (k0, ea) in arrhenius.items()}
            dy = riser_rhs(t, state[:4].tolist(), k, alpha)
            dt = 0.0 if isothermal else d_h * dy[0] / (cto * cp_cat + cp_oil)
            return np.array([*dy, dt])

        sol = solve_ivp(
            rhs,
            (0.0, contact),
            np.array([1.0, 0.0, 0.0, 0.0, t_start]),
            method="LSODA",
            rtol=1.0e-9,
            atol=1.0e-11,
        )
        if not bool(sol.success):
            raise FccSpecError(f"riser integration failed: {sol.message}")
        y1, y2, y3, y4, t_ode = (float(v) for v in sol.y[:, -1])
        scale = y1 + y2 + y3 + y4  # exactly 1 up to the ODE tolerance
        y1, y2, y3, y4 = y1 / scale, y2 / scale, y3 / scale, y4 / scale
        yields = {
            "dry_gas": y3 * f_dry,
            "lpg": y3 * (1.0 - f_dry),
            "gasoline": y2,
            "lco": y1 * f_lco,
            "slurry": y1 * (1.0 - f_lco),
            "coke": y4,
        }
        converted = 1.0 - y1
        info: dict[str, float] = {f"{key}_wt_pct": 100.0 * value for key, value in yields.items()}
        info["conversion_wt_pct"] = 100.0 * converted
        info[SENSIBLE_ONLY_FLAG] = 1.0
        h_in = feed.enthalpy * feed.molar_flow
        if isothermal:
            outlets, h_out = _outlets(flows, yields, t_start, p_out, thermo)
            return UnitResult(outlets=outlets, duty_W=h_out - h_in, info=info)

        def closure(t: float) -> float:
            _, h = _outlets(flows, yields, t, p_out, thermo)
            return cto * cp_cat * mass * (t_regen - t) - (h - h_in) - mass * converted * d_h

        t_low = t_regen - 600.0
        if closure(t_low) * closure(t_regen) > 0.0:
            raise FccSpecError("the riser heat balance has no outlet temperature below T_regen_K")
        t_out = float(brentq(closure, t_low, t_regen, xtol=1.0e-9, maxiter=100))
        outlets, h_out = _outlets(flows, yields, t_out, p_out, thermo)
        catalyst_heat = cto * cp_cat * mass * (t_regen - t_out)
        coke_burn = mass * y4 * hc
        info.update(
            T_mix_K=t_start,
            T_out_K=t_out,
            T_closure_gap_K=t_out - t_ode,
            catalyst_heat_W=catalyst_heat,
            reaction_heat_W=mass * converted * d_h,
            coke_burn_heat_W=coke_burn,
            regenerator_residual_W=coke_burn - catalyst_heat,
        )
        return UnitResult(outlets=outlets, duty_W=h_out - h_in, info=info)

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Test-only kinetics and heat data, NOT published constants or defaults."""
        feeds = {"feed_in": {"T": 500.0, "P": 3.0e5, "molar_flow": 1.0, "composition": {"fcc_vgo": 1.0}}}
        params: dict[str, Any] = {
            "kinetics": {
                "gasoil_to_gasoline": {"k0_per_s": 300.0, "Ea_J_mol": 45000.0},
                "gasoil_to_gases": {"k0_per_s": 60.0, "Ea_J_mol": 50000.0},
                "gasoil_to_coke": {"k0_per_s": 20.0, "Ea_J_mol": 45000.0},
                "gasoline_to_gases": {"k0_per_s": 15.0, "Ea_J_mol": 60000.0},
                "gasoline_to_coke": {"k0_per_s": 2.0, "Ea_J_mol": 60000.0},
            },
            "contact_time_s": 3.0,
            "deactivation_alpha_per_s": 0.1,
            "catalyst_to_oil": 6.0,
            "cp_cat_J_kgK": 1150.0,
            "T_regen_K": 960.0,
            "heat_of_cracking_J_kg": 2.5e5,
            "coke_heat_of_combustion_J_kg": 3.3e7,
            "dry_gas_fraction": 0.2,
            "lco_fraction": 0.7,
            "P_out": 2.5e5,
        }
        return feeds, params
