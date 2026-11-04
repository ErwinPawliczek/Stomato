"""Thermo adapter for the column solvers (spec P1-03).

Thin wrapper over the Thermo contract v2 (spec P1-01): K-values, per-phase
properties and bubble points are single protocol calls, and flash_pt /
phase_props are LRU-cached per package instance. The Clausius-Clapeyron
estimate stays as the documented fallback for single-phase states and
super-critical feeds.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import numpy as np

from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.stream import PhaseKind, StreamState
from ngdesign.contracts.thermo import PhaseProps

from .spec import _FLOW_FLOOR

# --------------------------------------------------------------------------------------
# Thermo adapter: K / per-phase enthalpy / bubble-temperature helpers per solve
# --------------------------------------------------------------------------------------


#: Mole-fraction floor for a fugacity evaluation: a species a stage has not yet
#: seen still needs a coefficient (reaction products, trace keys).
_K_TRACE = 1e-30
#: Vapour fixed point inside ``k_fugacity``: iteration cap and the largest
#: mole-fraction move accepted as converged.
_K_FIXED_POINT_MAX = 30
_K_FIXED_POINT_TOL = 1e-14
#: ``fixed_phase_sets`` window: a pooled liquid within this max mole-fraction
#: move and temperature move (K) of a fully tested state keeps its phase set.
#: Covers the FD Jacobian's perturbations (1e-7 relative, ~6e-5 K at 600 K).
_SPLIT_WINDOW_X = 1e-6
_SPLIT_WINDOW_T = 1e-3
#: Fully tested pooled-liquid states remembered for seeds and the window.
_SPLIT_REFS_MAX = 256


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

    Outside an inside-out sweep, plain columns read the fugacity surface at the
    stage liquid (``k_fugacity``), and pooled-liquid columns on a package with
    ``liquid_split`` read the pooled liquid's own split (``k_pooled``,
    ``pooled_split``) - no flash per stage K on either.
    """

    def __init__(
        self, thermo: Thermo, p_anchor_lo: float, p_anchor_hi: float, pool_liquids: bool = False
    ) -> None:
        self._thermo = thermo
        #: Three-phase stages: every liquid of a flash counts as THE stage
        #: liquid (see ``_liquid``). False keeps the first-liquid reading.
        self.pool_liquids = pool_liquids
        #: Fugacity K and single-phase enthalpies (P1-13): every package but a
        #: pooled column or a reactive amine package, whose K and liquid
        #: enthalpy are flash results.
        self.direct_phases = not pool_liquids and not getattr(thermo, "is_amine_reactive_package", False)
        #: A pooled column whose package splits a liquid without a flash
        #: (``liquid_split``): its stage K and liquid enthalpy are fugacity
        #: functions of the stage liquid (``k_pooled``) - the smooth surface
        #: the plain column's ``direct_phases`` reads.
        self.pooled_fugacity = (
            pool_liquids
            and getattr(thermo, "liquid_split", None) is not None
            and not getattr(thermo, "is_amine_reactive_package", False)
        )
        #: True inside a zero/one-tear inside-out model refresh, which reads
        #: the flash surface (see ``_refresh_model``). Newton, the gate and
        #: two-tear sweeps read ``exact_surface``.
        self.sweeping = False
        self._pt_cache: dict[tuple[Any, ...], StreamState] = {}
        self._k_cache: dict[tuple[Any, ...], dict[str, float] | None] = {}
        self._k_liquid_cache: dict[tuple[Any, ...], dict[str, float] | None] = {}
        self._bubble_cache: dict[tuple[Any, ...], float | None] = {}
        self._split_cache: dict[tuple[Any, ...], list[PhaseProps]] = {}
        self._split_refs: list[tuple[tuple[str, ...], tuple[float, ...], float, float, list[PhaseProps]]] = []
        #: (max mole-fraction move, temperature move) of ``fixed_phase_sets``; None outside it.
        self._fixed_sets: tuple[float, float] | None = None
        self._p_lo = p_anchor_lo
        self._p_hi = p_anchor_hi
        self._cc: dict[str, tuple[float, float, float]] = {}  # cid -> (D, T_ref, ln P_ref)

    def pt(self, z: dict[str, float], T: float, P: float, flow: float = 1.0) -> StreamState:
        """PT flash, memoized on the exact (composition, T, P, flow) state.

        The per-solve memo sits above the plugin's own LRU so repeated calls —
        the K chain, both enthalpy models, the exact-residual gate and the
        duty-path enthalpy wrappers at the same stage state — share one flash.
        """
        # A reactive package's heat-of-reaction continuation scale changes the
        # flashed enthalpies on the same instance, so it is part of the key.
        key = (tuple(sorted(z.items())), T, P, flow, getattr(self._thermo, "_heat_scale", None))
        hit = self._pt_cache.get(key)
        if hit is None:
            hit = self._thermo.flash_pt(z, T, P, flow)
            self._pt_cache[key] = hit
        return hit

    @property
    def reactive_direct(self) -> bool:
        """True where a reactive package's K and phase enthalpies are read at the
        stage compositions themselves (outside an inside-out sweep, as
        ``exact_surface``)."""
        return not self.sweeping and hasattr(self._thermo, "liquid_k_values")

    @property
    def exact_surface(self) -> bool:
        """True where K and enthalpies are the single-phase fugacity surface."""
        return self.direct_phases and not self.sweeping

    @property
    def pooled_exact(self) -> bool:
        """A pooled column outside a sweep: its homogeneous stages read the exact surface.

        A stage with one liquid IS a plain stage, so it takes the plain
        column's K and enthalpies (P1-13); only a stage whose contents split
        into two liquids keeps the pooled flash reading. Measured: a dry 8-stage
        nC4/iC4 kettle stripper through the pooled path settled 0.05 K below
        its top stage's bubble point on the flash K (whose phases are not the
        stage's x), against the plain column's exact bubble point.
        """
        return (
            self.pool_liquids
            and not self.sweeping
            and not getattr(self._thermo, "is_amine_reactive_package", False)
        )

    def heterogeneous(self, z: dict[str, float], T: float, P: float) -> bool:
        """True when the memoized flash of z at (T, P) carries two or more liquids."""
        state = self.pt(z, T, P)
        return sum(1 for p in state.phases if p.kind != PhaseKind.VAPOR) >= 2

    def _liquid(self, state: StreamState) -> tuple[dict[str, float], float, float] | None:
        """(composition, enthalpy, cp) of the state's liquid; None without one.

        Plain columns read the first liquid phase. With ``pool_liquids`` every
        liquid is pooled by its phase fraction into one pseudo-liquid, the
        MESH-with-overall-liquid formulation of three-phase columns (Block &
        Hegner, AIChE J. 22 (1976) 582; Cairns & Furzer, I&EC Res. 29 (1990)
        1349): K_i = y_i / xbar_i, where xbar is what the stage cascade carries
        and the split between the liquids is a stage-local flash result. The
        pooled enthalpy is the mole-weighted phase enthalpy, and the cp is
        weighted likewise: it is only the slope of the frozen inner line.
        """
        liquids = [p for p in state.phases if p.kind != PhaseKind.VAPOR]
        if not liquids:
            return None
        if not self.pool_liquids or len(liquids) == 1:
            first = liquids[0]
            return first.composition, first.enthalpy, first.cp
        total = sum(p.mole_fraction for p in liquids)
        comp: dict[str, float] = {}
        for p in liquids:
            for cid, frac in p.composition.items():
                comp[cid] = comp.get(cid, 0.0) + frac * p.mole_fraction / total
        h = sum(p.enthalpy * p.mole_fraction for p in liquids) / total
        cp = sum(p.cp * p.mole_fraction for p in liquids) / total
        return comp, h, cp

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
        liq = self._liquid(state)
        if vap is None or liq is None:
            return None
        liq_comp = liq[0]
        out: dict[str, float] = {}
        for cid in state.composition:
            y = vap.composition.get(cid, 0.0)
            x = liq_comp.get(cid, 0.0)
            if x > 0.0 and y > 0.0:
                out[cid] = max(y / x, 1e-12)
            elif y > 0.0:
                out[cid] = 1e6
            elif x > 0.0:
                out[cid] = 1e-12
            else:
                out[cid] = 1.0
        return out

    @property
    def splits_liquid(self) -> bool:
        """True when a pooled column reads its stage liquid's own liquid-liquid split.

        ``pooled_fugacity`` outside an inside-out sweep (which keeps reading
        the flash surface). Packages without ``liquid_split`` keep the flash
        reading of a heterogeneous stage.
        """
        return self.pooled_fugacity and not self.sweeping

    @contextmanager
    def fixed_phase_sets(self) -> Iterator[None]:
        """Within: a pooled stage liquid keeps the phase set of its reference state.

        For the finite-difference Jacobian (Naphtali & Sandholm 1971 linearise
        at fixed phase identity): a perturbed liquid within ``_SPLIT_WINDOW_X``
        (max mole-fraction move) and ``_SPLIT_WINDOW_T`` (K) of a state whose
        split was decided by the full stability test keeps that decision - one
        liquid stays one liquid (no test), two liquids re-split by successive
        substitution from the reference split. Values off the window, and
        every residual, gate and line-search evaluation outside this context,
        run the full test, so the converged state is the full test's.
        """
        saved = self._fixed_sets
        self._fixed_sets = (_SPLIT_WINDOW_X, _SPLIT_WINDOW_T)
        try:
            yield
        finally:
            self._fixed_sets = saved

    def _nearest_split(
        self, keys: tuple[str, ...], vals: tuple[float, ...], T: float, P: float
    ) -> tuple[float, float, list[PhaseProps]] | None:
        """(max |dx|, |dT|, split) of the closest fully tested state at (keys, P).

        Closest by max |dx| + 1e-3 |dT|, the first in insertion order on a
        tie. Vectorised over the remembered states (the same IEEE operations
        elementwise, ``argmin`` keeping the first minimum): the per-element
        Python scan was ~10 % of a 21-stage pooled crude column's solve.
        """
        refs = [ref for ref in self._split_refs if ref[0] == keys and ref[3] == P]
        if not refs:
            return None
        dxs = np.abs(np.array([ref[1] for ref in refs]) - np.array(vals)).max(axis=1)
        dts = np.abs(T - np.array([ref[2] for ref in refs]))
        i = int(np.argmin(dxs + dts * 1e-3))
        return float(dxs[i]), float(dts[i]), refs[i][4]

    def pooled_split(self, x: dict[str, float], T: float, P: float) -> list[PhaseProps]:
        """The liquid-liquid split of a pooled stage liquid x at (T, P), memoized.

        The pooled liquid (Block & Hegner 1976) is what the stage cascade
        carries; its split into equilibrium liquids is a function of (x, T, P)
        alone, read from the package's ``liquid_split`` (Michelsen 1982
        stability test plus a liquid-liquid successive substitution). The
        stability test is seeded with the nearest tested state's liquids
        (the answer is still the full test's); inside ``fixed_phase_sets``
        a state within the window of a tested one keeps its phase set.
        """
        keys = tuple(sorted(x))
        vals = tuple(x[cid] for cid in keys)
        key = (keys, vals, T, P)
        hit = self._split_cache.get(key)
        if hit is not None:
            return hit
        splitter = self._thermo.liquid_split  # type: ignore[attr-defined]
        near = self._nearest_split(keys, vals, T, P)
        seed = [p.composition for p in near[2]] if near is not None and len(near[2]) == 2 else None
        result: list[PhaseProps]
        window = self._fixed_sets
        if window is not None and near is not None and near[0] <= window[0] and near[1] <= window[1]:
            # One liquid stays one liquid (empty: the caller reads the plain
            # single-phase build); two re-split from the reference's liquids.
            result = splitter(x, T, P, seed=seed, stability=False) if seed is not None else []
        else:
            result = splitter(x, T, P, seed=seed)
            self._split_refs.append((keys, vals, T, P, result))
            if len(self._split_refs) > _SPLIT_REFS_MAX:
                del self._split_refs[0]
        self._split_cache[key] = result
        return result

    @staticmethod
    def _trace_normalized(x: dict[str, float]) -> dict[str, float]:
        """x floored at the trace fraction and renormalized (the fugacity-K liquid)."""
        floor = {cid: max(v, _K_TRACE) for cid, v in x.items()}
        xs = sum(floor.values())
        return {cid: v / xs for cid, v in floor.items()}

    def k_pooled(
        self, x: dict[str, float], y: dict[str, float], T: float, P: float
    ) -> dict[str, float] | None:
        """Fugacity K of a pooled stage liquid: K_i = fhat_i^L / (xbar_i phi_i^V P).

        The pooled liquid xbar splits into its equilibrium liquids k
        (``pooled_split``); their common fugacity is
        fhat_i / P = sum_k beta_k x_ki phi_ki (equal in every liquid at the
        split's solution), and K_i = y_i / xbar_i with y_i phi_i^V = fhat_i / P
        - the pooled-liquid E equation of Block & Hegner (1976), a function of
        (xbar, T, P) alone like ``k_fugacity``. A liquid that does not split
        IS the plain stage liquid and takes ``k_fugacity`` itself.
        """
        x_n = self._trace_normalized(x)
        split = self.pooled_split(x_n, T, P)
        if len(split) < 2:
            return self.k_fugacity(x, y, T, P)
        return self._k_fixed_point(x, x_n, y, _pooled_ln_phi(split, x_n), T, P)

    def k_fugacity(
        self, x: dict[str, float], y: dict[str, float], T: float, P: float
    ) -> dict[str, float] | None:
        """K_i = phi_i^L(x, T, P) / phi_i^V(y, T, P): equality of fugacity, no flash.

        The MESH E equation as written (Naphtali & Sandholm 1971): defined at
        every iterate, on or off the bubble point. A K read from a flash exists
        only where that composition splits at (T, P), so an iterate crossing the
        bubble surface jumps candidate and K with it, and Newton's full step
        predicts 1e-16 and achieves 1e-1 (measured, P1-13). None when the
        package has no per-phase ln phi; the caller keeps the flash chain.
        """
        x_n = self._trace_normalized(x)
        try:
            liquid = self._thermo.phase_props(x_n, T, P, PhaseKind.HC_LIQUID).ln_phi
        except ValueError:
            return None
        if not liquid:
            return None
        return self._k_fixed_point(x, x_n, y, liquid, T, P)

    def _k_fixed_point(
        self,
        x: dict[str, float],
        x_n: dict[str, float],
        y: dict[str, float],
        liquid: dict[str, float],
        T: float,
        P: float,
    ) -> dict[str, float] | None:
        """K_i = exp(ln phi_i^L - ln phi_i^V(y)) at the vapour's fixed point y = K x / sum(K x)."""
        trace = {cid: max(y.get(cid, 0.0), _K_TRACE) for cid in x}
        ys = sum(trace.values())
        y_n = {cid: v / ys for cid, v in trace.items()}
        # phi^V at the vapour this liquid is in equilibrium with: successive
        # substitution y <- K x / sum(K x) to a fixed point, so K is a function
        # of (x, T, P) alone and the caller's seed only picks the start. With
        # a single pass from the seed, Newton's pass-frozen seed and the gate's
        # refreshed one read two K surfaces (measured deethanizer at the spec
        # tears: rows predicted M = 1.4e-2, the gate read 2.0e-2 every pass).
        k: dict[str, float] = {}
        for _ in range(_K_FIXED_POINT_MAX):
            try:
                vapour = self._thermo.phase_props(y_n, T, P, PhaseKind.VAPOR).ln_phi
            except ValueError:
                return None
            if not vapour:
                return None
            k = {cid: math.exp(liquid[cid] - vapour[cid]) for cid in x}
            kx = {cid: max(k[cid] * x_n[cid], _K_TRACE) for cid in x}
            s = sum(kx.values())
            y_new = {cid: v / s for cid, v in kx.items()}
            moved = max(abs(y_new[cid] - y_n[cid]) for cid in x)
            y_n = y_new
            if moved <= _K_FIXED_POINT_TOL:
                break
        return k

    def k_liquid(self, x: dict[str, float], T: float, P: float) -> dict[str, float] | None:
        """K at the stage liquid itself, for a package whose K is a function of x alone.

        A reactive amine package's K_i(T, P, x) needs no flash (its
        ``liquid_k_values``); the flash chain in ``k_values`` returns K at the
        FLASH liquid instead, and a stage liquid on its bubble point flashes on
        the single-phase edge, so the chain jumps candidates between Newton
        trial states and the finite-difference Jacobian differentiates the
        jump. None for every other package, and inside an inside-out sweep,
        which keeps reading the flash surface (as ``exact_surface`` does).
        """
        direct = getattr(self._thermo, "liquid_k_values", None)
        if direct is None or not self.reactive_direct:
            return None
        key = (tuple(sorted(x.items())), T, P)
        if key not in self._k_liquid_cache:
            self._k_liquid_cache[key] = direct(x, T, P)
        k = self._k_liquid_cache[key]
        return dict(k) if k is not None else None

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
        liq = self._liquid(state)
        if vap is None or liq is None:
            return None
        return (vap.enthalpy, vap.cp, T), (liq[1], liq[2], T)

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
        the inside-out convergence was tuned against (a seed only: the
        total-condenser outlet state is ``saturated_liquid_temperature``); a
        true bubble-point seed sits ~25 K lower and drops the
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

    def saturated_liquid_temperature(self, z: dict[str, float], P: float) -> float | None:
        """True bubble temperature of z at P: the total-condenser outlet state.

        A total condenser returns reflux and distillate as saturated liquid at
        the condenser pressure (Seader, Henley & Roper, Separation Process
        Principles 3rd ed., §10.3: Q_c = V_1 (h_V1 - h_L0), L_0 and D at their
        bubble point). This is the package's ``bubble_point``, NOT
        ``bubble_temperature`` (the vapour-fraction-0.5 seed crossing). None
        when the package has no bubble point there (super-critical z).
        """
        key = ("sat", tuple(sorted(z.items())), P)
        if key in self._bubble_cache:
            return self._bubble_cache[key]
        try:
            result: float | None = self._thermo.bubble_point(z, P=P).T
        except Exception:  # noqa: BLE001 - SaturationError or a component outside the EOS domain
            result = None
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
        if not vapor and self.splits_liquid:
            # The pooled liquid's own split (see ``k_pooled``): the
            # mole-weighted enthalpy and cp of its equilibrium liquids; a
            # liquid that does not split takes the single-phase build below.
            split = self.pooled_split(self._trace_normalized(z), T, P)
            if len(split) >= 2:
                h = sum(p.mole_fraction * p.enthalpy for p in split)
                cp = sum(p.mole_fraction * p.cp for p in split)
                return h, cp, T
            homogeneous = True
        else:
            homogeneous = vapor or (self.pooled_exact and not self.heterogeneous(z, T, P))
        if self.exact_surface or (self.pooled_exact and homogeneous):
            # The phase AT z: a flash of z hands back a phase of another
            # composition, and which one jumps at the bubble surface. Falls
            # through only for a package that refuses the single-phase build.
            # A pooled liquid that splits keeps the pooled flash reading below.
            try:
                built = self._thermo.phase_props(z, T, P, PhaseKind.VAPOR if vapor else PhaseKind.HC_LIQUID)
                return built.enthalpy, built.cp, T
            except ValueError:
                pass
        if self.reactive_direct:
            # The reactive package's phases at z itself, as its K (``k_liquid``):
            # the aqueous build carries the heat of absorption at z's loading,
            # the vapour is the carrier's - the same builds its flash reports.
            built = self._thermo.phase_props(z, T, P, PhaseKind.VAPOR if vapor else PhaseKind.AQUEOUS)
            return built.enthalpy, built.cp, T
        state = self.pt(z, T, P)
        if vapor:
            phase = next((p for p in state.phases if p.kind == PhaseKind.VAPOR), None)
            if phase is not None:
                return phase.enthalpy, phase.cp, T
        else:
            liquid = self._liquid(state)
            if liquid is not None:
                return liquid[1], liquid[2], T
        kind = PhaseKind.VAPOR if vapor else PhaseKind.HC_LIQUID
        props = self._thermo.phase_props(z, T, P, kind)
        return props.enthalpy, props.cp, T

    def phase_state(self, z: dict[str, float], T: float, P: float, vapor: bool) -> PhaseProps:
        """One single-phase build of z at (T, P): fugacity coefficients, enthalpy, cp.

        Raises ValueError when the package refuses the build (callers keep
        their previous model then).
        """
        props = self._thermo.phase_props(z, T, P, PhaseKind.VAPOR if vapor else PhaseKind.HC_LIQUID)
        if not props.ln_phi:
            raise ValueError("package returns no fugacity coefficients for this phase build")
        return props

    def h_vapor(self, z: dict[str, float], T: float, P: float) -> float:
        h0, cp, t_ref = self.phase_enthalpy_model(z, T, P, vapor=True)
        return h0 + cp * (T - t_ref)

    def h_liquid(self, z: dict[str, float], T: float, P: float) -> float:
        h0, cp, t_ref = self.phase_enthalpy_model(z, T, P, vapor=False)
        return h0 + cp * (T - t_ref)


def _pooled_ln_phi(split: list[PhaseProps], x_n: dict[str, float]) -> dict[str, float]:
    """Effective ln phi_i of a split pooled liquid: ln(fhat_i / P) - ln xbar_i.

    fhat_i / P = sum_k beta_k x_ki phi_ki over the equilibrium liquids k (equal
    to x_ki phi_ki in each at the split's solution; the beta-weighted mean is
    symmetric in the liquids). Michelsen & Mollerup, Thermodynamic Models
    (2007), ch. 10: the liquid fugacities are equal in every coexisting phase.
    """
    return {
        cid: math.log(sum(p.mole_fraction * p.composition[cid] * math.exp(p.ln_phi[cid]) for p in split))
        - math.log(x_n[cid])
        for cid in x_n
    }


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
