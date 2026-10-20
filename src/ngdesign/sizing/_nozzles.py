"""Nozzle and datasheet-geometry helpers shared by the equipment sizers (spec P0-05).

Single home for the port-connection, nozzle-sizing, flange-class and nozzle-
construction helpers previously duplicated between ``vessels.py`` (S-31) and
``machines.py`` (S-32), plus the volumetric-flow/mixture-density helpers both
sizers need. All SI; nozzle geometry in the contracts convention (NPS inches,
positions mm). Behaviour-preserving: where the two former copies differed
(``role`` default, return-type alias), the signatures were reconciled with the
default both callers relied on.
"""

from __future__ import annotations

from ngdesign.contracts.common import Direction, Nozzle, Vec3
from ngdesign.contracts.flowsheet import SolvedFlowsheet, StreamSpec
from ngdesign.contracts.stream import StreamState
from ngdesign.sizing import flange_rating
from ngdesign.sizing.line_size import line_size

__all__ = [
    "PA_PER_PSIG",
    "Ports",
    "connected",
    "min_flange_class",
    "mixture_density",
    "nozzle",
    "nozzle_nps_in",
    "volumetric_flow",
]

# Exact psi (lbf/in^2) in Pa, used to convert design pressures for B16.5 (S-11).
PA_PER_PSIG = 6894.757293168

# Port name -> (stream spec, solved state) for one unit's connected ports.
Ports = dict[str, tuple[StreamSpec, StreamState]]


def volumetric_flow(state: StreamState) -> float:
    """Actual volumetric flow [m3/s] of a stream state, all phases summed.

    Phase model holds density [kg/m3] and molecular weight [g/mol]; the mass
    flow of one phase is mole_fraction * molar_flow * MW / 1000.
    """
    if not state.phases:
        raise ValueError("stream state has no phases (flash it with thermo first)")
    q = 0.0
    for phase in state.phases:
        mass = phase.mole_fraction * state.molar_flow * phase.molecular_weight / 1000.0
        if phase.density <= 0:
            raise ValueError(f"phase {phase.kind} has non-positive density {phase.density}")
        q += mass / phase.density
    return q


def mixture_density(state: StreamState) -> float:
    """Mixture density [kg/m3] = mass flow / volumetric flow."""
    q = volumetric_flow(state)
    if q <= 0:
        raise ValueError("stream state has zero volumetric flow")
    return state.mass_flow / q


def connected(solved: SolvedFlowsheet, tag: str) -> Ports:
    """Port name -> (stream spec, solved state) for every port of the unit."""
    out: Ports = {}
    fs = solved.flowsheet
    for spec in (*fs.inlets(tag), *fs.outlets(tag)):
        ref = spec.target if (spec.target is not None and spec.target.unit == tag) else spec.source
        if ref is None:  # pragma: no cover - Flowsheet forbids streams with both ends None
            raise ValueError(f"stream {spec.id} has no end on unit {tag}")
        out[ref.port] = (spec, solved.streams[spec.id])
    return out


def nozzle_nps_in(service: str, state: StreamState, role: str = "line") -> float:
    """Nozzle NPS [in] from the S-20 line sizing correlation.

    ``role`` defaults to ``"line"`` (the general S-20 limits); machine suction
    nozzles pass ``"suction"`` explicitly.
    """
    return float(
        line_size(
            service=service,
            flow_m3_s=volumetric_flow(state),
            rho_kg_m3=mixture_density(state),
            role=role,
        )["nps_in"]
    )


def min_flange_class(design_p_pa: float, design_t_k: float, material_group: str) -> int:
    """Lowest B16.5 flange class (S-11) rated at the datasheet design conditions.

    Design pressure arrives in Pa abs and temperature in K; the B16.5 tables
    take psig and Fahrenheit, so both are converted here.
    """
    psig = design_p_pa / PA_PER_PSIG
    temp_f = (design_t_k - 273.15) * 9.0 / 5.0 + 32.0
    return flange_rating.min_flange_class(material_group, psig, temp_f)


def nozzle(
    n: int,
    service: str,
    port: str | None,
    nps_in: float,
    position: Vec3,
    facing: Direction,
    flange_class: int,
) -> Nozzle:
    """Build one ``Nozzle``: N<n> ids, positions converted from m to mm."""
    return Nozzle(
        id=f"N{n}",
        service=service,
        port=port,
        nps_in=nps_in,
        flange_class=flange_class,
        position_mm=Vec3(x=position.x * 1000.0, y=position.y * 1000.0, z=position.z * 1000.0),
        facing=facing,
    )
