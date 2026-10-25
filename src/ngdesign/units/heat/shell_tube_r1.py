"""Shell-and-tube exchanger, R1 rating level: Kern method (spec U-R2, issue #314).

Kern-method rating of a TEMA E shell-and-tube exchanger against a utility
stream described by params (composition, T, P, flow); the utility is not a
port - the catalogue fixes one process port pair (``inlet`` -> ``outlet``,
U-01c) - and is computed internally and reported in ``info``.

Equations (Kern 1950, Ch. 7; Kakaç, Liu & Pramuanjaroenkij, *Heat
Exchangers*, 3rd ed., Ch. 8):

- shell side: ``a_s = Ds*C'*B/PT`` with ``C' = PT - Do`` (S1); the equivalent
  diameter per layout (S2); ``h_o = 0.36*(k/De)*Re_s^0.55*Pr^(1/3)*(mu/mu_w)^0.14``
  with ``(mu/mu_w) = 1`` at R1 (stated here: the wall-temperature correction is
  a second-order effect the R1 level does not iterate on); the friction factor
  ``f = exp(0.576 - 0.19*ln Re_s)`` (S3, the Kakaç et al. analytic fit to
  Kern's shell friction chart, valid 400 < Re_s <= 1e6); and
  ``dP_s = f*Gs^2*(Nb + 1)*Ds/(2*rho*De)`` with ``phi_s = 1``.
  ``ht.dP_Kern`` is deliberately NOT used: it interpolates a scanned chart and
  supports square pitch only.
- tube side: one duct per pass on the shared rating core (Gnielinski or
  laminar 3.66; double_pipe Eqs. 2-4) plus Kern's return loss of ``4*N_tp``
  velocity heads.
- overall U referenced to the outside tube area ``A_o = Nt*pi*Do*L`` through
  ``rating.u_outside_tube`` with h_i/h_o assigned by ``process_side``.

The R1 thermal model is epsilon-NTU for TEMA E shells: ``ht.effectiveness_
from_NTU(NTU, Cr, 'S&T', n_shell_tube=n)`` (Incropera eqs. 11.31a/b) for
multi-pass arrangements, pure counterflow for a single pass in one shell.
``N_tp = 1`` with ``n_shells > 1`` is refused: a pure counterflow series is
just a longer counterflow unit.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import ht

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.sizing.lmtd import lmtd_counter
from ngdesign.units._examples import INLET_COMPOSITION, MMSCFD_TO_MOL_S
from ngdesign.units._physics.heat_balance import TemperatureCross
from ngdesign.units.heat.rating import DuctResult, FilmProps, RatingError, darcy_dP, duct_h
from ngdesign.units.heat.rating import film_props, inlet_kind, rate_two_stream, u_outside_tube

#: Allowed tube-pass counts (spec Params table).
TUBE_PASSES = (1, 2, 4, 6, 8)

#: Allowed tube layouts (spec Params table).
LAYOUTS = ("triangular30", "square90")

#: Allowed process sides (spec Params table).
PROCESS_SIDES = ("tube", "shell")

#: Kern's shell-side Reynolds validity band (Kern 1950, Ch. 7).
KERN_RE_MIN = 2000.0
KERN_RE_MAX = 1.0e6

#: Validity band of the S3 friction fit (400 < Re_s <= 1e6).
FRICTION_RE_MIN = 400.0


class ShellTubeGeometryError(ValueError):
    """R1 geometry or utility params are missing, non-positive or invalid; the param is named."""


class KernRangeError(RatingError):
    """Shell-side Reynolds number sits outside Kern's correlation band."""


def shell_flow_area(Ds: float, PT: float, Do: float, B: float) -> float:
    """Shell-side cross-flow area ``a_s = Ds*C'*B/PT`` with ``C' = PT - Do`` (Eq. S1)."""
    return Ds * (PT - Do) * B / PT


def equiv_diameter(PT: float, Do: float, layout: str) -> float:
    """Shell-side equivalent diameter per layout (Eq. S2).

    Triangular 30°: ``4*(sqrt(3)/4*PT^2 - pi*Do^2/8)/(pi*Do/2)``;
    square 90°: ``4*(PT^2 - pi*Do^2/4)/(pi*Do)``.
    """
    if layout == "triangular30":
        return 4.0 * (math.sqrt(3.0) / 4.0 * PT * PT - math.pi * Do * Do / 8.0) / (math.pi * Do / 2.0)
    if layout == "square90":
        return 4.0 * (PT * PT - math.pi * Do * Do / 4.0) / (math.pi * Do)
    raise ShellTubeGeometryError(f"layout must be one of {LAYOUTS}, got {layout!r}")


def shell_friction(Re_s: float) -> float:
    """Shell-side friction factor ``f = exp(0.576 - 0.19*ln Re_s)`` (Eq. S3).

    The Kakaç et al. analytic fit to Kern's shell friction chart, valid for
    ``400 < Re_s <= 1e6``.

    Raises:
        KernRangeError: ``Re_s`` outside the fit's validity band.
    """
    if not FRICTION_RE_MIN < Re_s <= KERN_RE_MAX:
        raise KernRangeError(f"shell friction fit valid for 400 < Re_s <= 1e6, got Re_s = {Re_s}")
    return math.exp(0.576 - 0.19 * math.log(Re_s))


def shell_h(k: float, De: float, Re_s: float, Pr: float, mu_ratio: float = 1.0) -> float:
    """Kern shell-side film coefficient ``0.36*(k/De)*Re_s^0.55*Pr^(1/3)*(mu/mu_w)^0.14``.

    ``(mu/mu_w) = 1`` at R1 (the wall-temperature correction is not iterated);
    valid for ``2e3 < Re_s < 1e6`` (Kern 1950, Ch. 7).
    """
    ratio: float = mu_ratio**0.14
    value: float = 0.36 * (k / De) * Re_s**0.55 * Pr ** (1.0 / 3.0) * ratio
    return value


def shell_dP(f: float, Gs: float, n_baffles: int, Ds: float, rho: float, De: float) -> float:
    """Shell-side pressure drop ``f*Gs^2*(Nb + 1)*Ds/(2*rho*De)`` with ``phi_s = 1`` (Eq. S3)."""
    return f * Gs * Gs * (n_baffles + 1) * Ds / (2.0 * rho * De)


def tube_flow_area(n_tubes: int, n_passes: int, Di: float) -> float:
    """Tube-side flow area per pass ``(Nt/Ntp)*pi*Di^2/4`` (tubes per pass carry the flow)."""
    return (n_tubes / n_passes) * math.pi * Di * Di / 4.0


def tube_dP(f_D: float, n_passes: int, L: float, Di: float, rho: float, v: float) -> float:
    """Tube-side pressure drop (Kern 1950, Ch. 7).

    ``Ntp*f_D*(L/Di)*rho*v^2/2`` straight-run loss plus Kern's return loss of
    ``4*Ntp`` velocity heads: ``+ 4*Ntp*rho*v^2/2``.
    """
    return n_passes * darcy_dP(f_D, L, Di, rho, v) + 4.0 * n_passes * rho * v * v / 2.0


def tube_duct(
    m_kg_s: float, n_tubes: int, n_passes: int, Di: float, props: FilmProps, roughness_m: float
) -> DuctResult:
    """Tube-side duct result on the shared core: one duct of ``Nt/Ntp`` tubes, ``Dh = Di``."""
    return duct_h(m_kg_s, tube_flow_area(n_tubes, n_passes, Di), Di, props, roughness_m)


@dataclass(frozen=True)
class ShellGeometry:
    """Validated R1 geometry and utility params (spec Params table, defaults applied)."""

    process_side: str
    shell_ID_m: float
    n_tubes: int
    tube_OD_m: float
    tube_ID_m: float
    tube_length_m: float
    pitch_m: float
    layout: str
    baffle_spacing_m: float
    n_baffles: int
    tube_passes: int
    n_shells: int
    utility_composition: dict[str, float]
    utility_T_K: float
    utility_P_Pa: float
    utility_molar_flow: float
    k_wall_W_mK: float
    R_f_tube_m2K_W: float
    R_f_shell_m2K_W: float
    roughness_m: float
    allow_extrapolation: bool


def _positive(name: str, value: Any) -> float:
    if value is None:
        raise ShellTubeGeometryError(f"shell_tube R1 requires geometry param {name!r}")
    value_f = float(value)
    if value_f <= 0.0:
        raise ShellTubeGeometryError(f"shell_tube R1: {name} must be > 0, got {value}")
    return value_f


def _non_negative(name: str, value: Any, default: float) -> float:
    value_f = float(default if value is None else value)
    if value_f < 0.0:
        raise ShellTubeGeometryError(f"shell_tube R1: {name} must be >= 0, got {value}")
    return value_f


def geometry(params: dict[str, Any]) -> ShellGeometry:
    """Validate the params against the refusal table; every message names the param."""
    process_side = params.get("process_side")
    if process_side not in PROCESS_SIDES:
        raise ShellTubeGeometryError(
            f"shell_tube R1: process_side must be one of {PROCESS_SIDES}, got {process_side!r}"
        )
    layout = params.get("layout")
    if layout not in LAYOUTS:
        raise ShellTubeGeometryError(f"shell_tube R1: layout must be one of {LAYOUTS}, got {layout!r}")
    tube_passes = params.get("tube_passes")
    if tube_passes not in TUBE_PASSES:
        raise ShellTubeGeometryError(
            f"shell_tube R1: tube_passes must be one of {TUBE_PASSES}, got {tube_passes!r}"
        )
    n_shells = int(params.get("n_shells", 1))
    if n_shells < 1:
        raise ShellTubeGeometryError(f"shell_tube R1: n_shells must be >= 1, got {n_shells}")
    if tube_passes == 1 and n_shells > 1:
        raise ShellTubeGeometryError(
            f"shell_tube R1: n_shells > 1 with tube_passes == 1 is refused "
            f"(a pure counterflow series is a longer counterflow unit); got n_shells {n_shells}"
        )

    shell_ID_m = _positive("shell_ID_m", params.get("shell_ID_m"))
    n_tubes_raw = params.get("n_tubes")
    if n_tubes_raw is None:
        raise ShellTubeGeometryError("shell_tube R1 requires geometry param 'n_tubes'")
    n_tubes = int(n_tubes_raw)
    if n_tubes < 1:
        raise ShellTubeGeometryError(f"shell_tube R1: n_tubes must be >= 1, got {n_tubes}")
    tube_OD_m = _positive("tube_OD_m", params.get("tube_OD_m"))
    tube_ID_m = _positive("tube_ID_m", params.get("tube_ID_m"))
    tube_length_m = _positive("tube_length_m", params.get("tube_length_m"))
    pitch_m = _positive("pitch_m", params.get("pitch_m"))
    baffle_spacing_m = _positive("baffle_spacing_m", params.get("baffle_spacing_m"))
    n_baffles_raw = params.get("n_baffles")
    if n_baffles_raw is None:
        raise ShellTubeGeometryError("shell_tube R1 requires geometry param 'n_baffles'")
    n_baffles = int(n_baffles_raw)
    if n_baffles < 1:
        raise ShellTubeGeometryError(f"shell_tube R1: n_baffles must be >= 1, got {n_baffles}")
    if pitch_m <= tube_OD_m:
        raise ShellTubeGeometryError(
            f"shell_tube R1: pitch_m must exceed tube_OD_m (got pitch_m {pitch_m} <= tube_OD_m {tube_OD_m})"
        )
    if tube_OD_m <= tube_ID_m:
        raise ShellTubeGeometryError(
            f"shell_tube R1: tube_OD_m must exceed tube_ID_m "
            f"(got tube_ID_m {tube_ID_m} >= tube_OD_m {tube_OD_m})"
        )

    utility: dict[str, Any] = {}
    for name in ("utility_composition", "utility_T_K", "utility_P_Pa", "utility_molar_flow"):
        value = params.get(name)
        if value is None:
            raise ShellTubeGeometryError(f"shell_tube R1 requires param {name!r}")
        utility[name] = value
    utility_T_K = _positive("utility_T_K", utility["utility_T_K"])
    utility_P_Pa = _positive("utility_P_Pa", utility["utility_P_Pa"])
    utility_molar_flow = _positive("utility_molar_flow", utility["utility_molar_flow"])
    composition = dict(utility["utility_composition"])
    if not composition or any(float(x) <= 0.0 for x in composition.values()):
        raise ShellTubeGeometryError("shell_tube R1: utility_composition must carry positive mole fractions")

    allow = params.get("allow_extrapolation", False)
    if not isinstance(allow, bool):
        raise ShellTubeGeometryError(f"shell_tube R1: allow_extrapolation must be a boolean, got {allow!r}")
    return ShellGeometry(
        process_side=str(process_side),
        shell_ID_m=shell_ID_m,
        n_tubes=n_tubes,
        tube_OD_m=tube_OD_m,
        tube_ID_m=tube_ID_m,
        tube_length_m=tube_length_m,
        pitch_m=pitch_m,
        layout=str(layout),
        baffle_spacing_m=baffle_spacing_m,
        n_baffles=n_baffles,
        tube_passes=int(tube_passes),
        n_shells=n_shells,
        utility_composition=composition,
        utility_T_K=utility_T_K,
        utility_P_Pa=utility_P_Pa,
        utility_molar_flow=utility_molar_flow,
        k_wall_W_mK=_positive("k_wall_W_mK", params.get("k_wall_W_mK", 45.0)),
        R_f_tube_m2K_W=_non_negative("R_f_tube_m2K_W", params.get("R_f_tube_m2K_W"), 0.0),
        R_f_shell_m2K_W=_non_negative("R_f_shell_m2K_W", params.get("R_f_shell_m2K_W"), 0.0),
        roughness_m=_non_negative("roughness_m", params.get("roughness_m"), 4.5e-5),
        allow_extrapolation=allow,
    )


def eps_counterflow(NTU: float, Cr: float) -> float:
    """Counter-current effectiveness for a single pass in one shell.

    ``[1 - exp(-NTU(1-Cr))] / [1 - Cr*exp(-NTU(1-Cr))]`` (Incropera
    eqs. 11.29a/b), or ``NTU/(1 + NTU)`` at ``Cr = 1``.
    """
    if Cr >= 1.0 - 1e-12:
        return NTU / (1.0 + NTU)
    ex = math.exp(-NTU * (1.0 - Cr))
    return (1.0 - ex) / (1.0 - Cr * ex)


def eps_tema_e(NTU: float, Cr: float, tube_passes: int, n_shells: int) -> float:
    """TEMA E effectiveness for ``tube_passes`` tube passes and ``n_shells`` shells.

    A single tube pass in a single shell is pure counterflow
    (:func:`eps_counterflow`); any multi-pass arrangement uses
    ``ht.effectiveness_from_NTU(NTU, Cr, subtype='S&T', n_shell_tube=n_shells)``
    (Incropera eqs. 11.31a/b), where each shell takes NTU/n. ``tube_passes = 1``
    with several shells is refused by :func:`geometry`.
    """
    if tube_passes == 1:
        return eps_counterflow(NTU, Cr)
    return float(ht.effectiveness_from_NTU(NTU, Cr, subtype="S&T", n_shell_tube=n_shells))


class ShellTubeR1:
    """Shell-and-tube exchanger, R1: single-phase Kern-method rating level.

    One process port pair (``inlet`` -> ``outlet``); the utility stream comes
    from the ``utility_*`` params, is computed internally and is never a port.
    """

    inlet_ports = ("inlet",)
    outlet_ports = ("outlet",)

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """The R0 vertical-slice gas cooled by cooling water on the shell side.

        The dry separator gas of the R0 slice, at 3.0 MPa (the R0 7 MPa feed
        condenses across the R1 full-duty bracket at 303.15 K, so the example
        holds the composition and cools it at a lower pressure - same practice
        as the double-pipe example's documented geometry substitution), in the
        tubes of geometry G1, against cooling water (H2O, 303.15 K, 4 bar,
        1000 mol/s) on the shell side - the water flow puts Kern's shell-side
        Re_s inside the 2e3-1e6 correlation band.
        """
        dry = {cid: x for cid, x in INLET_COMPOSITION.items() if cid != "H2O"}
        total = sum(dry.values())
        feed = {
            "T": 322.15,
            "P": 3.0e6,
            "molar_flow": 50 * MMSCFD_TO_MOL_S,
            "composition": {cid: x / total for cid, x in dry.items()},
        }
        params: dict[str, Any] = {
            "process_side": "tube",
            "shell_ID_m": 0.489,
            "n_tubes": 158,
            "tube_OD_m": 0.01905,
            "tube_ID_m": 0.01483,
            "tube_length_m": 4.877,
            "pitch_m": 0.02381,
            "layout": "triangular30",
            "baffle_spacing_m": 0.3048,
            "n_baffles": 15,
            "tube_passes": 2,
            "utility_composition": {"H2O": 1.0},
            "utility_T_K": 303.15,
            "utility_P_Pa": 4.0e5,
            "utility_molar_flow": 1000.0,
        }
        return {"inlet": feed}, params

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        """Rate the exchanger at the R1 level; see the module docstring."""
        geom = geometry(params)
        process = inlets["inlet"]
        utility = thermo.flash_pt(
            geom.utility_composition, geom.utility_T_K, geom.utility_P_Pa, geom.utility_molar_flow
        )

        # Hot/cold assignment: the hotter inlet is "hot"; equal inlets refuse.
        if abs(process.T - utility.T) <= 1e-9:
            raise TemperatureCross(
                f"shell_tube R1: inlet temperatures are equal (within 1e-9 K) at "
                f"T = {process.T} K; no driving force"
            )
        hot, cold = (process, utility) if process.T > utility.T else (utility, process)
        hot_is_process = hot is process

        # Single-phase check on both inlets; a phase change goes to R2.
        for side, state in (("process", process), ("utility", utility)):
            try:
                inlet_kind(state)
            except SinglePhaseRequired as exc:
                raise SinglePhaseRequired(f"{exc} ({side} inlet); use model R2") from exc

        # Geometry scalars (Eq. S1, S2 and A_o = Nt*pi*Do*L).
        a_s = shell_flow_area(geom.shell_ID_m, geom.pitch_m, geom.tube_OD_m, geom.baffle_spacing_m)
        de = equiv_diameter(geom.pitch_m, geom.tube_OD_m, geom.layout)
        a_o = geom.n_tubes * math.pi * geom.tube_OD_m * geom.tube_length_m

        def side_ducts(
            h_state: StreamState, c_state: StreamState, hT: float, cT: float, hP: float, cP: float
        ) -> tuple[DuctResult, DuctResult]:
            """Tube and shell duct results for (hot, cold) at the given mean states.

            The shell DuctResult carries Re in ``Re`` and G_s in ``v_m_s``;
            its ``fd`` is unused (the S3 friction fit replaces the Colebrook
            root on the shell side).
            """
            kind_h = inlet_kind(h_state)
            kind_c = inlet_kind(c_state)
            film_h = film_props(thermo, h_state.composition, hT, hP, kind_h)
            film_c = film_props(thermo, c_state.composition, cT, cP, kind_c)
            if geom.process_side == "tube":
                tube = tube_duct(
                    h_state.mass_flow, geom.n_tubes, geom.tube_passes, geom.tube_ID_m,
                    film_h, geom.roughness_m,
                )
                gs = c_state.mass_flow / a_s
                re_s = de * gs / film_c.mu_Pa_s
                h_shell = shell_h(film_c.k_W_mK, de, re_s, film_c.Pr)
            else:
                gs = h_state.mass_flow / a_s
                re_s = de * gs / film_h.mu_Pa_s
                h_shell = shell_h(film_h.k_W_mK, de, re_s, film_h.Pr)
                tube = tube_duct(
                    c_state.mass_flow, geom.n_tubes, geom.tube_passes, geom.tube_ID_m,
                    film_c, geom.roughness_m,
                )
            return tube, DuctResult(h_W_m2K=h_shell, Re=re_s, v_m_s=gs, fd=0.0)

        # Pressure drops from INLET-state properties (spec Algorithm step 4).
        tube_in, shell_in = side_ducts(hot, cold, hot.T, cold.T, hot.P, cold.P)
        film_hot_in = film_props(thermo, hot.composition, hot.T, hot.P, inlet_kind(hot))
        film_cold_in = film_props(thermo, cold.composition, cold.T, cold.P, inlet_kind(cold))
        f_in = shell_friction(shell_in.Re)
        if geom.process_side == "tube":
            dP_tube = tube_dP(
                tube_in.fd, geom.tube_passes, geom.tube_length_m, geom.tube_ID_m,
                film_hot_in.rho_kg_m3, tube_in.v_m_s,
            )
            dP_shell = shell_dP(
                f_in, shell_in.v_m_s, geom.n_baffles, geom.shell_ID_m, film_cold_in.rho_kg_m3, de
            )
        else:
            dP_tube = tube_dP(
                tube_in.fd, geom.tube_passes, geom.tube_length_m, geom.tube_ID_m,
                film_cold_in.rho_kg_m3, tube_in.v_m_s,
            )
            dP_shell = shell_dP(
                f_in, shell_in.v_m_s, geom.n_baffles, geom.shell_ID_m, film_hot_in.rho_kg_m3, de
            )
        # The side (tube/shell) belongs to the stream named by process_side;
        # hot/cold is only the temperature ranking.
        dP_process = dP_tube if geom.process_side == "tube" else dP_shell
        dP_utility = dP_shell if geom.process_side == "tube" else dP_tube
        p_process_out = process.P - dP_process
        p_utility_out = utility.P - dP_utility
        for side, p_out in (("process", p_process_out), ("utility", p_utility_out)):
            if p_out <= 0.0:
                raise RatingError(
                    f"non-positive outlet pressure: {side} side drops to {p_out} Pa across this geometry"
                )
        p_hot_out = p_process_out if hot_is_process else p_utility_out
        p_cold_out = p_utility_out if hot_is_process else p_process_out

        # UA at the bulk-mean film state of each side, re-evaluated at every
        # g(Q) step; the last evaluation is the reported rating.
        last: dict[str, DuctResult] = {}

        def ua_of(hot_out: StreamState, cold_out: StreamState) -> float:
            tube_m, shell_m = side_ducts(
                hot,
                cold,
                (hot.T + hot_out.T) / 2.0,
                (cold.T + cold_out.T) / 2.0,
                (hot.P + p_hot_out) / 2.0,
                (cold.P + p_cold_out) / 2.0,
            )
            last["tube"], last["shell"] = tube_m, shell_m
            u_o = u_outside_tube(
                h_i=tube_m.h_W_m2K,
                h_o=shell_m.h_W_m2K,
                Do=geom.tube_OD_m,
                Di=geom.tube_ID_m,
                k_wall=geom.k_wall_W_mK,
                R_fi=geom.R_f_tube_m2K_W,
                R_fo=geom.R_f_shell_m2K_W,
            )
            return u_o * a_o

        def eps_of(NTU: float, Cr: float) -> float:
            return eps_tema_e(NTU, Cr, geom.tube_passes, geom.n_shells)

        rated = rate_two_stream(hot, cold, thermo, p_hot_out, p_cold_out, ua_of, eps_of)

        # Kern's shell-side band, checked at mean properties before accepting
        # the result (spec Algorithm step 6).
        re_s_mean = last["shell"].Re
        kern_in_range = KERN_RE_MIN < re_s_mean < KERN_RE_MAX
        if not kern_in_range and not geom.allow_extrapolation:
            raise KernRangeError(
                f"shell-side Re_s = {re_s_mean} outside Kern's validity band "
                f"[{KERN_RE_MIN}, {KERN_RE_MAX}]; raise the utility flow or set allow_extrapolation"
            )

        hot_out, cold_out = rated.hot_out, rated.cold_out
        process_out = hot_out if hot_is_process else cold_out
        utility_out = cold_out if hot_is_process else hot_out
        duty_W = process.molar_flow * (process_out.enthalpy - process.enthalpy)
        f_lmtd = float(ht.F_LMTD_Fakheri(hot.T, hot_out.T, cold.T, cold_out.T, shells=geom.n_shells))
        info: dict[str, Any] = {
            "Q_W": rated.duty_W,
            "U_W_m2K": rated.UA_W_K / a_o,
            "A_m2": a_o,
            "UA_W_K": rated.UA_W_K,
            "NTU": rated.NTU,
            "effectiveness": rated.effectiveness,
            "F_LMTD": f_lmtd,
            "LMTD_K": lmtd_counter(hot.T, hot_out.T, cold.T, cold_out.T),
            "h_tube_W_m2K": last["tube"].h_W_m2K,
            "h_shell_W_m2K": last["shell"].h_W_m2K,
            "Re_tube": last["tube"].Re,
            "Re_shell": last["shell"].Re,
            "dP_tube_Pa": dP_tube,
            "dP_shell_Pa": dP_shell,
            "utility_T_out_K": utility_out.T,
            "utility_P_out_Pa": p_utility_out,
            "utility_duty_W": rated.duty_W,
            "kern_in_range": float(kern_in_range),
        }
        return UnitResult(
            outlets={"outlet": process_out},
            duty_W=duty_W,
            power_W=0.0,
            info=info,
        )


__all__ = [
    "FRICTION_RE_MIN",
    "KERN_RE_MAX",
    "KERN_RE_MIN",
    "KernRangeError",
    "LAYOUTS",
    "PROCESS_SIDES",
    "ShellGeometry",
    "ShellTubeGeometryError",
    "ShellTubeR1",
    "TUBE_PASSES",
    "eps_counterflow",
    "eps_tema_e",
    "equiv_diameter",
    "geometry",
    "shell_dP",
    "shell_flow_area",
    "shell_friction",
    "shell_h",
    "tube_dP",
    "tube_duct",
    "tube_flow_area",
]
