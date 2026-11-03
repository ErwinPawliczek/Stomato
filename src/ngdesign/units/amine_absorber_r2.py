"""Amine absorbers, R2: a countercurrent column of MESH stages on the reactive amine package.

Plugin kind "unit", rows ``mdea_absorber`` / ``mea_absorber`` / ``dea_absorber``,
level R2. Ports ``gas_in`` + ``lean_amine_in`` -> ``gas_out`` + ``rich_amine_out``,
as R0.

Where R0 closes one Kent-Eisenberg equilibrium stage at the rich end, this level
solves every stage: the column row's MESH solvers (Boston & Sullivan 1974
inside-out, Naphtali & Sandholm 1971 Newton) with each stage's K-values
K_i(T, x) and phase enthalpies read from the reactive amine package (the
chemistry lives in the package, not the stage; the aqueous enthalpy carries the
van 't Hoff heat of absorption, so the absorption exotherm is solved, not
assumed). The lean solvent enters the top stage, the sour gas the bottom stage;
there is no condenser or reboiler. The column runs at the gas pressure.

Energy: ``duty_W`` = (enthalpy out) - (enthalpy in) over the boundary streams
as given. The column itself is adiabatic (its closure, ``column_closure_W``,
reads below 1 W); the rest is ``basis_shift_W``, the inlets' enthalpy on the
package against the caller's basis (the package's aqueous phase carries the
bound-acid-gas heat a non-reactive package does not).

Measured (example feeds, 8 stages, amine_ke): components close to 1e-15
relative of the feed; see the catalogue rows for times and the stage audit.

All SI: K, Pa abs, mol/s, J/mol, W. Pure functions; no I/O; no global state.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.amine_regenerator_r2 import _amine_package
from ngdesign.units.column import Column

_ALLOWED_KEYS = frozenset({"n_stages"})

#: Default equilibrium stages (rich end at the bottom stage).
DEFAULT_N_STAGES = 8


class AmineAbsorberR2Error(ValueError):
    """Refusal: the absorber spec is invalid."""


class MdeaAbsorberR2:
    """Countercurrent MESH absorber of the sour gas into the lean solvent over the column API."""

    AMINE = "MDEA"
    inlet_ports = ("gas_in", "lean_amine_in")
    outlet_ports = ("gas_out", "rich_amine_out")

    def solve(self, inlets: dict[str, StreamState], params: dict[str, Any], thermo: Thermo) -> UnitResult:
        gas, lean = inlets.get("gas_in"), inlets.get("lean_amine_in")
        if gas is None or gas.molar_flow <= 0.0:
            raise AmineAbsorberR2Error("gas_in is required and must carry flow")
        if lean is None or lean.molar_flow <= 0.0:
            raise AmineAbsorberR2Error("lean_amine_in is required and must carry flow")
        for key in params:
            if key not in _ALLOWED_KEYS:
                raise AmineAbsorberR2Error(f"absorber R2 refuses unknown parameter {key!r}")
        if lean.composition.get(self.AMINE, 0.0) <= 0.0:
            raise AmineAbsorberR2Error(f"lean_amine_in carries no {self.AMINE}")
        n_stages = params.get("n_stages", DEFAULT_N_STAGES)
        if not isinstance(n_stages, int) or isinstance(n_stages, bool) or n_stages < 2:
            raise AmineAbsorberR2Error(f"n_stages must be an integer >= 2, got {n_stages!r}")

        package = _amine_package(thermo)
        pressure = gas.P
        gas_feed = package.flash_pt(dict(gas.composition), gas.T, pressure, gas.molar_flow)
        lean_feed = package.flash_pt(dict(lean.composition), lean.T, pressure, lean.molar_flow)
        result = Column().solve(
            {"feed": gas_feed},
            {
                "n_stages": n_stages,
                "condenser": "none",
                "reboiler": "none",
                "feed_stage": n_stages,
                "pressure_profile": pressure,
                "feeds": [
                    {
                        "T": lean.T,
                        "P": pressure,
                        "molar_flow": lean.molar_flow,
                        "composition": dict(lean.composition),
                        "stage": 1,
                    }
                ],
            },
            package,
        )
        sweet, rich = result.outlets["distillate"], result.outlets["bottoms"]
        h_in = gas.molar_flow * gas.enthalpy + lean.molar_flow * lean.enthalpy
        h_out = sweet.molar_flow * sweet.enthalpy + rich.molar_flow * rich.enthalpy
        basis_shift = (
            gas_feed.molar_flow * gas_feed.enthalpy + lean_feed.molar_flow * lean_feed.enthalpy - h_in
        )
        stage_ts = [float(result.info[f"stage_{j}_T_K"]) for j in range(n_stages)]
        amine_out = rich.composition[self.AMINE]

        info = {key: value for key, value in result.info.items() if key.startswith("stage_")}
        info.update(
            n_stages=float(n_stages),
            ns_used=result.info["ns_used"],
            column_closure_W=float(result.info["reboiler_duty_W"]),
            basis_shift_W=basis_shift,
            column_P_Pa=pressure,
            max_stage_T_K=max(stage_ts),
            rich_co2_loading=rich.composition.get("CO2", 0.0) / amine_out,
            rich_h2s_loading=rich.composition.get("H2S", 0.0) / amine_out,
            gas_out_co2_molpct=100.0 * sweet.composition.get("CO2", 0.0),
            gas_out_h2s_ppmv=1e6 * sweet.composition.get("H2S", 0.0),
        )
        return UnitResult(
            outlets={"gas_out": sweet, "rich_amine_out": rich},
            duty_W=h_out - h_in,
            power_W=0.0,
            info=info,
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """R0's sour gas and lean solvent of this amine, 8 equilibrium stages."""
        from ngdesign.units.mdea_absorber import DeaAbsorber, MdeaAbsorber, MeaAbsorber

        r0 = {"MDEA": MdeaAbsorber, "MEA": MeaAbsorber, "DEA": DeaAbsorber}[cls.AMINE]
        feeds, _ = r0.example_case()
        return feeds, {"n_stages": DEFAULT_N_STAGES}


class MeaAbsorberR2(MdeaAbsorberR2):
    """MEA absorber R2: the MESH absorber on aqueous MEA."""

    AMINE = "MEA"


class DeaAbsorberR2(MdeaAbsorberR2):
    """DEA absorber R2: the MESH absorber on aqueous DEA."""

    AMINE = "DEA"
