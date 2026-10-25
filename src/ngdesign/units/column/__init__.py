"""Rigorous equilibrium-stage vapour-liquid equilibrium column. Plugin kind "unit", name "column".

A staged distillation/absorption column on the shared Peng-Robinson thermo plugin.
N equilibrium stages numbered 1..N top to bottom; the kettle reboiler is stage N
and a partial condenser is stage 1. A total condenser is hardware *above* stage 1
(it adds no separation: x_D = y_1, the McCabe-Thiele convention), so stage 1
remains a normal equilibrium tray whose overhead vapour V_1 is fully condensed
into reflux L_0 + distillate D.

Method (primary): Boston-Sullivan inside-out. Outer sweeps refresh real K-values
stage by stage from ``thermo.k_values`` (contract v2), falling back to the
Clausius-Clapeyron estimate (``k_estimate``) where a stage state comes back
single-phase, and refit the frozen inner models - per
stage relative volatilities alpha_ij = K_ij / Kb_j against one column-wide
reference component, the two-parameter correlation ln Kb = A + B/T (Boston &
Sullivan 1974, "An Improved Algorithm for Solving Mass Balance Equations in
Multistage Separation Processes", Can. J. Chem. Eng. 52, 52-63), and linear
per-phase enthalpy models H(T) = h0 + cp*(T - T_ref). The inner loop then solves
MESH with those frozen models only (no thermo calls): component balances as a
tridiagonal system (Thomas algorithm), bubble equations Kb_j = 1/(sum_i
alpha_ij x_ij), stage temperatures from the Kb correlation, and the enthalpy
balances as a damped Newton system for the vapour profile. This keeps the
expensive flash-equivalent calls on the outer sweeps only (the v2 contract
k_values/flash_pt/phase_props/bubble_point are all LRU-cached per package
instance); PH/PS flashes are never used.

Fallback: if the inside-out loop fails to converge, a Naphtali-Sandholm style
simultaneous Newton corrects (x, T, V) together against the MESH residuals with
K-values frozen between Newton passes and refreshed from the thermo plugin each
pass (Naphtali & Sandholm 1971, "Multicomponent Separation Calculations by
Linearization", AIChE J. 17(1), 148-153: the equations are grouped by stage and
linearized; the K-composition coupling is updated between passes).

Boundary structure: the column's degrees of freedom are its boundary flows -
the top tear (reflux L_0 for a total condenser, distillate D for a partial
condenser) and the bottom tear (boilup V_N for a kettle reboiler). A
condenserless stage's vapour and a reboilerless stage's vapour are outcomes of
their enthalpy balances, as are all duties. The number of required column specs
therefore equals the number of tears: two for a condenser+reboiler column, one
for a stripper or a rectifier-without-reboiler, zero for a feed-determined
absorber. Specs are driven to their targets by a bounded Broyden secant loop
over the tears.

Per-phase enthalpies: the thermo contract v2 (spec P1-01) exposes per-phase
properties, so liquid/vapour phase enthalpies and heat capacities come from
single ``thermo.phase_props`` builds at the stage state — no straddling
flashes, no extrapolation across the phase boundary. The reboiler
duty is finally defined by the exact overall energy balance over the real
boundary streams, with the pumparound cooler duties folded in separately: the
reported ``reboiler_duty_W`` is the PHYSICAL reboiler duty, each pumparound
loop's own duty is reported in info (``pa_<name>_duty_W``, negative = heat
removed), and ``UnitResult.duty_W = Q_reb + Σ Q_pumparound − Q_cond`` is the
net unit duty that closes the stream table exactly (the Qc/Qr split is
accurate to the converged stage-balance residual).

All SI: K, Pa abs, mol/s, J/mol, W. Pure functions; no I/O; no global state.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.stream import PhaseKind
from ngdesign.registry import register

from .coupled import _needs_full, _solve_specs_full, _StripperReport
from .inside_out import (
    _build_column,
    _check_pumparounds,
    _close_energy_balance,
    _exact_residuals,
    _seed_profile,
    _temperature_seed,
)
from .spec import _FLOW_FLOOR, ColumnConvergenceError, ColumnSpecError, _parse_params
from .specs import _solve_mesh, _solve_specs
from .thermo_adapter import _flash_ready, _ThermoBox

__all__ = [
    "Column",
    "ColumnConvergenceError",
    "ColumnSpecError",
    "_ThermoBox",
    "_build_column",
    "_exact_residuals",
    "_flash_ready",
    "_parse_params",
    "_seed_profile",
    "_solve_mesh",
    "_solve_specs",
    "_temperature_seed",
]


def _condensed_distillate(
    tb: _ThermoBox, y0: dict[str, float], t_top: float, p_cond: float, d: float
) -> StreamState:
    """Total-condenser product: saturated liquid at the condenser pressure.

    Flashed at the bubble point of the vapour composition so the returned phase
    list is self-consistent; flashing the two-phase top-stage equilibrium would
    carry phase fractions that do not sum to one for a pure-liquid product.
    """
    y0_ready = _flash_ready(y0, y0)
    t_bubble = tb.bubble_temperature(y0_ready, p_cond)
    if t_bubble is None:
        t_bubble = t_top  # degenerate edge; flash near the top-stage state
    return tb.pt(y0_ready, t_bubble, p_cond, max(d, _FLOW_FLOOR))


def _split_water_decant(tb: _ThermoBox, state: StreamState) -> tuple[StreamState, StreamState]:
    """Split a condensed distillate into (hydrocarbon remainder, water decant).

    Spec S0-1, feature 3: water the condensate holds as an AQUEOUS phase
    leaves as a separate internal product. The package's single-liquid flash
    classifies a liquid as AQUEOUS above a 0.5 water mole fraction (the S-01
    rule); a condensate classified HC_LIQUID decants nothing - the zero-flow
    case the spec explicitly anticipates.
    """
    aq = next(
        (
            ph
            for ph in state.phases
            if ph.kind == PhaseKind.AQUEOUS and ph.mole_fraction * state.molar_flow > _FLOW_FLOOR
        ),
        None,
    )
    if aq is None:
        return state, _zero_flow_state(state.composition, state.T, state.P)
    decant_flow = aq.mole_fraction * state.molar_flow
    decant = tb.pt(aq.composition, state.T, state.P, decant_flow)
    # The remainder: total moles minus the aqueous phase's share, renormalized.
    rest: dict[str, float] = {}
    for cid, frac in state.composition.items():
        rest[cid] = max(frac * state.molar_flow - aq.composition.get(cid, 0.0) * decant_flow, 0.0)
    total = sum(rest.values())
    if total <= _FLOW_FLOOR:
        # Degenerate: everything decanted. The HC remainder is the zero-flow
        # edge; keep the original composition on a unit-normalized state.
        rest = dict(state.composition)
        total = 1.0
    remainder = {cid: f / total for cid, f in rest.items()}
    return tb.pt(remainder, state.T, state.P, state.molar_flow - decant_flow), decant


def _zero_flow_state(comp: dict[str, float], t: float, p: float) -> StreamState:
    """Placeholder outlet for a port the configuration leaves unused."""
    return StreamState(
        T=t,
        P=p,
        molar_flow=0.0,
        composition=_flash_ready(comp, comp),
        vapor_fraction=0.0,
        enthalpy=0.0,
        entropy=0.0,
        phases=[],
    )


@register("unit", "column")
class Column:
    """Rigorous equilibrium-stage column: inside-out (Boston-Sullivan) primary,
    Naphtali-Sandholm Newton fallback on non-convergence.

    Ports: one ``feed`` inlet; ``distillate``, ``bottoms`` and one ``side_draw``
    outlet (a zero-flow state when no draw is configured). Additional feeds on
    any stage and further draws are declared in params; their material stays
    inside the unit's own balance (reported in info) - the flowsheet graph sees
    the three outlet ports only.
    """

    inlet_ports = ("feed",)
    outlet_ports = ("distillate", "bottoms", "side_draw")

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        products = solve_column_full(inlets, params, thermo)
        return UnitResult(
            outlets={
                "distillate": products.distillate,
                "bottoms": products.bottoms,
                "side_draw": products.side_draw,
            },
            duty_W=products.duty_W,
            info=products.info,
        )

    @staticmethod
    def _solve_products(
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> ColumnProducts:
        graph_feed = inlets.get("feed")
        graph_dict: dict[str, Any] | None = None
        if graph_feed is not None:
            if graph_feed.molar_flow <= 0.0:
                raise ColumnSpecError("feed port stream has zero molar flow")
            graph_dict = {
                "T": graph_feed.T,
                "P": graph_feed.P,
                "molar_flow": graph_feed.molar_flow,
                "composition": dict(graph_feed.composition),
            }
        parsed = _parse_params(params, graph_dict)
        tb = _ThermoBox(thermo, min(parsed.pressures), max(parsed.pressures))
        if _needs_full(parsed):
            # S0-1 features 2/4: side strippers, free tears or refiner specs.
            # The generalized coupled driver owns the solve (the legacy
            # two-tear secant is locked by the distillation benchmarks); the
            # returned column carries the converged tear values, so every
            # downstream consumer reads live flows off ``col``.
            coupled = _solve_specs_full(parsed, tb)
            col = coupled.col
            prof = coupled.prof
            strip_reports: tuple[_StripperReport, ...] = coupled.reports
        else:
            col = _build_column(parsed, tb)
            prof = _solve_specs(col, tb, parsed)
            strip_reports = ()
        # Post-solve pumparound gates (review items 4/5, PR #238): run once on
        # the final profile - an infeasible loop flow or a heating loop refuses
        # the column instead of reporting a silently-wrong result.
        _check_pumparounds(col, prof)

        # Boundary stream states (exact; these drive the reported energy balance).
        feed_states: list[StreamState] = []
        if graph_feed is not None:
            feed_states.append(graph_feed)
        for f in parsed.feeds:
            if graph_feed is not None and f.comp == dict(graph_feed.composition) and f is parsed.feeds[0]:
                continue  # the port feed is already counted
            feed_states.append(tb.pt(f.comp, f.T, f.P, f.flow))
        if strip_reports:
            # Whole-unit boundary (spec S0-1, feature 2): stripping steam is
            # an internal FEED of the unit. The injected stripper draws and
            # vapour returns stay internal and are deliberately not counted.
            for st in parsed.side_strippers:
                if st.steam_flow and st.steam_flow > 0.0:
                    feed_states.append(tb.pt({"H2O": 1.0}, st.steam_T, st.steam_P, st.steam_flow))

        try:
            extra_states: list[tuple[str, StreamState]] = []
            decant_state: StreamState | None = None
            if col.condenser == "total":
                distillate = _condensed_distillate(tb, prof.y[0], prof.T[0], col.pressures[0], prof.d)
            else:
                distillate = tb.pt(prof.y[0], prof.T[0], col.pressures[0], prof.d)
            bottoms = tb.pt(prof.x[col.n - 1], prof.T[col.n - 1], col.pressures[col.n - 1], prof.b)
            out_states: list[StreamState] = [distillate, bottoms]
            if col.condenser == "total" and parsed.condenser_water_decant:
                # Condenser water decant (spec S0-1, feature 3): the aqueous
                # portion of the condensate leaves as a separate internal
                # product; the distillate carries only the hydrocarbon liquid.
                distillate, decant = _split_water_decant(tb, distillate)
                out_states[0] = distillate
                out_states.append(decant)
                decant_state = decant
            if parsed.draws:
                # Live flows: in the coupled path a free tear carries its
                # converged value in ``col.draws``; the legacy path has the
                # configured flows. Stripper draws appended by the coupled
                # driver are internal and are cut off here.
                orig_draws = col.draws[: len(parsed.draws)]
                first = orig_draws[0]
                assert first.flow is not None  # post-solve every free tear carries its converged flow
                j = first.stage - 1
                comp = prof.y[j] if first.vapor else prof.x[j]
                side_draw = tb.pt(comp, prof.T[j], col.pressures[j], first.flow)
                out_states.append(side_draw)
                for extra in orig_draws[1:]:
                    assert extra.flow is not None
                    je = extra.stage - 1
                    comp_e = prof.y[je] if extra.vapor else prof.x[je]
                    out_states.append(tb.pt(comp_e, prof.T[je], col.pressures[je], extra.flow))
            else:
                side_draw = _zero_flow_state(bottoms.composition, prof.T[col.n - 1], col.pressures[col.n - 1])

            _close_energy_balance(col, tb, prof, feed_states, out_states)
        except ValueError as exc:
            # A converged profile should be physical; a degenerate edge (zero
            # distillate at an extreme tear) still must not leak a pydantic
            # error past the plugin contract.
            raise ColumnConvergenceError(f"converged column state left the physical domain: {exc}") from exc

        info: dict[str, float] = {
            "n_stages": float(col.n),
            "condenser_duty_W": prof.qc,
            "reboiler_duty_W": prof.qr,
            "distillate_mol_s": prof.d,
            "bottoms_mol_s": prof.b,
            "outer_iterations": float(prof.outer),
            "inner_iterations": float(prof.inner),
            "ns_used": float(prof.ns_used),
            "reflux_ratio": prof.l0 / max(prof.d, _FLOW_FLOOR) if col.condenser == "total" else 0.0,
            "boilup_ratio": (
                prof.V[col.n - 1] / max(prof.b, _FLOW_FLOOR) if col.reboiler == "kettle" else 0.0
            ),
        }
        if col.pumparounds:
            # Per-loop converged state (review item 1, PR #238): pa_report is
            # always populated by _finalize_duties, so index it directly - a
            # missing report must surface, not hide behind a 0.0 default.
            for pa, rep in zip(col.pumparounds, prof.pa_report, strict=True):
                info[f"pa_{pa.name}_flow_mol_s"] = rep["flow_mol_s"]
                info[f"pa_{pa.name}_duty_W"] = rep["duty_W"]
                info[f"pa_{pa.name}_draw_T_K"] = rep["draw_T_K"]
                info[f"pa_{pa.name}_return_T_K"] = rep["return_T_K"]
        for rep in strip_reports:
            # Spec S0-1, feature 5: every internal product is reported.
            info[f"stripper_{rep.name}_product_mol_s"] = rep.product_flow
            info[f"stripper_{rep.name}_product_T_K"] = rep.product_T
            info[f"stripper_{rep.name}_reboiler_duty_W"] = rep.reboiler_duty_W
            info[f"stripper_{rep.name}_overhead_mol_s"] = rep.overhead_flow
            info[f"stripper_{rep.name}_overhead_T_K"] = rep.overhead_T
            for cid, frac in rep.product_comp.items():
                info[f"stripper_{rep.name}_product_x_{cid}"] = frac
        if parsed.condenser_water_decant:
            # Spec S0-1, feature 5: the decant is reported even at zero flow.
            info["water_decant_mol_s"] = decant.molar_flow
            info["water_decant_T_K"] = decant.T
        for j in range(col.n):
            info[f"stage_{j}_T_K"] = prof.T[j]
            info[f"stage_{j}_P_Pa"] = col.pressures[j]
            info[f"stage_{j}_L_mol_s"] = prof.L[j]
            info[f"stage_{j}_V_mol_s"] = prof.V[j]
            for cid, frac in prof.x[j].items():
                info[f"stage_{j}_x_{cid}"] = frac
            for cid, frac in prof.y[j].items():
                info[f"stage_{j}_y_{cid}"] = frac

        return UnitResult(
            outlets={"distillate": distillate, "bottoms": bottoms, "side_draw": side_draw},
            # Net unit duty (review item 1, PR #238): physical reboiler duty
            # plus the pumparound coolers' (negative) duties minus the
            # condenser duty - closes the boundary stream table exactly.
            duty_W=prof.qr
            - prof.qc
            + (sum(rep["duty_W"] for rep in prof.pa_report) if col.pumparounds else 0.0),
            info=info,
        )

    @staticmethod
    def example_case() -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """16-stage propane/isobutane split: 100 mol/s 50/50 at 330 K, 1.5 MPa.

        Total condenser, kettle reboiler, feed on stage 8, reflux ratio 2.5,
        distillate 45 mol/s.
        """
        feed = {
            "T": 330.0,
            "P": 1.5e6,
            "molar_flow": 100.0,
            "composition": {"C3": 0.5, "iC4": 0.5},
        }
        params = {
            "n_stages": 16,
            "condenser": "total",
            "reboiler": "kettle",
            "feed_stage": 8,
            "pressure_profile": 1.5e6,
            "specs": {"reflux_ratio": 2.5, "distillate_rate": 45.0},
        }
        return {"feed": feed}, params
