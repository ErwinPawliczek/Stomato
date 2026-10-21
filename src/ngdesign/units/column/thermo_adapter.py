"""Thermo adapter for the column solvers (spec P1-03).

Thin wrapper over the Thermo contract v2 (spec P1-01): K-values, per-phase
properties and bubble points are single protocol calls, and flash_pt /
phase_props are LRU-cached per package instance. The Clausius-Clapeyron
estimate stays as the documented fallback for single-phase states and
super-critical feeds.
"""

from __future__ import annotations

import math
from typing import Any

from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.stream import PhaseKind, StreamState

from .spec import _FLOW_FLOOR

# --------------------------------------------------------------------------------------
# Thermo adapter: K / per-phase enthalpy / bubble-temperature helpers per solve
# --------------------------------------------------------------------------------------


class _ThermoBox:
    """Adapts the Thermo protocol for the column solvers (contract v2, spec P1-03).

    Thin now: one memoized ``flash_pt`` per stage state serves K (phase
    y/x — numerically identical to ``thermo.k_values``, which runs the same
    internal flash), both phase enthalpy lines (``Phase.enthalpy`` / ``.cp``),
    and the duty-path enthalpy wrappers; bubble temperatures are
    ``thermo.bubble_point`` calls. The Clausius-Clapeyron estimate
    (``k_estimate`` and the pure-component CC line) stays as the documented
    fallback: a state is single-phase exactly where ``thermo.k_values`` would
    return None, and ``bubble_point`` raises ``SaturationError`` for
    super-critical feeds.

    The K chain (stage liquid composition, then stage overall composition, then
    feed composition) returns None when every candidate comes back single-phase;
    callers keep the previous K or the CC estimate in that case.
    """

    def __init__(self, thermo: Thermo, p_anchor_lo: float, p_anchor_hi: float) -> None:
        self._thermo = thermo
        self._pt_cache: dict[tuple[Any, ...], StreamState] = {}
        self._k_cache: dict[tuple[Any, ...], dict[str, float] | None] = {}
        self._bubble_cache: dict[tuple[Any, ...], float | None] = {}
        self._p_lo = p_anchor_lo
        self._p_hi = p_anchor_hi
        self._cc: dict[str, tuple[float, float, float]] = {}  # cid -> (D, T_ref, ln P_ref)

    def pt(self, z: dict[str, float], T: float, P: float, flow: float = 1.0) -> StreamState:
        """PT flash, memoized on the exact (composition, T, P, flow) state.

        The per-solve memo sits above the plugin's own LRU so repeated calls —
        the K chain, both enthalpy models, the exact-residual gate and the
        duty-path enthalpy wrappers at the same stage state — share one flash.
        """
        key = (tuple(sorted(z.items())), T, P, flow)
        hit = self._pt_cache.get(key)
        if hit is None:
            hit = self._thermo.flash_pt(z, T, P, flow)
            self._pt_cache[key] = hit
        return hit

    def _k_from_state(self, state: StreamState) -> dict[str, float] | None:
        """K_i = y_i/x_i from a flashed state's phases; None when single-phase.

        The solver's K convention — the one the inside-out and
        Naphtali-Sandholm meshes are calibrated against — maps the degenerate
        ratios: all-vapour components (x_i == 0, present in the state) to 1e6,
        all-liquid components (y_i == 0) to 1e-12, and components absent from
        the state entirely to 1.0; live ratios are floored at 1e-12.
        """
        if not 1e-6 < state.vapor_fraction < 1.0 - 1e-6:
            return None
        vap = next((p for p in state.phases if p.kind == PhaseKind.VAPOR), None)
        liq = next((p for p in state.phases if p.kind != PhaseKind.VAPOR), None)
        if vap is None or liq is None:
            return None
        out: dict[str, float] = {}
        for cid in state.composition:
            y = vap.composition.get(cid, 0.0)
            x = liq.composition.get(cid, 0.0)
            if x > 0.0 and y > 0.0:
                out[cid] = max(y / x, 1e-12)
            elif y > 0.0:
                out[cid] = 1e6
            elif x > 0.0:
                out[cid] = 1e-12
            else:
                out[cid] = 1.0
        return out

    def k_values(self, candidates: list[dict[str, float]], T: float, P: float) -> dict[str, float] | None:
        """K_i = y_i/x_i from the first two-phase candidate's cached PT flash.

        Reads the phases of the same memoized ``flash_pt`` the enthalpy models
        use — one flash per stage state serves K and both enthalpy lines (the
        spec Method's one-flash guidance). Numerically identical to
        ``thermo.k_values``, which runs the same internal PT flash; the phase
        read additionally keeps the all-liquid K convention (1e-12) the contract
        cannot express (it maps every zero ratio to 0.0). Returns None when
        every candidate is single-phase at (T, P); callers keep the previous K
        or fall back to the Clausius-Clapeyron estimate (see k_estimate).
        """
        for z in candidates:
            key = (tuple(sorted(z.items())), T, P)
            if key in self._k_cache:
                k = self._k_cache[key]
            else:
                k = self._k_from_state(self.pt(z, T, P))
                self._k_cache[key] = k
            if k is not None:
                return dict(k)
        return None

    def phase_enthalpy_pair(
        self, state: StreamState, T: float
    ) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
        """((h_vap, cp_vap, T), (h_liq, cp_liq, T)) from a flashed two-phase state.

        One flash serves K and both phase enthalpy lines (the spec Method's
        one-flash guidance): the phases carry real composition, enthalpy and cp
        at the stage state. None when the state is single-phase — callers fall
        back to ``phase_enthalpy_model`` per phase then.
        """
        if not 1e-6 < state.vapor_fraction < 1.0 - 1e-6:
            return None
        vap = next((p for p in state.phases if p.kind == PhaseKind.VAPOR), None)
        liq = next((p for p in state.phases if p.kind != PhaseKind.VAPOR), None)
        if vap is None or liq is None:
            return None
        return (vap.enthalpy, vap.cp, T), (liq.enthalpy, liq.cp, T)

    def pure_psat(self, cid: str, T: float) -> float | None:
        """Pure-component vapour pressure (Pa) at T (K); None at or above Tc."""
        return self._thermo.pure_psat(cid, T)

    def _cc_params(self, cid: str) -> tuple[float, float, float] | None:
        """Clausius-Clapeyron line (D, T_ref, ln P_ref) for a pure component.

        ln Psat(T) = ln P_ref - D * (1/T - 1/T_ref), with the slope measured
        between the pure-component saturation temperatures at the column's
        lowest and highest stage pressures (2500 K fallback when one anchor
        is unavailable, e.g. above the critical pressure).
        """
        hit = self._cc.get(cid)
        if hit is not None:
            return hit
        t_lo = self.bubble_temperature({cid: 1.0}, self._p_lo)
        t_hi = self.bubble_temperature({cid: 1.0}, self._p_hi)
        entry: tuple[float, float, float] | None = None
        if t_lo is not None and t_hi is not None and t_hi > t_lo + 1.0:
            d = math.log(self._p_hi / self._p_lo) / (1.0 / t_lo - 1.0 / t_hi)
            if math.isfinite(d) and d > 0.0:
                entry = (d, t_lo, math.log(self._p_lo))
        if entry is None and t_lo is not None:
            entry = (2500.0, t_lo, math.log(self._p_lo))
        if entry is None and t_hi is not None:
            entry = (2500.0, t_hi, math.log(self._p_hi))
        if entry is not None:
            self._cc[cid] = entry
        return entry

    def k_estimate(self, comp: dict[str, float], T: float, P: float) -> dict[str, float]:
        """Temperature-dependent K estimate at a single-phase stage state.

        Raoult form K_i = Psat_i(T)/P from the pure-component Clausius-Clapeyron
        line. This is the inner-loop K form; real flash K replaces it wherever a
        two-phase stage state exists, and the exact-residual gate (real K) still
        judges the converged profile.
        """
        out: dict[str, float] = {}
        for cid in comp:
            cc = self._cc_params(cid)
            if cc is None:
                out[cid] = 1.0
                continue
            d, t_ref, ln_p_ref = cc
            ln_psat = ln_p_ref - d * (1.0 / T - 1.0 / t_ref)
            out[cid] = max(math.exp(min(ln_psat, 50.0)) / P, 1e-10)
        return out

    def bubble_temperature(self, z: dict[str, float], P: float) -> float | None:
        """Pure/composition phase-jump temperature at P (the liquid-to-vapour seed).

        The former bracket walk converged on the vapour-fraction-0.5 crossing
        between the bubble and the dew — the calibrated seed/anchor estimator
        the inside-out convergence (and the condensed-distillate state) was
        tuned against; a true bubble-point seed sits ~25 K lower and drops the
        top stages into the subcooled CC-estimate region where the sweep
        diverges. Contract v2 reproduces that crossing exactly: bubble and dew
        from the v2 saturation surface, then a 12-step bisection on flash_pt
        between them (12 flash-equivalents, vs the old ~30-flash walk). A pure
        component or degenerate span returns the bubble itself. A super-critical
        feed raises ``SaturationError`` on the saturation surface; the
        Clausius-Clapeyron seed is the documented fallback — a mole-weighted
        mean of the pure-component CC saturation temperatures for a mixture,
        None for a pure component above its critical pressure (no CC line
        exists, and callers skip those).
        """
        key = (tuple(sorted(z.items())), P)
        hit = self._bubble_cache.get(key)
        if hit is not None:
            return hit
        try:
            bub = self._thermo.bubble_point(z, P=P).T
            dew = self._thermo.dew_point(z, P=P).T
            result: float | None
            if bub is None:
                result = None
            elif dew is None or dew <= bub + 1.0:
                result = bub
            else:
                lo, hi = bub, dew
                for _ in range(12):
                    mid = 0.5 * (lo + hi)
                    if self.pt(z, mid, P).vapor_fraction > 0.5:
                        hi = mid
                    else:
                        lo = mid
                result = 0.5 * (lo + hi)
        except Exception:  # noqa: BLE001 - SaturationError or a component outside the EOS domain
            result = None
        if result is None and len(z) > 1:
            result = self._cc_mixture_estimate(z, P)
        self._bubble_cache[key] = result
        return result

    def _cc_mixture_estimate(self, z: dict[str, float], P: float) -> float | None:
        """Mole-weighted mean of the pure-component CC saturation temperatures at P."""
        acc = 0.0
        total = 0.0
        for cid, x in z.items():
            if x <= 0.0:
                continue
            cc = self._cc_params(cid)
            if cc is None:
                continue
            d, t_ref, ln_p_ref = cc
            inv = 1.0 / t_ref + (ln_p_ref - math.log(P)) / d
            if inv <= 0.0:
                continue
            acc += x / inv
            total += x
        if total <= 0.0:
            return None
        return acc / total

    def phase_enthalpy_model(
        self, z: dict[str, float], T: float, P: float, vapor: bool
    ) -> tuple[float, float, float]:
        """(h0, cp, T_ref) for a linear enthalpy model of one phase near T.

        Contract v2. When the state contains the wanted phase (two-phase, or
        entirely the wanted one) the line anchors on that *actual* phase of the
        memoized ``flash_pt`` — real composition, enthalpy and cp at the state,
        the one-flash path the spec's Method section prescribes. Only a phase
        the state does not contain falls back to ``thermo.phase_props`` — a
        hypothetical single-phase build there, the documented approximation
        (single-phase builds are not budgeted; they are tracked as ``props``).
        The former straddling single-phase flashes with linear extrapolation
        across the phase boundary are gone (spec P1-03).

        Calibrated: anchoring these lines on ``phase_props`` builds of the
        requested composition instead — the spec-literal reading — stops the
        inside-out mesh early and the total-reflux/Fenske oracle columns then
        fail to converge; see the PR findings for both numbers.
        """
        state = self.pt(z, T, P)
        if vapor:
            phase = next((p for p in state.phases if p.kind == PhaseKind.VAPOR), None)
        else:
            phase = next((p for p in state.phases if p.kind != PhaseKind.VAPOR), None)
        if phase is not None:
            return phase.enthalpy, phase.cp, T
        kind = PhaseKind.VAPOR if vapor else PhaseKind.HC_LIQUID
        props = self._thermo.phase_props(z, T, P, kind)
        return props.enthalpy, props.cp, T

    def h_vapor(self, z: dict[str, float], T: float, P: float) -> float:
        h0, cp, t_ref = self.phase_enthalpy_model(z, T, P, vapor=True)
        return h0 + cp * (T - t_ref)

    def h_liquid(self, z: dict[str, float], T: float, P: float) -> float:
        h0, cp, t_ref = self.phase_enthalpy_model(z, T, P, vapor=False)
        return h0 + cp * (T - t_ref)


def _flash_ready(z: dict[str, float], fallback: dict[str, float]) -> dict[str, float]:
    """Normalize a composition for the thermo plugin, which validates sum-to-1.

    Newton trial states and mid-sweep meshes wander off-normalized; every
    direct flash or enthalpy evaluation of a stage composition goes through
    this projection so the residual machinery sees a continuous K/enthalpy
    field instead of a validation error.
    """
    total = sum(z.values())
    if total > _FLOW_FLOOR:
        return {cid: v / total for cid, v in z.items()}
    return fallback
