"""R3 adapters: rate-based (non-equilibrium) packed absorber and reboiled stripper.

Plugin kind "unit", rows ``absorber`` and ``reboiled_stripper``, level R3 (adapters
registered through the catalogue YAML ``levels.R3``). Same ports as the rows' R0/R2.
The model is :mod:`ngdesign.units.column.rate_based` (Krishna-Taylor rate-based
segments, effective-diffusivity film model, Onda 1968 random-packing coefficients and
wetted area); its module docstring carries the equations and sources.

**Absorber** - ``n_stages`` packed segments of equal height (``packed_height_m /
n_stages``), lean solvent onto segment 1 (liquid side), feed gas under segment N
(vapour side). ``gas_out`` is the vapour leaving segment 1, ``rich_out`` the liquid leaving segment
N, each PH-flashed at its bulk-phase enthalpy (the bulk temperatures ``T^V_1``,
``T^L_N`` are in ``info``). ``duty_W`` is the boundary energy residual
``sum(n h)_out - sum(n h)_in`` (no exchanger exists), which is the solver's
convergence residual only (reported as ``info['energy_residual_W']``, as R2 reports
its own).

**Reboiled stripper** - ``n_stages`` counts the kettle (stage N, an equilibrium stage,
as condensers and reboilers are in the rate-based literature); ``n_stages - 1``
packed segments above it, the feed onto segment 1. One kettle spec from
``boilup_ratio``, ``bottoms_rate``, ``distillate_rate`` (mol/s) or ``reboiler_duty_W``
(the simultaneous Newton carries the duty as the kettle energy balance, so the duty
spec R2 refuses is solvable here). ``info['reboiler_duty_W']`` is the kettle's model
duty; ``duty_W`` is the boundary balance over the flashed outlets, and their
difference is ``info['energy_residual_W']``.

``transfer_factor`` (default 1) multiplies every film conductance and heat-transfer
coefficient; as it grows each segment reduces to an equilibrium stage, and the result
reduces to the R2 MESH column on the same stages (the tests' oracle).

Surface tension: the thermo contract carries none, so ``surface_tension_N_m`` (one
value for the column, as the ``column_internals`` R1 unit takes it) is a required
input to the Onda wetted-area equation.

Refusals are :class:`RateBasedSpecError` (a ValueError) naming the parameter.
All SI. Pure functions; no I/O; no global state.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo

from .rate_based import (
    KETTLE_SPECS,
    RateColumnSpec,
    RateProfile,
    murphree_vapour,
    solve_rate_based,
    split_feed,
)
from .rate_based_transport import PackingGeometry

_PACKING_KEYS = (
    "column_diameter_m",
    "packed_height_m",
    "nominal_size_m",
    "specific_area_m2_m3",
    "critical_surface_tension_N_m",
    "surface_tension_N_m",
)
_COMMON_KEYS = frozenset({"n_stages", "pressure_profile", "transfer_factor", *_PACKING_KEYS})


class RateBasedSpecError(ValueError):
    """Refusal: the rate-based (R3) column spec is invalid."""


def _positive(params: dict[str, Any], key: str, unit: str) -> float:
    v = params.get(key)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not float(v) > 0.0:
        raise RateBasedSpecError(f"{unit} R3 parameter {key!r} must be a positive number, got {v!r}")
    return float(v)


def _pressures(params: dict[str, Any], n: int, default: float, unit: str) -> tuple[float, ...]:
    raw = params.get("pressure_profile", default)
    if isinstance(raw, (list, tuple)):
        if len(raw) != n or any(
            isinstance(p, bool) or not isinstance(p, (int, float)) or p <= 0 for p in raw
        ):
            raise RateBasedSpecError(
                f"{unit} R3 pressure_profile must be {n} positive stage pressures, got {raw!r}"
            )
        return tuple(float(p) for p in raw)
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or raw <= 0:
        raise RateBasedSpecError(f"{unit} R3 pressure_profile must be positive, got {raw!r}")
    return (float(raw),) * n


def _n_stages(params: dict[str, Any], minimum: int, unit: str) -> int:
    n = params.get("n_stages")
    if isinstance(n, bool) or not isinstance(n, int) or n < minimum:
        raise RateBasedSpecError(f"{unit} R3 needs an integer n_stages >= {minimum}, got {n!r}")
    return n


def _geometry(params: dict[str, Any], n_segments: int, unit: str) -> tuple[PackingGeometry, float, float]:
    vals = {k: _positive(params, k, unit) for k in _PACKING_KEYS}
    factor = _positive(params, "transfer_factor", unit) if "transfer_factor" in params else 1.0
    geom = PackingGeometry(
        diameter_m=vals["column_diameter_m"],
        segment_height_m=vals["packed_height_m"] / n_segments,
        nominal_size_m=vals["nominal_size_m"],
        specific_area_m2_m3=vals["specific_area_m2_m3"],
        critical_surface_tension_N_m=vals["critical_surface_tension_N_m"],
    )
    return geom, vals["surface_tension_N_m"], factor


def _cids(*streams: StreamState) -> tuple[str, ...]:
    out: list[str] = []
    for s in streams:
        for cid in s.composition:
            if cid not in out:
                out.append(cid)
    return tuple(out)


def _state(
    thermo: Thermo, cids: tuple[str, ...], flows: np.ndarray, h_flow_W: float, P: float
) -> StreamState:
    """Outlet stream at (composition, P, H): a PH flash of the bulk phase's own enthalpy.

    A rate-based bulk phase may leave metastable (a vapour a little below its dew point
    when its film is colder than the interface); the outlet carries its composition,
    pressure and enthalpy exactly and the package places it at equilibrium, so the
    boundary energy balance closes on the stage model's enthalpies.
    """
    total = float(np.sum(flows))
    comp = {cid: float(max(f, 0.0)) for cid, f in zip(cids, flows, strict=True)}
    s = sum(comp.values())
    return thermo.flash_ph({k: v / s for k, v in comp.items()}, P, h_flow_W / total, total)


def _info(prof: RateProfile, spec: RateColumnSpec, thermo: Thermo) -> dict[str, float]:
    info: dict[str, float] = {
        "n_stages": float(len(prof.v)),
        "outer_iterations": float(prof.outer_iterations),
        "inner_iterations": float(prof.inner_iterations),
        "max_scaled_residual": prof.max_residual,
        "transfer_factor": spec.transfer_factor,
    }
    effs = murphree_vapour(thermo, prof, spec)
    in_range = 1.0
    kinds = prof.kinds
    top = 1 if spec.condenser is not None else 0
    r = 0  # index into the rate-stage lists (yi, xi, flux, energy_flux_W, diagnostics)
    for j in range(len(prof.v)):
        v, liq = prof.v[j], prof.liq[j]
        info[f"stage_{j}_V_mol_s"] = float(np.sum(v))
        info[f"stage_{j}_L_mol_s"] = float(np.sum(liq))
        info[f"stage_{j}_TV_K"] = prof.tv[j]
        info[f"stage_{j}_TL_K"] = prof.tl[j]
        info[f"stage_{j}_P_Pa"] = spec.pressures[j]
        for i, cid in enumerate(prof.cids):
            info[f"stage_{j}_y_{cid}"] = float(v[i] / np.sum(v))
            info[f"stage_{j}_x_{cid}"] = float(liq[i] / np.sum(liq))
        if kinds[j] in ("rate", "tray"):
            for cid, e in effs[j - top].items():
                info[f"stage_{j}_EMV_{cid}"] = e
        if kinds[j] == "rate":
            info[f"stage_{j}_TI_K"] = prof.ti[j]
            info[f"stage_{j}_energy_flux_W"] = prof.energy_flux_W[r]
            for i, cid in enumerate(prof.cids):
                info[f"stage_{j}_N_{cid}_mol_s"] = float(prof.flux[r][i])
                info[f"stage_{j}_yI_{cid}"] = float(prof.yi[r][i])
                info[f"stage_{j}_xI_{cid}"] = float(prof.xi[r][i])
            d = prof.diagnostics[r]
            for key in ("a_w_m2_m3", "Re_L", "Re_G", "h_V_W_m2K", "h_L_W_m2K"):
                info[f"stage_{j}_{key}"] = d[key]
            in_range = min(in_range, d["onda_in_range"])
            r += 1
    if r:
        info["onda_in_range"] = in_range
    return info


class AbsorberR3:
    """Rate-based packed absorber (feed-determined, no condenser or reboiler)."""

    inlet_ports = ("gas_in", "solvent_in")
    outlet_ports = ("gas_out", "rich_out")

    def solve(self, inlets: dict[str, StreamState], params: dict[str, Any], thermo: Thermo) -> UnitResult:
        gas, solvent = inlets.get("gas_in"), inlets.get("solvent_in")
        if gas is None or solvent is None:
            raise RateBasedSpecError("absorber R3 needs both gas_in and solvent_in")
        if gas.molar_flow <= 0.0 or solvent.molar_flow <= 0.0:
            raise RateBasedSpecError("absorber R3 refuses a zero-molar-flow inlet")
        unknown = sorted(set(params) - _COMMON_KEYS)
        if unknown:
            raise RateBasedSpecError(f"absorber R3 refuses unknown parameter(s) {unknown}")
        n = _n_stages(params, 1, "absorber")
        geom, sigma, factor = _geometry(params, n, "absorber")
        pressures = _pressures(params, n, gas.P, "absorber")
        cids = _cids(gas, solvent)
        spec = RateColumnSpec(
            cids=cids,
            pressures=pressures,
            n_rate=n,
            kettle=False,
            feeds=(split_feed(0, cids, solvent), split_feed(n - 1, cids, gas)),
            geometry=geom,
            surface_tension_N_m=sigma,
            transfer_factor=factor,
        )
        prof = solve_rate_based(thermo, spec, [solvent.T, gas.T])
        gas_out = _state(thermo, cids, prof.v[0], prof.h_vap_W[0], pressures[0])
        rich_out = _state(thermo, cids, prof.liq[n - 1], prof.h_liq_W[n - 1], pressures[n - 1])
        h_in = gas.molar_flow * gas.enthalpy + solvent.molar_flow * solvent.enthalpy
        h_out = gas_out.molar_flow * gas_out.enthalpy + rich_out.molar_flow * rich_out.enthalpy
        q_res = h_out - h_in
        info = _info(prof, spec, thermo)
        info["energy_residual_W"] = q_res
        info["energy_residual_rel"] = abs(q_res) / max(abs(h_in), abs(h_out), 1.0)
        return UnitResult(
            outlets={"gas_out": gas_out, "rich_out": rich_out}, duty_W=q_res, power_W=0.0, info=info
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """The R2 example basis (C1/nC4 gas into lean nC4, 300 K, 2 MPa) in 4 packed
        segments of a 1.0 m x 4 m bed. Packing inputs are illustrative, not catalogue
        data: 25 mm rings, a_t = 200 m2/m3, sigma_c = 0.061 N/m (ceramic); liquid
        surface tension 0.008 N/m. At this traffic the Onda Reynolds numbers sit
        inside the paper's data span (measured Re_G ~ 1.4e3, Re_L ~ 88)."""
        return (
            {
                "gas_in": {"T": 300.0, "P": 2e6, "molar_flow": 100.0, "composition": {"C1": 0.9, "NC4": 0.1}},
                "solvent_in": {"T": 300.0, "P": 2e6, "molar_flow": 30.0, "composition": {"NC4": 1.0}},
            },
            {
                "n_stages": 4,
                "column_diameter_m": 1.0,
                "packed_height_m": 4.0,
                "nominal_size_m": 0.025,
                "specific_area_m2_m3": 200.0,
                "critical_surface_tension_N_m": 0.061,
                "surface_tension_N_m": 0.008,
            },
        )


class ReboiledStripperR3:
    """Rate-based packed stripper over an equilibrium kettle reboiler."""

    inlet_ports = ("feed",)
    outlet_ports = ("overhead", "bottoms")

    def solve(self, inlets: dict[str, StreamState], params: dict[str, Any], thermo: Thermo) -> UnitResult:
        feed = inlets.get("feed")
        if feed is None or feed.molar_flow <= 0.0:
            raise RateBasedSpecError("reboiled_stripper R3 needs a feed with positive molar flow")
        unknown = sorted(set(params) - _COMMON_KEYS - {"spec"})
        if unknown:
            raise RateBasedSpecError(f"reboiled_stripper R3 refuses unknown parameter(s) {unknown}")
        n = _n_stages(params, 2, "reboiled_stripper")
        raw = params.get("spec")
        if not isinstance(raw, dict) or len(raw) != 1:
            raise RateBasedSpecError(
                f"reboiled_stripper R3 spec must be one key from {list(KETTLE_SPECS)}, got {raw!r}"
            )
        name, value = next(iter(raw.items()))
        if name not in KETTLE_SPECS:
            raise RateBasedSpecError(f"reboiled_stripper R3 spec key {name!r} not in {list(KETTLE_SPECS)}")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not float(value) > 0.0:
            raise RateBasedSpecError(f"reboiled_stripper R3 spec {name} must be positive, got {value!r}")
        if name in ("bottoms_rate", "distillate_rate") and float(value) >= feed.molar_flow:
            raise RateBasedSpecError(
                f"reboiled_stripper R3 spec {name}={value} must be below the feed flow {feed.molar_flow}"
            )
        geom, sigma, factor = _geometry(params, n - 1, "reboiled_stripper")
        pressures = _pressures(params, n, feed.P, "reboiled_stripper")
        cids = _cids(feed)
        spec = RateColumnSpec(
            cids=cids,
            pressures=pressures,
            n_rate=n - 1,
            kettle=True,
            feeds=(split_feed(0, cids, feed),),
            geometry=geom,
            surface_tension_N_m=sigma,
            transfer_factor=factor,
            kettle_spec=(name, float(value)),
        )
        prof = solve_rate_based(thermo, spec, [feed.T])
        overhead = _state(thermo, cids, prof.v[0], prof.h_vap_W[0], pressures[0])
        bottoms = _state(thermo, cids, prof.liq[n - 1], prof.h_liq_W[n - 1], pressures[n - 1])
        h_in = feed.molar_flow * feed.enthalpy
        h_out = overhead.molar_flow * overhead.enthalpy + bottoms.molar_flow * bottoms.enthalpy
        duty = h_out - h_in
        info = _info(prof, spec, thermo)
        info["reboiler_duty_W"] = prof.reboiler_duty_W
        info["energy_residual_W"] = duty - prof.reboiler_duty_W
        info["boilup_ratio"] = float(np.sum(prof.v[n - 1]) / np.sum(prof.liq[n - 1]))
        info["distillate_mol_s"] = overhead.molar_flow
        info["bottoms_mol_s"] = bottoms.molar_flow
        return UnitResult(
            outlets={"overhead": overhead, "bottoms": bottoms}, duty_W=duty, power_W=0.0, info=info
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """The R2 example feed (Seader-Henley-Roper Ex. 9.8 basis) on R2's N = 3
        (two packed segments over the kettle) at boilup ratio 0.2, in a 0.5 m x 2 m
        bed. Packing inputs are illustrative, not catalogue data (25 mm rings,
        a_t = 200 m2/m3, sigma_c = 0.061 N/m); liquid surface tension 0.02 N/m.
        Measured: Re_G ~ 220, Re_L ~ 92, inside the Onda data span."""
        from ngdesign.units.column_shortcut.stripper import ReboiledStripper

        feeds, _ = ReboiledStripper.example_case()
        params: dict[str, Any] = {
            "n_stages": 3,
            "spec": {"boilup_ratio": 0.2},
            "column_diameter_m": 0.5,
            "packed_height_m": 2.0,
            "nominal_size_m": 0.025,
            "specific_area_m2_m3": 200.0,
            "critical_surface_tension_N_m": 0.061,
            "surface_tension_N_m": 0.02,
        }
        return feeds, params
