"""Generalized spec solve: named tears, side strippers, refiner specs (S0-1).

The legacy two-tear secant (``_solve_specs``) is locked by the distillation
benchmark; configurations that use any S0-1 extension solve here instead.

**Coupling method (S0-1 feature 2, declared per the spec's requirement):** the
main column and its side strippers are solved as a tear on the vapour return,
NOT as one simultaneous MESH system. One evaluation of the coupled system
means: solve the main column at the current tear values, with each stripper's
overhead vapour injected as a feed at ``return_stage`` (and its liquid draw
leaving at ``draw_stage``), then re-solve every stripper as a standalone
zero/one-tear column on the main column's draw-stage liquid. The return
state itself - flow, temperature and composition - is a tear vector of the
SAME bounded secant that drives the specs, with one residual per injected
quantity (``injected - recomputed``). An earlier draft iterated a damped
fixed point on the return state inside every mesh evaluation and never
converged: measured on the steam-stripper case, the coupling map amplifies a
4e-5 input change into a 1.3e-2 output change (the steep C3/iC4 profile in
the main column's midsection), and no relaxation converges a gain-300 map.
Newton-type secant iteration on the full residual vector does.

**Spec/tear counting (part 2a scope):** every free tear - reflux/boilup, a
stripper draw - is driven by exactly one user-facing residual: the classic
column specs from ``params['specs']`` plus one ``product_rate`` row per
configured stripper. The return-state tears add one coupling residual per
injected quantity; they are internal auxiliaries of the vapour-return tear,
not user specs, so the parse-time count rule (which pairs user specs with
tears) does not count them. The count rule is enforced at parse time; here
a mismatch is unreachable. The feature-4 refiner specs (``draw_rate``,
``stage_temperature``, ``pumparound_duty``, ``pumparound_return_T``) and
their free tears refuse at parse (S0-1 part 2b); this driver gains them
then.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from .inside_out import _build_column, _Column, _Profile, _seed_profile, _temperature_seed
from .linalg import _gauss
from .spec import (
    _FLOW_FLOOR,
    _SPEC_MAX,
    _SPEC_TOL,
    ColumnConvergenceError,
    ColumnSpecError,
    _DrawSpec,
    _FeedSpec,
    _Params,
    _parse_params,
    _SideStripper,
)
from .specs import _check_spec_feasibility, _initial_tears, _solve_mesh, _solve_specs
from .thermo_adapter import _ThermoBox

#: Component id of the stripping steam (pure water).
_STEAM_CID = "H2O"

#: Per-driver stop tolerances, in the residual's own units. Rate specs stop
#: on relative error. 1e-6 sits just above the MEASURED warm-start mesh
#: noise floor (return/product flows reproduce to ±5e-7 mol/s on the
#: steam-stripper case): a 1e-10 relative rate stop demands 8e-10 mol/s
#: absolute on that case - three orders below the noise floor, so the
#: secant chases iterate noise forever (measured: it stalls at 94x the
#: stop with the product already correct to 9e-9 RELATIVE, well inside the
#: spec's own 1e-8 rate-target requirement).
_STOP_RATE_REL = 1e-6

#: Vapour-return coupling stops. The injected return state must match the
#: recomputed stripper overhead to these bounds at the accepted solution.
#: They sit just above the MEASURED reproducibility of the STRIPPER
#: sub-solves (not the main mesh: at the converged tears the stripper
#: overhead reproduces to ~2e-6 relative flow and ~6e-5 K across
#: evaluations on the steam-stripper case - the warm-started stripper rungs
#: are noisier than the main column's ±5e-7 / ±4e-6). Stops below those
#: floors chase sub-solve iterate noise: measured, the secant ground 10
#: minutes to maxrel 2-6x and the stale counter fired on pure noise while
#: the tears sat frozen. The boundary BALANCES still close exactly by
#: construction - the return stream is injected into the main column as a
#: feed, so no reported balance depends on these residuals.
_STOP_COUPLE_FLOW_REL = 1e-5
_STOP_COUPLE_T_K = 1e-4
_STOP_COUPLE_COMP = 1e-5


@dataclass(frozen=True)
class _StripperReport:
    """Converged side-stripper boundary state (S0-1 feature 2)."""

    name: str
    overhead_flow: float
    overhead_T: float
    overhead_P: float
    overhead_comp: dict[str, float]
    product_flow: float
    product_T: float
    product_P: float
    product_comp: dict[str, float]
    reboiler_duty_W: float


@dataclass
class _Coupled:
    """One evaluation of the coupled system: main column plus its strippers."""

    params: _Params  # the injected params the main column actually solved on
    col: _Column
    prof: _Profile
    reports: list[_StripperReport]
    strip_draws: dict[str, float]
    #: Injected return states, name -> (flow, T, composition). These are the
    #: tear values the main column consumed; the coupling residuals compare
    #: them against each report's recomputed overhead.
    ret_states: dict[str, tuple[float, float, dict[str, float]]]
    #: Each stripper's last converged profile, name -> profile. Warm-start
    #: seeds for the next evaluation's stripper sub-solves (the main mesh
    #: warm-starts from ``prof``; the strippers need their own seeds - a cold
    #: 4-stage steam stripper stalls at a probe point 4% from a converged
    #: draw, measured M stuck at 3.8e-2 over 9 NS passes).
    strip_profiles: dict[str, _Profile]


def _needs_full(params: _Params) -> bool:
    """True when the configuration must solve on the generalized driver."""
    return bool(params.side_strippers)


def _species(params: _Params) -> list[str]:
    """The species the return composition is expressed over (sorted, deterministic).

    The union of every feed's components plus the steam. A stripper's
    overhead can in principle carry any of them, and the injected feed is
    renormalized over exactly this list.
    """
    names: set[str] = {_STEAM_CID}
    for f in params.feeds:
        names.update(f.comp)
    return sorted(names)


def _injected(
    params: _Params,
    strip_draws: dict[str, float],
    ret_states: dict[str, tuple[float, float, dict[str, float]]],
) -> _Params:
    """Copy params with the stripper couplings written in.

    Stripper draws leave the main column as liquid draws; stripper overhead
    vapour re-enters as a feed at ``return_stage`` (at the main column's own
    pressure there). Both are INTERNAL to the unit (the draw's material
    returns as vapour plus product) - the facade counts only the original
    feeds and the stripper products at the boundary.
    """
    feeds = list(params.feeds)
    draws = list(params.draws)
    for st in params.side_strippers:
        draws.append(_stripper_draw(st, strip_draws[st.name]))
        ret_flow, ret_T, ret_comp = ret_states[st.name]
        if st.n_stages > 0 and ret_flow > _FLOW_FLOOR:
            feeds.append(
                _FeedSpec(
                    stage=st.return_stage,
                    T=ret_T,
                    P=params.pressures[st.return_stage - 1],
                    flow=ret_flow,
                    comp=dict(ret_comp),
                )
            )
    return replace(params, feeds=feeds, draws=draws)


def _stripper_draw(st: _SideStripper, flow: float) -> _DrawSpec:
    """The stripper's liquid draw as a main-column draw row."""
    return _DrawSpec(stage=st.draw_stage, vapor=False, flow=flow, name=st.name)


def _solve_stripper(
    st: _SideStripper,
    tb: _ThermoBox,
    flow: float,
    prof: _Profile,
    col: _Column,
    seed: _Profile | None,
) -> tuple[_Column, _Profile, _StripperReport]:
    """Solve one stripper on the main column's draw-stage liquid state.

    A standalone zero/one-tear column (condenserless; kettle reboiler only
    under the duty option, then driven by a ``reboiler_duty_W`` spec through
    the legacy one-tear path). ``n_stages = 0`` is the plain-draw degenerate
    case: everything drawn leaves as product, nothing returns. Returns the
    stripper's own column and converged profile (the main column's when
    ``n_stages = 0``, where no stripper hardware exists) plus the boundary
    report; the profile only serves as the next evaluation's warm seed.
    """
    j = st.draw_stage - 1
    comp = dict(prof.x[j])
    t_draw = prof.T[j]
    p_draw = col.pressures[j]
    if st.n_stages == 0:
        return (
            col,
            prof,
            _StripperReport(
                name=st.name,
                overhead_flow=0.0,
                overhead_T=0.0,
                overhead_P=0.0,
                overhead_comp={},
                product_flow=flow,
                product_T=t_draw,
                product_P=p_draw,
                product_comp=comp,
                reboiler_duty_W=0.0,
            ),
        )
    feeds: list[dict[str, Any]] = [
        {"stage": 1, "T": t_draw, "P": p_draw, "molar_flow": flow, "composition": comp}
    ]
    steam = st.steam_flow or 0.0
    if steam > _FLOW_FLOOR:
        feeds.append(
            {
                "stage": st.n_stages,
                "T": st.steam_T,
                "P": st.steam_P,
                "molar_flow": steam,
                "composition": {_STEAM_CID: 1.0},
            }
        )
    params2: dict[str, Any] = {
        "n_stages": st.n_stages,
        "condenser": "none",
        "reboiler": "kettle" if st.reboiler_duty_W is not None else "none",
        "pressure_profile": p_draw,
        "feeds": feeds,
        "specs": {} if st.reboiler_duty_W is None else {"reboiler_duty_W": st.reboiler_duty_W},
    }
    parsed2 = _parse_params(params2, None)
    col2 = _build_column(parsed2, tb)
    if st.reboiler_duty_W is None:
        # Zero free tears: the feeds determine the column, so one mesh solve
        # IS the answer (the legacy path's zero-tear branch). The ladder is
        # deliberately DETERMINISTIC at every rung - the coupling stop floors
        # (and the secant's ability to polish at all) were calibrated on a
        # reproducible sub-solve: a history-warm stripper makes the overhead
        # noisy at the 1e-3 level and the secant then chases that noise
        # forever (measured: product residual plateaued at ~1e-3, jumped to
        # 1.6e-1 at iteration 31). Rung 1: cold. Rung 2: NS-first from the
        # crude hot-bottom seed - a zero-tear column cold runs the inside-out
        # loop first, which wanders off (M closes while H drifts) and the NS
        # fallback then stalls from the wandered state, but NS started from
        # the crude seed itself converges at every neighbouring tear in
        # ~0.2 s (measured, P1-10). Rung 3: the stripper's last converged
        # profile - the only non-deterministic rung, kept as the last resort
        # because the secant's probes sit a few percent from a good solution
        # where both deterministic rungs can stall.
        try:
            prof2 = _solve_mesh(col2, tb, None, None, None)
        except ColumnConvergenceError:
            try:
                t_top_seed, t_bot_seed = _temperature_seed(col2, tb)
                crude = _seed_profile(col2, tb, t_top_seed, t_bot_seed, v_bot_tear=None)
                prof2 = _solve_mesh(col2, tb, None, None, crude)
            except ColumnConvergenceError:
                if seed is None:
                    raise
                prof2 = _solve_mesh(col2, tb, None, None, seed)
    else:
        prof2 = _solve_specs(col2, tb, parsed2)
    rep = _StripperReport(
        name=st.name,
        overhead_flow=prof2.d,
        overhead_T=prof2.T[0],
        overhead_P=col2.pressures[0],
        overhead_comp=dict(prof2.y[0]),
        product_flow=prof2.b,
        product_T=prof2.T[col2.n - 1],
        product_P=col2.pressures[col2.n - 1],
        product_comp=dict(prof2.x[col2.n - 1]),
        reboiler_duty_W=prof2.qr if st.reboiler_duty_W is not None else 0.0,
    )
    return col2, prof2, rep


def _eval_coupled(
    params: _Params,
    tb: _ThermoBox,
    t_top: float | None,
    t_bot: float | None,
    strip_draws: dict[str, float],
    ret_states: dict[str, tuple[float, float, dict[str, float]]],
    seed: _Profile | None,
    strip_seeds: dict[str, _Profile],
) -> _Coupled:
    """One evaluation of the coupled system at the given tear values.

    The main mesh warm-starts from the previous evaluation's profile for
    speed; its warm-start reproducibility (flow ±5e-7, T ±4e-6 K, measured
    on the steam-stripper case) sets the coupling stop floors above. A
    failing main solve propagates to the secant's probe shrinking.
    """
    parsed_full = _injected(params, strip_draws, ret_states)
    col = _build_column(parsed_full, tb)
    prof = _solve_mesh(col, tb, t_top, t_bot, seed)
    reports = []
    strip_profiles: dict[str, _Profile] = {}
    for st in params.side_strippers:
        col_s, prof_s, rep = _solve_stripper(
            st, tb, strip_draws[st.name], prof, col, strip_seeds.get(st.name)
        )
        reports.append(rep)
        strip_profiles[st.name] = prof_s
    return _Coupled(
        params=parsed_full,
        col=col,
        prof=prof,
        reports=reports,
        strip_draws=dict(strip_draws),
        ret_states={k: (f, t, dict(c)) for k, (f, t, c) in ret_states.items()},
        strip_profiles=strip_profiles,
    )


def _stripper_seed(st: _SideStripper, col: _Column) -> float:
    """Starting guess for a stripper's draw flow (mol/s)."""
    assert st.product_rate is not None  # parse requires a driver (part 2a)
    return max(st.product_rate + (st.steam_flow or 0.0), _FLOW_FLOOR)


def _fmt_residuals(g: list[float], names: list[str]) -> str:
    return "{" + ", ".join(f"{n}: {v:.6g}" for n, v in zip(names, g, strict=True)) + "}"


def _g_full(coupled: _Coupled, params: _Params, skip: set[str]) -> tuple[list[float], list[float], list[str]]:
    """Residuals, stop tolerances, and driver names for every active driver.

    Rows follow the params.specs insertion order (the classic column specs),
    then one ``product_rate`` row per configured stripper, then the
    vapour-return coupling rows (``injected - recomputed``) per stripper with
    stages. Each stop is in its residual's own units, so ``|g| < stop`` means
    "satisfied"; the secant drives ``g / stop`` to zero (dimensionless, O(1)
    at the gate - the same scaling discipline the legacy loop applies with
    target scales).
    """
    g: list[float] = []
    stops: list[float] = []
    names: list[str] = []
    col, prof = coupled.col, coupled.prof
    for key, raw in params.specs.items():
        if key in skip:
            continue
        target_f = float(raw)
        if key == "reflux_ratio":
            g.append(prof.l0 / max(prof.d, _FLOW_FLOOR) - target_f)
        elif key == "boilup_ratio":
            g.append(prof.V[col.n - 1] / max(prof.b, _FLOW_FLOOR) - target_f)
        elif key == "distillate_rate":
            g.append(prof.d - target_f)
        elif key == "bottoms_rate":
            g.append(prof.b - target_f)
        elif key == "condenser_duty_W":
            g.append(prof.qc - target_f)
        elif key == "reboiler_duty_W":
            g.append(prof.qr - target_f)
        else:  # pragma: no cover - _parse_params rejects unknown keys
            raise ColumnSpecError(f"unsupported spec {key!r}")
        names.append(key)
        stops.append(_SPEC_TOL * max(target_f, 1e-12))
    for st in params.side_strippers:
        if st.product_rate is not None:
            rep = next(r for r in coupled.reports if r.name == st.name)
            g.append(rep.product_flow - st.product_rate)
            names.append(f"stripper:{st.name}.product_rate")
            stops.append(_STOP_RATE_REL * max(abs(st.product_rate), 1e-12))
    for st in params.side_strippers:
        if st.n_stages < 2:
            continue  # no stages: nothing returns, so there is no return tear
        rep = next(r for r in coupled.reports if r.name == st.name)
        inj_f, inj_t, inj_comp = coupled.ret_states[st.name]
        g.append(inj_f - rep.overhead_flow)
        names.append(f"stripper:{st.name}.return_flow")
        stops.append(_STOP_COUPLE_FLOW_REL * max(inj_f, 1.0))
        g.append(inj_t - rep.overhead_T)
        names.append(f"stripper:{st.name}.return_T")
        stops.append(_STOP_COUPLE_T_K)
        for cid in _species(params)[:-1]:
            g.append(inj_comp.get(cid, 0.0) - rep.overhead_comp.get(cid, 0.0))
            names.append(f"stripper:{st.name}.return_x[{cid}]")
            stops.append(_STOP_COUPLE_COMP)
    return g, stops, names


def _solve_specs_full(params: _Params, tb: _ThermoBox) -> _Coupled:
    """Generalized bounded secant over the named tears (S0-1 feature 2).

    Same pinning algebra as the legacy path for the classic ratio/rate pairs;
    the stripper draws and the strippers' vapour-return states (flow, T,
    composition) join the tear vector, and the per-stripper ``product_rate``
    rows and the return-coupling residuals join the residual vector. Every
    residual names itself in errors.
    """
    _check_spec_feasibility(_build_column(params, tb), tb, params)
    col0 = _build_column(params, tb)
    t_top, t_bot = _initial_tears(col0, params)
    specs = params.specs
    d_spec = specs.get("distillate_rate")
    b_spec = specs.get("bottoms_rate")
    r_spec = specs.get("reflux_ratio")
    vb_spec = specs.get("boilup_ratio")
    draw_total = sum(dr.flow for dr in params.draws if dr.flow is not None)
    pin_top = False
    pin_bot = False
    skip: set[str] = set()
    if col0.condenser == "total" and r_spec is not None and d_spec is not None:
        t_top = float(r_spec) * float(d_spec)
        pin_top = True
        skip.add("reflux_ratio")
    elif col0.condenser == "total" and r_spec is not None and b_spec is not None:
        t_top = float(r_spec) * max(col0.f_total - float(b_spec) - draw_total, _FLOW_FLOOR)
        pin_top = True
        skip.add("reflux_ratio")
    if col0.reboiler == "kettle" and vb_spec is not None and d_spec is not None:
        t_bot = float(vb_spec) * max(col0.f_total - float(d_spec) - draw_total, _FLOW_FLOOR)
        pin_bot = True
        skip.add("boilup_ratio")
    elif col0.reboiler == "kettle" and vb_spec is not None and b_spec is not None:
        t_bot = float(vb_spec) * float(b_spec)
        pin_bot = True
        skip.add("boilup_ratio")
    if col0.condenser == "partial" and d_spec is not None:
        t_top = float(d_spec)
        pin_top = True
        skip.add("distillate_rate")
    if col0.n_tears < 2 and col0.condenser == "total" and d_spec is not None and not pin_top:
        # Same as the legacy path: a total condenser's distillate-rate spec
        # drives the reflux tear (d = V_0 - l0); it stays a free tear.
        t_top = max(float(col0.f_total) - float(d_spec), _FLOW_FLOOR)
    free_top = t_top is not None and not pin_top
    free_bot = t_bot is not None and not pin_bot
    if col0.condenser == "total" and pin_top and free_bot and t_top is not None:
        # Legacy seed boost: start the first mesh at high vapour traffic.
        t_bot = t_top + col0.f_total * 0.2

    t_top_pinned = t_top
    t_bot_pinned = t_bot
    species = _species(params)
    feed_t = params.feeds[0].T if params.feeds else 300.0
    feed_comp = params.feeds[0].comp if params.feeds else {}

    def unpack(
        v: list[float],
    ) -> tuple[
        float | None,
        float | None,
        dict[str, float],
        dict[str, tuple[float, float, dict[str, float]]],
    ]:
        """Map the free-tear vector onto concrete tear values.

        Stripper draw flows are clamped to the physical floor, return
        temperatures to a wide window, compositions renormalized over the
        species list; the stale counter and _SPEC_MAX catch a run that only
        survives by clamping.
        """
        it = iter(v)
        top = next(it) if free_top else t_top_pinned
        bot = next(it) if free_bot else t_bot_pinned
        strip_draws: dict[str, float] = {}
        ret_states: dict[str, tuple[float, float, dict[str, float]]] = {}
        for st in params.side_strippers:
            strip_draws[st.name] = max(next(it), _FLOW_FLOOR)
            if st.n_stages < 2:
                ret_states[st.name] = (0.0, 0.0, {})
                continue
            ret_f = max(next(it), _FLOW_FLOOR)
            ret_t = min(max(next(it), 180.0), 2000.0)
            fr = [max(next(it), 0.0) for _ in species[:-1]]
            comp = {cid: x for cid, x in zip(species[:-1], fr, strict=True)}
            comp[species[-1]] = max(1.0 - sum(fr), 0.0)
            total = sum(comp.values())
            if total <= 0.0:  # every entry clamped to zero: fall back to the feed comp
                comp = {cid: feed_comp.get(cid, 0.0) for cid in species}
                total = sum(comp.values()) or 1.0
            ret_states[st.name] = (ret_f, ret_t, {k: x / total for k, x in comp.items()})
        return top, bot, strip_draws, ret_states

    x: list[float] = []
    tear_names: list[str] = []
    if free_top and t_top is not None:
        x.append(float(t_top))
        tear_names.append("top")
    if free_bot and t_bot is not None:
        x.append(float(t_bot))
        tear_names.append("boilup")
    for st in params.side_strippers:
        x.append(_stripper_seed(st, col0))
        tear_names.append(f"stripper:{st.name}.draw")
        if st.n_stages < 2:
            continue
        # Zero-return seed: the first evaluation runs with no vapour return
        # injected at all (the plain side-draw column), which is the benign
        # start; the coupling residuals then pull the return state up.
        x.append(_FLOW_FLOOR)
        tear_names.append(f"stripper:{st.name}.return_flow")
        x.append(feed_t)
        tear_names.append(f"stripper:{st.name}.return_T")
        for cid in species[:-1]:
            x.append(feed_comp.get(cid, 0.0) / max(sum(feed_comp.values()), 1e-12))
            tear_names.append(f"stripper:{st.name}.return_x[{cid}]")
    if not x:  # pragma: no cover - the parse-time count rule refuses this
        raise ColumnSpecError("column specs cannot be driven: no free tear variables remain")

    seed_prof: _Profile | None = None
    strip_seeds: dict[str, _Profile] = {}
    flow_cap = 50.0 * col0.f_total
    best_res2 = float("inf")
    stale = 0
    g: list[float] = []
    names: list[str] = []
    stops: list[float] = []
    # A step already evaluated and accepted by backtracking is reused here, so
    # the accepted iterate is not solved a second time at the loop top.
    pending: tuple[list[float], _Coupled] | None = None
    best_x: list[float] | None = None
    for _ in range(_SPEC_MAX):
        if pending is not None:
            x, coupled = pending
            pending = None
        else:
            top, bot, strip_draws, ret_states = unpack(x)
            coupled = _eval_coupled(
                params,
                tb,
                top,
                bot,
                strip_draws,
                ret_states,
                seed_prof,
                strip_seeds,
            )
        seed_prof = coupled.prof
        strip_seeds = coupled.strip_profiles
        g, stops, names = _g_full(coupled, params, skip)
        rel = [abs(gi) / si for gi, si in zip(g, stops, strict=True)]
        if max(rel, default=0.0) < 1.0:
            return coupled
        res = max(rel)
        # Best-iterate tracking on the L2 NORM of the scaled residuals, not
        # their max: the steam-stripper case keeps one row (a spec residual
        # early, the product_rate stop at rel ~1e7) orders of magnitude above
        # the others, and a max-metric "improvement" test rejects any step
        # that helps the remaining rows while nudging the dominant one -
        # measured: return_flow froze at -1.180 for six consecutive secant
        # iterations because every coupling-improving step was refused. The
        # L2 norm still rejects true blowups (a step into a worse basin
        # explodes it) but lets the secant trade a 1e-4 wobble on the
        # dominant row for real progress on the rest.
        res2 = sum(r * r for r in rel)
        if res2 < best_res2 - 1e-4 * best_res2:
            best_res2, stale, best_x = res2, 0, list(x)
        else:
            stale += 1
            if stale >= 6:
                raise ColumnSpecError(
                    f"column spec residuals stuck near {res:.4g}x their stop tolerances "
                    f"over 6 secant iterations; residuals {_fmt_residuals(g, names)}; "
                    f"the specification is likely infeasible for this column"
                )
        jac_cols = []
        for i in range(len(x)):
            is_flow = tear_names[i].endswith(
                (
                    "top",
                    "boilup",
                    *[f"stripper:{s.name}.draw" for s in params.side_strippers],
                    *[f"stripper:{s.name}.return_flow" for s in params.side_strippers],
                )
            )
            if is_flow:
                dx = max(0.02 * abs(x[i]), 1e-3 * col0.f_total)
            else:
                dx = max(0.02 * abs(x[i]), 1e-6)
            x2 = list(x)
            x2[i] += dx
            coupled2: _Coupled | None = None
            last_probe_err: ColumnConvergenceError | None = None
            for _shrink in range(3):
                try:
                    t2, b2, sd2, rs2 = unpack(x2)
                    coupled2 = _eval_coupled(params, tb, t2, b2, sd2, rs2, seed_prof, strip_seeds)
                    break
                except ColumnConvergenceError as exc:
                    last_probe_err = exc
                    x2 = list(x)
                    x2[i] += dx / 8.0 ** (_shrink + 1)
                except ValueError as exc:
                    last_probe_err = ColumnConvergenceError(f"iterate left the flash domain: {exc}")
                    x2 = list(x)
                    x2[i] += dx / 8.0 ** (_shrink + 1)
            if coupled2 is None:
                raise ColumnSpecError(
                    f"spec secant cannot probe the coupled column state (tear "
                    f"{tear_names[i]}); the specification is likely infeasible: {last_probe_err}"
                ) from last_probe_err
            g2, stops2, _ = _g_full(coupled2, params, skip)
            jac_cols.append([(g2[k] / stops2[k] - g[k] / stops[k]) / dx for k in range(len(g))])
        nf = len(x)
        matrix = [[jac_cols[i][k] for i in range(nf)] for k in range(nf)]
        try:
            step = _gauss(matrix, [-g[k] / stops[k] for k in range(nf)])
        except ZeroDivisionError as exc:
            raise ColumnSpecError(
                f"column specs are unsatisfiable (secant Jacobian singular); "
                f"residuals {_fmt_residuals(g, names)}"
            ) from exc
        if any(abs(v) > flow_cap for v in step):
            raise ColumnSpecError(
                f"column specs are unsatisfiable (secant Jacobian singular); "
                f"residuals {_fmt_residuals(g, names)}"
            )
        # Trust-region caps: the coupled residual landscape has cliffs (a 2%
        # draw move can change the stripper's zero-tear product by an order of
        # magnitude), so an unbounded secant step in the stiff return-state
        # tears throws the iterate into a worse basin it never leaves.
        for i in range(nf):
            if tear_names[i].endswith("return_T"):
                step[i] = max(min(step[i], 100.0), -100.0)
            elif ".return_x[" in tear_names[i]:
                step[i] = max(min(step[i], 0.5), -0.5)
            else:
                cap = 0.5 * abs(x[i]) + 1e-3
                if tear_names[i].endswith("return_flow"):
                    # A value-relative cap freezes a return-flow tear seeded
                    # near zero: its converged magnitude is the stripper
                    # overhead (order the steam flow), and a 0.5*|x| + 1e-3
                    # cap moves the tear only ~1e-3 per iteration (measured
                    # on the steam-stripper case: the coupling residual
                    # crawled from -1.584 to -1.572 mol/s over 15 secant
                    # iterations - it can never reach 1.56 that way). Scale
                    # the cap by the coupling residual instead: the step that
                    # cancels a residual is of the residual's own magnitude,
                    # so far from the solution the tear can move, and near it
                    # the residual - hence the extra headroom - vanishes,
                    # recovering the relative cap exactly where it matters.
                    j = names.index(tear_names[i]) if tear_names[i] in names else -1
                    if j >= 0:
                        cap = max(cap, abs(g[j]))
                step[i] = max(min(step[i], cap), -cap)
        # Damped update: a full secant step can overshoot into a worse basin
        # and the next iteration then linearises from THAT point (measured on
        # the coupled steam stripper: the product residual sat at -1.9e-3 at
        # draw 8.572, one full step landed at +1.7e-1 at draw 8.743, and the
        # run never recovered). Backtrack while the max scaled residual
        # worsens; each backtrack costs one coupled evaluation, an oscillating
        # full step costs the whole run. If every backtracked step either
        # fails to evaluate or worsens, REVERT to the best known iterate:
        # intermediate shrunk steps frequently land in sub-solve stalls, so
        # falling through to the full step (the old behavior) re-enters the
        # bad basin the backtracking just rejected. Only when no best iterate
        # exists yet does the full step stand.
        scale = 1.0
        accepted = False
        for _bt in range(4):
            x_try = [x[i] + scale * step[i] for i in range(nf)]
            try:
                top2, bot2, sd2, rs2 = unpack(x_try)
                coupled_try = _eval_coupled(params, tb, top2, bot2, sd2, rs2, seed_prof, strip_seeds)
            except (ColumnConvergenceError, ValueError):
                coupled_try = None
            if coupled_try is not None:
                g_try, stops_try, _ = _g_full(coupled_try, params, skip)
                rel_try = [abs(gi) / si for gi, si in zip(g_try, stops_try, strict=True)]
                if sum(r * r for r in rel_try) < res2:
                    x = x_try
                    pending = (x_try, coupled_try)
                    accepted = True
                    break
            scale /= 8.0
        if not accepted:
            if best_x is not None and best_res2 < res2:
                x = list(best_x)
            else:
                x = [x[i] + step[i] for i in range(nf)]
    raise ColumnSpecError(
        f"column specs could not be satisfied within {_SPEC_MAX} secant iterations; "
        f"residuals {_fmt_residuals(g, names)}"
    )
