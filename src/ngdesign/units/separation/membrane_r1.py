"""Membrane R1: multicomponent solution-diffusion, cross-flow module.

Plugin kind "unit", name "membrane" level R1 — registered from the catalogue
YAML; no decorator (round-1 conventions).

Method (spec `specs/backend/units/membrane.md`): solution-diffusion with
permeances ``Π_i`` in mol/(m2 s Pa) (1 GPU = 3.348e-10 mol/(m2 s Pa)).

- **M1 flux:** ``J_i = Π_i (P_h x_i − P_l y_i)`` with x the local feed-side and
  y the local permeate-side composition (Weller & Steiner, J. Appl. Phys.
  21:279 (1950); Pan, AIChE J. 29(4):545 (1983); Baker, *Membrane Technology
  and Applications*, Ch. 8).
- **M2 cross-flow local permeate:** the permeate leaves where it forms, with no
  mixing along the membrane, so ``y_i = J_i / ΣJ``. Eliminating J gives
  ``y_i = Π_i P_h x_i / (S + Π_i P_l)`` with S = ΣJ: the sum is above 1 at
  S = 0 (it equals P_h/P_l there) and at most 1 at ``S_hi = Σ Π_i P_h x_i``,
  so the root is bracketed (brentq); the closed form at ``P_l = 0`` is
  ``S = S_hi`` directly.
- **M3 cross-flow balance:** ``dn_i/da = −S(x) y_i(x)`` over the area
  a ∈ [0, A] with ``n_i(0) = F z_i``; permeate flows ``p_i = F z_i − n_i(A)``
  and stage cut ``θ = Σp / F``.

Isothermal (Geankoplis, 4th ed., §13.4–13.5): the permeate leaves at
``P_permeate``, the residue at the feed pressure, both at the feed T, through
``splitting.split_by_component`` exactly as in R0. ``duty_W`` closes the
energy balance; ``power_W = 0``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import brentq

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units._physics.splitting import split_by_component

_INTEGRATION_RTOL = 1e-11


class MembraneR1SpecError(ValueError):
    """The membrane spec is bad; the message names the parameter (also used by R2)."""


def _local_y(x: np.ndarray, Pi: np.ndarray, P_h: float, P_l: float) -> tuple[np.ndarray, float]:
    """M2 in vector form: the local permeate composition and total flux S."""
    flux_hi = Pi * P_h * x  # Π_i P_h x_i
    S_hi = float(np.sum(flux_hi))
    if P_l == 0.0:
        S = S_hi
        return flux_hi / S, S

    def total_y(S: float) -> float:
        return float(np.sum(flux_hi / (S + Pi * P_l))) - 1.0

    try:
        S = brentq(total_y, 0.0, S_hi, xtol=1e-14 * S_hi, maxiter=200)
    except ValueError as exc:
        raise MembraneR1SpecError(
            "local permeate root: did not converge in the bracket [0, Σ Π_i P_h x_i]"
        ) from exc
    return flux_hi / (S + Pi * P_l), S


def _validate_pure(
    F: float,
    z: Mapping[str, float],
    Pi: Mapping[str, float],
    P_h: float,
    P_l: Any,
    area: Any,
    stage_cut: Any,
) -> tuple[float | None, float | None]:
    """Shared spec validation for `cross_flow` and `counter_current` (refusal table)."""
    if not isinstance(P_l, (int, float)) or isinstance(P_l, bool):
        raise MembraneR1SpecError("P_permeate is required: the permeate-side absolute pressure, Pa")
    P_lf = float(P_l)
    # The pure functions accept P_l = 0 (the closed-form cross-flow limit the
    # spec's CF1/CF4 cases run at); the adapter refuses P_permeate <= 0.
    if P_lf < 0.0 or P_lf >= float(P_h):
        raise MembraneR1SpecError(f"P_permeate {P_lf} must be in [0, the feed pressure {float(P_h)})")
    if not isinstance(Pi, Mapping) or not Pi:
        raise MembraneR1SpecError("permeances_mol_m2_s_Pa is required: component id to permeance")
    unknown = [cid for cid in Pi if cid not in z]
    if unknown:
        raise MembraneR1SpecError(f"permeances_mol_m2_s_Pa names component(s) {unknown} not in the feed")
    missing = [cid for cid in z if cid not in Pi]
    if missing:
        raise MembraneR1SpecError(f"permeances_mol_m2_s_Pa is missing feed component(s) {missing}")
    bad = {cid: v for cid, v in Pi.items() if not isinstance(v, (int, float)) or float(v) <= 0.0}
    if bad:
        raise MembraneR1SpecError(f"permeances_mol_m2_s_Pa entries {bad} must be > 0")
    if (area is None) == (stage_cut is None):
        raise MembraneR1SpecError("give exactly one of area_m2 and stage_cut, not both or neither")
    area_f: float | None = None
    stage_cut_f: float | None = None
    if area is not None:
        if not isinstance(area, (int, float)) or isinstance(area, bool) or float(area) <= 0.0:
            raise MembraneR1SpecError(f"area_m2 {area} must be > 0")
        area_f = float(area)
    else:
        if not isinstance(stage_cut, (int, float)) or isinstance(stage_cut, bool):
            raise MembraneR1SpecError(f"stage_cut {stage_cut} must be a number in (0, 1)")
        stage_cut_f = float(stage_cut)
        if not 0.0 < stage_cut_f < 1.0:
            raise MembraneR1SpecError(f"stage_cut {stage_cut_f} outside (0, 1)")
    if float(F) <= 0.0:
        raise MembraneR1SpecError(f"feed molar flow {F} must be > 0")
    return area_f, stage_cut_f


def local_permeate(
    x: Mapping[str, float],
    Pi: Mapping[str, float],
    P_h: float,
    P_l: float,
) -> tuple[dict[str, float], float]:
    """Local cross-flow permeate composition (M2) and total flux S = ΣJ.

    Solves ``y_i = Π_i P_h x_i / (S + Π_i P_l)`` with ``Σ y_i = 1``: the closed
    form at ``P_l = 0``, otherwise brentq on ``[0, S_hi]`` with
    ``xtol = 1e-14 S_hi`` and ``maxiter = 200``.
    """
    cids = list(x)
    xv = np.array([float(x[c]) for c in cids])
    piv = np.array([float(Pi[c]) for c in cids])
    yv, S = _local_y(xv, piv, float(P_h), float(P_l))
    return {c: float(v) for c, v in zip(cids, yv, strict=True)}, S


def cross_flow(
    F: float,
    z: Mapping[str, float],
    Pi: Mapping[str, float],
    P_h: float,
    P_l: float,
    area: float | None = None,
    stage_cut: float | None = None,
) -> tuple[dict[str, float], dict[str, float], float, float]:
    """Cross-flow membrane (R1, M3): integrate the feed side over the area.

    Returns ``(residue_flows, permeate_flows, area, stage_cut)``. In rating
    mode (``area`` given) the stage cut is computed; in design mode
    (``stage_cut`` given) the area is found by a terminal `solve_ivp` event on
    ``Σ(F z_i − n_i) − θ F = 0``, integrated over ``[0, A_hard]`` with
    ``A_hard = 1e3 θ F / Σ_i Π_i P_h z_i`` — refusal `not achievable` when the
    event does not fire (with ``P_l > 0`` the permeate cannot exceed the
    pressure-ratio limit). Tolerances: DOP853, ``rtol=1e-11``, ``atol=1e-13 F``.
    """
    area_f, stage_cut_f = _validate_pure(F, z, Pi, P_h, P_l, area, stage_cut)
    order = list(z)
    zv = np.array([float(z[c]) for c in order])
    piv = np.array([float(Pi[c]) for c in order])
    Fz = float(F) * zv

    def rhs(a: float, n: np.ndarray) -> np.ndarray:
        x_local = n / float(np.sum(n))
        y_local, S = _local_y(x_local, piv, float(P_h), float(P_l))
        return -S * y_local

    if stage_cut_f is not None:

        def event(a: float, n: np.ndarray) -> float:
            return float(np.sum(Fz - n)) - stage_cut_f * float(F)

        event.terminal = True  # type: ignore[attr-defined]
        S_hi_feed = float(np.sum(piv * float(P_h) * zv))
        A_hard = 1e3 * stage_cut_f * float(F) / S_hi_feed
        sol = solve_ivp(
            rhs,
            (0.0, A_hard),
            Fz,
            method="DOP853",
            rtol=_INTEGRATION_RTOL,
            atol=1e-13 * float(F),
            events=[event],
        )
        if sol.status != 1:
            raise MembraneR1SpecError(
                f"stage cut {stage_cut_f} not achievable by the hard area cap {A_hard} m2"
            )
        A = float(sol.t[-1])
    else:
        assert area_f is not None
        A = area_f
        sol = solve_ivp(
            rhs,
            (0.0, A),
            Fz,
            method="DOP853",
            rtol=_INTEGRATION_RTOL,
            atol=1e-13 * float(F),
        )
    n_end = sol.y[:, -1]
    p_arr = Fz - n_end
    residue = {c: float(v) for c, v in zip(order, n_end, strict=True)}
    permeate = {c: float(v) for c, v in zip(order, p_arr, strict=True)}
    theta = stage_cut_f if stage_cut_f is not None else float(np.sum(p_arr)) / float(F)
    return residue, permeate, A, theta


def _adapter_params(
    inlet: StreamState,
    params: dict[str, Any],
) -> tuple[float, dict[str, float], float | None, float | None]:
    """Adapter-level parameter validation shared by the R1/R2 adapters.

    Returns ``(P_l, permeances, area_f, stage_cut_f)``. Unlike the pure
    functions, the adapter refuses `P_permeate <= 0` (a membrane with no
    permeate-side pressure is not a physical adapter configuration).
    """
    P_permeate = params.get("P_permeate")
    if not isinstance(P_permeate, (int, float)) or isinstance(P_permeate, bool):
        raise MembraneR1SpecError("P_permeate is required: the permeate-side absolute pressure, Pa")
    P_l = float(P_permeate)
    if P_l <= 0.0 or P_l >= float(inlet.P):
        raise MembraneR1SpecError(f"P_permeate {P_l} must be in (0, the feed pressure {inlet.P})")
    permeances_raw = params.get("permeances_mol_m2_s_Pa")
    if not isinstance(permeances_raw, Mapping) or not permeances_raw:
        raise MembraneR1SpecError(
            "permeances_mol_m2_s_Pa is required: component id to permeance, mol/(m2 s Pa)"
        )
    unknown = [cid for cid in permeances_raw if cid not in inlet.composition]
    if unknown:
        raise MembraneR1SpecError(f"permeances_mol_m2_s_Pa names component(s) {unknown} not in the feed")
    missing = [cid for cid in inlet.composition if cid not in permeances_raw]
    if missing:
        raise MembraneR1SpecError(f"permeances_mol_m2_s_Pa is missing feed component(s) {missing}")
    bad = {c: v for c, v in permeances_raw.items() if not isinstance(v, (int, float)) or float(v) <= 0.0}
    if bad:
        raise MembraneR1SpecError(f"permeances_mol_m2_s_Pa entries {bad} must be > 0")

    area = params.get("area_m2")
    stage_cut = params.get("stage_cut")
    if (area is None) == (stage_cut is None):
        raise MembraneR1SpecError("give exactly one of area_m2 and stage_cut, not both or neither")
    area_f: float | None = None
    stage_cut_f: float | None = None
    if area is not None:
        if not isinstance(area, (int, float)) or isinstance(area, bool) or float(area) <= 0.0:
            raise MembraneR1SpecError(f"area_m2 {area} must be > 0")
        area_f = float(area)
    else:
        if not isinstance(stage_cut, (int, float)) or isinstance(stage_cut, bool):
            raise MembraneR1SpecError(f"stage_cut {stage_cut} must be a number in (0, 1)")
        stage_cut_f = float(stage_cut)
        if not 0.0 < stage_cut_f < 1.0:
            raise MembraneR1SpecError(f"stage_cut {stage_cut_f} outside (0, 1)")
    return P_l, {c: float(v) for c, v in permeances_raw.items()}, area_f, stage_cut_f


def _outlets_result(
    inlet: StreamState,
    thermo: Thermo,
    residue_flows: dict[str, float],
    permeate_flows: dict[str, float],
    P_l: float,
    A: float,
    theta: float,
    extra_info: dict[str, float] | None = None,
) -> UnitResult:
    """Isothermal outlet build shared by the R1/R2 adapters (R0 pattern)."""
    fractions = {
        cid: permeate_flows[cid] / (float(inlet.molar_flow) * inlet.composition[cid])
        for cid in inlet.composition
    }
    permeate, residue = split_by_component(
        inlet,
        fractions,
        thermo,
        outlet_P={"top": P_l, "bottom": float(inlet.P)},
    )
    n_permeate = float(sum(permeate_flows.values()))
    n_residue = float(sum(residue_flows.values()))
    info: dict[str, float] = {"area_m2": A, "stage_cut": theta}
    if extra_info:
        info.update(extra_info)
    for cid in inlet.composition:
        info[f"permeate_y_{cid}"] = permeate_flows[cid] / n_permeate
        info[f"residue_x_{cid}"] = residue_flows[cid] / n_residue
    h_in_W = inlet.enthalpy * inlet.molar_flow
    h_out_W = sum(s.enthalpy * s.molar_flow for s in (permeate, residue))
    return UnitResult(
        outlets={"permeate": permeate, "residue": residue},
        duty_W=h_out_W - h_in_W,
        power_W=0.0,
        info=info,
    )


class MembraneR1:
    """Cross-flow membrane adapter (catalogue level R1, solution-diffusion)."""

    inlet_ports: tuple[str, ...] = ("feed_in",)
    outlet_ports: tuple[str, ...] = ("permeate", "residue")

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        inlet = inlets["feed_in"]
        P_l, permeances, area_f, stage_cut_f = _adapter_params(inlet, params)
        residue_flows, permeate_flows, A, theta = cross_flow(
            F=float(inlet.molar_flow),
            z=inlet.composition,
            Pi=permeances,
            P_h=float(inlet.P),
            P_l=P_l,
            area=area_f,
            stage_cut=stage_cut_f,
        )
        return _outlets_result(inlet, thermo, residue_flows, permeate_flows, P_l, A, theta)

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """The R0 example feed (Geankoplis Ex. 13.4-2 air basis) in rating mode.

        Air (z_O2 = 0.209) at 2.533125e5 Pa with the permeate at 2.533125e4 Pa,
        equal permeances 1e-9 mol/(m2 s Pa) for O2 and N2, area 50 m2. With
        equal permeances every component recovers the same fraction, so R1
        must reproduce the R0 `permeate_recovery` split at the same stage cut
        (spec identity R1 -> R0).
        """
        return {
            "feed_in": {
                "T": 298.15,
                "P": 2.533125e5,
                "molar_flow": 100.0,
                "composition": {"O2": 0.209, "N2": 0.791},
            }
        }, {
            "permeances_mol_m2_s_Pa": {"O2": 1e-9, "N2": 1e-9},
            "P_permeate": 2.533125e4,
            "area_m2": 50.0,
        }
