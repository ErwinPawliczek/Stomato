"""``desalter`` adapter (spec U-H1).

Two-stage-equivalent single-vessel electrostatic desalter, rigour R0: isothermal
at ``T`` with pressure drop ``dP`` from the crude inlet. Water (``H2O`` from both
inlets) splits by component: ``water_carryover_frac`` of it reports to the
desalted crude (the BS&W), the rest leaves as brine. Tracked salt (``NaCl``)
leaves with the brine: ``salt_removal`` of the inlet salt, the rest stays in
the crude. Non-water wash components report to the brine. ``info`` reports the
BS&W of the desalted crude on the reference-volume basis and the achieved salt
removal.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.registry import register
from ngdesign.units.refining._cuts import RefiningSpecError, optional_float, require_float
from ngdesign.units.refining.slate import (
    WATER_60F_KG_M3,
    assay_slate,
    reference_volume,
    register_slate,
)

#: Assay id of the example crude (the stored Bagajewicz & Ji 2001 light crude).
_EXAMPLE_ASSAY = "bagajewicz_ji_2001_light"

#: Component id of tracked salt (sodium chloride, the data bank basis).
SALT_ID = "NaCl"

#: Water id.
WATER_ID = "H2O"

_EXAMPLE_CARRYOVER = 0.04
_EXAMPLE_SALT_REMOVAL = 0.95
_EXAMPLE_T = 403.15  # 130 degC: inside the printed 90-150 degC operating band


@register("unit", "desalter")
class Desalter:
    """Wash, coalesce and split crude into desalted crude and brine."""

    inlet_ports: tuple[str, ...] = ("crude_in", "wash_in")
    outlet_ports: tuple[str, ...] = ("crude_out", "water_out")

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """The light crude plus 5 vol% wash water at 130 degC (Gary et al. p. 76)."""
        register_slate(_EXAMPLE_ASSAY)
        _, mole = assay_slate(_EXAMPLE_ASSAY)
        # Dose the crude with 1 vol% BS&W water (Wauquier: oilfield crude reaches
        # the refinery at 1-2 vol%) and 1e-5 mol fraction NaCl so both tracked
        # splits are live.
        bsw = 0.01
        crude_mole: dict[str, float] = {cid: x * (1.0 - bsw - 1e-5) for cid, x in mole.items()}
        crude_mole[WATER_ID] = bsw
        crude_mole[SALT_ID] = 1e-5
        # Wash water at 5 reference vol% of the crude: n = V * rho_water / MW.
        crude_volume = _mole_volume(crude_mole) * 1000.0  # m3/s at 1000 mol/s
        wash_flow = 0.05 * crude_volume * 999.0 * 1000.0 / 18.01528
        feeds = {
            "crude_in": {
                "T": 403.15,
                "P": 1.0e6,
                "molar_flow": 1000.0,
                "composition": crude_mole,
            },
            "wash_in": {
                "T": 403.15,
                "P": 1.0e6,
                "molar_flow": wash_flow,
                "composition": {WATER_ID: 1.0},
            },
        }
        return feeds, {
            "T": _EXAMPLE_T,
            "dP": 0.0,
            "water_carryover_frac": _EXAMPLE_CARRYOVER,
            "salt_removal": _EXAMPLE_SALT_REMOVAL,
        }

    def solve(self, inlets: dict[str, StreamState], params: dict[str, Any], thermo: Thermo) -> UnitResult:
        """Split water and salt by component, then flash both outlets isothermally."""
        crude = inlets.get("crude_in")
        wash = inlets.get("wash_in")
        if crude is None:
            raise RefiningSpecError("crude_in: the crude inlet stream is required")
        if wash is None:
            raise RefiningSpecError("wash_in: the wash water inlet stream is required")
        t_out = require_float(params, "T")
        dp = optional_float(params, "dP", 0.0)
        if dp < 0.0:
            raise RefiningSpecError("dP: must be >= 0")
        carryover = require_float(params, "water_carryover_frac")
        if not 0.0 <= carryover <= 1.0:
            raise RefiningSpecError("water_carryover_frac: must be in [0, 1]")
        salt_removal = require_float(params, "salt_removal")
        if not 0.0 <= salt_removal <= 1.0:
            raise RefiningSpecError("salt_removal: must be in [0, 1]")
        p_out = crude.P - dp
        if p_out <= 0.0:
            raise RefiningSpecError("dP: leaves a non-positive outlet pressure")

        # Component-wise mole flows into each outlet.
        crude_flows: dict[str, float] = {}
        water_flows: dict[str, float] = {}
        salt_in = 0.0
        for stream in (crude, wash):
            for cid, x in stream.composition.items():
                n = x * stream.molar_flow
                if cid == WATER_ID:
                    crude_flows[cid] = crude_flows.get(cid, 0.0) + carryover * n
                    water_flows[cid] = water_flows.get(cid, 0.0) + (1.0 - carryover) * n
                elif cid == SALT_ID and stream is crude:
                    salt_in += n
                    crude_flows[cid] = crude_flows.get(cid, 0.0) + (1.0 - salt_removal) * n
                    water_flows[cid] = water_flows.get(cid, 0.0) + salt_removal * n
                elif stream is wash:  # non-water wash component: brine contaminant
                    water_flows[cid] = water_flows.get(cid, 0.0) + n
                else:
                    crude_flows[cid] = crude_flows.get(cid, 0.0) + n
        crude_out_flow = sum(crude_flows.values())
        water_out_flow = sum(water_flows.values())
        crude_out = _flash_or_zero(thermo, crude_flows, crude_out_flow, t_out, p_out, crude)
        water_out = _flash_or_zero(thermo, water_flows, water_out_flow, t_out, p_out, wash)
        duty = (
            sum(s.enthalpy * s.molar_flow for s in (crude_out, water_out))
            - crude.enthalpy * crude.molar_flow
            - wash.enthalpy * wash.molar_flow
        )
        salt_tracked = 1.0 if salt_in > 0.0 else 0.0
        removed = salt_removal if salt_tracked else 0.0
        info = {
            "bsw_vol_pct": 100.0 * reference_volume(crude_out) and 100.0 * _water_volume_frac(crude_out),
            "salt_removed_frac": removed,
            "salt_tracked": salt_tracked,
        }
        return UnitResult(
            outlets={"crude_out": crude_out, "water_out": water_out},
            duty_W=duty,
            power_W=0.0,
            info=info,
        )


def _flash_or_zero(
    thermo: Thermo,
    flows: dict[str, float],
    total: float,
    t_out: float,
    p_out: float,
    reference: StreamState,
) -> StreamState:
    """Flash ``flows`` at (T, P); a zero-flow outlet mirrors the reference composition."""
    if total <= 0.0:
        return reference.model_copy(update={"T": t_out, "P": p_out, "molar_flow": 0.0, "phases": []})
    composition = {cid: n / total for cid, n in flows.items() if n > 0.0}
    return thermo.flash_pt(composition, t_out, p_out, total)


def _water_volume_frac(state: StreamState) -> float:
    """Water volume fraction of ``state`` on the reference-volume basis."""
    from ngdesign.data import component_record

    record = component_record(WATER_ID)
    water_mass = state.composition.get(WATER_ID, 0.0) * state.molar_flow * record["mw"] / 1000.0
    water_vol = water_mass / (record["sg"] * WATER_60F_KG_M3)
    total_vol = reference_volume(state)
    return water_vol / total_vol if total_vol else 0.0


def _mole_volume(mole: dict[str, float]) -> float:
    """Reference volume of 1 mol/s of ``mole`` (m3, per mol/s of stream)."""
    from ngdesign.data import component_record

    volume = 0.0
    for cid, x in mole.items():
        record = component_record(cid)
        volume += x * record["mw"] / (record["sg"] * WATER_60F_KG_M3) / 1000.0
    return volume
