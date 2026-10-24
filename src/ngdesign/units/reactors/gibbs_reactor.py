"""Gibbs reactor: species-set equilibrium by Gibbs minimisation (spec U-F, R0).

Plugin kind "unit", name "gibbs_reactor".

Method (spec): ports inlet -> outlet. Params ``species`` (every component
allowed to react), ``inerts`` (fixed-amount spectators), and ``thermal``. Every
feed component must be listed in exactly one of the two; the overlap refusal
and the unlisted-component refusal are both hard. The amounts come from
:func:`ngdesign.units._physics.gibbs.gibbs_minimum` on the same standard-state
potentials the equilibrium reactor's ln K uses (V2 cross-check, 1e-6). Adiabatic
mode solves the outlet temperature around the minimisation (composition
re-equilibrates at every trial T).
"""

from __future__ import annotations

from typing import Any

from scipy.optimize import brentq

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.registry import register
from ngdesign.units._physics.gibbs import gibbs_minimum
from ngdesign.units._physics.kinetics import enthalpy_with_formation
from ngdesign.units.reactors._shared import _T_MAX, _T_MIN, z_from


@register("unit", "gibbs_reactor")
class GibbsReactor:
    """Reactor relaxing its species set to the Gibbs minimum (spec U-F, R0)."""

    inlet_ports = ("inlet",)
    outlet_ports = ("outlet",)

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        inlet = inlets["inlet"]
        species = list(params["species"])
        inerts = list(params.get("inerts", []))
        overlap = sorted(set(species) & set(inerts))
        if overlap:
            raise ValueError(f"{overlap} are both species and inerts")
        unlisted = sorted(set(inlet.composition) - set(species) - set(inerts))
        if unlisted:
            raise ValueError(f"feed components {unlisted} are not listed in species or inerts")
        n_in = inlet.component_flows()
        thermal = params.get("thermal", "isothermal")

        if isinstance(thermal, str) and thermal == "adiabatic":
            outlet, duty = self._adiabatic(species, inerts, n_in, inlet, thermo)
        else:
            n_out = gibbs_minimum(species, inerts, n_in, inlet.T, inlet.P)
            amounts = {**n_out, **{cid: n_in[cid] for cid in inerts}}
            outlet = thermo.flash_pt(z_from(amounts), inlet.T, inlet.P, sum(amounts.values()))
            duty = enthalpy_with_formation(outlet) - enthalpy_with_formation(inlet)
        return UnitResult(outlets={"outlet": outlet}, duty_W=duty)

    def _adiabatic(
        self,
        species: list[str],
        inerts: list[str],
        n_in: dict[str, float],
        inlet: StreamState,
        thermo: Thermo,
    ) -> tuple[StreamState, float]:
        """Outlet state at zero duty: temperature solved around the minimiser."""
        target = enthalpy_with_formation(inlet)

        def f(T: float) -> float:
            n_out = gibbs_minimum(species, inerts, n_in, T, inlet.P)
            amounts = {**n_out, **{cid: n_in[cid] for cid in inerts}}
            z = z_from(amounts)
            return enthalpy_with_formation(thermo.flash_pt(z, T, inlet.P, sum(amounts.values()))) - target

        lo, hi = inlet.T - 400.0, inlet.T + 2000.0
        while f(lo) > 0.0 and lo > _T_MIN:
            lo = max(_T_MIN, lo - 500.0)
        while f(hi) < 0.0:
            if hi >= _T_MAX:
                raise ValueError(f"reactor outlet temperature exceeds {_T_MAX} K closing the heat balance")
            hi = min(_T_MAX, hi + 1000.0)
        T_out = float(brentq(f, lo, hi, xtol=1e-8, maxiter=100))
        n_out = gibbs_minimum(species, inerts, n_in, T_out, inlet.P)
        amounts = {**n_out, **{cid: n_in[cid] for cid in inerts}}
        return thermo.flash_pt(z_from(amounts), T_out, inlet.P, sum(amounts.values())), 0.0

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Water-gas shift at 1100 K — the equilibrium example's Gibbs twin.

        Both reactors solve the same physics by different routes and agree to
        1e-6 in the mole fractions (spec U-F V2).
        """
        feed = {
            "T": 1100.0,
            "P": 1013250.0,
            "molar_flow": 2.0,
            "composition": {"CO": 0.5, "H2O": 0.5},
        }
        params = {
            "species": ["CO", "H2O", "CO2", "H2"],
            "thermal": "isothermal",
        }
        return {"inlet": feed}, params
