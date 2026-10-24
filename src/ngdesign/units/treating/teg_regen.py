"""TEG regenerator unit, R0 (spec U-G). Catalogue row ``teg_regen``.

Shortcut regeneration of rich glycol from the TEG contactor:

    rich_in [+ stripping_gas_in] -> lean_out + water_out

R0 method (spec U-G): balances plus a spec, no sizing physics.

- **Lean purity from the reboiler temperature.** The lean glycol leaving the
  reboiler sits on its boiling line: the equilibrium water mole fraction
  ``x_w`` over the TEG phase at the reboiler temperature ``T_reboiler`` and
  pressure ``P`` solves ``gamma_w(T, x_w) * x_w * Psat_H2O(T) / P = 1`` (the
  overhead is essentially pure water; TEG vapor pressure and Poynting terms
  are neglected, exactly as in the owner correlation). ``gamma_w`` and the
  water activity come from ``ngdesign.units.teg_activity`` (Parrish-Won-
  Baltatu) — the one owner of TEG-water equilibrium in the repo; nothing is
  re-derived here. The solved ``x_w`` is a purity **cap**: a rich feed already
  drier than the equilibrium water content cannot boil water at all, so the
  lean glycol keeps its water and only the absorbed lights strip. Every other
  mole of water in the rich feed, and every absorbed light component, leaves
  overhead.

- **Stripping gas is refused at R0.** The GPSA enhancement (lean-glycol
  concentration vs stripping-gas rate, GPSA Engineering Data Book Sect. 20
  chart) is not available in citable open numeric form: the officially posted
  GPSA 14th-edition Section 20 calculation workbook contains no stripping-gas
  chart values, and the open literature reproduces it only as simulation
  results (Moshfeghian, Campbell Tip of the Month, May 2013 — ProMax/SRK
  cases, not a correlation). Per the spec ("... or refused when not cited") a
  positive stripping-gas flow raises a typed error instead of silently
  ignoring the gas or inventing an uncited enhancement. A zero-flow
  ``stripping_gas_in`` stream is accepted so flowsheets can wire the port.

- **Energy.** ``duty_W`` is the enthalpy difference across the unit: sensible
  heating of the rich glycol to the reboiler temperature plus the heat of
  vaporizing the stripped water and lights. Both outlets leave at the reboiler
  temperature and pressure (single equilibrium-stage shortcut; overhead
  cooling and condenser duty are out of scope, the ``mdea_regenerator``
  precedent).

Validity note (measured, carried into the V1 case's ``assessed`` note): the
Parrish correlation was fitted at 300-380 K; at a 477 K reboiler it degenerates
to ``gamma_w ~= 1``, so the shortcut reproduces the ideal-boiling limit
(~99.3 wt% TEG at 204 °C / 1 atm) while the GPSA Section 20 chart reads
98.8 wt% — the model over-purifies by ~0.5 wt% absolute at reboiler
conditions, and reports the ideal-limit purity it can defend.

All SI: K, Pa abs, mol/s, J/mol, W. Pure functions; no I/O; no global state.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.data import component_record
from ngdesign.units.teg_activity import activity_equilibrium_slope

__all__ = ["TEGRegen", "TEGRegenError"]

#: Default reboiler temperature, K (204 C — the conventional TEG reboiler
#: ceiling; above ~206 C / 404 °F TEG degrades, GPSA EDB Sect. 20).
DEFAULT_T_REBOILER = 477.15

#: Default regenerator pressure, Pa abs (atmospheric still).
DEFAULT_P = 101325.0

#: Mole-fraction bracket and iteration count for the boiling-line bisection.
_X_LO, _X_HI, _ITERS = 1e-9, 1.0 - 1e-9, 100

#: The Parrish-Won-Baltatu activity correlation's fitted temperature range, K
#: (the owner's fit, module docstring). A reboiler temperature outside this
#: range extrapolates the correlation; ``info["activity_extrapolated"]`` is
#: 1.0 then and 0.0 inside it.
_PARRISH_T_MIN, _PARRISH_T_MAX = 300.0, 380.0

#: The component that stays in the liquid (everything else is water or lights).
_TEG = "TEG"
_WATER = "H2O"


class TEGRegenError(ValueError):
    """A rich glycol feed or spec the R0 regenerator refuses."""


def _mw(cid: str) -> float:
    """Molecular weight of a databanked component, g/mol."""
    return float(component_record(cid)["mw"])


def _lean_water_mole_fraction(T: float, P: float) -> float:
    """Water mole fraction of the lean glycol on its boiling line at (T, P).

    Solves ``m(x_w) * x_w = 1`` where ``m = gamma_w * Psat_H2O / P`` is the
    activity equilibrium slope (``teg_activity.activity_equilibrium_slope``),
    i.e. ``gamma_w(x_w) * x_w * Psat_H2O(T) = P``. The left side is monotone
    increasing in ``x_w``, so the root is bracketed and bisected. The high
    limit ``x_w -> 1`` reduces the condition to ``Psat_H2O(T) / P``: if that
    is below 1 the water cannot boil at all at this pressure, so the caller
    must refuse before solving.
    """
    # Water saturation pressure at T, from the owner's slope at the pure-water
    # limit: m(x_w -> 1) = Psat/P, so require it above the boiling line.
    slope_pure = activity_equilibrium_slope(T, P, 1.0 - 1e-9)
    if slope_pure <= 1.0:
        raise TEGRegenError(
            f"infeasible regeneration: pressure {P:.4g} Pa is at or above the water saturation "
            f"pressure {P * slope_pure:.4g} Pa at the reboiler temperature {T:.4g} K -- no boiling, "
            "no stripping; lower the pressure or raise the reboiler temperature"
        )
    lo, hi = _X_LO, _X_HI
    for _ in range(_ITERS):
        mid = 0.5 * (lo + hi)
        if activity_equilibrium_slope(T, P, mid) * mid > 1.0:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


def _flows(state: StreamState) -> dict[str, float]:
    """Component molar flows of a stream, mol/s."""
    return {cid: frac * state.molar_flow for cid, frac in state.composition.items()}


class TEGRegen:
    """R0 TEG regenerator: lean purity from the reboiler T at pressure P."""

    inlet_ports: tuple[str, ...] = ("rich_in", "stripping_gas_in")
    outlet_ports: tuple[str, ...] = ("lean_out", "water_out")

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        rich_in = inlets["rich_in"]

        T_reb = float(params.get("T_reboiler", DEFAULT_T_REBOILER))
        P = float(params.get("P", DEFAULT_P))
        if not T_reb > 0.0:
            raise TEGRegenError(f"T_reboiler must be positive, got {T_reb}")
        if not P > 0.0:
            raise TEGRegenError(f"P must be positive, got {P}")

        gas_in = inlets.get("stripping_gas_in")
        if gas_in is not None and gas_in.molar_flow > 0.0:
            raise TEGRegenError(
                "stripping_gas_in: the R0 regenerator refuses stripping gas -- the GPSA EDB Sect. 20 "
                "lean-glycol concentration vs stripping-gas-rate enhancement is not available in "
                "citable open numeric form, and the spec refuses uncited correlations; run without "
                "stripping gas (the equilibrium purity still applies) or model the gas explicitly "
                "as a mixer + flash sequence"
            )

        if not rich_in.phases:
            raise TEGRegenError("rich_in must be a flashed stream (has phases)")
        rich = _flows(rich_in)
        n_teg = rich.get(_TEG, 0.0)
        if n_teg <= 0.0:
            raise TEGRegenError("rich_in carries no TEG; not a rich glycol stream")

        # Lean purity: the boiling line at (T_reb, P), via the owner correlation.
        x_w_lean = _lean_water_mole_fraction(T_reb, P)
        n_water_in = rich.get(_WATER, 0.0)
        n_water_at_equilibrium = n_teg * x_w_lean / (1.0 - x_w_lean)
        # The boiling line is a purity CAP, not a demand: a feed already drier
        # than the equilibrium water content cannot boil water (the activity
        # product sits below the pressure), so the glycol heats through and
        # keeps every mole of its water -- only the lights strip.
        n_water_lean = min(n_water_at_equilibrium, n_water_in)

        # Lean outlet: all the TEG plus the equilibrium-held water.
        n_lean = n_teg + n_water_lean
        lean_comp = {_TEG: n_teg / n_lean, _WATER: n_water_lean / n_lean}
        lean_out = thermo.flash_pt(lean_comp, T_reb, P, n_lean)

        # Overhead: the rest of the water and every absorbed light component.
        overhead = {cid: n for cid, n in rich.items() if cid not in (_TEG, _WATER)}
        n_water_overhead = n_water_in - n_water_lean
        if n_water_overhead > 0.0:
            overhead[_WATER] = overhead.get(_WATER, 0.0) + n_water_overhead
        total_overhead = sum(overhead.values())
        if total_overhead > 0.0:
            overhead_comp = {cid: n / total_overhead for cid, n in overhead.items()}
            water_out = thermo.flash_pt(overhead_comp, T_reb, P, total_overhead)
        elif n_water_in > 0.0:
            # Drier than the cap and no absorbed lights: nothing strips, yet
            # the overhead port still exists -- as a zero-flow stream (the
            # plugin convention for empty ports).
            water_out = StreamState(
                T=T_reb,
                P=P,
                molar_flow=0.0,
                composition={_WATER: 1.0},
                vapor_fraction=1.0,
                enthalpy=0.0,
                entropy=0.0,
                phases=[],
            )
        else:
            raise TEGRegenError(
                "rich_in carries no water or light components to strip: the regenerator has nothing "
                "to regenerate"
            )

        duty_W = (
            lean_out.enthalpy * lean_out.molar_flow
            + water_out.enthalpy * water_out.molar_flow
            - rich_in.enthalpy * rich_in.molar_flow
        )
        # A wired-but-zero-flow stripping_gas_in contributes nothing to the
        # balance (molar_flow 0); a positive flow was refused above.

        mw_teg, mw_water = _mw(_TEG), _mw(_WATER)
        mass_teg = n_teg * mw_teg
        lean_mass_fraction = mass_teg / (mass_teg + n_water_lean * mw_water)
        rich_mass = sum(n * _mw(cid) for cid, n in rich.items())
        info: dict[str, float] = {
            "lean_teg_mass_fraction": lean_mass_fraction,
            "lean_water_mole_fraction": x_w_lean,
            "rich_teg_mass_fraction": mass_teg / rich_mass,
            "water_stripped_mol_s": n_water_overhead,
            "water_held_in_lean_mol_s": n_water_lean,
            "lean_out_mol_s": n_lean,
            "overhead_mol_s": total_overhead,
            "reboiler_T_K": T_reb,
            "regenerator_P_Pa": P,
            "activity_extrapolated": 0.0 if _PARRISH_T_MIN <= T_reb <= _PARRISH_T_MAX else 1.0,
        }
        return UnitResult(
            outlets={"lean_out": lean_out, "water_out": water_out},
            duty_W=duty_W,
            info=info,
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Rich glycol at 97.5 wt% TEG (the conventional rich end) at 300 F / 1.5 bara.

        The 300 F (422.15 K) rich-feed temperature and the mass-fraction basis
        follow the GPSA EDB 14th ed. Sect. 20 regeneration example basis
        (Example 20-12: rich TEG enters the regenerator at 300 F, reboiler at
        400 F); the 1.5 bara feed pressure is a typical still-column pressure.
        """
        wt_teg = 0.975
        n_teg = wt_teg / _mw(_TEG)
        n_water = (1.0 - wt_teg) / _mw(_WATER)
        total = n_teg + n_water
        feeds: dict[str, dict[str, Any]] = {
            "rich_in": {
                "T": 422.15,
                "P": 1.5e5,
                "molar_flow": 100.0,
                "composition": {_TEG: n_teg / total, _WATER: n_water / total},
            },
            # Optional inlet, present with zero flow: the GPSA basis uses no
            # stripping gas, and the adapter refuses any positive flow at R0
            # (the enhancement correlation is not implemented).
            "stripping_gas_in": {
                "T": 422.15,
                "P": 1.5e5,
                "molar_flow": 0.0,
                "composition": {"N2": 1.0},
            },
        }
        params: dict[str, Any] = {
            "T_reboiler": DEFAULT_T_REBOILER,
            "P": DEFAULT_P,
        }
        return feeds, params
