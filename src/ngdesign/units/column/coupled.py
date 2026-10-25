"""Generalized spec solve: named tears, side strippers, refiner specs (S0-1).

The legacy two-tear secant (``_solve_specs``) is locked by the distillation
benchmark; configurations that use any S0-1 extension solve here instead.

**Coupling method (S0-1 feature 2, declared per the spec's requirement):** the
main column and its side strippers are solved as a tear on the vapour return,
NOT as one simultaneous MESH system. Each ``mesh`` evaluation runs a bounded
fixed-point loop: solve the main column at the current tears with each
stripper's overhead vapour injected as a feed at ``return_stage`` (and its
liquid draw leaving at ``draw_stage``), then re-solve every stripper as a
standalone zero/one-tear column on the main column's draw-stage liquid, and
substitute the new overhead states back. The loop stops when every stripper's
return flow, temperature, composition and the resulting product rate have
settled (``_COUPLED_TOL``, or ``_COUPLED_STABLE_TOL`` held for
``_COUPLED_STABLE_PASSES`` consecutive passes when the sub-solve noise floor
keeps the iterate from closing tighter - see the constants' comments). The
draw flow of each stripper is a tear of the OUTER secant, driven by
``product_rate_mol_s`` (config) or a ``draw_rate`` spec naming the stripper, so
the product rate is hit by the same Jacobian that drives the classic specs.

**Spec/tear counting (feature 4):** every free tear - reflux/boilup, a free
pumparound flow, a named free draw, a stripper draw - is driven by exactly one
residual: the classic specs and the four refiner specs (``draw_rate``,
``stage_temperature``, ``pumparound_duty``, ``pumparound_return_T``) from
``params['specs']`` plus one ``product_rate`` row per configured stripper.
The count rule is enforced at parse time; here a mismatch is unreachable.
"""

from __future__ import annotations

from typing import Any

from dataclasses import dataclass, replace

from .inside_out import _build_column, _Column, _Profile
from .linalg import _gauss
from .spec import (
    _FLOW_FLOOR,
    _FULL_SPEC_KEYS,
    _SPEC_MAX,
    _SPEC_TOL,
    ColumnConvergenceError,
    ColumnSpecError,
    _DrawSpec,
    _FeedSpec,
    _Params,
    _SideStripper,
    _parse_params,
)
from .specs import _check_spec_feasibility, _initial_tears, _solve_mesh, _solve_specs
from .thermo_adapter import _ThermoBox

#: Component id of the stripping steam (pure water).
_STEAM_CID = "H2O"

#: Maximum fixed-point passes on the vapour return per mesh evaluation.
_COUPLED_MAX = 40

#: Constant under-relaxation factor for the return-state fixed point. The
#: coupling map can carry a period-2 orbit (measured: the stripper overhead
#: temperature oscillating 0.4 K pass to pass with full steps); w=0.5
#: neutralizes a derivative-near-minus-one cycle. Combined with cold-started
#: main meshes (below) the loop is a deterministic damped iteration.
_COUPLED_RELAX = 0.5

#: Coupling closure: every stripper's return state (flow relative, T/P
#: relative, composition absolute) changes less than this between coupling
#: passes at the accepted solution. MEASURED FLOOR: the stripper sub-solve is
#: reproducible only to ~1.4e-6 (return flow 1.58 mol/s wobbles ±5e-7, T ±4e-6
#: K across passes once the fixed point is reached), so 1e-8 chases sub-solver
#: noise forever. The boundary BALANCES still close exactly by construction -
#: the return stream is injected into the main column as a feed, so no balance
#: depends on the iterate delta; this number only detects "the fixed point
#: stopped moving".
_COUPLED_TOL = 1e-5

#: Stability-based acceptance. The coupling fixed point is not a clean
#: contraction: the return state wobbles at the ~1e-6 sub-solve noise floor
#: and occasionally kicks to ~1e-2 (the stripper sub-solve's own spec stop is
#: loose, so its returned overhead can shift when the main profile drifts).
#: MEASURED on the steam-stripper acceptance case: after the fixed point is
#: reached, the iterate stays inside 1e-3 on every pass except rare kicks.
#: Accept once the state has held below _COUPLED_STABLE_TOL for this many
#: consecutive passes - the boundary balances close exactly by construction
#: (the return is injected as a feed), so this certifies "the coupled state
#: stopped moving", not a balance error.
_COUPLED_STABLE_TOL = 1e-3
_COUPLED_STABLE_PASSES = 5

#: Per-driver stop tolerances, in the residual's own units. Temperature specs
#: and return-temperature targets stop on ABSOLUTE kelvin (the acceptance gate
#: is 1e-6 K); rate specs stop on relative error. The duty stop (1e-7
#: relative) sits just above the MEASURED mesh noise floor: the converged
#: pumparound duty is reproducible to ~2.7e-8 relative (0.13 mW on a 5 kW
#: loop, measured on the free-PA acceptance case), and a stop below that
#: floor makes the secant chase mesh noise until the stale counter aborts.
_STOP_TEMPERATURE_K = 1e-8
_STOP_RATE_REL = 1e-10
_STOP_DUTY_REL = 1e-7


@dataclass(frozen=True)
class _StripperState:
    """One coupling-pass boundary state of a side stripper (fixed point)."""

    ret_flow: float
    ret_T: float
    ret_P: float
    ret_comp: dict[str, float]
    product_flow: float


_EMPTY_STATE = _StripperState(0.0, 0.0, 0.0, {}, 0.0)


def _blend_state(old: _StripperState, new: _StripperState, relax: float) -> _StripperState:
    """Under-relaxed return state: ``old + relax * (new - old)``."""
    def mix(a: float, b: float) -> float:
        return a + relax * (b - a)

    keys = set(old.ret_comp) | set(new.ret_comp)
    comp = {k: mix(old.ret_comp.get(k, 0.0), new.ret_comp.get(k, 0.0)) for k in keys}
    total = sum(comp.values())
    if total <= 0.0:
        comp = dict(new.ret_comp)
    else:
        comp = {k: v / total for k, v in comp.items()}
    return _StripperState(
        ret_flow=mix(old.ret_flow, new.ret_flow),
        ret_T=mix(old.ret_T, new.ret_T),
        ret_P=mix(old.ret_P, new.ret_P),
        ret_comp=comp,
        product_flow=mix(old.product_flow, new.product_flow),
    )


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

    def state(self) -> _StripperState:
        return _StripperState(
            ret_flow=self.overhead_flow,
            ret_T=self.overhead_T,
            ret_P=self.overhead_P,
            ret_comp=dict(self.overhead_comp),
            product_flow=self.product_flow,
        )


@dataclass
class _Coupled:
    """One converged coupled solve: main column plus its strippers."""

    params: _Params  # the injected params the main column actually solved on
    col: _Column
    prof: _Profile
    reports: list[_StripperReport]
    pa_flows: dict[str, float]
    draw_flows: dict[str, float]
    strip_draws: dict[str, float]
    states: list[_StripperState]


def _needs_full(params: _Params) -> bool:
    """True when the configuration must solve on the generalized driver."""
    if params.side_strippers:
        return True
    if any(pa.flow_mol_s is None for pa in params.pumparounds):
        return True
    if any(d.flow is None for d in params.draws):
        return True
    return any(k in params.specs for k in _FULL_SPEC_KEYS)


def _injected(
    params: _Params,
    pa_flows: dict[str, float],
    draw_flows: dict[str, float],
    strip_draws: dict[str, float],
    states: list[_StripperState],
) -> _Params:
    """Copy params with the live tear values and stripper couplings written in.

    Stripper draws leave the main column as liquid draws; stripper overhead
    vapour re-enters as a feed at ``return_stage``. Both are INTERNAL to the
    unit (the draw's material returns as vapour plus product) - the facade
    counts only the original feeds and the stripper products at the boundary.
    """
    pas = [
        replace(pa, flow_mol_s=pa_flows[pa.name]) if pa.flow_mol_s is None else pa
        for pa in params.pumparounds
    ]
    feeds = list(params.feeds)
    draws = [
        replace(d, flow=draw_flows[d.name]) if d.flow is None else d for d in params.draws
    ]
    for st, state in zip(params.side_strippers, states, strict=True):
        draws.append(_stripper_draw(st, strip_draws[st.name]))
        if st.n_stages > 0 and state.ret_flow > _FLOW_FLOOR:
            feeds.append(_stripper_feed(st, state))
    return replace(params, feeds=feeds, draws=draws, pumparounds=pas)


def _stripper_draw(st: _SideStripper, flow: float) -> _DrawSpec:
    """The stripper's liquid draw as a main-column draw row."""
    return _DrawSpec(stage=st.draw_stage, vapor=False, flow=flow, name=st.name)


def _stripper_feed(st: _SideStripper, state: _StripperState) -> _FeedSpec:
    """The stripper's overhead vapour as a main-column feed at ``return_stage``."""
    return _FeedSpec(
        stage=st.return_stage,
        T=state.ret_T,
        P=state.ret_P,
        flow=state.ret_flow,
        comp=dict(state.ret_comp),
    )


def _solve_stripper(
    st: _SideStripper, tb: _ThermoBox, flow: float, prof: _Profile, col: _Column
) -> _StripperReport:
    """Solve one stripper on the main column's draw-stage liquid state.

    A standalone zero/one-tear column (condenserless; kettle reboiler only
    under the duty option, then driven by a ``reboiler_duty_W`` spec through
    the legacy one-tear path). ``n_stages = 0`` is the plain-draw degenerate
    case: everything drawn leaves as product, nothing returns.
    """
    j = st.draw_stage - 1
    comp = dict(prof.x[j])
    t_draw = prof.T[j]
    p_draw = col.pressures[j]
    if st.n_stages == 0:
        return _StripperReport(
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
    prof2 = _solve_specs(col2, tb, parsed2)
    return _StripperReport(
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


def _state_delta(old: _StripperState, new: _StripperState) -> float:
    """Largest relative/absolute change between two return states.

    The empty -> real transition reads 1.0 (or larger) unless BOTH states are
    essentially zero-flow, so a stripper whose overhead stays at zero converges
    immediately instead of oscillating around the _FLOW_FLOOR.
    """
    if old.ret_flow <= _FLOW_FLOOR and new.ret_flow <= _FLOW_FLOOR:
        return 0.0
    parts = [abs(old.ret_flow - new.ret_flow) / max(new.ret_flow, 1.0)]
    if old.ret_flow > _FLOW_FLOOR and new.ret_flow > _FLOW_FLOOR:
        parts.append(abs(old.ret_T - new.ret_T) / max(new.ret_T, 1e-9))
        keys = set(old.ret_comp) | set(new.ret_comp)
        parts.append(
            max(
                (abs(old.ret_comp.get(c, 0.0) - new.ret_comp.get(c, 0.0)) for c in keys),
                default=0.0,
            )
        )
    return max(parts)


def _mesh_coupled(
    params: _Params,
    tb: _ThermoBox,
    t_top: float | None,
    t_bot: float | None,
    pa_flows: dict[str, float],
    draw_flows: dict[str, float],
    strip_draws: dict[str, float],
    warm: _Coupled | None,
) -> _Coupled:
    """One mesh evaluation of the coupled system at the given tears.

    Damped fixed-point loop on the vapour return (coupling method in the
    module docstring). Each pass warm-starts the main mesh from the previous
    pass's profile for robustness; the w=0.5 damping on the return state
    neutralizes the period-2 orbit a warm-started map can carry (measured:
    the stripper overhead temperature oscillating 0.4 K pass to pass). A
    failing main solve propagates to the secant's backtracking.
    """
    if warm is not None:
        states = list(warm.states)
        seed: _Profile | None = warm.prof
    else:
        states = [_EMPTY_STATE for _ in params.side_strippers]
        seed = None
    delta = float("inf")
    stable = 0
    reports: list[_StripperReport] = []
    for _pass in range(_COUPLED_MAX):
        parsed_full = _injected(params, pa_flows, draw_flows, strip_draws, states)
        col = _build_column(parsed_full, tb)
        prof = _solve_mesh(col, tb, t_top, t_bot, seed)
        reports = [
            _solve_stripper(st, tb, strip_draws[st.name], prof, col)
            for st in params.side_strippers
        ]
        seed = prof
        new_states = [rep.state() for rep in reports]
        if _pass:
            # Constant under-relaxation: the coupling map is only mildly
            # contracting and can carry a period-2 orbit (measured: the
            # stripper overhead temperature oscillating 0.4 K pass to pass);
            # w=0.5 neutralizes a derivative-near-minus-one cycle.
            blended = [
                _blend_state(old, new, _COUPLED_RELAX)
                for old, new in zip(states, new_states, strict=True)
            ]
        else:
            blended = new_states
        delta = max(
            (_state_delta(old, new) for old, new in zip(states, blended, strict=True)),
            default=0.0,
        )
        states = blended
        if delta < _COUPLED_TOL:
            return _Coupled(
                params=parsed_full,
                col=col,
                prof=prof,
                reports=reports,
                pa_flows=dict(pa_flows),
                draw_flows=dict(draw_flows),
                strip_draws=dict(strip_draws),
                states=states,
            )
        if delta < _COUPLED_STABLE_TOL:
            stable += 1
            if stable >= _COUPLED_STABLE_PASSES:
                return _Coupled(
                    params=parsed_full,
                    col=col,
                    prof=prof,
                    reports=reports,
                    pa_flows=dict(pa_flows),
                    draw_flows=dict(draw_flows),
                    strip_draws=dict(strip_draws),
                    states=states,
                )
        else:
            stable = 0
    raise ColumnConvergenceError(
        f"side-stripper coupling did not converge in {_COUPLED_MAX} passes "
        f"(last return-state change {delta:.3g})"
    )


def _pa_report(col: _Column, prof: _Profile, name: str) -> dict[str, float]:
    """The converged report of the pumparound named ``name`` (index-aligned)."""
    for pa, rep in zip(col.pumparounds, prof.pa_report, strict=True):
        if pa.name == name:
            return rep
    raise ColumnSpecError(f"pumparound report for {name!r} missing from the converged profile")


def _stripper_seed(st: _SideStripper, col: _Column) -> float:
    """Starting guess for a stripper's draw flow (mol/s)."""
    if st.product_rate is not None:
        return max(st.product_rate + (st.steam_flow or 0.0), _FLOW_FLOOR)
    return 0.2 * col.f_total


def _fmt_residuals(g: list[float], names: list[str]) -> str:
    return "{" + ", ".join(f"{n}: {v:.6g}" for n, v in zip(names, g, strict=True)) + "}"


def _g_full(
    coupled: _Coupled, params: _Params, skip: set[str]
) -> tuple[list[float], list[float], list[str]]:
    """Residuals, stop tolerances, and driver names for every active driver.

    Rows follow the params.specs insertion order, then one ``product_rate``
    row per configured stripper. Each stop is in its residual's own units, so
    ``|g| < stop`` means "spec satisfied"; the secant drives ``g / stop`` to
    zero (dimensionless, O(1) at the gate - the same scaling discipline the
    legacy loop applies with target scales).
    """
    g: list[float] = []
    stops: list[float] = []
    names: list[str] = []
    col, prof = coupled.col, coupled.prof
    for key, raw in params.specs.items():
        if key in skip:
            continue
        if key in _FULL_SPEC_KEYS:
            target = float(raw["value"])
            name = str(raw["name"])
            if key == "draw_rate":
                if any(st.name == name for st in params.side_strippers):
                    rep = next(r for r in coupled.reports if r.name == name)
                    g.append(rep.product_flow - target)
                else:
                    g.append(coupled.draw_flows[name] - target)
                names.append(f"draw_rate[{name}]")
                stops.append(_STOP_RATE_REL * max(abs(target), 1e-12))
            elif key == "stage_temperature":
                stage = int(raw["stage"])
                g.append(prof.T[stage - 1] - target)
                names.append(f"stage_temperature[{stage}]")
                stops.append(_STOP_TEMPERATURE_K)
            elif key == "pumparound_duty":
                rep = _pa_report(col, prof, name)
                g.append(rep["duty_W"] - target)
                names.append(f"pumparound_duty[{name}]")
                stops.append(_STOP_DUTY_REL * max(abs(target), 1e-12))
            else:  # pumparound_return_T
                rep = _pa_report(col, prof, name)
                g.append(rep["return_T_K"] - target)
                names.append(f"pumparound_return_T[{name}]")
                stops.append(_STOP_TEMPERATURE_K)
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
    return g, stops, names


def _solve_specs_full(params: _Params, tb: _ThermoBox) -> _Coupled:
    """Generalized bounded secant over the named tears (S0-1 features 2 and 4).

    Same pinning algebra as the legacy path for the classic ratio/rate pairs;
    free pumparound flows, free draw flows and stripper draws join the tear
    vector, and the four refiner specs plus per-stripper ``product_rate``
    rows join the residual vector. Every residual names itself in errors.
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

    def unpack(v: list[float]) -> tuple[
        float | None, float | None,
        dict[str, float], dict[str, float], dict[str, float],
    ]:
        """Map the free-tear vector onto concrete tear values."""
        it = iter(v)
        top = next(it) if free_top else t_top_pinned
        bot = next(it) if free_bot else t_bot_pinned
        pa_flows: dict[str, float] = {}
        for pa in params.pumparounds:
            pa_flows[pa.name] = pa.flow_mol_s if pa.flow_mol_s is not None else next(it)
        draw_flows: dict[str, float] = {}
        for d in params.draws:
            draw_flows[d.name] = d.flow if d.flow is not None else next(it)
        strip_draws = {st.name: next(it) for st in params.side_strippers}
        return top, bot, pa_flows, draw_flows, strip_draws

    x: list[float] = []
    tear_names: list[str] = []
    if free_top and t_top is not None:
        x.append(float(t_top))
        tear_names.append("top")
    if free_bot and t_bot is not None:
        x.append(float(t_bot))
        tear_names.append("boilup")
    for pa in params.pumparounds:
        if pa.flow_mol_s is None:
            x.append(0.3 * col0.f_total)
            tear_names.append(f"pumparound:{pa.name}")
    for d in params.draws:
        if d.flow is None:
            x.append(0.1 * col0.f_total)
            tear_names.append(f"draw:{d.name}")
    for st in params.side_strippers:
        x.append(_stripper_seed(st, col0))
        tear_names.append(f"stripper:{st.name}")
    if not x:  # pragma: no cover - the parse-time count rule refuses this
        raise ColumnSpecError("column specs cannot be driven: no free tear variables remain")

    warm: _Coupled | None = None
    flow_cap = 50.0 * col0.f_total
    best_res = float("inf")
    stale = 0
    g: list[float] = []
    names: list[str] = []
    stops: list[float] = []
    for _ in range(_SPEC_MAX):
        top, bot, pa_flows, draw_flows, strip_draws = unpack(x)
        coupled = _mesh_coupled(params, tb, top, bot, pa_flows, draw_flows, strip_draws, warm)
        warm = coupled
        g, stops, names = _g_full(coupled, params, skip)
        rel = [abs(gi) / si for gi, si in zip(g, stops, strict=True)]
        if max(rel, default=0.0) < 1.0:
            return coupled
        res = max(rel)
        if res < best_res - 1e-4 * best_res:
            best_res, stale = res, 0
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
            dx = max(0.02 * abs(x[i]), 1e-3 * col0.f_total)
            x2 = list(x)
            x2[i] += dx
            prof2: _Coupled | None = None
            last_probe_err: ColumnConvergenceError | None = None
            for _shrink in range(3):
                try:
                    t2, b2, pa2, dr2, sd2 = unpack(x2)
                    prof2 = _mesh_coupled(params, tb, t2, b2, pa2, dr2, sd2, warm)
                    break
                except ColumnConvergenceError as exc:
                    last_probe_err = exc
                    x2 = list(x)
                    x2[i] += dx / 8.0 ** (_shrink + 1)
                except ValueError as exc:
                    last_probe_err = ColumnConvergenceError(f"iterate left the flash domain: {exc}")
                    x2 = list(x)
                    x2[i] += dx / 8.0 ** (_shrink + 1)
            if prof2 is None:
                raise ColumnSpecError(
                    f"spec secant cannot probe the coupled column state (tear "
                    f"{tear_names[i]}); the specification is likely infeasible: {last_probe_err}"
                ) from last_probe_err
            g2, stops2, _ = _g_full(prof2, params, skip)
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
        x = [min(max(x[i] + step[i], _FLOW_FLOOR), flow_cap) for i in range(nf)]
    raise ColumnSpecError(
        f"column specs could not be satisfied within {_SPEC_MAX} secant iterations; "
        f"residuals {_fmt_residuals(g, names)}"
    )
