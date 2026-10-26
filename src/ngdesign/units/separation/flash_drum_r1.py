"""Flash drum R1: Souders-Brown sizing and droplet carry-over at a given diameter.

Spec ``specs/backend/units/flash_drum.md``; conventions in
``specs/backend/U-R2-level-wave-conventions.md`` (U-R1 still binds).

The R0 adapter (:class:`ngdesign.units.separation.flash_drum.FlashDrum`)
adiabatically PH-mixes the inlets at the lowest inlet pressure and runs one
PT/PH/PVF flash at the outlet pressure. R1 adds, on top of that result, the
same sizing chain as scrubber R1 (spec S1-S6, one owner per equation — the
helpers are imported from :mod:`ngdesign.units.separation.scrubber_r1`, never
copied):

- **Souders-Brown sizing** (GPSA Sect. 7; Svrcek & Monnery 1993) through
  ``size_gas_section``, reported in ``info`` whenever the R0 flash is two-phase
  (a single-phase R0 result cannot carry liquid-side keys; with a given
  ``diameter_m`` it is refused per the table).
- **York demister K** (``york_K_m_s``) when no ``K_m_s`` param is given.
- At a given ``diameter_m``: gas velocity ``v_G = 4 Q_G / (pi D^2)``, Morrison
  drag cut diameter (``cut_diameter_m``), Rosin-Rammler fines
  (``rosin_rammler_fines``) and carry-over ``mdot_co = E mdot_L F(d_cut)``
  (``carryover_mass_flow``).

The flash drum difference is the liquid side: **the liquid is ``liquid_out``
and ``aqueous_out`` together**. The mean liquid density is the mass-weighted
volumetric mean over every liquid phase of both outlets
(``liquid_density_kg_m3``); a zero-flow outlet contributes nothing. The
carry-over leaves each liquid outlet in proportion to its mass — the same
molar fraction ``f = mdot_co / mdot_L`` removed from both — so the outlets are
``model_copy`` scalings (never re-flashed, S-24b) and the gas outlet is the
one genuinely two-phase mix, re-flashed at R0's outlet temperature and the
R0 gas pressure. With ``f == 0`` (no diameter, or E = 0) the level reduces
exactly to R0. No ``@register``: dispatch comes from the catalogue YAML row.
"""

from __future__ import annotations

import math
from typing import Any

from ngdesign.contracts import PhaseKind, StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.separation.flash_drum import FlashDrum
from ngdesign.units.separation.scrubber_r1 import (
    ScrubberR1SpecError,
    carryover_mass_flow,
    cut_diameter_m,
    liquid_density_kg_m3,
    rosin_rammler_fines,
    size_gas_section,
    york_K_m_s,
)

__all__ = ["FlashDrumR1", "FlashDrumR1SpecError"]

#: The param keys this level consumes; everything else belongs to R0.
_R1_PARAM_KEYS = (
    "K_m_s",
    "diameter_m",
    "inlet_entrained_fraction",
    "droplet_d_rr_m",
    "droplet_n_rr",
    "gas_viscosity_Pa_s",
)


class FlashDrumR1SpecError(ValueError):
    """A refused flash-drum R1 specification (typed ValueError, spec U-R1)."""


def _stream_mass_flow(stream: StreamState) -> float:
    """Stream mass flow [kg/s] from its phases: sum n x mole_fraction x MW/1000."""
    return stream.molar_flow * sum(p.mole_fraction * p.molecular_weight for p in stream.phases) / 1000.0


def _vapour_phase(stream: StreamState) -> Any:
    """The stream's vapour phase, or None (a zero-flow outlet carries none)."""
    for p in stream.phases:
        if p.kind is PhaseKind.VAPOR:
            return p
    return None


def _york_K(P_Pa: float) -> float:
    """York demister K at P, re-typed to this level's spec error.

    The refusal table is this level's (``FlashDrumR1SpecError``); the York fit
    is the scrubber's single owner of the constants and raises its own typed
    error, which is re-raised here with the same message.
    """
    try:
        return york_K_m_s(P_Pa)
    except ScrubberR1SpecError as exc:
        raise FlashDrumR1SpecError(str(exc)) from exc


class FlashDrumR1:
    """Flash drum R1: Souders-Brown sizing and carry-over at a given diameter."""

    inlet_ports: tuple[str, ...] = ("inlet", "inlet_2")
    outlet_ports: tuple[str, ...] = ("gas_out", "liquid_out", "aqueous_out")

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """The R0 example feeds (slice wet gas, 7.0 and 5.0 MPa, let down to 3.0 MPa)."""
        return FlashDrum.example_case()

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        """Solve the R1 level on top of the R0 flash (spec algorithm, steps 1-7)."""
        diameter = params.get("diameter_m")
        E = params.get("inlet_entrained_fraction")
        d_rr = params.get("droplet_d_rr_m")
        n_rr = params.get("droplet_n_rr")
        K_param = params.get("K_m_s")
        if diameter is not None and diameter <= 0:
            raise FlashDrumR1SpecError(f"diameter_m must be positive, got {diameter}")
        if K_param is not None and K_param <= 0:
            raise FlashDrumR1SpecError(f"K_m_s must be positive, got {K_param}")
        if E is not None and not 0.0 <= E <= 1.0:
            raise FlashDrumR1SpecError(f"inlet_entrained_fraction must be within [0, 1], got {E}")
        # A diameter carry-over calculation requires the entrainment and
        # droplet-distribution params (refusal table); bind them narrowed.
        entrainment = 0.0
        droplet_d_m = 0.0
        droplet_n = 0.0
        if diameter is not None:
            if E is None or d_rr is None or n_rr is None:
                raise FlashDrumR1SpecError(
                    "a diameter_m carry-over calculation requires inlet_entrained_fraction, "
                    "droplet_d_rr_m and droplet_n_rr"
                )
            entrainment = float(E)
            droplet_d_m = float(d_rr)
            droplet_n = float(n_rr)
        if d_rr is not None and d_rr <= 0:
            raise FlashDrumR1SpecError(f"droplet_d_rr_m must be positive, got {d_rr}")
        if n_rr is not None and n_rr <= 0:
            raise FlashDrumR1SpecError(f"droplet_n_rr must be positive, got {n_rr}")

        # Step 1: the R0 flash owns the phase split; the R1 keys are not R0 params.
        r0_params = {k: v for k, v in params.items() if k not in _R1_PARAM_KEYS}
        r0 = FlashDrum().solve(inlets, r0_params, thermo)
        gas0 = r0.outlets["gas_out"]
        liq0 = r0.outlets["liquid_out"]
        aq0 = r0.outlets["aqueous_out"]
        n_liq = liq0.molar_flow
        n_aq = aq0.molar_flow
        has_liquid = n_liq > 0.0 or n_aq > 0.0
        # Refusal row (spec Refusals): `diameter_m` given and R0 gas_out
        # zero-flow (it then carries no vapour phase), or all liquid outlets
        # zero-flow — the sizing chain is not computable. Without a diameter
        # the level is R0 plus whatever info keys the phases support.
        vap = _vapour_phase(gas0)
        if diameter is not None and (vap is None or not has_liquid):
            raise FlashDrumR1SpecError("sizing needs both a gas and a liquid outlet with non-zero flow")

        # Step 4: K from the param or the York fit at the drum pressure (the
        # R0 gas outlet pressure, i.e. the outlet pressure). Always reported.
        K = float(K_param) if K_param is not None else _york_K(gas0.P)
        info: dict[str, float] = {"T_out_K": r0.info["T_out_K"], "K_m_s": K}
        outlets = dict(r0.outlets)

        # Steps 2/3/5: gas properties, liquid density and Souders-Brown
        # sizing. The spec reports these keys always; on a single-phase R0
        # result only the computable subset is reported — with a given
        # `diameter_m` such a result is refused above.
        if diameter is not None:
            # Step 5: sizing, then velocity, cut diameter, fines, carry-over.
            rho_G = vap.density
            Q_G = _stream_mass_flow(gas0) / rho_G
            rho_L = liquid_density_kg_m3(liq0, aq0)
            size = size_gas_section(K, rho_L, rho_G, Q_G)
            v_max = size["v_max_m_s"]
            mu_G = vap.viscosity
            if mu_G is None:
                override = params.get("gas_viscosity_Pa_s")
                if override is None:
                    raise FlashDrumR1SpecError(
                        "the package gives no gas viscosity; pass gas_viscosity_Pa_s"
                    )
                mu_G = float(override)
            info.update(
                {
                    "rho_gas_kg_m3": rho_G,
                    "rho_liquid_kg_m3": rho_L,
                    "Q_gas_m3_s": Q_G,
                    "v_max_m_s": v_max,
                    "D_min_m": size["min_diameter_m"],
                }
            )
            v_G = 4.0 * Q_G / (math.pi * float(diameter) ** 2)
            cut = cut_diameter_m(v_G, rho_L, rho_G, mu_G)
            d_cut = cut["d_cut_m"]
            F = 1.0 if math.isinf(d_cut) else rosin_rammler_fines(d_cut, droplet_d_m, droplet_n)
            mdot_L = _stream_mass_flow(liq0) + _stream_mass_flow(aq0)
            mdot_co = carryover_mass_flow(mdot_L, entrainment, F)
            f = mdot_co / mdot_L
            info.update(
                {
                    "v_gas_m_s": v_G,
                    "v_ratio": v_G / v_max,
                    "d_cut_m": d_cut,
                    "fines_fraction": F,
                    "carryover_kg_s": mdot_co,
                    "carryover_mol_fraction": f,
                }
            )
            if f > 0.0:
                # Step 6: the liquid outlets are R0's scaled by (1 - f), never
                # re-flashed (S-24b); the gas outlet is the one genuine
                # two-phase mix, re-flashed at R0's outlet T and the R0 gas P.
                n_G = gas0.molar_flow
                n_carried = f * (n_liq + n_aq)
                n_total = n_G + n_carried
                z_mix: dict[str, float] = {}
                for stream, n_stream in ((gas0, n_G), (liq0, f * n_liq), (aq0, f * n_aq)):
                    for cid, x in stream.composition.items():
                        z_mix[cid] = z_mix.get(cid, 0.0) + x * n_stream
                z_mix = {cid: x / n_total for cid, x in z_mix.items()}
                outlets["liquid_out"] = liq0.model_copy(update={"molar_flow": (1.0 - f) * n_liq})
                outlets["aqueous_out"] = aq0.model_copy(update={"molar_flow": (1.0 - f) * n_aq})
                outlets["gas_out"] = thermo.flash_pt(z_mix, r0.info["T_out_K"], gas0.P, n_total)
        else:
            if vap is not None:
                rho_G = vap.density
                Q_G = _stream_mass_flow(gas0) / rho_G
                info["rho_gas_kg_m3"] = rho_G
                info["Q_gas_m3_s"] = Q_G
                if has_liquid:
                    # Step 3: the liquid is liquid_out and aqueous_out together;
                    # a zero-flow outlet contributes no mass and no volume.
                    rho_L = liquid_density_kg_m3(liq0, aq0)
                    size = size_gas_section(K, rho_L, rho_G, Q_G)
                    info["v_max_m_s"] = size["v_max_m_s"]
                    info["D_min_m"] = size["min_diameter_m"]
                    info["rho_liquid_kg_m3"] = rho_L

        # Step 7: the balance duty, recomputed and summed exactly as R0 sums it.
        h_in_W = sum(s.enthalpy * s.molar_flow for s in inlets.values() if s.molar_flow > 0.0)
        h_out_W = sum(s.enthalpy * s.molar_flow for s in outlets.values())
        return UnitResult(
            outlets=outlets,
            duty_W=h_out_W - h_in_W,
            power_W=0.0,
            info=info,
        )
