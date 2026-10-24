"""Membrane (gas) (plan §2 U-D 8, spec U-D).

Plugin kind "unit", name "membrane" — registered from the catalogue YAML; no
decorator (round-1 conventions).

R0 method (spec): a per-component ``permeate_recovery`` split (the fraction of
each component's molar flow that crosses the membrane) via
``splitting.split_by_component`` — the permeate leaves at ``P_permeate``, the
residue at the feed pressure — or the Weller-Steiner complete-mixing binary
model from a ``stage_cut`` with a ``perm_ratio`` (Geankoplis, "Transport
Processes and Separation Process Principles", 4th ed., Example 13.4-2,
p. 767: air at a 10:1 pressure ratio, alpha = 10, stage cut 0.2 gives a
permeate y_O2 = 0.5068 and a reject x_O2 = 0.1345). Cross-flow (R1) and
counter-current module (R2) models are planned levels (spec U-D).
"""

from __future__ import annotations

import math
from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units._physics.splitting import split_by_component


class MembraneSpecError(ValueError):
    """The membrane spec is bad; the message names the parameter."""


class Membrane:
    """Permeate/recovery split with a Weller-Steiner stage-cut option."""

    inlet_ports: tuple[str, ...] = ("feed_in",)
    outlet_ports: tuple[str, ...] = ("permeate", "residue")

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        inlet = inlets["feed_in"]
        recovery = params.get("permeate_recovery")
        stage_cut = params.get("stage_cut")
        if recovery is not None and stage_cut is not None:
            raise MembraneSpecError("give exactly one of permeate_recovery and stage_cut, not both")
        if recovery is None and stage_cut is None:
            raise MembraneSpecError(
                "give permeate_recovery (component fractions crossing to the permeate) "
                "or stage_cut with perm_ratio"
            )
        P_permeate = params.get("P_permeate")
        if not isinstance(P_permeate, (int, float)):
            raise MembraneSpecError("P_permeate is required: the permeate-side absolute pressure, Pa")
        P_permeate = float(P_permeate)
        if P_permeate <= 0:
            raise MembraneSpecError(f"P_permeate {P_permeate} must be positive")
        if P_permeate >= inlet.P:
            raise MembraneSpecError(f"P_permeate {P_permeate} must be below the feed pressure {inlet.P}")

        info: dict[str, Any] = {}
        if recovery is not None:
            fractions = self._recovery_fractions(inlet, recovery)
        else:
            assert stage_cut is not None
            fractions = self._stage_cut_fractions(
                inlet, float(stage_cut), perm_ratio=params.get("perm_ratio"), phi=inlet.P / P_permeate
            )
            fast = max(fractions, key=lambda cid: fractions[cid] * inlet.composition[cid])
            y_fast = fractions[fast] * inlet.composition[fast] / float(stage_cut)
            # UnitResult.info is dict[str, float]; the model and component
            # names stay out of it (the catalogue note documents the model).
            info = {
                "stage_cut": float(stage_cut),
                "permeate_y_fast": y_fast,
                "residue_x_fast": (inlet.composition[fast] - float(stage_cut) * y_fast)
                / (1.0 - float(stage_cut)),
            }

        permeate, residue = split_by_component(
            inlet,
            fractions,
            thermo,
            outlet_P={"top": P_permeate, "bottom": inlet.P},
        )
        outlets = {"permeate": permeate, "residue": residue}
        h_in_W = inlet.enthalpy * inlet.molar_flow
        h_out_W = sum(s.enthalpy * s.molar_flow for s in outlets.values())
        return UnitResult(outlets=outlets, duty_W=h_out_W - h_in_W, power_W=0.0, info=info)

    def _recovery_fractions(self, feed: StreamState, recovery: Any) -> dict[str, float]:
        if not isinstance(recovery, dict) or not recovery:
            raise MembraneSpecError(
                "permeate_recovery is required: a non-empty map of component id to the "
                "fraction crossing to the permeate"
            )
        unknown = [cid for cid in recovery if cid not in feed.composition]
        if unknown:
            raise MembraneSpecError(f"permeate_recovery names component(s) {unknown} not in the feed")
        bad = {cid: f for cid, f in recovery.items() if not 0.0 <= float(f) <= 1.0}
        if bad:
            raise MembraneSpecError(f"permeate_recovery entries {bad} outside [0, 1]")
        return {cid: float(recovery.get(cid, 0.0)) for cid in feed.composition}

    def _stage_cut_fractions(
        self,
        feed: StreamState,
        stage_cut: float,
        perm_ratio: Any,
        phi: float,
    ) -> dict[str, float]:
        """Weller-Steiner complete-mixing recoveries from a stage cut."""
        if not 0.0 < stage_cut < 1.0:
            raise MembraneSpecError(f"stage cut {stage_cut} outside (0, 1)")
        if not isinstance(perm_ratio, dict) or not perm_ratio:
            raise MembraneSpecError(
                "perm_ratio is required with stage_cut: a non-empty map of component id to relative permeance"
            )
        unknown = [cid for cid in perm_ratio if cid not in feed.composition]
        if unknown:
            raise MembraneSpecError(f"perm_ratio names component(s) {unknown} not in the feed")
        missing = [cid for cid in feed.composition if cid not in perm_ratio]
        if missing:
            raise MembraneSpecError(f"perm_ratio is missing feed component(s) {missing}")
        bad = {cid: r for cid, r in perm_ratio.items() if float(r) <= 0}
        if bad:
            raise MembraneSpecError(f"perm_ratio entries {bad} must be > 0")
        if len(feed.composition) != 2:
            raise MembraneSpecError(
                "the stage-cut model is binary; give permeate_recovery for multicomponent feeds"
            )
        fast, slow = sorted(feed.composition, key=lambda cid: -float(perm_ratio[cid]))
        alpha = float(perm_ratio[fast]) / float(perm_ratio[slow])
        z_fast = feed.composition[fast]
        y_fast = _permeate_fraction(stage_cut, phi, alpha, z_fast, 1.0 - z_fast)
        recovery_fast = stage_cut * y_fast / z_fast
        recovery_slow = stage_cut * (1.0 - y_fast) / (1.0 - z_fast)
        out_of_range = {
            cid: f for cid, f in ((fast, recovery_fast), (slow, recovery_slow)) if not 0.0 <= f <= 1.0
        }
        if out_of_range:
            raise MembraneSpecError(
                f"stage cut {stage_cut} implies permeate recoveries {out_of_range} outside [0, 1]"
            )
        return {fast: recovery_fast, slow: recovery_slow}

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Geankoplis' membrane air separation (Example 13.4-2, p. 767, 4th ed.).

        Air (z_O2 = 0.209) at 190 cmHg with the permeate at 19 cmHg (pressure
        ratio 10), O2/N2 permeance ratio 10, stage cut 0.2: the model gives
        y_O2 = 0.5068 and a reject x_O2 = 0.1345. Pressures use
        1 cmHg = 1333.22 Pa.
        """
        return {
            "feed_in": {
                "T": 298.15,
                "P": 2.533125e5,
                "molar_flow": 100.0,
                "composition": {"O2": 0.209, "N2": 0.791},
            }
        }, {"stage_cut": 0.2, "perm_ratio": {"O2": 10.0, "N2": 1.0}, "P_permeate": 2.533125e4}


def _permeate_fraction(theta: float, phi: float, alpha: float, z_fast: float, z_slow: float) -> float:
    """Permeate mole fraction of the fast component, complete mixing.

    Weller-Steiner: the flux-ratio equation ``y/(1-y) = alpha (phi x - y) /
    (phi (1-x) - (1-y))`` with the residue composition eliminated by the
    stage-cut balance ``x = (z - theta y)/(1 - theta)`` reduces to

        B (1 - alpha) y^2 + c1 y - alpha phi z = 0,

    with ``B = 1 + theta (phi - 1)`` and
    ``c1 = alpha + (phi - 1) (1 + theta (alpha - 1)) + phi z (alpha - 1)``.
    The physical root is the smaller one. ``z_slow`` completes the feed
    (``z_fast + z_slow = 1``) and is checked, not used.
    """
    if not math.isclose(z_fast + z_slow, 1.0, rel_tol=1e-9, abs_tol=1e-9):
        raise MembraneSpecError(f"the feed fractions {z_fast} + {z_slow} do not sum to 1")
    if alpha == 1.0:
        return z_fast
    b_coef = 1.0 + theta * (phi - 1.0)
    c1 = alpha + (phi - 1.0) * (1.0 + theta * (alpha - 1.0)) + phi * z_fast * (alpha - 1.0)
    disc = c1 * c1 + 4.0 * b_coef * (1.0 - alpha) * alpha * phi * z_fast
    if disc < 0.0:
        raise MembraneSpecError("the complete-mixing model has no real permeate composition for this spec")
    return (c1 - math.sqrt(disc)) / (2.0 * b_coef * (alpha - 1.0))
