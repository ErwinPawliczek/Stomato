"""Vessel sizers (spec S-31): separators, scrubbers, TEG contactor.

Produces an equipment datasheet (pressure vessel shell + nozzle table) for one
solved unit from the ``sizer`` plugin kind. All SI; nozzle geometry in the
contracts convention (NPS inches, positions mm).

Sizing method
-------------
Horizontal 3-phase separator (``separator_3phase``):
    Gas capacity by Souders-Brown (GPSA Sec. 7) with a horizontal design
    constant, gas flowing through the top half of the shell cross-section:

        v_max = K_h * sqrt((rho_L - rho_G) / rho_G)      K_h = 0.12 m/s (VERIFY)
        Q_g   = v_max * pi * D^2 / 8                     (half-full shell)

    Liquid volume from retention times (HC 3 min, water 5 min -- VERIFY) held
    in the bottom half of the shell; length chosen so L/D lands in [3, 5].
    Diameter rounds up to 0.15 m.

Vertical scrubber / TEG contactor:
    Souders-Brown diameter with the full cross-section available to the gas;
    K from params (default 0.06 m/s for packed contactors -- VERIFY).

Design conditions (both shapes):
    P_design = max(1.1 * P_op, P_op + 170 kPa)   (typical vessel design margin)
    T_design = T_op + 25 K
    Operating conditions = the most severe (max P, max T) over the streams
    connected to the unit.

Nozzle convention (documented per spec; positions are relative to the vessel
origin, shell axis = x for horizontal vessels, z for vertical vessels):
    - One process nozzle per simulation port, sized with the line sizing
      correlation (S-20) on the connected stream's service code and actual
      volumetric flow. Mixed-phase ports use the mixture density.
    - Accessories with no simulation port: psv, vent, drain, one level tap and
      one pressure tap, at the fixed nominal NPS below (VERIFY with piping
      practice; PSV sizing itself is spec S-34).
    - Horizontal shell: process inlet on the -x head, gas out at the +x end
      top, HC liquid out at bottom centre, water out at bottom +x, psv and
      vent on top, drain at bottom -x, taps on the shell sides.
    - Vertical shell: inlet at -z head, gas out at +z head, liquid out at the
      bottom shell, psv/vent on the +z head, drain at the very bottom, taps on
      the shell sides.

Flange class per nozzle = lowest B16.5 class rated for the datasheet design
conditions (S-11), material group from params (default 1.1 carbon steel,
VERIFY).

Out of scope (per spec): internals (demisters, vane packs, weirs, ...).
"""

from __future__ import annotations

import math
from typing import Any

from ngdesign.contracts.common import Direction, Nozzle, Vec3
from ngdesign.contracts.flowsheet import Datasheet, SolvedFlowsheet, StreamSpec
from ngdesign.contracts.stream import StreamState
from ngdesign.registry import register
from ngdesign.sizing._nozzles import (
    PA_PER_PSIG,
    Ports,
    connected,
    min_flange_class,
    mixture_density,
    nozzle,
    nozzle_nps_in,
    volumetric_flow,
)
from ngdesign.sizing.souders_brown import souders_brown

__all__ = [
    "HORIZONTAL_K_M_S",
    "PA_PER_PSIG",
    "RETENTION_HC_S",
    "RETENTION_WATER_S",
    "VERTICAL_K_M_S",
    "design_conditions",
    "horizontal_3phase",
    "mixture_density",
    "volumetric_flow",
]

# Defaults flagged VERIFY in the spec; overridable per unit via sizer params.
HORIZONTAL_K_M_S = 0.12  # m/s, horizontal separator gas capacity constant
VERTICAL_K_M_S = 0.06  # m/s, vertical packed scrubber/contactors
RETENTION_HC_S = 180.0  # 3 min hydrocarbon liquid retention
RETENTION_WATER_S = 300.0  # 5 min free-water retention
LD_MIN, LD_MAX = 3.0, 5.0
DIAMETER_STEP_M = 0.15  # nominal diameter rounds up to this grid

# Accessory nozzle NPS [in] -- no flow basis in this spec. VERIFY.
PSV_NPS_IN = 6.0
VENT_NPS_IN = 2.0
DRAIN_NPS_IN = 2.0
LEVEL_NPS_IN = 2.0
PRESSURE_NPS_IN = 1.0


def _ceil_step(value: float, step: float) -> float:
    """Smallest multiple of ``step`` >= value (tolerance-safe)."""
    if value <= 0:
        raise ValueError(f"value must be positive, got {value}")
    return round(math.ceil(round(value / step, 9)) * step, 9)


def design_conditions(P_op: float, T_op: float) -> dict[str, float]:
    """Vessel design conditions from operating conditions.

    P_design = max(1.1 * P_op, P_op + 170 kPa); T_design = T_op + 25 K
    (typical design margins over operating conditions -- VERIFY).
    """
    if P_op <= 0:
        raise ValueError(f"operating pressure must be positive, got {P_op}")
    if T_op <= 0:
        raise ValueError(f"operating temperature must be positive, got {T_op}")
    return {
        "design_pressure_Pa": max(1.1 * P_op, P_op + 170e3),
        "design_temperature_K": T_op + 25.0,
    }


def horizontal_3phase(
    gas_flow_m3_s: float,
    hc_flow_m3_s: float,
    water_flow_m3_s: float,
    rho_gas: float,
    rho_hc_liquid: float,
    K_m_s: float = HORIZONTAL_K_M_S,
    retention_hc_s: float = RETENTION_HC_S,
    retention_water_s: float = RETENTION_WATER_S,
) -> dict[str, float]:
    """Horizontal 3-phase separator shell sizing.

    Gas capacity sets the minimum diameter (gas through the top half of the
    shell); hydrocarbon (``retention_hc_s``) and water (``retention_water_s``)
    retention volumes set the minimum length; L/D is kept in [3, 5] by growing
    the diameter when the retention length demand exceeds L/D = 5. The final
    diameter rounds up to the 0.15 m grid.

    Returns dict with ``diameter_m``, ``length_tt_m``, ``ld_ratio``,
    ``v_max_m_s`` and ``liquid_volume_m3``.
    """
    if rho_hc_liquid <= 0:
        raise ValueError(f"rho_hc_liquid must be positive, got {rho_hc_liquid}")
    if gas_flow_m3_s < 0 or hc_flow_m3_s < 0 or water_flow_m3_s < 0:
        raise ValueError("flows must be non-negative")
    if retention_hc_s < 0 or retention_water_s < 0:
        raise ValueError("retention times must be non-negative")

    sb = souders_brown(K_m_s=K_m_s, rho_liquid=rho_hc_liquid, rho_gas=rho_gas, gas_flow_m3_s=gas_flow_m3_s)
    v_max = float(sb["v_max_m_s"])
    liquid_volume = hc_flow_m3_s * retention_hc_s + water_flow_m3_s * retention_water_s

    # Diameter from gas through the top half of the shell. With no gas flow the
    # liquid retention demand alone must fit at L/D = LD_MAX.
    if gas_flow_m3_s > 0:
        diameter = math.sqrt(8.0 * gas_flow_m3_s / (math.pi * v_max))
    else:
        diameter = (8.0 * liquid_volume / (LD_MAX * math.pi)) ** (1.0 / 3.0)

    for _ in range(100):
        half_area = math.pi * diameter**2 / 8.0
        length = max(liquid_volume / half_area if half_area > 0 else 0.0, LD_MIN * diameter)
        if length / diameter <= LD_MAX:
            break
        diameter = math.sqrt(length / LD_MAX)
    else:  # pragma: no cover - the fixed point is reached in a few iterations
        raise RuntimeError("horizontal sizing did not converge")

    diameter = _ceil_step(diameter, DIAMETER_STEP_M)
    half_area = math.pi * diameter**2 / 8.0
    length = max(liquid_volume / half_area, LD_MIN * diameter)
    ld_ratio = length / diameter
    if not LD_MIN <= ld_ratio <= LD_MAX:
        raise ValueError(f"rounding produced L/D {ld_ratio} outside [{LD_MIN}, {LD_MAX}]")
    return {
        "diameter_m": diameter,
        "length_tt_m": length,
        "ld_ratio": ld_ratio,
        "v_max_m_s": v_max,
        "liquid_volume_m3": liquid_volume,
    }


class _VesselSizerBase:
    """Shared datasheet assembly; subclasses pick the shell sizing."""

    unit_kind: str

    def _shell(self, ports: Ports, params: dict[str, Any]) -> dict[str, float]:
        raise NotImplementedError

    def size(self, tag: str, solved: SolvedFlowsheet, params: dict[str, Any]) -> Datasheet:
        unit = solved.flowsheet.unit(tag)
        if unit.kind != self.unit_kind:
            raise ValueError(f"sizer {self.unit_kind} got unit {tag} of kind {unit.kind}")
        ports = connected(solved, tag)
        if not ports:
            raise ValueError(f"unit {tag} has no connected streams to size from")

        # Most severe connected operating conditions drive the design conditions.
        p_op = max(state.P for _, state in ports.values())
        t_op = max(state.T for _, state in ports.values())
        design = design_conditions(p_op, t_op)
        material_group = str(params.get("material_group", "1.1"))  # VERIFY
        flange_class = min_flange_class(
            design["design_pressure_Pa"], design["design_temperature_K"], material_group
        )

        shell = self._shell(ports, params)
        nozzles = self._nozzles(tag, ports, shell, flange_class)

        return Datasheet(
            tag=tag,
            kind=unit.kind,
            design_pressure_Pa=design["design_pressure_Pa"],
            design_temperature_K=design["design_temperature_K"],
            dimensions={k: v for k, v in shell.items() if isinstance(v, float)},
            nozzles=nozzles,
            notes=[
                f"flange class {flange_class} (B16.5 group {material_group}) at design conditions",
                "gas capacity K, retention times and accessory NPS are VERIFY defaults; "
                "override via sizer params",
            ],
        )

    def _nozzles(
        self,
        tag: str,
        ports: dict[str, tuple[StreamSpec, StreamState]],
        shell: dict[str, float],
        flange_class: int,
    ) -> list[Nozzle]:
        raise NotImplementedError


@register("sizer", "separator_3phase")
class Separator3PhaseSizer(_VesselSizerBase):
    """Horizontal 3-phase separator sizer (spec S-31)."""

    unit_kind = "separator_3phase"

    def _shell(self, ports: Ports, params: dict[str, Any]) -> dict[str, float]:
        gas = ports["gas_out"][1]
        hc = ports["hc_out"][1]
        water = ports["water_out"][1]
        rho_liquid = max(p.density for state in (hc, water) for p in state.phases if p.kind.value != "vapor")
        return horizontal_3phase(
            gas_flow_m3_s=volumetric_flow(gas),
            hc_flow_m3_s=volumetric_flow(hc),
            water_flow_m3_s=volumetric_flow(water),
            rho_gas=mixture_density(gas),
            rho_hc_liquid=rho_liquid,
            K_m_s=float(params.get("K_gas_m_s", HORIZONTAL_K_M_S)),
            retention_hc_s=float(params.get("retention_hc_s", RETENTION_HC_S)),
            retention_water_s=float(params.get("retention_water_s", RETENTION_WATER_S)),
        )

    def _nozzles(
        self,
        tag: str,
        ports: Ports,
        shell: dict[str, float],
        flange_class: int,
    ) -> list[Nozzle]:
        d, length = shell["diameter_m"], shell["length_tt_m"]
        # Positions in m on the shell (converted to mm in _nozzle); axis = x.
        spot = {
            "inlet": (Vec3(x=-length / 2, y=0.0, z=0.0), Direction.W),
            "gas_out": (Vec3(x=length / 2, y=0.0, z=d / 4), Direction.E),
            "hc_out": (Vec3(x=0.0, y=0.0, z=-d / 2), Direction.DOWN),
            "water_out": (Vec3(x=length / 4, y=0.0, z=-d / 2), Direction.DOWN),
            "psv": (Vec3(x=0.0, y=0.0, z=d / 2), Direction.UP),
            "vent": (Vec3(x=length / 2, y=0.0, z=d / 2), Direction.UP),
            "drain": (Vec3(x=-length / 4, y=0.0, z=-d / 2), Direction.DOWN),
            "level": (Vec3(x=-length / 4, y=d / 2, z=0.0), Direction.N),
            "pressure": (Vec3(x=length / 4, y=d / 2, z=0.0), Direction.N),
        }
        accessory_nps = {
            "psv": PSV_NPS_IN,
            "vent": VENT_NPS_IN,
            "drain": DRAIN_NPS_IN,
            "level": LEVEL_NPS_IN,
            "pressure": PRESSURE_NPS_IN,
        }

        nozzles: list[Nozzle] = []
        n = 0
        for port in ("inlet", "gas_out", "hc_out", "water_out"):
            if port not in ports:
                raise ValueError(f"separator {tag} is missing its {port} stream")
            spec, state = ports[port]
            n += 1
            pos, facing = spot[port]
            nozzles.append(
                nozzle(n, spec.service, port, nozzle_nps_in(spec.service, state), pos, facing, flange_class)
            )
        for service, nps in accessory_nps.items():
            n += 1
            pos, facing = spot[service]
            nozzles.append(nozzle(n, service, None, nps, pos, facing, flange_class))
        return nozzles


def vertical_diameter(
    gas_flow_m3_s: float,
    rho_gas: float,
    rho_liquid: float,
    K_m_s: float = VERTICAL_K_M_S,
) -> dict[str, float]:
    """Vertical scrubber/contactor diameter: Souders-Brown, full cross-section,
    rounded up to the 0.15 m grid. K default 0.06 m/s for packed contactors
    (VERIFY)."""
    sb = souders_brown(K_m_s=K_m_s, rho_liquid=rho_liquid, rho_gas=rho_gas, gas_flow_m3_s=gas_flow_m3_s)
    return {
        "diameter_m": _ceil_step(float(sb["min_diameter_m"]), DIAMETER_STEP_M),
        "v_max_m_s": float(sb["v_max_m_s"]),
    }


class _VerticalSizerBase(_VesselSizerBase):
    """Shared vertical-shell sizing: SB diameter + sim-port and accessory nozzles."""

    def _shell(self, ports: Ports, params: dict[str, Any]) -> dict[str, float]:
        k = float(params.get("K_gas_m_s", VERTICAL_K_M_S))

        # Gas stream = the connected stream carrying the most vapor by volume;
        # liquid density = densest liquid phase among the connected streams.
        def _vapor_flow(state: StreamState) -> float:
            q = 0.0
            for p in state.phases:
                if p.kind.value == "vapor":
                    mass = p.mole_fraction * state.molar_flow * p.molecular_weight / 1000.0
                    q += mass / p.density
            return q

        gas_port = max(ports, key=lambda port: _vapor_flow(ports[port][1]))
        gas_state = ports[gas_port][1]
        if _vapor_flow(gas_state) <= 0:
            raise ValueError("no gas stream connected to the vertical vessel")
        rhos = [p.density for _, state in ports.values() for p in state.phases if p.kind.value != "vapor"]
        if not rhos:
            raise ValueError("no liquid phase on any connected stream")
        return vertical_diameter(
            gas_flow_m3_s=volumetric_flow(gas_state),
            rho_gas=mixture_density(gas_state),
            rho_liquid=max(rhos),
            K_m_s=k,
        )

    def _nozzles(
        self,
        tag: str,
        ports: Ports,
        shell: dict[str, float],
        flange_class: int,
    ) -> list[Nozzle]:
        d = shell["diameter_m"]
        # Vertical convention: shell axis = z, origin at the tangent line; shell
        # length is a layout concern, so nozzles sit at the heads and mid-shell.
        spot: dict[str, tuple[Vec3, Direction]] = {
            "gas_in": (Vec3(x=0.0, y=0.0, z=0.0), Direction.N),
            "inlet": (Vec3(x=0.0, y=0.0, z=0.0), Direction.N),
            "gas_out": (Vec3(x=0.0, y=0.0, z=d / 2), Direction.UP),
            "lean_teg_in": (Vec3(x=-d / 2, y=0.0, z=-d / 4), Direction.W),
            "rich_teg_out": (Vec3(x=d / 2, y=0.0, z=-d / 4), Direction.E),
            "liquid_out": (Vec3(x=0.0, y=0.0, z=-d / 2), Direction.DOWN),
            "psv": (Vec3(x=d / 4, y=0.0, z=d / 2), Direction.UP),
            "vent": (Vec3(x=-d / 4, y=0.0, z=d / 2), Direction.UP),
            "drain": (Vec3(x=0.0, y=0.0, z=-d / 2), Direction.DOWN),
            "level": (Vec3(x=0.0, y=d / 2, z=0.0), Direction.N),
            "pressure": (Vec3(x=d / 2, y=0.0, z=0.0), Direction.E),
        }
        accessory_nps = {
            "psv": PSV_NPS_IN,
            "vent": VENT_NPS_IN,
            "drain": DRAIN_NPS_IN,
            "level": LEVEL_NPS_IN,
            "pressure": PRESSURE_NPS_IN,
        }

        nozzles: list[Nozzle] = []
        n = 0
        for port, (spec, state) in ports.items():
            n += 1
            pos, facing = spot[port]
            nozzles.append(
                nozzle(n, spec.service, port, nozzle_nps_in(spec.service, state), pos, facing, flange_class)
            )
        for service, nps in accessory_nps.items():
            n += 1
            pos, facing = spot[service]
            nozzles.append(nozzle(n, service, None, nps, pos, facing, flange_class))
        return nozzles


@register("sizer", "scrubber")
class ScrubberSizer(_VerticalSizerBase):
    """Vertical scrubber sizer (spec S-31)."""

    unit_kind = "scrubber"


@register("sizer", "teg_contactor")
class TegContactorSizer(_VerticalSizerBase):
    """Vertical TEG contactor sizer (spec S-31)."""

    unit_kind = "teg_contactor"
