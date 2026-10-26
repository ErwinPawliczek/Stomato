"""Air-cooled heat exchanger, R1 rating level (spec U-R2, issue #315).

Finned-tube bundle rating on one process port pair (``inlet`` -> ``outlet``);
the ambient air side is described by params and reported in ``info``, never a
port. Method (spec "Equations"):

1. Geometry: ``fluids.geometry.AirCooledExchanger`` from the params (m).
2. Air side (Briggs & Young 1963, Chem. Eng. Prog. Symp. Ser. 59(41)):
   ``V_max = m_air/(A_min*rho)``, ``Re = rho*V_max*D_o/mu``,
   ``Nu = 0.134*Re^0.681*Pr^(1/3)*(s/l_f)^0.2*(s/t_f)^0.1134`` with the fin
   gap ``s = bare_length`` and ``l_f = (D_fin - D_o)/2``, ``h_fin = Nu*k/D_o``,
   the Kern-Kraus (1972) annular-fin efficiency, and ``h_bare =
   (eta_f*A_fin + A_tube_showing)/A*h_fin*A_increase`` - exactly
   ``ht.h_Briggs_Young``, which returns h on the BARE-TUBE outside-area basis
   already including the fin efficiency and ``A_increase``.
3. Air ΔP (ESDU 86022, high fin): ``K_f = 4.567*Re^-0.242*A_increase^0.504*
   (p_n/D_o)^-0.376*(p_p/D_o)^-0.546``, ``K_a = 1 + sigma^2`` with ``sigma =
   flow_area_contraction_ratio``, ``dP_air = (K_a + N_rows*K_f)*rho*V_max^2/2``.
4. Fan power ``W_fan = (m_air/rho_in)*dP_air/eta_fan`` - info only (it goes
   into the air, not the process, so it is not ``power_W``).
5. Tube side: ``rating.duct_h`` with ``A_flow = A_tube_flow*(tubes/tube_passes)``
   and ``D_h = Di``; ``dP_t = N_tp*f_D*(L/D_i)*rho*v^2/2 + 4*N_tp*rho*v^2/2``
   (the header/return losses as in Kern Ch. 7).
6. Overall, bare outside area ``A_b = A_bare_tube``:
   ``1/U_b = 1/h_bare + D_o*ln(D_o/D_i)/(2*k_w) + R_fi*D_o/D_i + D_o/(D_i*h_i)``.
7. Thermal: ``Q = U_b*A_b*F_t*LMTD_cf`` with ``F_t = ht.Ft_aircooler`` (VDI
   Heat Atlas; Roetzel-Spang crossflow fits) and ``LMTD_cf = lmtd_counter``.

Validity (Briggs-Young): 1000 < Re < 8000 at the converged mean air state;
outside it the unit refuses (``BriggsYoungRangeError``) unless
``allow_extrapolation`` is set, and then flags ``briggs_young_in_range``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import ht
from fluids.geometry import AirCooledExchanger
from scipy.optimize import brentq

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.sizing.lmtd import lmtd_counter
from ngdesign.units._examples import INLET_COMPOSITION, MMSCFD_TO_MOL_S
from ngdesign.units._physics.heat_balance import TemperatureCross
from ngdesign.units.heat.rating import (
    BRENTQ_MAXITER,
    BRENTQ_XTOL_FRACTION,
    Q_LO_FRACTION,
    RatingConvergenceError,
    RatingError,
    SinglePhaseRequired,
    darcy_dP,
    duct_h,
    film_props,
    inlet_kind,
    u_outside_tube,
)

#: Briggs-Young correlation validity window on the air-side Reynolds number.
RE_AIR_MIN = 1000.0
RE_AIR_MAX = 8000.0

#: (tube_passes, tube_rows) pairs with an explicit ``Ft_aircooler`` branch.
#: (n, n) for n > 4 is also accepted on ht's documented "reasonable
#: assumption" (passes = rows); the adapter flags it in info.
SUPPORTED_PASSES_ROWS: frozenset[tuple[int, int]] = frozenset(
    {(1, 1), (1, 2), (1, 3), (1, 4), (2, 2), (2, 4), (3, 3), (4, 4)}
)


class AirCoolerGeometryError(ValueError):
    """R1 geometry params are missing, non-positive or unsupported; the param is named."""


class BriggsYoungRangeError(RatingError):
    """The converged air-side Reynolds number sits outside 1000 < Re < 8000."""


@dataclass(frozen=True)
class ValidatedParams:
    """Validated R1 params (spec Params table, defaults applied)."""

    geo: AirCooledExchanger
    tube_rows: int
    tube_passes: int
    tubes_per_row: int
    parallel_bays: int
    bundles_per_bay: int
    k_fin_W_mK: float
    k_wall_W_mK: float
    R_f_tube_m2K_W: float
    roughness_m: float
    air_T_K: float
    air_P_Pa: float
    air_mass_flow_kg_s: float
    air_composition: dict[str, float]
    fan_efficiency: float
    allow_extrapolation: bool

    @property
    def passes_equal_rows_over_four(self) -> bool:
        """True when (tube_passes, tube_rows) runs on ht's n>4 assumption."""
        return self.tube_passes == self.tube_rows and self.tube_rows > 4


def _require_positive(params: dict[str, Any], name: str) -> float:
    """A required number param that must be present and > 0; the param is named."""
    value = params.get(name)
    if value is None:
        raise AirCoolerGeometryError(f"air_cooler R1 requires geometry param {name!r}")
    value_f = float(value)
    if value_f <= 0.0:
        raise AirCoolerGeometryError(f"air_cooler R1: {name} must be > 0, got {value}")
    return value_f


def _require_positive_int(params: dict[str, Any], name: str) -> int:
    """A required integer param that must be present and >= 1; the param is named."""
    value = params.get(name)
    if value is None:
        raise AirCoolerGeometryError(f"air_cooler R1 requires geometry param {name!r}")
    value_i = int(value)
    if value_i != value or value_i < 1:
        raise AirCoolerGeometryError(f"air_cooler R1: {name} must be an integer >= 1, got {value}")
    return value_i


def _optional_positive(params: dict[str, Any], name: str) -> float | None:
    """An optional number param that must be > 0 when present; the param is named."""
    if name not in params or params[name] is None:
        return None
    value_f = float(params[name])
    if value_f <= 0.0:
        raise AirCoolerGeometryError(f"air_cooler R1: {name} must be > 0, got {params[name]}")
    return value_f


def _exactly_one(params: dict[str, Any], names: tuple[str, str], what: str) -> tuple[bool, float]:
    """Exactly one of two alternative params, present and > 0; the pair is named."""
    a, b = _optional_positive(params, names[0]), _optional_positive(params, names[1])
    if (a is not None) == (b is not None):
        raise AirCoolerGeometryError(
            f"air_cooler R1: exactly one of {names[0]}/{names[1]} is required ({what}); "
            f"got {names[0]}={a}, {names[1]}={b}"
        )
    value = a if a is not None else b
    return names[0] in params, float(value)  # type: ignore[arg-type]  # not None above


def build_geometry(params: dict[str, Any]) -> ValidatedParams:
    """Validate the params (spec Params table and refusal table) and build the bundle.

    Raises:
        AirCoolerGeometryError: a geometry value is missing or <= 0, the fin
            or pitch spec is not exactly one of its alternatives, the
            (tube_passes, tube_rows) pair has no ``Ft_aircooler`` branch, the
            air flow is <= 0, or the fan efficiency is outside (0, 1].
    """
    tube_rows = _require_positive_int(params, "tube_rows")
    tube_passes = _require_positive_int(params, "tube_passes")
    tubes_per_row = _require_positive_int(params, "tubes_per_row")
    tube_length_m = _require_positive(params, "tube_length_m")
    tube_OD_m = _require_positive(params, "tube_OD_m")
    tube_wall_m = _require_positive(params, "tube_wall_m")
    fin_thickness_m = _require_positive(params, "fin_thickness_m")

    if (tube_passes, tube_rows) not in SUPPORTED_PASSES_ROWS and not (
        tube_passes == tube_rows and tube_rows > 4
    ):
        raise AirCoolerGeometryError(
            f"air_cooler R1: tube_passes/tube_rows pair ({tube_passes}, {tube_rows}) has no "
            "Ft_aircooler branch; supported: (1, 1-4), (2, 2), (2, 4), (3, 3), (4, 4) "
            "and passes = rows > 4"
        )

    fin_by_height, fin_size_m = _exactly_one(params, ("fin_height_m", "fin_diameter_m"), "fin size")
    fin_by_density, fin_spacing_m = _exactly_one(
        params, ("fin_density_per_m", "fin_interval_m"), "fin spacing"
    )

    pitch_parallel: float | None = None
    pitch_normal: float | None = None
    pitch_pair: float | None = None
    angle_deg: float | None = None
    has_staggered = params.get("pitch_parallel_m") is not None or params.get("pitch_normal_m") is not None
    has_inline = params.get("pitch_m") is not None or params.get("angle_deg") is not None
    if has_staggered and has_inline:
        raise AirCoolerGeometryError(
            "air_cooler R1: give one pitch pair, pitch_m + angle_deg or "
            "pitch_parallel_m + pitch_normal_m, not both"
        )
    if has_staggered:
        pitch_parallel = _require_positive(params, "pitch_parallel_m")
        pitch_normal = _require_positive(params, "pitch_normal_m")
    elif has_inline:
        pitch_pair = _require_positive(params, "pitch_m")
        angle_raw = params.get("angle_deg")
        if angle_raw is None:
            raise AirCoolerGeometryError(
                "air_cooler R1: angle_deg is required with pitch_m (30 = triangular)"
            )
        angle_deg = float(angle_raw)
    else:
        raise AirCoolerGeometryError(
            "air_cooler R1 requires a pitch pair: pitch_m + angle_deg or pitch_parallel_m + pitch_normal_m"
        )

    parallel_bays = (
        _require_positive_int(params, "parallel_bays") if params.get("parallel_bays") is not None else 1
    )
    bundles_per_bay = (
        _require_positive_int(params, "bundles_per_bay") if params.get("bundles_per_bay") is not None else 1
    )

    k_fin = float(params.get("k_fin_W_mK", 205.0))
    k_wall = float(params.get("k_wall_W_mK", 45.0))
    R_f = float(params.get("R_f_tube_m2K_W", 0.0))
    roughness = float(params.get("roughness_m", 4.5e-5))
    if k_fin <= 0.0:
        raise AirCoolerGeometryError(f"air_cooler R1: k_fin_W_mK must be > 0, got {k_fin}")
    if k_wall <= 0.0:
        raise AirCoolerGeometryError(f"air_cooler R1: k_wall_W_mK must be > 0, got {k_wall}")
    if R_f < 0.0:
        raise AirCoolerGeometryError(f"air_cooler R1: R_f_tube_m2K_W must be >= 0, got {R_f}")
    if roughness < 0.0:
        raise AirCoolerGeometryError(f"air_cooler R1: roughness_m must be >= 0, got {roughness}")

    air_T = _require_positive(params, "air_T_K")
    air_P = float(params.get("air_P_Pa", 101325.0))
    if air_P <= 0.0:
        raise AirCoolerGeometryError(f"air_cooler R1: air_P_Pa must be > 0, got {air_P}")
    air_m = _require_positive(params, "air_mass_flow_kg_s")
    composition = params.get("air_composition", {"N2": 0.79, "O2": 0.21})
    if not isinstance(composition, dict) or not composition:
        raise AirCoolerGeometryError("air_cooler R1: air_composition must be a mole-fraction object")
    if abs(sum(float(x) for x in composition.values()) - 1.0) > 1e-6:
        raise AirCoolerGeometryError("air_cooler R1: air_composition mole fractions must sum to 1")
    fan_efficiency_raw = params.get("fan_efficiency")
    if fan_efficiency_raw is None:
        raise AirCoolerGeometryError("air_cooler R1 requires geometry param 'fan_efficiency'")
    fan_efficiency = float(fan_efficiency_raw)
    if not 0.0 < fan_efficiency <= 1.0:
        raise AirCoolerGeometryError(f"air_cooler R1: fan_efficiency must be in (0, 1], got {fan_efficiency}")

    geo = AirCooledExchanger(
        tube_rows=tube_rows,
        tube_passes=tube_passes,
        tubes_per_row=tubes_per_row,
        tube_length=tube_length_m,
        tube_diameter=tube_OD_m,
        fin_thickness=fin_thickness_m,
        fin_height=fin_size_m if fin_by_height else None,
        fin_diameter=None if fin_by_height else fin_size_m,
        fin_density=fin_spacing_m if fin_by_density else None,
        fin_interval=None if fin_by_density else fin_spacing_m,
        pitch_parallel=pitch_parallel,
        pitch_normal=pitch_normal,
        pitch=pitch_pair,
        angle=angle_deg,
        parallel_bays=parallel_bays,
        bundles_per_bay=bundles_per_bay,
        tube_thickness=tube_wall_m,
    )
    return ValidatedParams(
        geo=geo,
        tube_rows=tube_rows,
        tube_passes=tube_passes,
        tubes_per_row=tubes_per_row,
        parallel_bays=parallel_bays,
        bundles_per_bay=bundles_per_bay,
        k_fin_W_mK=k_fin,
        k_wall_W_mK=k_wall,
        R_f_tube_m2K_W=R_f,
        roughness_m=roughness,
        air_T_K=air_T,
        air_P_Pa=air_P,
        air_mass_flow_kg_s=air_m,
        air_composition={str(k): float(v) for k, v in composition.items()},
        fan_efficiency=fan_efficiency,
        allow_extrapolation=bool(params.get("allow_extrapolation", False)),
    )


@dataclass(frozen=True)
class AirSideResult:
    """Air-side rating scalars; ``h_bare_W_m2K`` is on the bare-tube area basis."""

    V_max_m_s: float
    Re: float
    Pr: float
    Nu: float
    h_fin_W_m2K: float
    fin_efficiency: float
    h_total_W_m2K: float
    h_bare_W_m2K: float


def air_side_h(
    m_air_kg_s: float,
    geo: AirCooledExchanger,
    tube_diameter_m: float,
    rho: float,
    Cp: float,
    mu: float,
    k: float,
    k_fin: float,
) -> AirSideResult:
    """Briggs-Young air-side h on the bare-tube area basis (Eq. 2).

    ``Nu = 0.134*Re^0.681*Pr^(1/3)*(s/l_f)^0.2*(s/t_f)^0.1134`` with the fin
    gap ``s = bare_length`` and ``l_f = (D_fin - D_o)/2``; ``h_fin = Nu*k/D_o``;
    the Kern-Kraus annular-fin efficiency (Kern & Kraus, Extended Surface Heat
    Transfer, 1972, Bessel form); ``h_bare = (eta_f*A_fin + A_tube_showing)/A*
    h_fin*A_increase``, exactly ``ht.h_Briggs_Young``.
    """
    do = tube_diameter_m
    fin_diameter = geo.fin_diameter
    assert fin_diameter is not None, "AirCooledExchanger sets fin_diameter from fin_height"
    s = geo.bare_length
    assert s is not None, "AirCooledExchanger sets bare_length from the fin spec"
    V_max = m_air_kg_s / (geo.A_min * rho)
    Re = rho * V_max * do / mu
    Pr = Cp * mu / k
    l_f = (fin_diameter - do) / 2.0
    Nu = 0.134 * Re**0.681 * Pr ** (1.0 / 3.0) * (s / l_f) ** 0.2 * (s / geo.fin_thickness) ** 0.1134
    h_fin = Nu * k / do
    eta_f = float(ht.fin_efficiency_Kern_Kraus(do, fin_diameter, geo.fin_thickness, k_fin, h_fin))
    h_total = (eta_f * geo.A_fin + geo.A_tube_showing) / geo.A * h_fin
    h_bare = float(
        ht.h_Briggs_Young(
            m_air_kg_s,
            geo.A,
            geo.A_min,
            geo.A_increase,
            geo.A_fin,
            geo.A_tube_showing,
            do,
            fin_diameter,
            geo.fin_thickness,
            s,
            rho,
            Cp,
            mu,
            k,
            k_fin,
        )
    )
    return AirSideResult(
        V_max_m_s=V_max,
        Re=Re,
        Pr=Pr,
        Nu=Nu,
        h_fin_W_m2K=h_fin,
        fin_efficiency=eta_f,
        h_total_W_m2K=h_total,
        h_bare_W_m2K=h_bare,
    )


@dataclass(frozen=True)
class AirDeltaPResult:
    """ESDU 86022 high-fin air pressure drop (Eq. 3) with its coefficients."""

    K_f: float
    K_a: float
    dP_air_Pa: float


def esdu_dP(
    m_air_kg_s: float,
    geo: AirCooledExchanger,
    tube_diameter_m: float,
    tube_rows: int,
    rho: float,
    mu: float,
) -> AirDeltaPResult:
    """Air pressure drop through the bundle (ESDU 86022, high fin; Eq. 3).

    ``K_f = 4.567*Re^-0.242*A_increase^0.504*(p_n/D_o)^-0.376*(p_p/D_o)^-0.546``,
    ``K_a = 1 + sigma^2`` with ``sigma = flow_area_contraction_ratio``,
    ``dP_air = (K_a + N_rows*K_f)*rho*V_max^2/2``.
    """
    do = tube_diameter_m
    V_max = m_air_kg_s / (geo.A_min * rho)
    Re = rho * V_max * do / mu
    K_f = (
        4.567
        * Re**-0.242
        * geo.A_increase**0.504
        * (geo.pitch_normal / do) ** -0.376
        * (geo.pitch_parallel / do) ** -0.546
    )
    K_a = 1.0 + geo.flow_area_contraction_ratio**2
    dP_air = (K_a + tube_rows * K_f) * rho * V_max**2 / 2.0
    return AirDeltaPResult(K_f=K_f, K_a=K_a, dP_air_Pa=dP_air)


def fan_power_W(m_air_kg_s: float, rho: float, dP_air_Pa: float, fan_efficiency: float) -> float:
    """Fan power ``W_fan = (m_air/rho)*dP_air/eta_fan`` (Eq. 4); info only."""
    return (m_air_kg_s / rho) * dP_air_Pa / fan_efficiency


def check_briggs_young_range(Re_air: float, allow_extrapolation: bool) -> bool:
    """The Briggs-Young validity check (Algorithm step 6).

    Returns True when Re_air is inside (1000, 8000). Raises
    ``BriggsYoungRangeError`` outside it unless ``allow_extrapolation``;
    then returns False so the caller flags ``briggs_young_in_range``.
    """
    if RE_AIR_MIN < Re_air < RE_AIR_MAX:
        return True
    if allow_extrapolation:
        return False
    raise BriggsYoungRangeError(
        f"Re_air {Re_air} is outside the Briggs-Young validity range "
        f"({RE_AIR_MIN}, {RE_AIR_MAX}); set allow_extrapolation to rate anyway"
    )


class AirCoolerR1:
    """Air-cooled heat exchanger, R1: finned-bundle single-phase rating level.

    One process port pair (``inlet`` -> ``outlet``); the ambient air side is
    described by the params and reported in ``info`` - never a port.
    """

    inlet_ports = ("inlet",)
    outlet_ports = ("outlet",)

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """The R0 slice air cooler E-101 basis: dry separator gas, 308.15 K air.

        The R0 example feed (322.15 K, 7 MPa) cooled by 308.15 K ambient air
        on the spec's 4-row bundle geometry (ht's ``AirCooledExchanger``
        docstring example); air at 8 kg/s keeps the converged mean Re_air
        inside the Briggs-Young window.
        """
        dry = {cid: x for cid, x in INLET_COMPOSITION.items() if cid != "H2O"}
        total = sum(dry.values())
        feed = {
            "T": 322.15,
            "P": 7.0e6,
            "molar_flow": 50 * MMSCFD_TO_MOL_S,
            "composition": {cid: x / total for cid, x in dry.items()},
        }
        params: dict[str, Any] = {
            "tube_rows": 4,
            "tube_passes": 4,
            "tubes_per_row": 20,
            "tube_length_m": 3.0,
            "tube_OD_m": 0.0254,
            "tube_wall_m": 0.0034,
            "fin_thickness_m": 0.000406,
            "fin_height_m": 0.0159,
            "fin_density_per_m": 1.0 / 0.002309,
            "pitch_parallel_m": 0.05207,
            "pitch_normal_m": 0.06033,
            "air_T_K": 308.15,
            "air_mass_flow_kg_s": 8.0,
            "fan_efficiency": 0.7,
        }
        return {"inlet": feed}, params

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        """Rate the bundle at the R1 level; see the module docstring."""
        proc = inlets["inlet"]
        vp = build_geometry(params)
        geo = vp.geo
        do = geo.tube_diameter
        if proc.mass_flow <= 0.0:
            raise RatingError(f"R1 rating needs a flowing process stream: got {proc.mass_flow} kg/s")
        # The phase check runs before the cross check (as in double_pipe R1).
        kind_proc = inlet_kind(proc)
        if proc.T <= vp.air_T_K:
            raise TemperatureCross(
                f"process inlet T={proc.T} K is at or below the air inlet T={vp.air_T_K} K"
            )

        # Air inlet state (Algorithm step 3): n_air from phase_props' molar mass.
        air_z = vp.air_composition
        air_state = thermo.flash_pt(air_z, vp.air_T_K, vp.air_P_Pa, 1.0)
        kind_air = inlet_kind(air_state)
        air_film_in = film_props(thermo, air_z, vp.air_T_K, vp.air_P_Pa, kind_air)
        air_mw = thermo.phase_props(air_z, vp.air_T_K, vp.air_P_Pa, kind_air).molecular_weight
        n_air = vp.air_mass_flow_kg_s / (air_mw / 1000.0)

        # Pressure drops from INLET-state properties (Algorithm step 4),
        # before the solve; no deltaP-property loop.
        film_proc_in = film_props(thermo, proc.composition, proc.T, proc.P, kind_proc)
        if geo.A_tube_flow is None or geo.Di is None:
            raise RatingError("bundle geometry is missing the tube flow area or inner diameter")
        a_flow = geo.A_tube_flow * (geo.tubes / vp.tube_passes)
        di = float(geo.Di)
        duct_in = duct_h(proc.mass_flow, a_flow, di, film_proc_in, vp.roughness_m)
        # dP_t = N_tp*f_D*(L/D_i)*rho*v^2/2 + 4*N_tp*rho*v^2/2 (Kern Ch. 7).
        dP_tube = vp.tube_passes * (
            darcy_dP(duct_in.fd, geo.tube_length, di, film_proc_in.rho_kg_m3, duct_in.v_m_s)
            + 2.0 * film_proc_in.rho_kg_m3 * duct_in.v_m_s**2
        )
        P_out = proc.P - dP_tube
        if P_out <= 0.0:
            raise RatingError(
                f"non-positive outlet pressure: the tube side drops to {P_out} Pa "
                f"({dP_tube} Pa across this bundle)"
            )
        air_dp = esdu_dP(
            vp.air_mass_flow_kg_s, geo, do, vp.tube_rows, air_film_in.rho_kg_m3, air_film_in.mu_Pa_s
        )
        w_fan = fan_power_W(vp.air_mass_flow_kg_s, air_film_in.rho_kg_m3, air_dp.dP_air_Pa, vp.fan_efficiency)

        F = proc.molar_flow
        # Q_max (Algorithm step 5): the smaller of the process enthalpy drop
        # to the air inlet T and the air enthalpy rise to the process inlet T.
        h_proc_airT = thermo.flash_pt(proc.composition, vp.air_T_K, P_out, F).enthalpy
        h_air_Tproc = thermo.flash_pt(air_z, proc.T, vp.air_P_Pa, n_air).enthalpy
        Q_max = min(F * (proc.enthalpy - h_proc_airT), n_air * (h_air_Tproc - air_state.enthalpy))

        last: dict[str, Any] = {}

        def evaluate(Q: float) -> float:
            """g(Q) = U_b*A_b*F_t*LMTD - Q; a crossflow-infeasible point is -Q."""
            proc_out = thermo.flash_ph(proc.composition, P_out, proc.enthalpy - Q / F, F)
            if len(proc_out.phases) != 1 or abs(proc_out.vapor_fraction - proc.vapor_fraction) > 1e-6:
                raise SinglePhaseRequired(
                    f"R1 rates single-phase duty: the process outlet leaves the inlet's phase "
                    f"(vapor fraction {proc_out.vapor_fraction} vs inlet {proc.vapor_fraction}) at Q={Q} W"
                )
            air_out = thermo.flash_ph(air_z, vp.air_P_Pa, air_state.enthalpy + Q / n_air, n_air)
            # Films at the side bulk-mean states.
            film_pm = film_props(
                thermo, proc.composition, (proc.T + proc_out.T) / 2.0, (proc.P + P_out) / 2.0, kind_proc
            )
            film_am = film_props(thermo, air_z, (vp.air_T_K + air_out.T) / 2.0, vp.air_P_Pa, kind_air)
            duct_m = duct_h(proc.mass_flow, a_flow, di, film_pm, vp.roughness_m)
            air = air_side_h(
                vp.air_mass_flow_kg_s,
                geo,
                do,
                film_am.rho_kg_m3,
                film_am.cp_J_kgK,
                film_am.mu_Pa_s,
                film_am.k_W_mK,
                vp.k_fin_W_mK,
            )
            # Eq. 6 on the bare outside area: u_outside_tube with R_fo = 0 and
            # h_o = h_bare - the bare basis, so neither A_increase nor the fin
            # efficiency is applied twice.
            u_bare = u_outside_tube(
                h_i=duct_m.h_W_m2K,
                h_o=air.h_bare_W_m2K,
                Do=do,
                Di=di,
                k_wall=vp.k_wall_W_mK,
                R_fi=vp.R_f_tube_m2K_W,
                R_fo=0.0,
            )
            ft = ht.Ft_aircooler(
                proc.T, proc_out.T, vp.air_T_K, air_out.T, Ntp=vp.tube_passes, rows=vp.tube_rows
            )
            lmtd: float | None = None
            if math.isfinite(ft) and ft > 0.0:
                try:
                    lmtd = lmtd_counter(proc.T, proc_out.T, vp.air_T_K, air_out.T)
                except ValueError:
                    lmtd = None  # a terminal approach died: infeasible in crossflow
            last["proc_out"], last["air_out"], last["duct"], last["air"] = proc_out, air_out, duct_m, air
            last["u_bare"], last["ft"], last["lmtd"] = u_bare, float(ft), lmtd
            if lmtd is None:
                return -Q
            return u_bare * geo.A_bare_tube * ft * lmtd - Q

        Q_lo = Q_LO_FRACTION * Q_max
        # Q_hi is pulled off Q_max so LMTD stays defined (Algorithm step 5).
        Q_hi = Q_max * (1.0 - 1e-9)
        try:
            Q = float(brentq(evaluate, Q_lo, Q_hi, xtol=BRENTQ_XTOL_FRACTION * Q_max, maxiter=BRENTQ_MAXITER))
        except (RuntimeError, ValueError) as exc:
            raise RatingConvergenceError(
                f"air cooler rating did not converge: {exc}; duty bracket [{Q_lo}, {Q_hi}] W"
            ) from exc
        evaluate(Q)  # re-populate `last` at the converged duty

        # Range check on the converged MEAN air state (Algorithm step 6).
        air_final = last["air"]
        in_range = check_briggs_young_range(air_final.Re, vp.allow_extrapolation)

        proc_out: StreamState = last["proc_out"]
        air_out: StreamState = last["air_out"]
        duct_final = last["duct"]
        lmtd_final = last["lmtd"]
        if lmtd_final is None:  # pragma: no cover - brentq converged at a feasible point
            raise RatingConvergenceError(
                "air cooler rating did not converge: infeasible at the converged duty"
            )
        duty_W = F * (proc_out.enthalpy - proc.enthalpy)  # negative for cooling (R0 convention)
        info: dict[str, Any] = {
            "Q_W": Q,
            "U_bare_W_m2K": last["u_bare"],
            "A_bare_m2": geo.A_bare_tube,
            "A_total_m2": geo.A,
            "F_t": last["ft"],
            "LMTD_K": lmtd_final,
            "h_air_bare_W_m2K": air_final.h_bare_W_m2K,
            "fin_efficiency": air_final.fin_efficiency,
            "Re_air": air_final.Re,
            "h_tube_W_m2K": duct_final.h_W_m2K,
            "Re_tube": duct_final.Re,
            "dP_tube_Pa": dP_tube,
            "dP_air_Pa": air_dp.dP_air_Pa,
            "fan_power_W": w_fan,
            "air_T_out_K": air_out.T,
            "briggs_young_in_range": 1.0 if in_range else 0.0,
            "passes_equal_rows_assumption": 1.0 if vp.passes_equal_rows_over_four else 0.0,
        }
        return UnitResult(outlets={"outlet": proc_out}, duty_W=duty_W, power_W=0.0, info=info)
