"""R3 adapter of the ``column`` row: rate-based distillation and Murphree-efficiency trays.

Plugin kind "unit", row ``column``, level R3 (registered through the catalogue YAML
``levels.R3``). Same ports as the R2 :class:`ngdesign.units.column.Column`: one
``feed``; ``distillate``, ``bottoms`` and ``side_draw`` (a zero-flow state: R3 has no
draws). The plan is ``specs/backend/units/column_r3.md``.

Stage numbering is R2's, so the same ``n_stages``/``feed_stage`` describe the same
column at both levels: stage 1 is the partial condenser (``condenser="partial"``) or
the first stage under a total condenser (``condenser="total"``, hardware above stage
1), stage N the kettle reboiler. The stages between condenser and kettle (N-1 for a
total condenser, N-2 for a partial one) are

* ``stage_model="rate_based"`` (default) - packed segments of equal height, the
  Krishna-Taylor rate-based model of :mod:`ngdesign.units.column.rate_based`
  (Taylor & Krishna 1993 ch. 14; Taylor, Kooijman & Hung 1994), Onda (1968) packing
  coefficients; condenser and kettle stay equilibrium stages;
* ``stage_model="murphree"`` - equilibrium-stage MESH trays with a Murphree vapour
  efficiency ``y_n = y_{n+1} + E_MV (y*_n - y_{n+1})`` (Murphree, Ind. Eng. Chem. 17
  (1925) 747-750), scalar or one per tray; ``E = 1`` is R2's MESH stage.

Both are solved by the one simultaneous Newton in ``solve_rate_based``; its module
docstring carries every equation. A total condenser returns saturated (bubble-point)
reflux and distillate, as R2 does (``inside_out._reflux_state``); ``murphree`` at
``E = 1`` and R2 agree to 9.2e-5 in product mole fraction for a total condenser
(R2's bubble point is refined on its own K surface) and to round-off for a partial one.

Specs (exactly two, R2's names): top ``reflux_ratio``, ``condenser_duty_W`` (heat
removed, W); bottom ``boilup_ratio``, ``reboiler_duty_W``; either end
``distillate_rate``, ``bottoms_rate`` (mol/s; on the top as ``D = F - B``, exact at
convergence). The simultaneous Newton carries the duties as energy balances, so duty
specs are solved directly.

``duty_W`` is the boundary balance ``sum(n h)_out - n h_feed`` over the flashed
outlets; ``info['reboiler_duty_W'] - info['condenser_duty_W']`` is the model's, and
the difference is ``info['energy_residual_W']``. ``info`` stage keys use the solver's
block index (0 = the condenser; for a total condenser its ``y`` is the liquid
distillate's composition).

Refusals are :class:`RateBasedSpecError` (a ValueError) naming the parameter.
All SI. Pure functions; no I/O; no global state.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo

from . import _zero_flow_state
from .rate_based import RateColumnSpec, solve_rate_based, split_feed
from .rate_based_units import (
    _PACKING_KEYS,
    RateBasedSpecError,
    _cids,
    _geometry,
    _info,
    _n_stages,
    _pressures,
    _state,
)

STAGE_MODELS = ("rate_based", "murphree")
_TOP_ONLY = frozenset({"reflux_ratio", "condenser_duty_W"})
_BOTTOM_ONLY = frozenset({"boilup_ratio", "reboiler_duty_W"})
_EITHER = frozenset({"distillate_rate", "bottoms_rate"})
_BASE_KEYS = frozenset(
    {"stage_model", "n_stages", "condenser", "reboiler", "feed_stage", "pressure_profile", "specs"}
)
_UNIT = "column"


def _place_specs(raw: Any, feed_flow: float) -> tuple[tuple[str, float], tuple[str, float]]:
    """Two specs -> (top, bottom). ``bottoms_rate`` on the top becomes ``D = F - B``."""
    names = sorted(_TOP_ONLY | _BOTTOM_ONLY | _EITHER)
    if not isinstance(raw, dict) or len(raw) != 2:
        raise RateBasedSpecError(f"column R3 specs must be two keys from {names}, got {raw!r}")
    for name, value in raw.items():
        if name not in names:
            raise RateBasedSpecError(f"column R3 specs key {name!r} not in {names}")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not float(value) > 0.0:
            raise RateBasedSpecError(f"column R3 specs.{name} must be a positive number, got {value!r}")
        if name in _EITHER and float(value) >= feed_flow:
            raise RateBasedSpecError(
                f"column R3 specs.{name}={value} must be below the feed flow {feed_flow}"
            )
    (a, va), (b, vb) = ((k, float(v)) for k, v in raw.items())
    if {a, b} <= _EITHER:
        raise RateBasedSpecError(
            "column R3 specs distillate_rate + bottoms_rate do not determine a column (D + B = F); "
            "replace one with a ratio or duty spec"
        )
    if {a, b} <= _TOP_ONLY or {a, b} <= _BOTTOM_ONLY:
        raise RateBasedSpecError(
            f"column R3 specs {a} + {b} both act on the same end; give one condenser-side "
            f"({sorted(_TOP_ONLY | _EITHER)}) and one reboiler-side ({sorted(_BOTTOM_ONLY | _EITHER)}) spec"
        )
    if a in _TOP_ONLY or b in _BOTTOM_ONLY:
        top, bottom = (a, va), (b, vb)
    else:
        top, bottom = (b, vb), (a, va)
    if top[0] == "bottoms_rate":
        top = ("distillate_rate", feed_flow - top[1])
    return top, bottom


def _efficiencies(raw: Any, n_trays: int) -> tuple[float, ...]:
    def ok(e: Any) -> bool:
        return not isinstance(e, bool) and isinstance(e, (int, float)) and 0.0 < float(e) <= 1.0

    if raw is None:
        return (1.0,) * n_trays
    if isinstance(raw, (list, tuple)):
        if len(raw) != n_trays or not all(ok(e) for e in raw):
            raise RateBasedSpecError(
                f"column R3 murphree_efficiency must be {n_trays} values in (0, 1] (one per tray "
                f"between condenser and kettle), got {raw!r}"
            )
        return tuple(float(e) for e in raw)
    if not ok(raw):
        raise RateBasedSpecError(f"column R3 murphree_efficiency must be in (0, 1], got {raw!r}")
    return (float(raw),) * n_trays


class ColumnR3:
    """Rate-based (or Murphree-tray) distillation column: condenser, middle stages, kettle."""

    inlet_ports = ("feed",)
    outlet_ports = ("distillate", "bottoms", "side_draw")

    def solve(self, inlets: dict[str, StreamState], params: dict[str, Any], thermo: Thermo) -> UnitResult:
        feed = inlets.get("feed")
        if feed is None or feed.molar_flow <= 0.0:
            raise RateBasedSpecError("column R3 needs a feed with positive molar flow")
        model = params.get("stage_model", "rate_based")
        if model not in STAGE_MODELS:
            raise RateBasedSpecError(f"column R3 stage_model {model!r} not in {list(STAGE_MODELS)}")
        own = (
            frozenset({*_PACKING_KEYS, "transfer_factor"})
            if model == "rate_based"
            else frozenset({"murphree_efficiency"})
        )
        unknown = sorted(set(params) - _BASE_KEYS - own)
        if unknown:
            raise RateBasedSpecError(f"column R3 ({model}) refuses unknown parameter(s) {unknown}")
        condenser = params.get("condenser")
        if condenser not in ("total", "partial"):
            raise RateBasedSpecError(f"column R3 condenser must be 'total' or 'partial', got {condenser!r}")
        if params.get("reboiler", "kettle") != "kettle":
            raise RateBasedSpecError(f"column R3 reboiler must be 'kettle', got {params.get('reboiler')!r}")
        n = _n_stages(params, 3, _UNIT)
        k = params.get("feed_stage")
        if isinstance(k, bool) or not isinstance(k, int) or not 1 <= k <= n:
            raise RateBasedSpecError(f"column R3 feed_stage must be an integer in 1..{n}, got {k!r}")
        top_spec, bottom_spec = _place_specs(params.get("specs"), feed.molar_flow)
        total = condenser == "total"
        n_mid = n - 1 if total else n - 2
        r2_pressures = _pressures(params, n, feed.P, _UNIT)
        pressures = (r2_pressures[0], *r2_pressures) if total else r2_pressures
        cids = _cids(feed)
        if model == "rate_based":
            geom, sigma, factor = _geometry(params, n_mid, _UNIT)
            murphree = None
        else:
            geom, sigma, factor = None, 0.0, 1.0
            murphree = _efficiencies(params.get("murphree_efficiency"), n_mid)
        spec = RateColumnSpec(
            cids=cids,
            pressures=pressures,
            n_rate=n_mid,
            kettle=True,
            feeds=(split_feed(k if total else k - 1, cids, feed),),
            geometry=geom,
            surface_tension_N_m=sigma,
            transfer_factor=factor,
            kettle_spec=bottom_spec,
            condenser=condenser,
            condenser_spec=top_spec,
            murphree=murphree,
        )
        prof = solve_rate_based(thermo, spec, [feed.T])
        last = len(pressures) - 1
        distillate = _state(thermo, cids, prof.v[0], prof.h_vap_W[0], pressures[0])
        bottoms = _state(thermo, cids, prof.liq[last], prof.h_liq_W[last], pressures[last])
        side_draw = _zero_flow_state(dict(bottoms.composition), bottoms.T, pressures[last])
        h_in = feed.molar_flow * feed.enthalpy
        h_out = distillate.molar_flow * distillate.enthalpy + bottoms.molar_flow * bottoms.enthalpy
        duty = h_out - h_in
        q_model = prof.reboiler_duty_W - prof.condenser_duty_W
        d_flow, b_flow = float(np.sum(prof.v[0])), float(np.sum(prof.liq[last]))
        info = _info(prof, spec, thermo)
        info.update(
            {
                "condenser_duty_W": prof.condenser_duty_W,
                "reboiler_duty_W": prof.reboiler_duty_W,
                "energy_residual_W": duty - q_model,
                "energy_residual_rel": abs(duty - q_model) / max(abs(h_in), abs(h_out), 1.0),
                "reflux_ratio": float(np.sum(prof.liq[0])) / d_flow,
                "boilup_ratio": float(np.sum(prof.v[last])) / b_flow,
                "distillate_mol_s": distillate.molar_flow,
                "bottoms_mol_s": bottoms.molar_flow,
                "murphree_stages": 1.0 if murphree is not None else 0.0,
            }
        )
        return UnitResult(
            outlets={"distillate": distillate, "bottoms": bottoms, "side_draw": side_draw},
            duty_W=duty,
            power_W=0.0,
            info=info,
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """R2's example column (16 stages, C3/iC4 50/50 at 330 K and 1.5 MPa, total
        condenser, feed on stage 8, reflux ratio 2.5, distillate 45 mol/s), the 15
        stages between condenser and kettle as packed segments of a 1.8 m x 15 m bed.
        Packing inputs are illustrative, not catalogue data (25 mm rings,
        a_t = 200 m2/m3, sigma_c = 0.061 N/m as the absorber R3); liquid surface
        tension 0.006 N/m is an illustrative light-hydrocarbon value. Measured
        Re_G 1.6e3-1.84e3, Re_L 125-283: inside the Onda data span."""
        from . import Column

        feeds, r2 = Column.example_case()
        params: dict[str, Any] = {
            "n_stages": r2["n_stages"],
            "condenser": r2["condenser"],
            "feed_stage": r2["feed_stage"],
            "pressure_profile": r2["pressure_profile"],
            "specs": dict(r2["specs"]),
            "column_diameter_m": 1.8,
            "packed_height_m": 15.0,
            "nominal_size_m": 0.025,
            "specific_area_m2_m3": 200.0,
            "critical_surface_tension_N_m": 0.061,
            "surface_tension_N_m": 0.006,
        }
        return feeds, params
