"""Adsorption bed, TSA/PSA (plan §2 U-D 9, spec U-D).

Plugin kind "unit", name "adsorption_bed" — registered from the catalogue
YAML; no decorator (round-1 conventions).

R0 method (spec): ``removal_fraction`` maps each adsorbate component id to
the fraction of its molar flow taken to the desorbate outlet (``regen_out``);
everything else leaves on ``product_out``. Product and desorbate are flashed
at their own T and P (the feed T, with per-outlet pressures ``product_P`` /
``regen_P``, both defaulting to the feed pressure). Params
``capacity_kg_per_kg`` and ``bed_mass_kg`` report
``cycle_time_s = capacity * bed_mass / adsorbate mass rate`` in ``info``
(0.0 when the pair or an adsorbate flow is absent). No heat of adsorption at
R0: the flashes run at the feed temperature.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.separation._util import stream_molar_mass, zero_flow_outlet


class AdsorptionBedSpecError(ValueError):
    """The adsorption-bed spec is bad; the message names the parameter."""


class AdsorptionBed:
    """Fixed bed: an adsorbate split spec plus a cycle-time report."""

    inlet_ports: tuple[str, ...] = ("feed_in",)
    outlet_ports: tuple[str, ...] = ("product_out", "regen_out")

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        feed = inlets["feed_in"]
        removal = params.get("removal_fraction")
        if not isinstance(removal, dict) or not removal:
            raise AdsorptionBedSpecError(
                "removal_fraction is required: a non-empty map of component id to removed fraction"
            )
        unknown = [cid for cid in removal if cid not in feed.composition]
        if unknown:
            raise AdsorptionBedSpecError(f"removal_fraction names component(s) {unknown} not in the feed")
        bad = {cid: f for cid, f in removal.items() if not 0.0 <= float(f) <= 1.0}
        if bad:
            raise AdsorptionBedSpecError(f"removal_fraction entries {bad} outside [0, 1]")
        capacity = params.get("capacity_kg_per_kg")
        if capacity is not None and float(capacity) < 0:
            raise AdsorptionBedSpecError(f"capacity_kg_per_kg {capacity} must be >= 0")
        bed_mass = params.get("bed_mass_kg")
        if bed_mass is not None and float(bed_mass) < 0:
            raise AdsorptionBedSpecError(f"bed_mass_kg {bed_mass} must be >= 0")
        P_product = float(params.get("product_P", feed.P))
        P_regen = float(params.get("regen_P", feed.P))
        if min(P_product, P_regen) <= 0:
            raise AdsorptionBedSpecError("product_P and regen_P must be positive")

        n_regen: dict[str, float] = {}
        for cid, x in feed.composition.items():
            n_regen[cid] = x * feed.molar_flow * float(removal.get(cid, 0.0))
        regen_flow = sum(n_regen.values())
        product_flow = feed.molar_flow - regen_flow

        outlets: dict[str, StreamState]
        if regen_flow > 0.0 and product_flow > 0.0:
            regen_z = {cid: n / regen_flow for cid, n in n_regen.items()}
            product_z = {
                cid: (x * feed.molar_flow - n_regen[cid]) / product_flow
                for cid, x in feed.composition.items()
            }
            regen = thermo.flash_pt(regen_z, feed.T, P_regen, regen_flow)
            product = thermo.flash_pt(product_z, feed.T, P_product, product_flow)
            outlets = {"product_out": product, "regen_out": regen}
        elif regen_flow > 0.0:  # everything adsorbed: empty product
            regen_z = {cid: n / regen_flow for cid, n in n_regen.items()}
            regen = thermo.flash_pt(regen_z, feed.T, P_regen, regen_flow)
            outlets = {
                "product_out": zero_flow_outlet(feed, feed.T, P_product),
                "regen_out": regen,
            }
        else:  # nothing adsorbed
            product = (
                thermo.flash_pt(dict(feed.composition), feed.T, P_product, feed.molar_flow)
                if feed.molar_flow > 0.0
                else zero_flow_outlet(feed, feed.T, P_product)
            )
            outlets = {
                "product_out": product,
                "regen_out": zero_flow_outlet(feed, feed.T, P_regen),
            }

        # cycle_time_s = capacity * bed_mass / adsorbate mass rate (kg/s).
        adsorbate_mass_rate = 0.0
        for cid, n in n_regen.items():
            adsorbate_mass_rate += n * stream_molar_mass({cid: 1.0}) * 1e-3  # kg/s
        cycle_time = 0.0
        if capacity is not None and bed_mass is not None and adsorbate_mass_rate > 0.0:
            cycle_time = float(capacity) * float(bed_mass) / adsorbate_mass_rate

        h_in_W = feed.enthalpy * feed.molar_flow
        h_out_W = sum(s.enthalpy * s.molar_flow for s in outlets.values())
        return UnitResult(
            outlets=outlets,
            duty_W=h_out_W - h_in_W,
            power_W=0.0,
            info={
                "cycle_time_s": cycle_time,
                "adsorbate_mass_rate_kg_s": adsorbate_mass_rate,
            },
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Molecular-sieve dehydration of the slice wet gas: 95 % water removal.

        ``capacity_kg_per_kg = 0.10`` is the ~10 wt% design water loading GPSA
        quotes for molecular sieves (Sect. 20, dehydration); the 500 kg bed is
        an example value, not a correlation constant.
        """
        from ngdesign.units._examples import INLET_COMPOSITION, MMSCFD_TO_MOL_S

        feed = {
            "T": 322.15,
            "P": 7.0e6,
            "molar_flow": 50 * MMSCFD_TO_MOL_S,
            "composition": dict(INLET_COMPOSITION),
        }
        return {"feed_in": feed}, {
            "removal_fraction": {"H2O": 0.95},
            "capacity_kg_per_kg": 0.10,
            "bed_mass_kg": 500.0,
        }
