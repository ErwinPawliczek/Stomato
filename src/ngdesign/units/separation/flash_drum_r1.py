"""Flash drum R1: Souders-Brown sizing and carry-over (``specs/backend/units/flash_drum.md``).

The S1-S6 equations are the scrubber R1's, imported from their single owner
(:mod:`ngdesign.units.separation.scrubber_r1`), which in turn calls the registered
Souders-Brown sizing, on the flash drum's outlets.  The liquid is ``liquid_out`` and
``aqueous_out`` together, and carry-over leaves each in proportion to its mass.  With
no diameter, or no entrainment, R0's outlets return unchanged.
"""

from __future__ import annotations

import math
from typing import Any

from ngdesign.contracts import PhaseKind, StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.separation.flash_drum import FlashDrum
from ngdesign.units.separation.scrubber_r1 import (
    carryover_mass_flow,
    cut_diameter_m,
    liquid_density_kg_m3,
    rosin_rammler_fines,
    size_gas_section,
    york_K_m_s,
)

_R1_KEYS = (
    "K_m_s",
    "diameter_m",
    "inlet_entrained_fraction",
    "droplet_d_rr_m",
    "droplet_n_rr",
    "gas_viscosity_Pa_s",
)


class FlashDrumR1SpecError(ValueError):
    """A refused flash-drum R1 specification; the message names the parameter."""


class FlashDrumR1:
    """Flash drum with Souders-Brown sizing and droplet carry-over at a given diameter."""

    inlet_ports: tuple[str, ...] = FlashDrum.inlet_ports
    outlet_ports: tuple[str, ...] = FlashDrum.outlet_ports

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        diameter = params.get("diameter_m")
        entrained = params.get("inlet_entrained_fraction")
        d_rr = params.get("droplet_d_rr_m")
        n_rr = params.get("droplet_n_rr")
        k_param = params.get("K_m_s")
        if diameter is not None and diameter <= 0:
            raise FlashDrumR1SpecError(f"diameter_m must be positive, got {diameter}")
        if k_param is not None and k_param <= 0:
            raise FlashDrumR1SpecError(f"K_m_s must be positive, got {k_param}")
        if entrained is not None and not 0.0 <= entrained <= 1.0:
            raise FlashDrumR1SpecError(f"inlet_entrained_fraction must be within [0, 1], got {entrained}")
        if d_rr is not None and d_rr <= 0:
            raise FlashDrumR1SpecError(f"droplet_d_rr_m must be positive, got {d_rr}")
        if n_rr is not None and n_rr <= 0:
            raise FlashDrumR1SpecError(f"droplet_n_rr must be positive, got {n_rr}")
        if diameter is not None and (entrained is None or d_rr is None or n_rr is None):
            raise FlashDrumR1SpecError(
                "a diameter_m carry-over calculation requires inlet_entrained_fraction, "
                "droplet_d_rr_m and droplet_n_rr"
            )

        r0_params = {key: value for key, value in params.items() if key not in _R1_KEYS}
        r0 = FlashDrum().solve(inlets, r0_params, thermo)
        gas = r0.outlets["gas_out"]
        liquid = r0.outlets["liquid_out"]
        aqueous = r0.outlets["aqueous_out"]
        if gas.molar_flow <= 0.0 or liquid.molar_flow + aqueous.molar_flow <= 0.0:
            if diameter is not None:
                raise FlashDrumR1SpecError(
                    "carry-over needs both a gas and a liquid outlet with non-zero flow"
                )
            return r0  # one phase and no vessel: nothing to size, and R0 stands

        vapour = next(p for p in gas.phases if p.kind is PhaseKind.VAPOR)
        rho_g = vapour.density
        rho_l = liquid_density_kg_m3(*(s for s in (liquid, aqueous) if s.molar_flow > 0.0))
        q_g = gas.mass_flow / rho_g
        k = float(k_param) if k_param is not None else york_K_m_s(gas.P)
        size = size_gas_section(k, rho_l, rho_g, q_g)
        info: dict[str, float] = {
            **r0.info,
            "K_m_s": k,
            "v_max_m_s": size["v_max_m_s"],
            "D_min_m": size["min_diameter_m"],
            "rho_gas_kg_m3": rho_g,
            "rho_liquid_kg_m3": rho_l,
            "Q_gas_m3_s": q_g,
        }
        outlets = dict(r0.outlets)
        duty = r0.duty_W
        if diameter is not None:
            mu_g = vapour.viscosity
            if mu_g is None:
                if "gas_viscosity_Pa_s" not in params:
                    raise FlashDrumR1SpecError("the package gives no gas viscosity; pass gas_viscosity_Pa_s")
                mu_g = float(params["gas_viscosity_Pa_s"])
            v_g = 4.0 * q_g / (math.pi * float(diameter) ** 2)
            d_cut = cut_diameter_m(v_g, rho_l, rho_g, mu_g)["d_cut_m"]
            fines = 1.0 if math.isinf(d_cut) else rosin_rammler_fines(d_cut, float(d_rr), float(n_rr))  # type: ignore[arg-type]
            mass_l = liquid.mass_flow + aqueous.mass_flow
            carry = carryover_mass_flow(mass_l, float(entrained), fines)  # type: ignore[arg-type]
            f = carry / mass_l
            info.update(
                {
                    "v_gas_m_s": v_g,
                    "v_ratio": v_g / size["v_max_m_s"],
                    "d_cut_m": d_cut,
                    "fines_fraction": fines,
                    "carryover_kg_s": carry,
                    "carryover_mol_fraction": f,
                }
            )
            if f > 0.0:
                # The same fraction of both liquids, by mass, so of each one's moles;
                # the liquids are scaled, never re-flashed, and the gas is genuinely mixed.
                n_g = gas.molar_flow
                n_l = liquid.molar_flow
                n_a = aqueous.molar_flow
                total = n_g + f * (n_l + n_a)
                z_mix = {
                    cid: (
                        n_g * gas.composition.get(cid, 0.0)
                        + f * n_l * liquid.composition.get(cid, 0.0)
                        + f * n_a * aqueous.composition.get(cid, 0.0)
                    )
                    / total
                    for cid in {**gas.composition, **liquid.composition, **aqueous.composition}
                }
                outlets["liquid_out"] = liquid.model_copy(update={"molar_flow": (1.0 - f) * n_l})
                outlets["aqueous_out"] = aqueous.model_copy(update={"molar_flow": (1.0 - f) * n_a})
                outlets["gas_out"] = thermo.flash_pt(z_mix, r0.info["T_out_K"], gas.P, total)
                h_in = sum(s.enthalpy * s.molar_flow for s in inlets.values() if s.molar_flow > 0.0)
                duty = sum(s.enthalpy * s.molar_flow for s in outlets.values()) - h_in
        return UnitResult(outlets=outlets, duty_W=duty, power_W=0.0, info=info)

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """The R0 example with an illustrative vessel and droplet spectrum (test inputs)."""
        feeds, params = FlashDrum.example_case()
        return feeds, {
            **params,
            "duty_W": -2.0e6,  # the R0 duty leaves one phase; this one leaves all three
            "diameter_m": 0.6,
            "inlet_entrained_fraction": 0.05,
            "droplet_d_rr_m": 3.0e-4,
            "droplet_n_rr": 2.5,
            "gas_viscosity_Pa_s": 1.2e-5,
        }
