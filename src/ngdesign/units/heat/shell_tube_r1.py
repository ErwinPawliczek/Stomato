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

from ngdesign.units.heat.rating import DuctResult, FilmProps, RatingError, darcy_dP, duct_h

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


__all__ = [
    "FRICTION_RE_MIN",
    "KERN_RE_MAX",
    "KERN_RE_MIN",
    "KernRangeError",
    "LAYOUTS",
    "PROCESS_SIDES",
    "ShellGeometry",
    "ShellTubeGeometryError",
    "TUBE_PASSES",
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
