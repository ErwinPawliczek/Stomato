"""Liquid control-valve Cv, non-choked (spec S-10).

Method (USC per data/golden/cv_liquid.yaml): Cv = Q[gpm]*sqrt(SG/dP[psi]).
An SI wrapper around fluids.control_valve.size_control_valve_l provides the full
ISA/IEC 60534 sizing (Cv = Kv/0.865; fluids returns metric Kv in (m^3/h)/bar^0.5).
"""

from __future__ import annotations

from typing import Any

from fluids.control_valve import size_control_valve_l

from ngdesign.registry import register

_KV_PER_CV = 0.865  # 1 US Cv = 0.865 metric Kv (m^3/h per bar^0.5)


def cv_liquid(Q_gpm: float, SG: float, dP_psi: float) -> float:
    """Liquid control-valve flow coefficient Cv (US units, non-choked turbulent)."""
    if Q_gpm <= 0:
        raise ValueError(f"Q_gpm must be > 0, got {Q_gpm!r}")
    if SG <= 0:
        raise ValueError(f"SG must be > 0, got {SG!r}")
    if dP_psi <= 0:
        raise ValueError(f"dP_psi must be > 0, got {dP_psi!r}")
    return Q_gpm * (SG / dP_psi) ** 0.5


def cv_liquid_isa(
    Q_m3_s: float,
    rho: float,
    Psat_Pa: float,
    Pc_Pa: float,
    mu: float,
    P1_Pa: float,
    P2_Pa: float,
) -> float:
    """Full ISA/IEC 60534 liquid sizing via fluids, returned as US Cv.

    Takes SI inputs (Q in m^3/s, pressures in Pa, mu in Pa*s) and delegates to
    fluids.control_valve.size_control_valve_l, which returns metric Kv; the
    result is converted to Cv with Kv = 0.865*Cv.
    """
    if Q_m3_s <= 0:
        raise ValueError(f"Q_m3_s must be > 0, got {Q_m3_s!r}")
    if rho <= 0:
        raise ValueError(f"rho must be > 0, got {rho!r}")
    if mu <= 0:
        raise ValueError(f"mu must be > 0, got {mu!r}")
    if P1_Pa <= P2_Pa:
        raise ValueError(f"need P1_Pa > P2_Pa, got {P1_Pa!r} <= {P2_Pa!r}")
    result = size_control_valve_l(
        rho=rho,
        Psat=Psat_Pa,
        Pc=Pc_Pa,
        mu=mu,
        P1=P1_Pa,
        P2=P2_Pa,
        Q=Q_m3_s,
        allow_choked=True,
        allow_laminar=False,
    )
    if not isinstance(result, float):
        raise TypeError("fluids size_control_valve_l returned a dict; expected a float Kv")
    return result / _KV_PER_CV


@register("correlation", "cv_liquid")
class CvLiquid:
    """Correlation plugin named `cv_liquid` (matches data/golden/cv_liquid.yaml)."""

    def __call__(self, **inputs: Any) -> dict[str, Any]:
        return {"Cv": cv_liquid(Q_gpm=inputs["Q_gpm"], SG=inputs["SG"], dP_psi=inputs["dP_psi"])}
