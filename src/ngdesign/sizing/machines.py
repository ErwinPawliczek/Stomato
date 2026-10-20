"""Machine and heat-exchanger sizers (spec S-32): pump, compressor, exchangers.

Produces equipment datasheets with nozzle tables for rotating and
heat-transfer equipment from the ``sizer`` plugin kind. All SI; nozzle
geometry in the contracts convention (NPS inches, positions mm).

Sizing method
-------------
Pump (``pump``):
    Rated flow = 1.1 x operating volumetric flow (VERIFY margin); operating
    head from the solved unit (``info["head_m"]``, S-27 pump plugin);
    NPSHa from the S-08 definition -- (P_s - P_vp)/(rho g) + z - h_f with
    g = 9.80665 -- evaluated on the suction stream with static head, friction
    head and vapour pressure from params (defaults 0 -- supply real values
    when known; a zero vapour pressure reads as the optimistic bound, VERIFY);
    motor rating = shaft power rounded up to the standard motor size list
    (IEC 60072 frames, VERIFY).

Compressor (``compressor``):
    Shaft power and actual discharge temperature from the solved unit /
    discharge stream; number of stages from the pressure ratio so no stage
    exceeds 3.5: n = max(1, ceil(ln(ratio) / ln(3.5))).

Exchangers (``air_cooler``, ``shell_tube``):
    Area = Q / (U * F * LMTD), F = 1.0 (counter-current, no correction).
    U defaults by process service: 300 W/m2K gas cooling, 600 W/m2K liquid
    (VERIFY). LMTD is the counter-current logarithmic mean from the registered
    ``lmtd_counter`` correlation (S-04, ``ngdesign.sizing.lmtd``).
    Air cooler utility: ambient air at 35 C in with a 15 K rise
    (308.15 -> 323.15 K). Shell-and-tube utility temperatures come from
    params (``utility_T_in``/``utility_T_out``) -- the utility is a design
    decision the flowsheet owns, so there is no default.

Nozzle convention (documented per spec; positions relative to the equipment
origin, shaft/nozzle axis = x, z up):
    - Machines: one suction nozzle (port ``inlet``, sized with the S-20
      suction limits for liquid service) and one discharge nozzle (port
      ``outlet``, S-20 line limits).
    - Exchangers: process in/out nozzles (ports ``inlet``/``outlet``, S-20
      line limits) plus vent and drain accessories with no simulation port at
      the fixed nominal NPS below (VERIFY).
    - Positions: suction/inlet on the -x side facing W, discharge/outlet on
      the +x side facing E; exchanger vent on top (+z), drain on the bottom.

Design conditions = most severe (max P, max T) over the connected streams,
with the same margins as the vessel sizers (S-31): P_d = max(1.1 P_op,
P_op + 170 kPa), T_d = T_op + 25 K. Flange class per nozzle = lowest B16.5
class rated at design conditions (S-11), material group param default 1.1
carbon steel (VERIFY).

Out of scope (per spec): vendor selection.
"""

from __future__ import annotations

import math
from typing import Any

from ngdesign.contracts.common import Direction, Nozzle, Vec3
from ngdesign.contracts.flowsheet import Datasheet, SolvedFlowsheet, StreamSpec
from ngdesign.contracts.stream import StreamState
from ngdesign.registry import register
from ngdesign.sizing._nozzles import (
    connected,
    min_flange_class,
    mixture_density,
    nozzle,
    nozzle_nps_in,
)
from ngdesign.sizing.lmtd import lmtd_counter
from ngdesign.sizing.pump_power import npsh_available

__all__ = [
    "G_STD",
    "STANDARD_MOTOR_KW",
    "compressor_stages",
    "exchanger_area",
    "lmtd_counter",
    "motor_kw",
    "npsh_available",
]

G_STD = 9.80665  # standard gravity [m/s2] (S-08 definition)

# IEC 60072 standard motor ratings [kW] -- VERIFY against the vendor frame list.
STANDARD_MOTOR_KW: tuple[float, ...] = (
    0.75,
    1.1,
    1.5,
    2.2,
    3.0,
    4.0,
    5.5,
    7.5,
    11.0,
    15.0,
    18.5,
    22.0,
    30.0,
    37.0,
    45.0,
    55.0,
    75.0,
    90.0,
    110.0,
    132.0,
    160.0,
    200.0,
    250.0,
    315.0,
    400.0,
    450.0,
    500.0,
    560.0,
    630.0,
    710.0,
    800.0,
    900.0,
    1000.0,
)

# Accessory nozzle NPS [in] -- no flow basis in this spec. VERIFY.
VENT_NPS_IN = 2.0
DRAIN_NPS_IN = 2.0

# U defaults [W/m2K] by process service -- VERIFY.
U_GAS_COOLING = 300.0
U_LIQUID = 600.0

# Air-cooler utility air: 35 C in, 15 K rise (spec method). VERIFY.
AIR_T_IN_K = 308.15
AIR_T_OUT_K = 323.15

# Max pressure ratio per compressor stage (spec method).
MAX_STAGE_RATIO = 3.5


def exchanger_area(Q_W: float, U_W_m2K: float, lmtd_K: float, F: float = 1.0) -> float:
    """Required heat-transfer area [m2] from Q = U * A * F * LMTD."""
    if Q_W <= 0:
        raise ValueError(f"Q_W must be positive, got {Q_W}")
    if U_W_m2K <= 0:
        raise ValueError(f"U_W_m2K must be positive, got {U_W_m2K}")
    if lmtd_K <= 0:
        raise ValueError(f"lmtd_K must be positive, got {lmtd_K}")
    if F <= 0:
        raise ValueError(f"F must be positive, got {F}")
    return Q_W / (U_W_m2K * F * lmtd_K)


def motor_kw(shaft_kW: float) -> float:
    """Shaft power rounded up to the next standard motor size [kW]."""
    if shaft_kW <= 0:
        raise ValueError(f"shaft_kW must be positive, got {shaft_kW}")
    for rating in STANDARD_MOTOR_KW:
        if rating >= shaft_kW:
            return rating
    raise ValueError(f"shaft_kW {shaft_kW} exceeds the largest standard motor {STANDARD_MOTOR_KW[-1]}")


def compressor_stages(pressure_ratio: float, max_per_stage: float = MAX_STAGE_RATIO) -> int:
    """Fewest stages so no stage exceeds ``max_per_stage`` pressure ratio."""
    if pressure_ratio < 1.0:
        raise ValueError(f"pressure_ratio must be >= 1, got {pressure_ratio}")
    if max_per_stage <= 1.0:
        raise ValueError(f"max_per_stage must be > 1, got {max_per_stage}")
    if pressure_ratio <= max_per_stage:
        return 1
    # 1e-9 guard: ln(3.5**2)/ln(3.5) can exceed 2.0 by one ulp, and the
    # physically exact two-stage case must not round up to 3.
    return math.ceil(math.log(pressure_ratio) / math.log(max_per_stage) - 1e-9)


def _design_conditions(ports: dict[str, tuple[StreamSpec, StreamState]]) -> tuple[float, float]:
    """(P_d, T_d): most severe connected stream with the S-31 design margins."""
    p_op = max(state.P for _, state in ports.values())
    t_op = max(state.T for _, state in ports.values())
    return max(1.1 * p_op, p_op + 170e3), t_op + 25.0


class _MachineSizerBase:
    """Shared datasheet assembly; subclasses fill dimensions and nozzles."""

    unit_kind: str

    def _dimensions(
        self,
        tag: str,
        solved: SolvedFlowsheet,
        ports: dict[str, tuple[StreamSpec, StreamState]],
        params: dict[str, Any],
    ) -> dict[str, float]:
        raise NotImplementedError

    def _nozzles(
        self,
        tag: str,
        ports: dict[str, tuple[StreamSpec, StreamState]],
        flange_class: int,
    ) -> list[Nozzle]:
        raise NotImplementedError

    def size(self, tag: str, solved: SolvedFlowsheet, params: dict[str, Any]) -> Datasheet:
        unit = solved.flowsheet.unit(tag)
        if unit.kind != self.unit_kind:
            raise ValueError(f"sizer {self.unit_kind} got unit {tag} of kind {unit.kind}")
        ports = connected(solved, tag)
        if not ports:
            raise ValueError(f"unit {tag} has no connected streams to size from")

        p_d, t_d = _design_conditions(ports)
        material_group = str(params.get("material_group", "1.1"))  # VERIFY
        flange_class = min_flange_class(p_d, t_d, material_group)
        dimensions = self._dimensions(tag, solved, ports, params)

        return Datasheet(
            tag=tag,
            kind=unit.kind,
            design_pressure_Pa=p_d,
            design_temperature_K=t_d,
            dimensions=dimensions,
            nozzles=self._nozzles(tag, ports, flange_class),
            notes=[
                f"flange class {flange_class} (B16.5 group {material_group}) at design conditions",
                "U defaults, NPSHa inputs, motor frames and accessory NPS are VERIFY defaults; "
                "override via sizer params",
            ],
        )


def _machine_nozzles(
    tag: str,
    ports: dict[str, tuple[StreamSpec, StreamState]],
    flange_class: int,
) -> list[Nozzle]:
    """Suction/discharge pair; suction uses the S-20 pump-suction limits."""
    nozzles: list[Nozzle] = []
    for n, (port, spot, facing, role) in enumerate(
        (
            ("inlet", Vec3(x=-0.5, y=0.0, z=0.0), Direction.W, "suction"),
            ("outlet", Vec3(x=0.5, y=0.0, z=0.0), Direction.E, "line"),
        ),
        start=1,
    ):
        if port not in ports:
            raise ValueError(f"machine {tag} is missing its {port} stream")
        spec, state = ports[port]
        nozzles.append(
            nozzle(
                n, spec.service, port, nozzle_nps_in(spec.service, state, role), spot, facing, flange_class
            )
        )
    return nozzles


@register("sizer", "pump")
class PumpSizer(_MachineSizerBase):
    """Centrifugal pump sizer (spec S-32)."""

    unit_kind = "pump"

    def _dimensions(
        self,
        tag: str,
        solved: SolvedFlowsheet,
        ports: dict[str, tuple[StreamSpec, StreamState]],
        params: dict[str, Any],
    ) -> dict[str, float]:
        result = solved.units[tag]
        q = float(result.info["Q_m3_s"])
        head = float(result.info["head_m"])
        if result.power_W <= 0:
            raise ValueError(f"pump {tag} solved with non-positive shaft power")
        suction = ports["inlet"][1]
        npsh = npsh_available(
            P_suction_Pa=suction.P,
            P_vapor_Pa=float(params.get("vapor_Pa", 0.0)),  # VERIFY: supply when known
            rho=mixture_density(suction),
            static_head_m=float(params.get("static_head_m", 0.0)),  # VERIFY
            friction_head_m=float(params.get("friction_head_m", 0.0)),  # VERIFY
        )
        return {
            "rated_flow_m3_s": 1.1 * q,  # VERIFY margin
            "head_m": head,
            "npsh_available_m": npsh,
            "shaft_kW": result.power_W / 1000.0,
            "motor_kW": motor_kw(result.power_W / 1000.0),
        }

    def _nozzles(
        self,
        tag: str,
        ports: dict[str, tuple[StreamSpec, StreamState]],
        flange_class: int,
    ) -> list[Nozzle]:
        return _machine_nozzles(tag, ports, flange_class)


@register("sizer", "compressor")
class CompressorSizer(_MachineSizerBase):
    """Compressor sizer (spec S-32)."""

    unit_kind = "compressor"

    def _dimensions(
        self,
        tag: str,
        solved: SolvedFlowsheet,
        ports: dict[str, tuple[StreamSpec, StreamState]],
        params: dict[str, Any],
    ) -> dict[str, float]:
        result = solved.units[tag]
        if result.power_W <= 0:
            raise ValueError(f"compressor {tag} solved with non-positive shaft power")
        ratio = float(result.info["pressure_ratio"])
        discharge = ports["outlet"][1]
        return {
            "power_kW": result.power_W / 1000.0,
            "pressure_ratio": ratio,
            "stages": float(compressor_stages(ratio)),
            "discharge_T_K": discharge.T,
        }

    def _nozzles(
        self,
        tag: str,
        ports: dict[str, tuple[StreamSpec, StreamState]],
        flange_class: int,
    ) -> list[Nozzle]:
        return _machine_nozzles(tag, ports, flange_class)


class _ExchangerSizerBase(_MachineSizerBase):
    """Shared exchanger sizing: area from UA with service-based U defaults."""

    def _utility_temps(self, params: dict[str, Any]) -> tuple[float, float]:
        raise NotImplementedError

    def _dimensions(
        self,
        tag: str,
        solved: SolvedFlowsheet,
        ports: dict[str, tuple[StreamSpec, StreamState]],
        params: dict[str, Any],
    ) -> dict[str, float]:
        result = solved.units[tag]
        duty = abs(result.duty_W)
        if duty <= 0:
            raise ValueError(f"exchanger {tag} solved with zero duty")
        inlet = ports["inlet"][1]
        outlet = ports["outlet"][1]
        service = str(ports["inlet"][0].service)
        u = U_GAS_COOLING if service == "PG" else U_LIQUID  # VERIFY

        # Assign hot/cold by temperature; counter-current LMTD (S-04 formula).
        t_utility_in, t_utility_out = self._utility_temps(params)
        if t_utility_in > inlet.T:  # utility heats the process
            lmtd = lmtd_counter(t_utility_in, t_utility_out, inlet.T, outlet.T)
        else:  # utility cools the process (air cooler always lands here)
            lmtd = lmtd_counter(inlet.T, outlet.T, t_utility_in, t_utility_out)

        f = float(params.get("F", 1.0))
        return {
            "area_m2": exchanger_area(duty, u, lmtd, F=f),
            "U_W_m2K": u,
            "lmtd_K": lmtd,
            "duty_kW": duty / 1000.0,
        }

    def _nozzles(
        self,
        tag: str,
        ports: dict[str, tuple[StreamSpec, StreamState]],
        flange_class: int,
    ) -> list[Nozzle]:
        nozzles: list[Nozzle] = []
        spots = (
            ("inlet", Vec3(x=-0.5, y=0.0, z=0.0), Direction.W),
            ("outlet", Vec3(x=0.5, y=0.0, z=0.0), Direction.E),
        )
        n = 0
        for port, spot, facing in spots:
            if port not in ports:
                raise ValueError(f"exchanger {tag} is missing its {port} stream")
            spec, state = ports[port]
            n += 1
            nozzles.append(
                nozzle(
                    n,
                    spec.service,
                    port,
                    nozzle_nps_in(spec.service, state, "line"),
                    spot,
                    facing,
                    flange_class,
                )
            )
        for service, spot, facing in (
            ("vent", Vec3(x=0.0, y=0.0, z=0.3), Direction.UP),
            ("drain", Vec3(x=0.0, y=0.0, z=-0.3), Direction.DOWN),
        ):
            n += 1
            nozzles.append(
                nozzle(
                    n,
                    service,
                    None,
                    VENT_NPS_IN if service == "vent" else DRAIN_NPS_IN,
                    spot,
                    facing,
                    flange_class,
                )
            )
        return nozzles


@register("sizer", "air_cooler")
class AirCoolerSizer(_ExchangerSizerBase):
    """Air cooler sizer: utility air at 35 C in, 15 K rise (spec S-32)."""

    unit_kind = "air_cooler"

    def _utility_temps(self, params: dict[str, Any]) -> tuple[float, float]:
        t_in = float(params.get("air_T_in", AIR_T_IN_K))
        rise = float(params.get("air_rise_K", 15.0))  # VERIFY
        return t_in, t_in + rise


@register("sizer", "shell_tube")
class ShellTubeSizer(_ExchangerSizerBase):
    """Shell-and-tube sizer; utility temperatures are required params."""

    unit_kind = "shell_tube"

    def _utility_temps(self, params: dict[str, Any]) -> tuple[float, float]:
        if "utility_T_in" not in params or "utility_T_out" not in params:
            raise ValueError(
                "shell_tube sizing needs utility_T_in and utility_T_out params "
                "(the utility is a design decision; no default is provided)"
            )
        t_in = float(params["utility_T_in"])
        t_out = float(params["utility_T_out"])
        if t_in <= 0 or t_out <= 0:
            raise ValueError(f"utility temperatures must be positive, got {t_in}, {t_out}")
        return t_in, t_out
