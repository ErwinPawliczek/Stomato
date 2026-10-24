"""Hydrate check / inhibitor injection (plan §2 U-D 10, spec U-D).

Plugin kind "unit", name "hydrate_check" — registered from the catalogue YAML;
no decorator (round-1 conventions).

One outlet: an adiabatic PH mix of the gas inlet and the (optional) inhibitor
inlet at ``P = min inlet P`` (or a given ``P``). ``info`` reports

- ``hydrate_T_K`` — from the ``hammerschmidt_formation`` correlation at the
  mixed pressure, with the gas specific gravity of the ``inlet`` port (mean
  molar mass over the standard dry-air molar mass);
- ``suppression_K`` — from the ``nielsen_bucklin_suppression`` correlation at
  the inhibitor's mass fraction in the outlet's aqueous phase (0.0 when there
  is no aqueous phase or no inhibitor in it);
- ``required_inhibitor_mass_fraction`` and ``required_inhibitor_rate_kg_s`` —
  for a target ``T_operating_K``: the aqueous mass fraction whose suppression
  meets ``hydrate_T - T_operating`` (found by bisecting the correlation, never
  re-deriving it), and the injection rate that builds it,
  ``rate = w / (1 - w) * aqueous water mass flow`` — exact when the injection
  is the only inhibitor source and the aqueous water flow is unchanged.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import Phase, PhaseKind, StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.sizing.hydrates import (
    hammerschmidt_formation,
    nielsen_bucklin_suppression,
)
from ngdesign.units.separation._util import stream_molar_mass

#: Standard dry-air molar mass, g/mol — GPSA defines gas specific gravity as
#: MW_gas / MW_air with this value (GPSA, physical-constant tables).
MW_AIR_G_MOL = 28.9625

#: Inhibitors this unit recognises (component ids); Nielsen-Bucklin is
#: calibrated for methanol and used as the MEG screening correlation.
INHIBITORS: tuple[str, ...] = ("MeOH", "MEG")


class HydrateCheckSpecError(ValueError):
    """The hydrate-check spec is bad; the message names the parameter."""


def _inhibitor_in(composition: dict[str, float]) -> str | None:
    """The single recognised inhibitor present at a positive fraction."""
    present = [cid for cid in INHIBITORS if composition.get(cid, 0.0) > 0.0]
    if len(present) > 1:
        raise HydrateCheckSpecError(
            f"both {present} present; dose one inhibitor at a time"
        )
    return present[0] if present else None


class HydrateCheck:
    """Adiabatic mix plus hydrate-margin and inhibitor-dose reporting."""

    inlet_ports: tuple[str, ...] = ("inlet", "inhibitor_in")
    outlet_ports: tuple[str, ...] = ("outlet",)

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        T_operating = params.get("T_operating_K")
        if T_operating is not None and float(T_operating) <= 0:
            raise HydrateCheckSpecError(
                f"T_operating_K {T_operating} must be positive"
            )
        P_param = params.get("P")
        if P_param is not None and float(P_param) <= 0:
            raise HydrateCheckSpecError(f"P {P_param} must be positive")

        gas = inlets["inlet"]
        inhibitor = inlets["inhibitor_in"]
        active = [s for s in (gas, inhibitor) if s.molar_flow > 0.0]
        if not active:  # all ports zero-flow: no flash possible or needed
            zero = gas.model_copy(update={"molar_flow": 0.0})
            return UnitResult(
                outlets={"outlet": zero},
                duty_W=0.0,
                power_W=0.0,
                info={"hydrate_T_K": 0.0, "suppression_K": 0.0},
            )

        P_out = float(P_param) if P_param is not None else min(s.P for s in active)
        total = sum(s.molar_flow for s in active)
        z: dict[str, float] = {}
        for s in active:
            for cid, x in s.composition.items():
                z[cid] = z.get(cid, 0.0) + x * s.molar_flow
        composition = {cid: n / total for cid, n in z.items()}
        h_mix = sum(s.enthalpy * s.molar_flow for s in active) / total
        outlet = thermo.flash_ph(composition, P_out, h_mix, total)

        info = self._hydrate_info(gas, outlet, P_out, T_operating)
        return UnitResult(
            outlets={"outlet": outlet},
            duty_W=0.0,
            power_W=0.0,
            info=info,
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Wet slice gas at 7 MPa dosed with ~0.5 kg/s of methanol.

        The gas is the dry slice composition plus 3 % water at 15 °C — enough
        free water for an aqueous phase at 7 MPa; ``T_operating_K = 273.15``
        drives the required-dose info fields.
        """
        from ngdesign.units._examples import MMSCFD_TO_MOL_S

        z = {
            "N2": 0.005,
            "CO2": 0.015,
            "C1": 0.848,
            "C2": 0.062,
            "C3": 0.032,
            "iC4": 0.007,
            "nC4": 0.010,
            "iC5": 0.004,
            "nC5": 0.004,
            "C6+": 0.010,
            "H2O": 0.030,
        }
        total = sum(z.values())
        feed = {
            "T": 288.15,
            "P": 7.0e6,
            "molar_flow": 50 * MMSCFD_TO_MOL_S,
            "composition": {cid: x / total for cid, x in z.items()},
        }
        inhibitor = {
            "T": 288.15,
            "P": 7.0e6,
            "molar_flow": 15.6,  # 0.5 kg/s / 0.03204 kg/mol ≈ 15.6 mol/s
            "composition": {"MeOH": 1.0},
        }
        return {"inlet": feed, "inhibitor_in": inhibitor}, {"T_operating_K": 273.15}

    def _hydrate_info(
        self,
        gas: StreamState,
        outlet: StreamState,
        P_out: float,
        T_operating: float | None,
    ) -> dict[str, float]:
        """Hydrate T, achieved suppression and (when asked) required dose."""
        sg = stream_molar_mass(gas.composition) / MW_AIR_G_MOL
        hydrate_T = hammerschmidt_formation(P_out, sg)["T_hydrate_K"]

        info: dict[str, float] = {
            "hydrate_T_K": hydrate_T,
            "gas_specific_gravity": sg,
        }

        aqueous = next(
            (p for p in outlet.phases if p.kind is PhaseKind.AQUEOUS), None
        )
        inhibitor_cid = _inhibitor_in(aqueous.composition) if aqueous else None
        if aqueous is None or inhibitor_cid is None:
            info["suppression_K"] = 0.0
        else:
            w = _inhibitor_mass_fraction(aqueous.composition, inhibitor_cid)
            suppression = nielsen_bucklin_suppression(
                w, stream_molar_mass({inhibitor_cid: 1.0})
            )["dT_suppression_K"]
            info["suppression_K"] = suppression

        if T_operating is not None:
            info.update(
                _required_dose(outlet, aqueous, inhibitor_cid, hydrate_T - float(T_operating))
            )
        return info


def _required_dose(
    outlet: StreamState,
    aqueous: Phase | None,
    inhibitor_cid: str | None,
    dT_required: float,
) -> dict[str, float]:
    """Required aqueous mass fraction and injection rate for a target T."""
    if dT_required <= 0.0:  # already below the hydrate formation T
        return {
            "required_inhibitor_mass_fraction": 0.0,
            "required_inhibitor_rate_kg_s": 0.0,
        }
    if inhibitor_cid is None:
        raise HydrateCheckSpecError(
            "T_operating_K below the hydrate T needs an inhibitor "
            "(MeOH or MEG) in the mixed stream to dose for"
        )
    assert aqueous is not None  # an inhibitor implies an aqueous phase
    mw_inhibitor = stream_molar_mass({inhibitor_cid: 1.0})
    w = _bisect_required_fraction(dT_required, mw_inhibitor)

    water_mass_flow = 0.0
    if "H2O" in aqueous.composition:
        n_aqueous = aqueous.mole_fraction * outlet.molar_flow  # mol/s
        x_water = aqueous.composition["H2O"]
        water_mass_flow = n_aqueous * x_water * stream_molar_mass({"H2O": 1.0}) * 1e-3
    rate = w / (1.0 - w) * water_mass_flow if water_mass_flow > 0.0 else 0.0
    return {
        "required_inhibitor_mass_fraction": w,
        "required_inhibitor_rate_kg_s": rate,
    }


def _inhibitor_mass_fraction(composition: dict[str, float], cid: str) -> float:
    """Inhibitor mass fraction within the aqueous-phase composition."""
    mass = stream_molar_mass(composition)  # g/mol of the aqueous mixture
    return composition.get(cid, 0.0) * float(stream_molar_mass({cid: 1.0})) / mass


def _bisect_required_fraction(dT_required: float, mw_inhibitor: float) -> float:
    """Aqueous mass fraction w whose Nielsen-Bucklin suppression matches dT.

    Bisects the published correlation itself — the equation is never
    re-derived here. Raises a typed refusal when the required suppression
    exceeds the correlation's validity range (x_M <= 0.8).
    """
    w_lo, w_hi = 1e-9, 1.0 - 1e-9

    def suppression(w: float) -> float | None:
        try:
            return nielsen_bucklin_suppression(w, mw_inhibitor)["dT_suppression_K"]
        except ValueError:
            return None  # x_M beyond the published validity limit

    lo_sup = suppression(w_lo)
    if lo_sup is None or lo_sup > dT_required:
        return 0.0
    # Largest valid w: bisection on the x_M <= 0.8 validity transition (the
    # correlation raises above it). Suppression is monotone increasing in w,
    # so suppression at that boundary is the largest reportable value.
    if suppression(w_hi) is None:
        lo_v, hi_v = w_lo, w_hi
        while hi_v - lo_v > 1e-12:
            mid = 0.5 * (lo_v + hi_v)
            if suppression(mid) is None:
                hi_v = mid
            else:
                lo_v = mid
        w_max = lo_v
    else:
        w_max = w_hi
    s_max = suppression(w_max)
    if s_max is None or s_max < dT_required:
        raise HydrateCheckSpecError(
            f"required suppression {dT_required:.1f} K exceeds the "
            "Nielsen-Bucklin validity range (aqueous methanol mole fraction "
            "x_M <= 0.8)"
        )
    while w_hi - w_lo > 1e-12:
        mid = 0.5 * (w_lo + w_hi)
        s_mid = suppression(mid)
        if s_mid is None or s_mid > dT_required:
            w_hi = mid
        else:
            w_lo = mid
    return 0.5 * (w_lo + w_hi)
