"""Yield reactor: product yields on a mass basis (spec U-F, R0).

Plugin kind "unit", name "yield_reactor".

Method (spec): ports inlet -> outlet. Params ``feed_components`` (the lumped
feed consumed), ``products``, ``yields_mass`` (kg per kg of consumed feed,
aligned with ``products``, summing to 1), and ``thermal``. The outlet mole
amounts come from :func:`ngdesign.units._physics.kinetics.yield_shift`, which
enforces the mass balance and passes undeclared components through untouched.
The mass yields are the only oracle: no element check is implied beyond the
mass closure the shift guarantees (spec-permitted closed form; a reaction set
is intentionally not required).
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.data import component_record
from ngdesign.provenance.recorder import active
from ngdesign.units._physics.kinetics import yield_shift
from ngdesign.units.reactors._shared import thermal_outlet, trace_component_flows, trace_mw


class YieldReactor:
    """Reactor driven to stated product mass yields (spec U-F, R0)."""

    inlet_ports = ("inlet",)
    outlet_ports = ("outlet",)

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        inlet = inlets["inlet"]
        n_in = inlet.component_flows()
        feed_cids = list(params["feed_components"])
        yields_mass = [float(y) for y in params["yields_mass"]]
        products = list(params["products"])
        n_out = yield_shift(n_in, feed_cids=feed_cids, yields_mass=yields_mass, products=products)
        rec = active()
        if rec is not None:
            inputs: dict[str, Any] = {"n_in": trace_component_flows(rec, inlet, n_in)}
            inputs.update({f"Y[{cid}]": y for cid, y in zip(products, yields_mass, strict=True)})
            inputs.update({f"M[{cid}]": trace_mw(rec, cid) for cid in dict.fromkeys([*feed_cids, *products])})
            rec.equation("n_out", n_out, "mol/s", "yield_shift", inputs)
        outlet, duty = thermal_outlet(inlet, n_out, params.get("thermal", "isothermal"), thermo)
        return UnitResult(outlets={"outlet": outlet}, duty_W=duty)

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """SMR slice matching the conversion reactor's example basis.

        Feed 10 CH4 + 40 H2O + 5 N2, yields encoding CH4 + H2O -> CO + 3 H2 at
        X = 0.7: outlet amounts CH4 3, H2O 33, CO 7, H2 21, N2 5 (total 69).
        The mass-yield literals derive at call time from the component
        databank's molar masses, so they stay exact if the databank revises a
        value.
        """
        feed = {
            "T": 298.15,
            "P": 3.0e6,
            "molar_flow": 55.0,
            "composition": {"CH4": 10.0 / 55.0, "H2O": 40.0 / 55.0, "N2": 5.0 / 55.0},
        }
        consumed_mass = 10.0 * float(component_record("CH4")["mw"]) + 40.0 * float(
            component_record("H2O")["mw"]
        )
        params = {
            "feed_components": ["CH4", "H2O"],
            "products": ["CH4", "H2O", "CO", "H2"],
            "yields_mass": [
                n * float(component_record(cid)["mw"]) / consumed_mass
                for cid, n in (("CH4", 3.0), ("H2O", 33.0), ("CO", 7.0), ("H2", 21.0))
            ],
            "thermal": "isothermal",
        }
        return {"inlet": feed}, params
