"""Conversion reactor: fractional conversion per reaction (spec U-F, R0).

Plugin kind "unit", name "conversion_reactor".

Method (spec): ports inlet -> outlet. Params ``reaction_set`` (an inline
reaction set; the solver resolves string ids against the flowsheet's owned
sets), ``conversion`` ({reaction_id: fraction of the base component
converted}), the optional ``sequential`` (true: each conversion applies to the
amounts left by the preceding reactions, in declaration order; default false:
all conversions on the inlet basis), and ``thermal`` (isothermal / adiabatic /
fixed duty / fixed T_out). Components
absent from the reaction set pass through unconverted; the outlet is flashed at
the inlet pressure (no pressure drop at R0). ``info`` carries each reaction's
extent, mol/s.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.reactors._shared import extents_from_conversion, reaction_set_param, thermal_outlet


class ConversionReactor:
    """Reactor driven to a stated fractional conversion (spec U-F, R0)."""

    inlet_ports = ("inlet",)
    outlet_ports = ("outlet",)

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        inlet = inlets["inlet"]
        rset = reaction_set_param(params["reaction_set"])
        n_in = inlet.component_flows()
        extents = extents_from_conversion(
            rset, n_in, params["conversion"], sequential=bool(params.get("sequential", False))
        )
        n_out = apply_extents(n_in, rset, extents)
        outlet, duty = thermal_outlet(inlet, n_out, params.get("thermal", "isothermal"), thermo)
        info = {f"extent_{reaction.id}": xi for reaction, xi in zip(rset.reactions, extents, strict=True)}
        return UnitResult(outlets={"outlet": outlet}, duty_W=duty, info=info)

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """SMR slice: 10 CH4 + 40 H2O + 5 N2 at 1000 K, reforming at X = 0.7.

        Closed-form outlet amounts (mol/s): CH4 3, H2O 33, CO 7, H2 21, N2 5 —
        the V1 yield case shares this basis, so the two adapters' outlets agree
        by construction. Adiabatic mode needs a hot feed: at 298 K the
        reaction's heat uptake exceeds all available sensible heat (the outlet
        would cool below absolute zero), so the feed enters at reforming
        temperature.
        """
        feed = {
            "T": 1000.0,
            "P": 3.0e6,
            "molar_flow": 55.0,
            "composition": {"CH4": 10.0 / 55.0, "H2O": 40.0 / 55.0, "N2": 5.0 / 55.0},
        }
        params = {
            "reaction_set": {
                "id": "smr_case",
                "components": ["CH4", "H2O", "CO", "H2", "N2"],
                "reactions": [
                    {
                        "id": "ref",
                        "stoichiometry": {"CH4": -1.0, "H2O": -1.0, "CO": 1.0, "H2": 3.0},
                        "base_component": "CH4",
                        "provenance": "steam-methane reforming, lumped (closed-form worked example)",
                        "equilibrium": {"form": "from_gibbs"},
                    }
                ],
            },
            "conversion": {"ref": 0.7},
            "thermal": "adiabatic",
        }
        return {"inlet": feed}, params
