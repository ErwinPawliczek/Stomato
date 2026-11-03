"""MDEA regenerator, R2: a reboiled stripper of MESH stages on the reactive amine package.

Plugin kind "unit", row ``mdea_regenerator``, level R2. Port ``rich_amine_in``
-> ``lean_amine_out`` + ``acid_gas_out``, as R0.

Where R0 inverts one Kent-Eisenberg equilibrium at the reboiler temperature,
this level solves every stage: the column row's MESH solvers (Boston & Sullivan
1974 inside-out, Naphtali & Sandholm 1971 Newton) with the stage K-values and
enthalpies read from the reactive amine package (the chemistry lives in the
package, not the stage). The rich solvent is let down to ``regenerator_P``,
heated to ``feed_T`` (the lean/rich exchanger outlet, folded into this unit as
R0 folds its sensible heating) and fed to the top stage; a kettle reboiler
boils ``boilup_rate`` of vapour up the column. There is no overhead condenser:
``acid_gas_out`` is the wet top vapour, water included; a condenser and reflux
drum downstream return the water.

Energy: ``duty_W`` = (enthalpy out) - (enthalpy in) over the boundary streams
as given; ``info`` splits it into the feed preheat (inlet basis to the
package's feed state) and the reboiler duty, whose kettle balance closes the
column.

Measured (P1-13 tree, 6 stages, 1.9 bar, 100 mol/s rich solvent at 370 K):
components close to 1e-11 at boilup 15/20/30 mol/s in 2-6 s; the stage audit
(material balances from the reported profile, and a re-flash of each stage's
contents on the package) reads 1.6e-12 and 1.7e-4 at worst. Not shipped:
a rich feed left at 303 K (170 s, M = 0.53); DEA, whose top stage contents
re-flash single-phase on the package (audit 1.0) although the column closes;
MEA, which does not converge (M = 52).

All SI: K, Pa abs, mol/s, J/mol, W. Pure functions; no I/O; no global state.
"""

from __future__ import annotations

from typing import Any

from ngdesign import registry
from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.column import Column

_ALLOWED_KEYS = frozenset({"n_stages", "boilup_rate", "regenerator_P", "feed_T"})

#: Defaults: a typical amine still pressure and lean/rich exchanger outlet.
DEFAULT_REGENERATOR_P = 1.9e5
DEFAULT_FEED_T = 370.0


class AmineRegeneratorR2Error(ValueError):
    """Refusal: the regenerator spec is invalid."""


def _amine_package(thermo: Thermo) -> Thermo:
    """The reactive amine package: the caller's, or amine_ke over its default carrier."""
    if getattr(thermo, "is_amine_reactive_package", False):
        return thermo
    package: Thermo = registry.create("thermo", "amine_ke")
    return package


class MdeaRegeneratorR2:
    """Reboiled MESH stripper of the rich solvent over the public column API."""

    AMINE = "MDEA"
    inlet_ports = ("rich_amine_in",)
    outlet_ports = ("lean_amine_out", "acid_gas_out")

    def solve(self, inlets: dict[str, StreamState], params: dict[str, Any], thermo: Thermo) -> UnitResult:
        rich = inlets.get("rich_amine_in")
        if rich is None or rich.molar_flow <= 0.0:
            raise AmineRegeneratorR2Error("rich_amine_in is required and must carry flow")
        for key in params:
            if key not in _ALLOWED_KEYS:
                raise AmineRegeneratorR2Error(f"regenerator R2 refuses unknown parameter {key!r}")
        if rich.composition.get(self.AMINE, 0.0) <= 0.0:
            raise AmineRegeneratorR2Error(f"rich_amine_in carries no {self.AMINE}")
        n_stages = params.get("n_stages", 6)
        if not isinstance(n_stages, int) or isinstance(n_stages, bool) or n_stages < 2:
            raise AmineRegeneratorR2Error(f"n_stages must be an integer >= 2, got {n_stages!r}")
        boilup = float(params.get("boilup_rate", 0.0))
        if not boilup > 0.0:
            raise AmineRegeneratorR2Error("boilup_rate (mol/s) must be positive")
        pressure = float(params.get("regenerator_P", DEFAULT_REGENERATOR_P))
        feed_t = float(params.get("feed_T", DEFAULT_FEED_T))
        if not pressure > 0.0 or not feed_t > 0.0:
            raise AmineRegeneratorR2Error("regenerator_P and feed_T must be positive")

        package = _amine_package(thermo)
        feed = package.flash_pt(dict(rich.composition), feed_t, pressure, rich.molar_flow)
        result = Column().solve(
            {"feed": feed},
            {
                "n_stages": n_stages,
                "condenser": "none",
                "reboiler": "kettle",
                "feed_stage": 1,
                "pressure_profile": pressure,
                "specs": {"boilup_rate": boilup},
            },
            package,
        )
        lean, acid = result.outlets["bottoms"], result.outlets["distillate"]
        h_in = rich.molar_flow * rich.enthalpy
        h_out = lean.molar_flow * lean.enthalpy + acid.molar_flow * acid.enthalpy
        preheat = feed.molar_flow * feed.enthalpy - h_in
        reboiler = float(result.info["reboiler_duty_W"])

        def loading(state: StreamState, cid: str) -> float:
            return state.composition.get(cid, 0.0) / state.composition[self.AMINE]

        info = {key: value for key, value in result.info.items() if key.startswith("stage_")}
        info.update(
            n_stages=float(n_stages),
            ns_used=result.info["ns_used"],
            boilup_mol_s=boilup,
            reboiler_duty_W=reboiler,
            preheat_duty_W=preheat,
            rich_co2_loading=loading(rich, "CO2"),
            rich_h2s_loading=loading(rich, "H2S"),
            lean_co2_loading=loading(lean, "CO2"),
            lean_h2s_loading=loading(lean, "H2S"),
            regenerator_P_Pa=pressure,
            reboiler_T_K=lean.T,
        )
        return UnitResult(
            outlets={"lean_amine_out": lean, "acid_gas_out": acid},
            duty_W=h_out - h_in,
            power_W=0.0,
            info=info,
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """R0's rich solvent (CO2 0.40 / H2S 0.15 mol per mol amine), 6 stages, 20 mol/s boilup."""
        from ngdesign.units.mdea_regenerator import MdeaRegenerator

        feeds, _ = MdeaRegenerator.example_case()
        return feeds, {"n_stages": 6, "boilup_rate": 20.0}
