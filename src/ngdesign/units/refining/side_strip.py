"""``side_strip`` adapter (spec U-H1).

Steam-stripped side draw, rigour R0: the liquid draw from the main column
enters the top of the stripper, superheated steam enters the bottom, and each
component of the draw is stripped per pseudo by the Kremser equilibrium-stage
shortcut — the stripping form of ``units/_physics/shortcut.kremser_fraction``
(Seader, Henley & Roper eq. (5-46)/(6-13): ``phi_i = kremser_fraction(S_i, N)``
with the stripping factor ``S_i = K_i * V / L``). ``K_i`` comes from
``thermo.k_values`` at the stripper ``T`` and ``P`` (U-E physics, reused, never
re-derived); ``N`` ideal stages is a parameter.

R0 approximations (documented, no sizing physics):
- ``L`` is the liquid downflow, taken as the ``draw_in`` molar flow (constant
  through the section);
- ``V`` is the rising vapour, taken as the steam plus the stripped
  hydrocarbon — solved as a fixed point on ``V`` (the stripped amount depends
  on ``V`` through ``S_i``), deterministic and seeded at the steam flow;
- ``K_i`` is evaluated once on the combined (draw + steam) composition at the
  stripper ``(T, P)``, so the steam's dilution of the liquid is in the K-values;
- the stripping steam is non-condensing at R0 and reports to ``overhead_out``
  (the vapour return to the main column) with the stripped pseudo
  components.

The steam-stripped design rule of thumb is ~10 lb steam per barrel of stripped
liquid (Watkins, *How to Design Crude Distillation*, 1969); the example case
uses it for the steam rate.
"""

from __future__ import annotations

import math
from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.data import component_record
from ngdesign.units._physics.shortcut import kremser_fraction
from ngdesign.units.refining._cuts import RefiningSpecError, optional_float, require_float
from ngdesign.units.refining.slate import WATER_60F_KG_M3, register_slate

#: Assay id of the example crude (the stored Bagajewicz & Ji 2001 light crude).
_EXAMPLE_ASSAY = "bagajewicz_ji_2001_light"

#: Fixed-point cap on the vapour-rate iterations (a contraction: each mol of
#: rising vapour strips at most the draw's moles, and S_i grows sublinearly).
_MAX_V_ITERATIONS = 200

#: Relative convergence band of the vapour-rate fixed point.
_V_TOL = 1e-12


class SideStrip:
    """Strip the light tail off a side draw with superheated steam (Kremser R0)."""

    inlet_ports: tuple[str, ...] = ("draw_in", "steam_in")
    outlet_ports: tuple[str, ...] = ("overhead_out", "bottoms_out")

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """The light crude's full draw (worst case: every pseudo plus its
        light-end tail) at 500 K and 3 bar, stripped with superheated steam at
        the Watkins (1969) rule of 10 lb steam per barrel of stripped liquid.
        Standalone runs register the assay slate through the module-level
        ``register_pseudo`` default (``slate.register_slate``). N = 5 ideal
        stages is an example value, not a cited optimum."""
        from ngdesign.units.refining.assay_feeder import _EXAMPLE_ASSAY
        from ngdesign.units.refining.slate import assay_slate

        register_slate(_EXAMPLE_ASSAY)
        _, mole = assay_slate(_EXAMPLE_ASSAY)
        draw_flow = 500.0
        # Steam rate: 10 lb/bbl (Watkins 1969) -> mol/s on the draw's reference
        # volume; 1 bbl = 42 US gal = 42 x 3.785411784e-3 m3 (exact).
        barrel_m3 = 42.0 * 3.785411784e-3
        draw_volume_m3_s = _mole_volume(mole) * draw_flow
        steam_per_bbl_mol = 10.0 * 0.45359237 / 0.01801528  # lb x kg/lb / kg/mol
        steam_flow = steam_per_bbl_mol * draw_volume_m3_s / barrel_m3
        feeds = {
            "draw_in": {
                "T": 500.0,
                "P": 3.0e5,
                "molar_flow": draw_flow,
                "composition": dict(mole),
            },
            "steam_in": {
                # Superheated relative to saturation at the stripper pressure.
                "T": 530.0,
                "P": 3.0e5,
                "molar_flow": steam_flow,
                "composition": {"H2O": 1.0},
            },
        }
        return feeds, {"T": 500.0, "P": 3.0e5, "N": 5.0}

    def solve(self, inlets: dict[str, StreamState], params: dict[str, Any], thermo: Thermo) -> UnitResult:
        """Split the draw per pseudo by the Kremser stripping fraction, pass the
        steam to the vapour return, and flash both outlets at the stripper
        (T, P); the duty closes ``sum nH in + duty = sum nH out``."""
        draw = inlets.get("draw_in")
        steam = inlets.get("steam_in")
        if draw is None:
            raise RefiningSpecError("draw_in: the side-draw inlet stream is required")
        if steam is None:
            raise RefiningSpecError("steam_in: the stripping-steam inlet stream is required")
        t_out = require_float(params, "T")
        p_out = optional_float(params, "P", draw.P)
        if p_out <= 0.0:
            raise RefiningSpecError("P: must be positive")
        if not math.isfinite(t_out) or t_out <= 0.0:
            raise RefiningSpecError("T: must be a positive temperature")
        n_stages = require_float(params, "N")
        if not math.isfinite(n_stages) or n_stages < 0.0:
            raise RefiningSpecError("N: must be a non-negative stage count")

        draw_flows = {cid: x * draw.molar_flow for cid, x in draw.composition.items()}
        steam_flows = {cid: x * steam.molar_flow for cid, x in steam.composition.items()}

        # K_i from the thermo protocol at the stripper conditions, on the
        # combined (draw + steam) composition. Single-phase states have no
        # equilibrium K-values: refuse rather than clamp.
        combined_total = draw.molar_flow + steam.molar_flow
        if combined_total > 0.0:
            combined = {
                cid: (draw_flows.get(cid, 0.0) + steam_flows.get(cid, 0.0)) / combined_total
                for cid in (*draw.composition, *steam.composition)
            }
            k_values = thermo.k_values(combined, t_out, p_out)
            if k_values is None:
                raise RefiningSpecError(
                    "T/P: the draw plus steam is single phase at the stripper conditions; "
                    "equilibrium K-values (and stripping) are undefined"
                )
        else:
            k_values = {}

        stripped_total, phi = _stripped_amounts(
            draw_flows, k_values, draw.molar_flow, steam.molar_flow, n_stages
        )

        # Overhead_out: stripped pseudo components + all of the steam
        # (non-condensing stripping agent at R0). Bottoms_out: the stripped
        # liquid product.
        overhead_flows = dict(steam_flows)
        bottoms_flows: dict[str, float] = {}
        for cid, n in draw_flows.items():
            overhead_flows[cid] = overhead_flows.get(cid, 0.0) + phi.get(cid, 0.0) * n
            bottoms_flows[cid] = n - phi.get(cid, 0.0) * n
        overhead_flow = sum(overhead_flows.values())
        bottoms_flow = sum(bottoms_flows.values())

        overhead_out = _flash_or_zero(thermo, overhead_flows, overhead_flow, t_out, p_out, steam)
        bottoms_out = _flash_or_zero(thermo, bottoms_flows, bottoms_flow, t_out, p_out, draw)
        duty = (
            overhead_out.enthalpy * overhead_out.molar_flow
            + bottoms_out.enthalpy * bottoms_out.molar_flow
            - draw.enthalpy * draw.molar_flow
            - steam.enthalpy * steam.molar_flow
        )
        stripped_frac = stripped_total / draw.molar_flow if draw.molar_flow > 0.0 else 0.0
        info = {
            "stripped_mol_s": stripped_total,
            "stripped_frac": stripped_frac,
            "steam_mol_s": steam.molar_flow,
            "vapour_return_mol_s": overhead_out.molar_flow,
            "bottoms_mol_s": bottoms_out.molar_flow,
        }
        return UnitResult(
            outlets={"overhead_out": overhead_out, "bottoms_out": bottoms_out},
            duty_W=duty,
            power_W=0.0,
            info=info,
        )


def _stripped_amounts(
    draw_flows: dict[str, float],
    k_values: dict[str, float],
    l_flow: float,
    steam_flow: float,
    n_stages: float,
) -> tuple[float, dict[str, float]]:
    """Total stripped mol/s and the per-component Kremser fractions.

    Fixed point on the rising vapour rate ``V = steam + stripped``: seed at the
    steam flow, recompute the stripping fractions at ``S_i = K_i V / L``, and
    iterate to a 1e-12 relative band (deterministic; refuses if the cap is
    hit). ``L`` is the draw flow (constant-liquid-flow R0 approximation).
    """
    if l_flow <= 0.0:
        return 0.0, {cid: 0.0 for cid in draw_flows}
    if n_stages == 0.0:
        # Zero stages strip exactly nothing by definition; kremser_fraction's
        # exp(log(A)) round-trip would leak ~1e-17 per component instead.
        return 0.0, {cid: 0.0 for cid in draw_flows}
    v = steam_flow
    phi: dict[str, float] = {}
    for _ in range(_MAX_V_ITERATIONS):
        stripped_total = 0.0
        phi = {}
        for cid, n in draw_flows.items():
            k_i = k_values.get(cid, 0.0)
            if k_i > 0.0 and n > 0.0:
                # A stripped fraction is by definition in [0, 1]; the
                # exp(log(A)) round-trip in kremser_fraction can leak ~1e-15
                # of float noise outside it (visible at N = 0).
                phi[cid] = min(1.0, max(0.0, kremser_fraction(k_i * v / l_flow, n_stages)))
            else:
                phi[cid] = 0.0  # a non-volatile component cannot strip
            stripped_total += phi[cid] * n
        v_next = steam_flow + stripped_total
        if abs(v_next - v) <= _V_TOL * max(1.0, v_next):
            return stripped_total, phi
        v = v_next
    raise RefiningSpecError("N: the vapour-rate fixed point did not converge in 200 iterations")


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


def _mole_volume(mole: dict[str, float]) -> float:
    """Reference volume of 1 mol/s of ``mole`` (m3, per mol/s of stream)."""
    volume = 0.0
    for cid, x in mole.items():
        record = component_record(cid)
        volume += x * record["mw"] / (record["sg"] * WATER_60F_KG_M3) / 1000.0
    return volume
