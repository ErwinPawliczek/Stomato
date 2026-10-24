"""Gibbs reactor: species-set equilibrium by Gibbs minimisation (spec U-F, R0).

Plugin kind "unit", name "gibbs_reactor".

Method (spec): ports inlet -> outlet. Params ``species`` (every component
allowed to react), ``inerts`` (fixed-amount spectators), and ``thermal``:
``isothermal`` (T_out = inlet T), ``adiabatic`` (duty 0), ``{"duty_W": q}``
(fixed duty) or ``{"T_out": K}`` (fixed outlet temperature). Every feed
component must be listed in exactly one of the two; the overlap refusal and the
unlisted-component refusal are both hard. The amounts come from
:func:`ngdesign.units._physics.gibbs.gibbs_minimum` on the same standard-state
potentials the equilibrium reactor's ln K uses (V2 cross-check, 1e-6). Adiabatic
and duty modes solve the outlet temperature around the minimisation
(composition re-equilibrates at every trial T).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from scipy.optimize import brentq

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units._physics.gibbs import gibbs_minimum
from ngdesign.units._physics.kinetics import enthalpy_with_formation
from ngdesign.units.reactors._shared import _T_MAX, _T_MIN, z_from


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
        h_in_W = enthalpy_with_formation(inlet)

        def state_at(T: float) -> StreamState:
            """Outlet state with the minimisation re-solved at temperature T."""
            n_out = gibbs_minimum(species, inerts, n_in, T, inlet.P)
            amounts = {**n_out, **{cid: n_in[cid] for cid in inerts}}
            return thermo.flash_pt(z_from(amounts), T, inlet.P, sum(amounts.values()))

        if isinstance(thermal, Mapping) and set(thermal) == {"T_out"}:
            outlet = state_at(float(thermal["T_out"]))
            duty = enthalpy_with_formation(outlet) - h_in_W
        elif isinstance(thermal, str) and thermal == "isothermal":
            outlet = state_at(inlet.T)
            duty = enthalpy_with_formation(outlet) - h_in_W
        elif (
            isinstance(thermal, str)
            and thermal == "adiabatic"
            or (isinstance(thermal, Mapping) and set(thermal) == {"duty_W"})
        ):
            duty = 0.0 if isinstance(thermal, str) else float(thermal["duty_W"])
            target = h_in_W + duty

            def f(T: float) -> float:
                return enthalpy_with_formation(state_at(T)) - target

            lo, hi = inlet.T - 400.0, inlet.T + 2000.0
            while f(lo) > 0.0 and lo > _T_MIN:
                lo = max(_T_MIN, lo - 500.0)
            if f(lo) > 0.0:
                raise ValueError(
                    "heat balance is infeasible: even at 1 K the outlet enthalpy exceeds "
                    "the inlet enthalpy (the reaction heat exceeds all available sensible heat)"
                )
            while f(hi) < 0.0:
                if hi >= _T_MAX:
                    raise ValueError(
                        f"reactor outlet temperature exceeds {_T_MAX} K closing the heat balance"
                    )
                hi = min(_T_MAX, hi + 1000.0)
            T_out = float(brentq(f, lo, hi, xtol=1e-8, maxiter=100))
            outlet = state_at(T_out)
        else:
            raise ValueError(
                f"thermal mode {thermal!r} is not one of 'isothermal', 'adiabatic', "
                '{"duty_W": W} or {"T_out": K}'
            )
        return UnitResult(outlets={"outlet": outlet}, duty_W=duty)

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
