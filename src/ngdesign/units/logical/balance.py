"""Balance unit plugin (spec U-A).

Closes one unknown outlet: the inlet minus the declared ``known_outlets``
(given as FeedSpec kwargs in params), per component. The outlet is then PH
flashed at ``params.P`` so the energy closes too: the flash enthalpy carries
whatever the component balance implies. A negative component flow is refused,
naming the component.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo


class Balance:
    """Closes an unknown outlet stream by component balance + PH flash."""

    inlet_ports = ("inlet",)
    outlet_ports = ("outlet",)

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        inlet = inlets["inlet"]
        known = params.get("known_outlets") or []
        if not isinstance(known, list):
            raise ValueError("known_outlets must be a list of FeedSpec kwargs")
        P = params.get("P", inlet.P)
        P = float(P)
        if P <= 0.0:
            raise ValueError(f"P must be > 0, got {P}")

        n_out = inlet.molar_flow
        composition = {cid: x * inlet.molar_flow for cid, x in inlet.composition.items()}
        for i, spec in enumerate(known):
            n_known = float(spec["molar_flow"])
            n_out -= n_known
            known_comp = spec["composition"]
            known_total = sum(float(x) for x in known_comp.values())
            for cid in set(composition) | set(known_comp):
                composition[cid] = (
                    composition.get(cid, 0.0) - float(known_comp.get(cid, 0.0)) / known_total * n_known
                )

        negative = {cid: f for cid, f in composition.items() if f < 0.0}
        if negative:
            cid = min(negative, key=negative.get)
            raise ValueError(
                f"balance closes negative: component {cid!r} flow would be "
                f"{negative[cid]!r} mol/s; the known outlets exceed the inlet"
            )
        if n_out <= 0.0:
            raise ValueError(f"balance closes at {n_out!r} mol/s total; known outlets exceed the inlet")

        outlet = thermo.flash_ph(
            {cid: f / n_out for cid, f in composition.items()}, P, inlet.enthalpy, n_out
        )
        return UnitResult(outlets={"outlet": outlet}, duty_W=0.0, power_W=0.0, info={})

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Identity form (known_outlets empty): the locked V0 property test
        requires the example case to conserve moles; the subtracting forms are
        covered by the closed-form tests."""
        from ngdesign.units.jt_valve import dry_gas_feed

        feed = dry_gas_feed(322.15, 7.0e6)
        return {"inlet": feed}, {"known_outlets": [], "P": feed["P"]}
