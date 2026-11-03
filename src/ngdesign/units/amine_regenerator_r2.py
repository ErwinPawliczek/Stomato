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
as given; ``info`` splits it into the basis shift (the rich inlet re-read on
the package at its own T and P - the package's aqueous phase carries the bound
acid-gas heat a non-reactive package does not), the feed preheat (package, inlet
state to ``feed_T``) and the reboiler duty, whose kettle balance closes the
column.

Measured (6 stages, 1.9 bar, 100 mol/s rich solvent at 370 K, stage K and
enthalpies on the package's direct surface): components close to 1e-12 or
better; the stage audit (reported-profile material balances, package re-flash
of each stage's contents) passes below 1e-9 / 1e-6. MDEA at boilup 15/20/30
and DEA at 10-30 mol/s converge cold in 2-16 s; MEA converges cold at 35-60
mol/s (6-14 s). Below that the cold heat-of-reaction ladder stalls (MEA at 30
mol/s: scale-0 NS at M = 5.9 after 25 s) and the column core's boilup
continuation solves a 2x / 4x anchor cold and walks the kettle tear down warm:
MEA at 30/25/20/15/10 mol/s in 32/35/45/74/87 s, components closed to 1e-13.
The acid gas is vapour at every boilup (below 26 mol/s DEA's top vapour used to
re-flash as a false liquid on the package, 11 kJ/mol below its vapour
enthalpy, understating the reboiler duty by ~215 kW at 24 mol/s). A rich feed
left at 303 K was measured not to converge (170 s, M = 0.53, P1-13 tree).

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
        rich_on_package = package.flash_pt(dict(rich.composition), rich.T, rich.P, rich.molar_flow)
        basis_shift = rich_on_package.molar_flow * rich_on_package.enthalpy - h_in
        preheat = feed.molar_flow * feed.enthalpy - rich_on_package.molar_flow * rich_on_package.enthalpy
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
            basis_shift_W=basis_shift,
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

    #: Example kettle vapour, mol/s per 100 mol/s of rich solvent.
    EXAMPLE_BOILUP = 20.0

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """R0's rich solvent (CO2 0.40 / H2S 0.15 mol per mol amine), 6 stages, the class's boilup."""
        from ngdesign.units.mdea_regenerator import DeaRegenerator, MdeaRegenerator, MeaRegenerator

        r0 = {"MDEA": MdeaRegenerator, "MEA": MeaRegenerator, "DEA": DeaRegenerator}[cls.AMINE]
        feeds, _ = r0.example_case()
        return feeds, {"n_stages": 6, "boilup_rate": cls.EXAMPLE_BOILUP}


class MeaRegeneratorR2(MdeaRegeneratorR2):
    """MEA regenerator R2: the reboiled MESH stripper on aqueous MEA.

    Example boilup 40 mol/s: the primary amine binds CO2 as carbamate and needs
    more stripping vapour. Lower boilups converge (via the boilup continuation
    below 35 mol/s) but strip less than the shared physics check's lean CO2
    bound of 0.1 x rich = 0.040: measured lean CO2 0.0400 at 36, 0.0421 at 35,
    0.057 at 30 and 0.104 at 20 mol/s; 0.0366 at 38 and 0.0338 at 40.
    """

    AMINE = "MEA"
    EXAMPLE_BOILUP = 40.0


class DeaRegeneratorR2(MdeaRegeneratorR2):
    """DEA regenerator R2: the reboiled MESH stripper on aqueous DEA.

    Example boilup 25 mol/s (lean H2S 0.0271, CO2 0.0043, 1.01 MW). DEA strips
    H2S slower than CO2 on the package: the shared physics check's lean H2S
    bound of 0.2 x rich = 0.030 is met down to 24 mol/s (0.0289) and missed
    at 22 (0.0321) and 20 (0.0345), where the column still converges.
    """

    AMINE = "DEA"
    EXAMPLE_BOILUP = 25.0
