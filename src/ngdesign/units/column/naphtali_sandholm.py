"""Naphtali-Sandholm fallback: simultaneous damped Newton on (x, T, V) (spec P1-03).

Moved unchanged from the former ``units/column.py`` god-file.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from .inside_out import (
    _Column,
    _exact_residuals,
    _finalize_duties,
    _h_equation_stages,
    _l_profile,
    _live_residual_vector,
    _Profile,
    _residual_row_blocks,
    _residual_scales,
    _stage_k_values,
    _v_free_indices,
)
from .linalg import _gauss
from .spec import (
    _FLOW_FLOOR,
    _MESH_H_TOL,
    _MESH_M_TOL,
    _MESH_M_TOL_REACTIVE,
    _MESH_M_TOL_ZERO_ONE_TEAR,
    _NS_MAX,
    _NS_MAX_ZERO_ONE_TEAR,
    ColumnConvergenceError,
    _is_reactive_package,
)
from .thermo_adapter import _flash_ready, _ThermoBox

# --------------------------------------------------------------------------------------
# Naphtali-Sandholm fallback
# --------------------------------------------------------------------------------------

#: LM damping attempts per pass before the pass is abandoned.
_NS_LM_TRIES = 6

#: Line-search halvings per pass: full-step attempts before the LM fallback
#: (one controller, both engines - the graph engine's former
#: _GRAPH_LINE_SEARCH_TRIES was the same number).
_NS_LINE_SEARCH_TRIES = 10


def _reactive_trial_seeds(
    col: _Column,
    tb: _ThermoBox,
    l0: float,
    xs: list[dict[str, float]],
    ts: list[float],
    vs: list[float],
    y_reference: list[dict[str, float]],
    k_fallbacks: list[dict[str, float]],
    seed_cache: dict[
        tuple[tuple[tuple[str, float], ...], float, float, tuple[tuple[str, float], ...]],
        dict[str, float],
    ],
    k_misses: list[int],
) -> list[dict[str, float]]:
    """Vapour seeds for one residual evaluation, computed AT the trial state.

    P1-11 R1 (ruling on #153): on the reactive package the stage-K vapour seed
    enters the loading walk, so a residual evaluated with seeds frozen at the
    pass's reference state sits on a different K surface than the exact gate,
    which refreshes its seeds at the state it gates. Newton then linearises -
    and descends - a residual the gate never reads (measured 20-stage MDEA
    absorber, exothermic reference: warm-started NS descended its internal
    rows to M = 7.8e-6 while the pass-5 seed refresh threw the exact energy
    residual back to ~1e-1; cold, the FD Jacobian went singular at pass 1).
    One loading-walk fixed-point iteration from the pass's reference y,
    evaluated at the trial state itself: the seed responds to the trial's T
    and x the way the gate's refreshed y = K*x does at the applied state, so
    the FD Jacobian linearises the exact live residual the gate reads.

    Deterministic in the trial state - a fixed iteration count from a
    per-pass-frozen reference - which is what the finite-difference
    directional derivative requires. The extra K evaluations go through their
    own cache: the shared ``k_cache`` is keyed WITHOUT the seed, so sharing it
    would return reference-seeded values for trial-seeded queries. The price
    of linearising the gate's surface is a second round of stage flashes per
    residual evaluation, reactive path only.

    Returns the per-stage seed list (never None entries: the candidate chain
    ends at the caller's pass-frozen K models, so the y = K*x construction is
    always evaluable - matching `_refresh_y`'s fallback chain).
    """
    liquid = _l_profile(col, l0, vs)
    out: list[dict[str, float]] = []
    for j in range(col.n):
        key = (
            tuple(sorted(xs[j].items())),
            round(ts[j], 12),
            col.pressures[j],
            tuple(sorted(y_reference[j].items())),
        )
        k = seed_cache.get(key)
        if k is None:
            k_misses[0] += 1
            k = (
                _stage_k_values(col, tb, j, xs[j], y_reference[j], ts[j], liquid[j], vs[j])
                or tb.k_estimate(_flash_ready(xs[j], col.feed_comp), ts[j], col.pressures[j])
                or k_fallbacks[j]
            )
            seed_cache[key] = k
        y = {cid: k.get(cid, 1.0) * xs[j].get(cid, 0.0) for cid in col.comps}
        total = sum(y.values())
        out.append({cid: v / total for cid, v in y.items()} if total > _FLOW_FLOOR else y)
    return out


def _fd_jacobian(
    residuals: Callable[[list[float]], list[float]], r0: list[float], u: list[float], n_unk: int
) -> list[list[float]] | None:
    """Forward-difference Jacobian of the shared residual at u.

    Returns None when a perturbed trial state is unevaluable (a degenerate or
    off-chemistry flash the residual machinery rejects) - the caller ends the
    pass with the line-search state intact for the polish.
    """
    jac: list[list[float]] = [[0.0] * n_unk for _ in range(len(r0))]
    for i in range(n_unk):
        delta = max(abs(u[i]) * 1e-7, 1e-9)
        u2 = list(u)
        u2[i] += delta
        try:
            r1 = residuals(u2)
        except (ColumnConvergenceError, ValueError):
            return None
        for row in range(len(r0)):
            jac[row][i] = (r1[row] - r0[row]) / delta
    return jac


def _lm_damped_step(jac: list[list[float]], r0: list[float], lam: float) -> list[float] | None:
    """Levenberg-Marquardt step: solve (J'J + lam*diag(J'J)) d = -J'r.

    Marquardt scaling (diag(J'J), not identity) keeps the damping per-variable:
    the packed unknowns span mole fractions ~1e-2, temperatures ~300 K and
    flows ~100 mol/s, so an identity damping would strangle the temperature and
    flow blocks first for no reason. Returns None when the damped system is
    singular (the caller abandons the pass).
    """
    m = len(r0)
    n_unk = len(jac[0]) if jac else 0
    if n_unk == 0:
        return None
    jtj = [[0.0] * n_unk for _ in range(n_unk)]
    g = [0.0] * n_unk
    for k in range(m):
        row = jac[k]
        rk = r0[k]
        for i in range(n_unk):
            ri = row[i]
            if ri == 0.0:
                continue
            g[i] -= ri * rk
            for j in range(i, n_unk):
                jtj[i][j] += ri * row[j]
    for i in range(n_unk):
        for j in range(i + 1, n_unk):
            jtj[j][i] = jtj[i][j]
    a = [[jtj[i][j] + (lam * jtj[i][i] if i == j else 0.0) for j in range(n_unk)] for i in range(n_unk)]
    try:
        return _gauss(a, g)
    except ColumnConvergenceError:
        return None


def _ns_try_accept(
    svec: list[float],
    u: list[float],
    n_unk: int,
    residuals: Callable[[list[float]], list[float]],
    m_norm_of: Callable[[list[float]], float],
    h_norm_of: Callable[[list[float]], float],
    m_current: float,
    h_current: float,
    live_norm: bool,
    ex_m: float,
    ex_h: float,
    prof: _Profile,
    apply: Callable[[_Profile, list[float]], None],
    exact_norms: Callable[[_Profile], tuple[float, float]],
) -> tuple[bool, tuple[float, float], float]:
    """One trial state through the joint descent + exact-gate tests.

    ``apply`` writes a trial state into the profile and ``exact_norms``
    evaluates the exact (refreshed-thermo) norms - the TWO engine-specific
    pieces here (dense `_apply_state` + `_refresh_y`/`_exact_residuals` vs
    the graph engine's graph apply + the same exact refreshed-thermo norms);
    the acceptance policy is the shared controller's, one for
    both engines.

    Returns (accepted, achieved norms, sum-of-squares of the trial residuals
    for the LM trust ratio). The trial norms and the exact double-check read
    the SAME shared residual (P1-11 step 2, ruling on #153); the double-check
    re-evaluates after ``_refresh_y``, which is what the NEXT pass's gate sees.
    """
    u_try = [u[i] + svec[i] for i in range(n_unk)]
    try:
        r_try = residuals(u_try)
        trial_m = m_norm_of(r_try)
        trial_h = h_norm_of(r_try)
        ss_try = sum(rv * rv for rv in r_try)
    except (ColumnConvergenceError, ValueError):
        # A trial step landed in a degenerate or off-chemistry state the
        # residual machinery cannot evaluate (SaturationError is a
        # ValueError subclass); reject it and shrink the step.
        trial_m, trial_h, ss_try = float("inf"), float("inf"), float("inf")
    # Joint max-norm descent: a step that polishes M while letting H
    # drift is rejected (measured P1-09 rectifier: the M-only search
    # walked M to 1e-8 with H pinned at 0.34 - the state had drifted
    # into an energy-infeasible corner the model refresh never
    # recovered from).
    if max(trial_m, trial_h) >= max(m_current, h_current):
        return False, (trial_m, trial_h), ss_try
    apply(prof, u_try)
    if not live_norm:
        return True, (trial_m, trial_h), ss_try
    # Live-norm acceptance: the frozen-row descent must also not worsen
    # either exact (refreshed-thermo) norm. Trials that improve the frozen
    # rows while walking either exact residual uphill are rejected and the
    # pre-step state restored (measured P1-09 stripper: frozen rows closed
    # to 6.9e-10 while refreshed exact M rose to 1.00 - the diverged trial
    # displaced a near-converged state the mesh could have kept).
    try:
        ex_try_m, ex_try_h = exact_norms(prof)
    except (ColumnConvergenceError, ValueError):
        ex_try_m, ex_try_h = float("inf"), float("inf")
    if max(ex_try_m, ex_try_h) < max(ex_m, ex_h):
        return True, (trial_m, trial_h), ss_try
    apply(prof, u)
    return False, (trial_m, trial_h), ss_try


def _ns_residual_function(
    col: _Column,
    tb: _ThermoBox,
    l0: float,
    k_fallback: list[dict[str, float]],
    t_bot_tear: float | None,
    scales: list[float] | None,
    k_cache: dict[tuple[tuple[tuple[str, float], ...], float, float], dict[str, float]],
    k_misses: list[int],
    h_evals: list[int],
    y_estimates: list[dict[str, float]] | None = None,
    y_reference: list[dict[str, float]] | None = None,
    seed_cache: dict[
        tuple[tuple[tuple[str, float], ...], float, float, tuple[tuple[str, float], ...]],
        dict[str, float],
    ]
    | None = None,
) -> Callable[[list[float]], list[float]]:
    """Build the residual callable for one Newton pass (fresh closures per pass).

    The rows are THE shared live residual (`_live_residual_vector`, inside_out.py
    - P1-11 step 2, ruling on #153): per-row relative-scaled M balances with
    y = K(T, x) * x from the live package, canonical NS summation rows, and live
    package enthalpies on the H rows - the exact gate's own vector. The FD
    Jacobian, the LM damping and the line-search norms below all linearise and
    test the number the gate reads, so the model-validity question ("did the
    achieved reduction match what the linear model predicted?") is asked on one
    residual by construction. No frozen enthalpy lines and no absolute rows
    remain in NS.

    ``y_reference`` + ``seed_cache`` (P1-11 R1, ruling on #153): on the reactive
    package the pass-frozen ``y_estimates`` snapshot leaves the loading walk
    seeded at the reference state while the trials move - Newton's linear model
    aligned with a residual the gate never reads (measured exothermic absorber:
    FD-singular at pass 1 cold; warm, M = 7.8e-6 on the internal rows vs ~1e-1
    exact after the pass-5 seed refresh). When both are set, every residual
    evaluation derives its seeds AT the state being evaluated (one loading-walk
    iteration from the frozen reference - `_reactive_trial_seeds`), so the
    Jacobian, the line search and the acceptance norm all read the exact
    gate's own surface. Scoped to the reactive live-norm path by the caller.

    ``scales`` (P1-11 ruling (c) on #153): the pass's FROZEN per-row M scale
    vector, computed by the caller from the pass's reference state (the iterate
    the Jacobian is built from) via `_residual_scales` and held fixed for the
    FD Jacobian, every line-search trial and the acceptance test of this pass.
    A scale derived per evaluation from the state being evaluated saturates the
    dominated rows at plus/minus one - not a smooth function of the unknowns -
    and the max-norm descent test then rejects the full steps that reduce the
    true imbalance (measured on the N4-r0.8 stripper). The cache and the
    counters are created by the caller and shared with the scale derivation,
    so the frozen scale costs no flashes beyond the cache entries it fills.
    ``None`` keeps the per-evaluation scale derivation - the warm two-tear
    path only, where pass-frozen scales measurably degrade the FD Jacobian
    (see `_naphtali_sandholm` for the deethanizer regression measurement).

    ``y_estimates`` (P1-11 step 3, ruling on #153): the caller's pass-frozen
    refreshed vapour seeds, handed to the shared stage-K evaluation. On the
    reactive package the seed enters the loading walk, so a residual evaluated
    with empty seeds sits on a different K surface than the exact gate, which
    reads the refreshed y = K*x - Newton's linear model then aligns with a
    residual the gate never sees (measured 20-stage MDEA absorber at the stall
    state: NS-internal M=1.4956e-1 vs exact M=1.1345e-2; with the seeds
    aligned the absorber closes in four NS passes). ``None`` keeps empty
    seeds - the non-reactive path, where passing seeds measurably moved the
    Kremser oracle outcomes.

    A per-stage K cache keeps the finite-difference Jacobian affordable: a
    perturbation of one packed unknown changes only its own stage's state, so
    all other stages hit the cache and cost no flash. The pass-frozen K models
    are the last-resort fallback when neither the live evaluation nor the
    k_estimate fallback is evaluable at a trial state.

    Returns the residual callable; ``k_misses``/``h_evals`` are the caller's
    per-pass counters (K evaluations beyond the cache, live-enthalpy
    evaluations) for the flash-cost measurement the ruling requires.
    """

    def residuals(u: list[float]) -> list[float]:
        xs = _unpack_x(u, col)
        ts = _unpack_t(u, col)
        vs = _unpack_v(u, col, _v_free_indices(col), t_bot_tear)
        return _live_residual_vector(
            col,
            tb,
            l0,
            xs,
            ts,
            vs,
            y_estimates=y_estimates,
            k_fallbacks=k_fallback,
            k_cache=k_cache,
            k_misses=k_misses,
            h_evals=h_evals,
            scales=scales,
        )

    return residuals


class _NSEngine(Protocol):
    """The ONE Newton controller's engine interface.

    `_ns_controller` drives both Naphtali-Sandholm engines - the dense
    fallback below and the stage-graph engine (``graph_ns.py``). An engine
    differs ONLY in its residual builder (``begin_pass``'s closure), its
    Jacobian builder (full one-column-at-a-time FD vs stage-coloured FD) and
    its linear solve (dense Gaussian elimination vs ``scipy.sparse`` LU),
    plus the graph-only per-pass temperature clamp behind ``cap_step`` (a
    no-op for the dense engine, whose behaviour must stay byte-identical).
    Everything else - the pass loop, the pass gate, the line search and
    acceptance through ``_ns_try_accept`` with best-iterate tracking, the
    rho-based LM damping adaptation, the pass budget and the final gate - is
    the controller's, by construction.
    """

    prof: _Profile
    live_norm: bool
    ex_m: float
    ex_h: float
    m_tol: float
    best_u: list[float] | None
    best_m: float
    best_h: float

    def begin_pass(self) -> tuple[list[float], Callable[[list[float]], list[float]]]: ...

    def m_norm_of(self, r: list[float]) -> float: ...

    def h_norm_of(self, r: list[float]) -> float: ...

    def norms(self, r: list[float]) -> tuple[float, float]: ...

    def jacobian(
        self, residuals: Callable[[list[float]], list[float]], r0: list[float], u: list[float]
    ) -> Any: ...

    def solve_linear(self, jac: Any, r0: list[float]) -> list[float] | None: ...

    def lm_step(self, jac: Any, r0: list[float], lam: float) -> list[float] | None: ...

    def linear_prediction(self, jac: Any, r0: list[float], step: list[float]) -> list[float]: ...

    def cap_step(self, step: list[float]) -> None: ...

    def apply(self, prof: _Profile, u: list[float]) -> None: ...

    def exact_norms(self, prof: _Profile) -> tuple[float, float]: ...

    def trace_jacobian_failed(self) -> None: ...

    def trace_solve_failed(self) -> None: ...

    def trace_pass(
        self,
        r0: list[float],
        jac: Any,
        step: list[float],
        lam: float,
        lam_lm: float,
        ach_m: float,
        ach_h: float,
        via: str,
        accepted: bool,
    ) -> None: ...

    def exhausted(self) -> None: ...

    def finish(self) -> None: ...


def _ns_controller(eng: _NSEngine, ns_max: int) -> None:
    """The ONE Naphtali-Sandholm damped-Newton controller, both engines.

    Per pass: build the pass's reference state and residual closure
    (``begin_pass``), evaluate it, run the ONE shared pass gate - refresh
    y = K*x at the checkpoint, then the exact (refreshed-thermo) norms with
    best-iterate tracking on the live-norm path, gated at the mesh
    tolerances - then the ONE shared step policy: the injected linear solve,
    the injected step cap, the line search and the Levenberg-Marquardt
    fallback, all accepting through ``_ns_try_accept``'s joint max-norm
    descent + exact-gate test, with the damping adapted from the
    achieved-vs-predicted sum-of-squares ratio.
    """
    for _ in range(ns_max):
        prof = eng.prof
        prof.ns_passes += 1
        u, residuals = eng.begin_pass()
        r0 = residuals(u)
        # The ONE shared pass gate, both engines: the dense engine's former
        # checkpoint moved here verbatim (review round 2, item 1), so the
        # dense behaviour is byte-identical. ``exact_norms`` refreshes
        # y = K*x and reads the exact refreshed-thermo residual - the NS
        # residual derives vapour compositions as K*x (equilibrium-consistent
        # by construction), so a state whose STORED y is stale reads as
        # converged internally while the exact check - which uses the stored
        # y - is wide open (measured P1-09 absorber, seed state: NS-internal
        # M=6.3e-3 vs exact M=1.00).
        eng.ex_m, eng.ex_h = eng.exact_norms(eng.prof)
        # Best-iterate tracking (zero/one-tear columns): keep the best exact
        # state across passes and restore it at exit. NS's finite-difference
        # Newton can walk PAST the near-converged state it started from into
        # an unevaluable one; the best-exact state is what the inside-out
        # polish in _solve_mesh needs.
        if eng.live_norm and eng.ex_m + eng.ex_h < eng.best_m + eng.best_h:
            eng.best_u, eng.best_m, eng.best_h = list(u), eng.ex_m, eng.ex_h
        if eng.ex_m < eng.m_tol and eng.ex_h < _MESH_H_TOL:
            break
        m_current, h_current = eng.norms(r0)
        n_unk = len(u)
        jac = eng.jacobian(residuals, r0, u)
        if jac is None:
            # A perturbed trial state the shared rows cannot evaluate: the
            # pass ends with the line-search state intact for the polish.
            eng.trace_jacobian_failed()
            break
        step = eng.solve_linear(jac, r0)
        if step is None:
            eng.trace_solve_failed()
            break
        # Graph-only safeguard (no-op for the dense engine): see the graph
        # engine's cap_step.
        eng.cap_step(step)

        lam = 1.0
        accepted = False
        ach_m = ach_h = float("inf")
        for _ in range(_NS_LINE_SEARCH_TRIES):
            # svec semantics: the helper builds u_try = u + svec, so the
            # lambda-scaled STEP goes in - not u + lam*step (measured
            # absorber[8] bisect: passing the trial state doubled it and
            # every trial read trial_m ~2600 against m_cur=218).
            ok, ach, _ss = _ns_try_accept(
                [lam * step[i] for i in range(n_unk)],
                u,
                n_unk,
                residuals,
                eng.m_norm_of,
                eng.h_norm_of,
                m_current,
                h_current,
                eng.live_norm,
                eng.ex_m,
                eng.ex_h,
                prof,
                eng.apply,
                eng.exact_norms,
            )
            if ok:
                accepted = True
                ach_m, ach_h = ach
                break
            lam *= 0.5
        via = "newton"
        lam_lm = 0.0
        if not accepted:
            # Model-validity fallback (P1-11 step 2, ruling on #153): when the
            # full step fails the shared-residual descent test, the linear
            # model's validity radius is shorter than the step (measured on the
            # reactive absorber: one full step predicted 8.3e-11 and achieved
            # 2346.7). Damp with Levenberg-Marquardt on the SAME Jacobian, the
            # damping adapted from the achieved-vs-predicted sum-of-squares
            # ratio. Package-agnostic: one residual, one controller.
            lam_lm = 1.0
            ss0 = sum(rv * rv for rv in r0)
            for _ in range(_NS_LM_TRIES):
                d_step = eng.lm_step(jac, r0, lam_lm)
                if d_step is None:
                    break
                lin_lm = eng.linear_prediction(jac, r0, d_step)
                ss_lin = sum(rv * rv for rv in lin_lm)
                ok, ach, ss_try = _ns_try_accept(
                    d_step,
                    u,
                    n_unk,
                    residuals,
                    eng.m_norm_of,
                    eng.h_norm_of,
                    m_current,
                    h_current,
                    eng.live_norm,
                    eng.ex_m,
                    eng.ex_h,
                    prof,
                    eng.apply,
                    eng.exact_norms,
                )
                denom = ss0 - ss_lin
                rho = (ss0 - ss_try) / denom if denom > 0.0 else float("inf")
                if ok:
                    accepted = True
                    ach_m, ach_h = ach
                    via = "lm"
                    break
                # Damping adaptation: a rejected trial (rho <= 0) or a poor
                # model match (rho < 0.25) means the step overreached even
                # damped - raise lambda; a good match pre-acceptance would
                # lower it, but a trial this good is accepted above.
                lam_lm *= 4.0 if rho < 0.25 else 2.0
        eng.trace_pass(r0, jac, step, lam, lam_lm, ach_m, ach_h, via, accepted)
        if not accepted:
            break
    else:
        eng.exhausted()
    eng.finish()


class _DenseNSEngine:
    """The dense fallback's injected pieces for `_ns_controller`.

    The residual closure is `_ns_residual_function`'s shared live residual,
    the Jacobian the full one-column-at-a-time FD matrix (`_fd_jacobian`),
    the linear solve dense Gaussian elimination (`_gauss`), and nothing
    else: the pass gate - the exact (refreshed-thermo) norms with
    best-iterate tracking and the mesh tolerances - lives in
    `_ns_controller`.
    ``cap_step`` is a no-op: the dense path's behaviour must stay
    byte-identical (bench and dispatch golden), so no graph-only safeguard
    may touch its steps.
    """

    prof: _Profile
    live_norm: bool
    ex_m: float
    ex_h: float

    def __init__(self, col: _Column, tb: _ThermoBox, prof: _Profile, t_bot_tear: float | None) -> None:
        self._col = col
        self._tb = tb
        self.prof = prof
        self._t_bot_tear = t_bot_tear
        self._v_free = _v_free_indices(col)
        self._m_rows, self._h_rows = _residual_row_blocks(col, _h_equation_stages(col))
        self.live_norm = col.n_tears < 2
        if col.n_tears >= 2:
            self.m_tol = _MESH_M_TOL
        elif _is_reactive_package(tb):
            self.m_tol = _MESH_M_TOL_REACTIVE
        else:
            # Same gate the mesh accepts at (_MESH_M_TOL_ZERO_ONE_TEAR): the NS
            # state hands off to _solve_mesh's inside-out polish, and the polish
            # lifts the state further before the mesh's own acceptance decides.
            # A tighter intermediate gate only discarded measurably converged
            # states (measured P1-09 stripper: NS polished a warm-chained state
            # to M=2.90e-7, H=4.46e-10 and the 1e-7 gate typed the tear failed).
            self.m_tol = _MESH_M_TOL_ZERO_ONE_TEAR
        self.best_u: list[float] | None = None
        self.best_m = float("inf")
        self.best_h = float("inf")
        self.ex_m = float("inf")
        self.ex_h = float("inf")
        self._k_misses = [0]
        self._h_evals = [0]

    def begin_pass(self) -> tuple[list[float], Callable[[list[float]], list[float]]]:
        """One pass's reference state, residual closure and frozen quantities."""
        col, tb, prof = self._col, self._tb, self.prof
        k_stages = [
            _stage_k_values(col, tb, j, prof.x[j], prof.y[j], prof.T[j], prof.L[j], prof.V[j])
            or tb.k_estimate(_flash_ready(prof.x[j], col.feed_comp), prof.T[j], col.pressures[j])
            or {cid: 1.0 for cid in col.comps}
            for j in range(col.n)
        ]
        # Ruling (c) on #153: the per-row M scale is a function of the iterate
        # (a row divided by its own state-derived scale saturates at plus/minus
        # one and the max-norm descent test then rejects the full steps that
        # reduce the true imbalance - measured on the N4-r0.8 stripper), so it
        # is computed ONCE per pass, here, from the pass's reference state
        # (this iterate), and held fixed for the FD Jacobian, every
        # line-search trial and the acceptance test. The cache and counters
        # are shared with the residual closure so the derivation costs no
        # flashes beyond the cache entries it fills.
        #
        # Frozen scales apply on the live-norm (zero/one-tear) path only.
        # Measured regression on the warm two-tear path (C1-C5 deethanizer,
        # 22 stages, inside-out best M=4.2e-6 whose stored y lags K*x so the
        # NS rows start at M~0.5): with pass-frozen scales the FD Jacobian
        # loses the d(scale) terms the per-evaluation rows carry, the full
        # Newton step predicted machine-zero and achieved M=0.47, and the
        # next pass went FD-singular - the legacy per-evaluation scaling
        # converges this state in a few passes (main, measured). The two-tear
        # path keeps its 1e-8 gate and its measured-good semantics; ruling
        # (c)'s stall is a zero/one-tear physical-branch failure.
        u = _pack_state(prof, col, self._v_free)
        k_cache: dict[tuple[tuple[tuple[str, float], ...], float, float], dict[str, float]] = {}
        self._k_misses = [0]
        self._h_evals = [0]
        pass_scales: list[float] | None = None
        y_seeds: list[dict[str, float]] | None = None
        seed_cache: dict[
            tuple[tuple[tuple[str, float], ...], float, float, tuple[tuple[str, float], ...]],
            dict[str, float],
        ] = {}
        if self.live_norm and _is_reactive_package(tb):
            # P1-11 step 3 (ruling on #153): the exact gate reads its K surface
            # with the profile's refreshed y = K*x as the stage-K vapour seed,
            # while the NS rows passed empty seeds - on the reactive package the
            # seed enters the loading walk, so Newton's linear model aligned
            # with a residual the gate never saw (measured 20-stage MDEA
            # absorber at the stall state: NS-internal M=1.4956e-1 vs exact
            # M=1.1345e-2). Refresh once per pass from this pass's reference
            # state and hand the frozen snapshot to both the scale derivation
            # and the residual evaluation, so the linearisation, the line
            # search and the gate read one surface. Scoped to the reactive
            # package (passing seeds on non-reactive columns measurably moved
            # the Kremser oracle outcomes) and to the live-norm path (the warm
            # two-tear path keeps its convention; see the deethanizer
            # regression above).
            _refresh_y(col, tb, prof)
            y_seeds = list(prof.y)
        if self.live_norm:
            pass_scales = _residual_scales(
                col,
                tb,
                prof.l0,
                _unpack_x(u, col),
                _unpack_t(u, col),
                _unpack_v(u, col, self._v_free, self._t_bot_tear),
                y_estimates=y_seeds,
                k_fallbacks=k_stages,
                k_cache=k_cache,
                k_misses=self._k_misses,
            )
        residuals = _ns_residual_function(
            col,
            tb,
            prof.l0,
            k_stages,
            self._t_bot_tear,
            pass_scales,
            k_cache,
            self._k_misses,
            self._h_evals,
            y_estimates=y_seeds,
            y_reference=y_seeds,
            seed_cache=seed_cache if y_seeds is not None else None,
        )
        return u, residuals

    def m_norm_of(self, r: list[float]) -> float:
        """Max scaled residual over the M rows (the exact-M gate's block)."""
        return max(abs(r[i]) for i in self._m_rows)

    def h_norm_of(self, r: list[float]) -> float:
        """Max scaled residual over the H rows (the line-search's second block)."""
        return max((abs(r[i]) for i in self._h_rows), default=0.0)

    def norms(self, r: list[float]) -> tuple[float, float]:
        return (self.m_norm_of(r), self.h_norm_of(r))

    def jacobian(
        self, residuals: Callable[[list[float]], list[float]], r0: list[float], u: list[float]
    ) -> Any:
        return _fd_jacobian(residuals, r0, u, len(u))

    def solve_linear(self, jac: Any, r0: list[float]) -> list[float] | None:
        try:
            return _gauss(jac, [-r for r in r0])
        except ColumnConvergenceError:
            return None

    def lm_step(self, jac: Any, r0: list[float], lam: float) -> list[float] | None:
        return _lm_damped_step(jac, r0, lam)

    def linear_prediction(self, jac: Any, r0: list[float], step: list[float]) -> list[float]:
        n_unk = len(step)
        return [r0[i] + sum(jac[i][j] * step[j] for j in range(n_unk)) for i in range(len(r0))]

    def cap_step(self, step: list[float]) -> None:
        """No-op: the dense path's steps stay byte-identical (see class doc)."""
        _ = step

    def apply(self, prof: _Profile, u: list[float]) -> None:
        _apply_state(prof, u, self._col, self._v_free, self._t_bot_tear)

    def exact_norms(self, prof: _Profile) -> tuple[float, float]:
        _refresh_y(self._col, self._tb, prof)
        return _exact_residuals(self._col, self._tb, prof)

    def trace_jacobian_failed(self) -> None:
        self.prof.ns_trace.append(
            f"pass {self.prof.ns_passes}: exact M={self.ex_m:.3e} H={self.ex_h:.3e} | FD unavailable "
            f"| flashes(k+h)={self._k_misses[0] + self._h_evals[0]} via=fd-failed"
        )

    def trace_solve_failed(self) -> None:
        self.prof.ns_trace.append(
            f"pass {self.prof.ns_passes}: exact M={self.ex_m:.3e} H={self.ex_h:.3e} | FD singular "
            f"| flashes(k+h)={self._k_misses[0] + self._h_evals[0]} via=fd-failed"
        )

    def trace_pass(
        self,
        r0: list[float],
        jac: Any,
        step: list[float],
        lam: float,
        lam_lm: float,
        ach_m: float,
        ach_h: float,
        via: str,
        accepted: bool,
    ) -> None:
        _ = accepted
        # Linear-model prediction of the full uncapped Newton step: the
        # denominator of the achieved-vs-predicted trust test in the trace.
        # Measured absorber probe: max|r| predicted 8.3e-11 vs 2346.7 achieved -
        # the 11-order validity gap that motivates the controller.
        n_unk = len(step)
        lin = [r0[i] + sum(jac[i][j] * step[j] for j in range(n_unk)) for i in range(len(r0))]
        pred_m = max(abs(lin[i]) for i in self._m_rows)
        pred_h = max((abs(lin[i]) for i in self._h_rows), default=0.0)
        self.prof.ns_trace.append(
            f"pass {self.prof.ns_passes}: exact M={self.ex_m:.3e} H={self.ex_h:.3e} "
            f"| lin-pred M={pred_m:.3e} H={pred_h:.3e} | lam={lam:.3g} lam_lm={lam_lm:.3g} "
            f"achieved M={ach_m:.3e} H={ach_h:.3e} via={via} "
            f"flashes(k+h)={self._k_misses[0] + self._h_evals[0]}"
        )

    def exhausted(self) -> None:
        if self.live_norm and self.best_u is not None:
            _apply_state(self.prof, self.best_u, self._col, self._v_free, self._t_bot_tear)
        raise ColumnConvergenceError("Naphtali-Sandholm fallback did not converge within budget")

    def finish(self) -> None:
        col, tb, prof = self._col, self._tb, self.prof
        if self.live_norm and self.best_u is not None:
            _apply_state(prof, self.best_u, col, self._v_free, self._t_bot_tear)
        _refresh_y(col, tb, prof)
        m_res, h_res = _exact_residuals(col, tb, prof)
        prof.ns_used = True
        # Same tolerances as the inside-out acceptance gate: the enthalpy-line
        # anchor floor sits around 1e-3-1e-4 relative, while mass closes to
        # machine precision. Demanding 1e-6 on H here would reject a solution
        # the mesh itself accepts.
        if m_res > self.m_tol or h_res > _MESH_H_TOL:
            raise ColumnConvergenceError(
                f"Naphtali-Sandholm fallback stalled: max residuals M={m_res:.2e}, H={h_res:.2e}"
                + (f" | {'; '.join(prof.ns_trace)}" if prof.ns_trace else "")
            )
        _finalize_duties(col, tb, prof)


def _naphtali_sandholm(col: _Column, tb: _ThermoBox, prof: _Profile, t_bot_tear: float | None) -> _Profile:
    """Fallback: simultaneous damped Newton on (x, T, V), the shared controller.

    Unknowns: the liquid mole fractions x_ij, the stage temperatures T_j and the
    free vapour flows V_j. Equations: the M balances, the summations
    sum_i x_ij = 1, and the H balances whose duty is not an output - square per
    stage grouping (Naphtali & Sandholm 1971). The rows are the ONE shared live
    residual (``_live_residual_vector``, P1-11 step 2 ruling on #153): K and the
    package enthalpies are evaluated live at every state the walk visits, the
    pass-frozen K models survive only as the last-resort fallback, and the FD
    Jacobian, the LM damping and the line-search norms all read the exact
    gate's own vector - with the per-row M scale frozen once per pass from the
    pass's reference state (ruling (c) on #153; the gate freezes it from the
    state it gates, the only frozen quantity that differs).

    The pass loop, the line search and acceptance, the LM damping adaptation
    and the final gate are `_ns_controller`'s - the ONE Newton policy shared
    with the stage-graph engine; the dense engine's injected pieces are the
    dense residual closure, the full FD Jacobian and the Gaussian solve.
    """
    eng = _DenseNSEngine(col, tb, prof, t_bot_tear)
    ns_max = _NS_MAX if col.n_tears >= 2 else _NS_MAX_ZERO_ONE_TEAR
    _ns_controller(eng, ns_max)
    return prof


def _pack_state(prof: _Profile, col: _Column, v_free: list[int]) -> list[float]:
    # .get with a 0.0 default: the seed profile for a zero/one-tear column can
    # carry only the components present in the seed compositions (measured P1-09
    # absorber: a pure-nC4 liquid seed gives x = {"nC4": 1.0} and a bare
    # [cid] lookup raises KeyError before the first Newton pass - the fallback
    # never ran at all for these columns).
    u = [prof.x[j].get(cid, 0.0) for j in range(col.n) for cid in col.comps]
    u.extend(prof.T)
    u.extend(prof.V[j] for j in v_free)
    return u


def _unpack_x(u: list[float], col: _Column) -> list[dict[str, float]]:
    out = []
    pos = 0
    for _ in range(col.n):
        out.append({cid: max(u[pos + i], 0.0) for i, cid in enumerate(col.comps)})
        pos += len(col.comps)
    return out


def _unpack_t(u: list[float], col: _Column) -> list[float]:
    base = col.n * len(col.comps)
    # Trial temperatures are clamped to the two-phase operating band (spec D):
    # an unclamped Newton trial can leave it and degenerate the live-K flash.
    return [min(max(u[base + j], col.t_band_lo), col.t_band_hi) for j in range(col.n)]


def _unpack_v(u: list[float], col: _Column, v_free: list[int], t_bot_tear: float | None) -> list[float]:
    base = col.n * len(col.comps) + col.n
    full = [_FLOW_FLOOR] * col.n
    for idx, j in enumerate(v_free):
        full[j] = max(_FLOW_FLOOR, u[base + idx])
    if t_bot_tear is not None:
        full[col.n - 1] = t_bot_tear
    return full


def _apply_state(
    prof: _Profile, u: list[float], col: _Column, v_free: list[int], t_bot_tear: float | None
) -> None:
    # _unpack_x clamps Newton trial values at zero without renormalizing (the
    # residual algebra needs the raw clamped values); the applied profile must
    # be a valid composition - downstream consumers flash it.
    prof.x = [
        _flash_ready({cid: max(v, 0.0) for cid, v in xs.items()}, col.feed_comp) for xs in _unpack_x(u, col)
    ]
    prof.T = _unpack_t(u, col)
    prof.V = _unpack_v(u, col, v_free, t_bot_tear)
    prof.L = _l_profile(col, prof.l0, prof.V)


def _refresh_y(col: _Column, tb: _ThermoBox, prof: _Profile) -> None:
    """Recompute vapour compositions y = K(T, P) x from the current stage states.

    The Newton apply writes x/T/V/L only; downstream consumers (boundary
    streams, spec residuals, duties, info) need the vapour side of the same
    equilibrium, not the stale flash composition from an earlier state.
    """
    for j in range(col.n):
        k = _stage_k_values(col, tb, j, prof.x[j], prof.y[j], prof.T[j], prof.L[j], prof.V[j])
        if k is None:
            k = tb.k_estimate(_flash_ready(prof.x[j], col.feed_comp), prof.T[j], col.pressures[j])
        if k is None:
            k = {cid: 1.0 for cid in col.comps}
        y = {cid: k.get(cid, 1.0) * prof.x[j].get(cid, 0.0) for cid in col.comps}
        total = sum(y.values())
        if total > _FLOW_FLOOR:
            y = {cid: v / total for cid, v in y.items()}
        prof.y[j] = y
