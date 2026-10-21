"""Shared state helpers for the thermo packages (spec P0-04).

Moved verbatim from `pr.py`, which had drifted into four near-identical copies
across pr/srk/pr78/nrtl (~75 % of nrtl.py repeated the same helpers). Pure
refactor: no change in tolerances, iteration caps, stability logic or phase
labelling. The docstring in `contracts/plugins.py` still says "Peng-Robinson
package" — left as is; Phase 1 rewrites that contract.

Contents:
- flasher construction from the component list, parameterised by the
  `thermo`-library mixture EOS class and the k_ij source used today,
- the FlashVLN result -> StreamState mapping,
- the aqueous-phase classification (water mole fraction > 0.5 rule),
- the single-phase stability re-check,
- the PT flash flow the PH/PS wrappers reuse.

Component ids resolve through the open component registry (spec P1-02):
`ngdesign.contracts.components.resolve` over `ngdesign.data.component_record` -
curated slate by id (C6+ stays n-hexane per its provenance note), the chemicals
databank by CAS or name, and registered pseudo-components (CAS None). All-databank
supports take thermo's own `from_IDs` path unchanged; supports with pseudos get a
merged constants package (databank constants for CAS-bearing records, Component
fields for pseudos, Lastovka-Shaw Cp and generalized VaporPressure correlations for
them). SI units throughout: K, Pa, kg/m3, Pa.s, J/mol, J/(mol K).
"""

from __future__ import annotations

import math
from functools import cache
from typing import Any, Literal, cast

from chemicals.elements import similarity_variable
from thermo import (
    CEOSGas,
    CEOSLiquid,
    ChemicalConstantsPackage,
    FlashVL,
    FlashVLN,
    PropertyCorrelationsPackage,
)
from thermo.heat_capacity import HeatCapacityGas
from thermo.interaction_parameters import IPDB
from thermo.vapor_pressure import VaporPressure

from ngdesign.contracts import Phase, PhaseKind, StreamState
from ngdesign.contracts.components import Component, resolve
from ngdesign.contracts.thermo import (
    PhaseProps,
    PropertyDerivatives,
    SaturationError,
    SaturationPoint,
)
from ngdesign.thermo.saturation import _solve_saturation, interior_vf_solve

#: CODATA 2018 molar gas constant, J/(mol.K).
R_IDEAL = 8.31446261815324

#: A liquid phase is the aqueous phase when its water mole fraction exceeds this.
AQUEOUS_WATER_FRACTION = 0.5

_KIND_ORDER = (PhaseKind.VAPOR, PhaseKind.HC_LIQUID, PhaseKind.AQUEOUS)

# (phase object, phase mole fraction) as carried through state construction.
PhasePair = tuple[Any, float]

# CH2 group mass and H2 mass for the paraffinic atom estimate (CnH2n+2),
# IUPAC standard atomic weights: C 12.011, H 1.008.
_CH2_MASS = 12.011 + 2.0 * 1.008
_H2_MASS = 2.0 * 1.008


def _records(ids: tuple[str, ...]) -> list[Component]:
    """Resolved Component records for a (sorted) flash support, in support order."""
    return [resolve(cid) for cid in ids]


def _pseudo_heat_capacity(record: Component) -> HeatCapacityGas:
    """Ideal-gas Cp correlation for a pseudo-component (Lastovka & Shaw 2013 via thermo).

    Lastovka-Shaw needs the similarity variable; a pseudo has no formula, so the
    atoms are estimated paraffinically (CnH2n+2) from the Riazi-Daubert MW of the
    record - the same stated approximation the Tb + sg characterization makes.
    """
    return HeatCapacityGas(CASRN="", MW=record.mw, similarity_variable=_pseudo_similarity_variable(record))


def _pseudo_similarity_variable(record: Component) -> float:
    """Lastovka-Shaw similarity variable from a paraffinic CnH2n+2 atom estimate."""
    n_carbon = (record.mw - _H2_MASS) / _CH2_MASS
    return float(similarity_variable(atoms={"C": n_carbon, "H": 2.0 * n_carbon + 2.0}, MW=record.mw))


def _pseudo_vapor_pressure(record: Component) -> VaporPressure:
    """Generalized vapor-pressure correlation for a pseudo (no CAS, no databank Psat).

    VaporPressure(Tb, Tc, Pc, omega) auto-selects a generalized method (Ambrose-
    Walton in-session); good enough for K-value phase splitting, not for design
    duty claims - provenance on the Component records says as much.
    """
    return VaporPressure(Tb=record.Tb, Tc=record.Tc, Pc=record.Pc, omega=record.omega)


def _constants_package(records: list[Component]) -> tuple[ChemicalConstantsPackage, Any]:
    """(constants, correlations) for a flash support, from resolved Component records.

    All-databank supports take thermo's own ``from_IDs`` path unchanged - the
    records carry the same CAS the EOS always used, so golden thermo output and
    the bench baseline stay byte-identical. Supports with pseudo-components
    (CAS None) get the merged package: databank constants for CAS-bearing
    records in slate order, Component fields for pseudos, Cp via
    ``_pseudo_heat_capacity`` and Psat via ``_pseudo_vapor_pressure`` for them,
    zero k_ij to every databank partner.
    """
    if all(r.cas is not None for r in records):
        constants, correlations = ChemicalConstantsPackage.from_IDs([str(r.cas) for r in records])
        return constants, correlations
    return _merged_constants_package(records)


def _merged_constants_package(records: list[Component]) -> tuple[ChemicalConstantsPackage, Any]:
    """Mixed databank + pseudo constants package, vectors in slate order."""
    databank_idx = [i for i, r in enumerate(records) if r.cas is not None]
    constants, correlations = ChemicalConstantsPackage.from_IDs([str(records[i].cas) for i in databank_idx])
    by_position = {i: j for j, i in enumerate(databank_idx)}  # slate position -> from_IDs index

    def db(i: int, vector: Any) -> Any:
        return vector[by_position[i]]

    tcs: list[float] = []
    pcs: list[float] = []
    omegas: list[float] = []
    mws: list[float] = []
    names: list[str] = []
    cass: list[str | None] = []
    tbs: list[float] = []
    heat_caps: list[Any] = []
    vapor_pressures: list[Any] = []
    for i, record in enumerate(records):
        if record.cas is not None:
            tcs.append(float(db(i, constants.Tcs)))
            pcs.append(float(db(i, constants.Pcs)))
            omegas.append(float(db(i, constants.omegas)))
            mws.append(float(db(i, constants.MWs)))
            names.append(str(db(i, constants.names)))
            cass.append(str(db(i, constants.CASs)))
            tbs.append(float(db(i, constants.Tbs)))
            heat_caps.append(correlations.HeatCapacityGases[by_position[i]])
            vapor_pressures.append(correlations.VaporPressures[by_position[i]])
        else:
            tcs.append(record.Tc)
            pcs.append(record.Pc)
            omegas.append(record.omega)
            mws.append(record.mw)
            names.append(record.name)
            cass.append(None)
            tbs.append(_required_tb(record))
            heat_caps.append(_pseudo_heat_capacity(record))
            vapor_pressures.append(_pseudo_vapor_pressure(record))
    merged = ChemicalConstantsPackage(
        Tcs=tcs,
        Pcs=pcs,
        omegas=omegas,
        MWs=mws,
        names=names,
        CASs=cass,
        Tbs=tbs,
    )
    mixed = PropertyCorrelationsPackage(
        constants=merged,
        HeatCapacityGases=heat_caps,
        VaporPressures=vapor_pressures,
        skip_missing=True,
    )
    return merged, mixed


def _required_tb(record: Component) -> float:
    """A pseudo must carry its Tb (the characterization pair includes it)."""
    if record.Tb is None:
        raise ValueError(f"pseudo-component {record.id!r} has no Tb; register it with Tb and sg")
    return record.Tb


def _kij_matrix(records: list[Component], kij_table: str) -> list[list[float]]:
    """Symmetric k_ij matrix for the support: fitted pairs from the IPDB table,
    0.0 to every pseudo (no fitted BIPs exist for pseudos)."""
    if all(r.cas is not None for r in records):
        fitted_databank: list[list[float]] = IPDB.get_ip_symmetric_matrix(
            name=kij_table, CASs=[str(r.cas) for r in records], ip="kij"
        )
        return fitted_databank
    databank_idx = [i for i, r in enumerate(records) if r.cas is not None]
    fitted = IPDB.get_ip_symmetric_matrix(
        name=kij_table, CASs=[str(records[i].cas) for i in databank_idx], ip="kij"
    )
    n = len(records)
    kijs: list[list[float]] = [[0.0] * n for _ in range(n)]
    for a, i in enumerate(databank_idx):
        for b, j in enumerate(databank_idx):
            kijs[i][j] = float(fitted[a][b])
    return kijs


def build_flasher(ids: tuple[str, ...], eos: Any, kij_table: str) -> Any:
    """Build a FlashVLN flasher over exactly this sorted component set.

    Parameterised by the `thermo`-library mixture EOS class (PRMIX, SRKMIX,
    PR78MIX) and the IPDB k_ij table used today; callers own the caching (the
    cache key is the reduced, sorted support of the feed composition -
    zero-fraction components are dropped by the caller before this is reached).
    Constants build from the resolved Component records (spec P1-02), so every
    id must resolve before this is reached.
    """
    records = _records(ids)
    constants, correlations = _constants_package(records)
    kijs = _kij_matrix(records, kij_table)
    eos_kwargs: dict[str, Any] = {
        "Tcs": constants.Tcs,
        "Pcs": constants.Pcs,
        "omegas": constants.omegas,
        "kijs": kijs,
    }
    heat_caps = correlations.HeatCapacityGases
    gas = CEOSGas(eos, eos_kwargs, HeatCapacityGases=heat_caps)
    liquids = [
        CEOSLiquid(eos, eos_kwargs, HeatCapacityGases=heat_caps),
        CEOSLiquid(eos, eos_kwargs, HeatCapacityGases=heat_caps),
    ]
    return FlashVLN(constants, correlations, liquids=liquids, gas=gas)


def _classify(is_gas: bool, water_fraction: float) -> PhaseKind:
    """Spec S-01 rule: vapor = gas phase; liquid with water mole fraction > 0.5 = AQUEOUS."""
    if is_gas:
        return PhaseKind.VAPOR
    if water_fraction > AQUEOUS_WATER_FRACTION:
        return PhaseKind.AQUEOUS
    return PhaseKind.HC_LIQUID


def _composition(zs: list[float], ids: tuple[str, ...], full_keys: tuple[str, ...]) -> dict[str, float]:
    """Map one phase composition back onto the caller's key set (dropped ids -> 0.0).

    Phase mole fractions are clamped at 0 (EOS solvers can emit ~-1e-17) and
    renormalized so the contract validator's sum-to-1 holds exactly.
    """
    out = {cid: 0.0 for cid in full_keys}
    for i, cid in enumerate(ids):
        out[cid] = max(0.0, float(zs[i]))
    total = sum(out.values())
    if total <= 0.0:
        raise ValueError(f"phase composition collapsed to zero for ids {ids}")
    return {cid: v / total for cid, v in out.items()}


def _viscosity(phase: Any) -> float | None:
    """Dynamic viscosity in Pa.s, None where thermo has no correlation.

    Spec S-01 allows None here; thermo's failure modes (missing correlations for a
    component, unit errors) are heterogeneous, so this is the one sanctioned fallback.
    """
    try:
        return float(phase.mu())
    except Exception:
        return None


def _stability_resolved(
    flasher: Any, zs: list[float], T: float, P: float
) -> tuple[list[PhasePair], float, float]:
    """Independently verify a single-phase flash result at (T, P).

    FlashVLN's fast TP path can stop at the wrong single-phase root - a gas for a
    compressed liquid (e.g. lean TEG at 325 K / 7.1 MPa). flash_TP_stability_test
    re-decides gas vs liquid by Gibbs energy and re-splits an unstable single phase.

    A stability-test convergence failure falls back to the flasher's own answer:
    treating a non-converged trial phase as stable is the standard Michelsen
    convention, and the alternative (raising) would break every downstream flash.
    """
    try:
        gas, liquids, _solids, betas, _info = flasher.flash_TP_stability_test(
            T, P, zs, liquid=flasher.liquids[0], gas=flasher.gas
        )
    except Exception:
        return [], 0.0, 0.0  # empty list signals "keep the flasher's own result"

    pairs: list[PhasePair] = []
    if gas is not None:  # thermo orders betas gas-first, then liquids
        pairs.append((gas, float(betas[0])))
    n_liq = len(liquids)
    for liq, beta in zip(liquids, betas[len(betas) - n_liq :], strict=False):
        pairs.append((liq, float(beta)))
    # Phase copies built inside the stability test (Phase.to) lose the
    # constants/correlations back-references the flasher normally attaches;
    # restore them so property methods (MW, rho_mass, H, S, mu) work.
    for phase, _ in pairs:
        if getattr(phase, "constants", None) is None:
            phase.constants = flasher.constants
        if getattr(phase, "correlations", None) is None:
            phase.correlations = flasher.correlations
    enthalpy = sum(beta * float(p.H()) for p, beta in pairs)
    entropy = sum(beta * float(p.S()) for p, beta in pairs)
    return pairs, enthalpy, entropy


def _build_stream_state(
    z: dict[str, float],
    molar_flow: float,
    T: float,
    P: float,
    ids: tuple[str, ...],
    phase_pairs: list[PhasePair],
    enthalpy: float,
    entropy: float,
) -> StreamState:
    """Convert present (phase, beta) pairs into the contract's StreamState."""
    full_keys = tuple(z.keys())
    water_idx = ids.index("H2O") if "H2O" in ids else -1

    built: list[Phase] = []
    vapor_fraction = 0.0
    for phase_obj, beta in phase_pairs:
        if beta <= 0.0:
            continue
        zs = [float(v) for v in phase_obj.zs]
        water_fraction = zs[water_idx] if water_idx >= 0 else 0.0
        is_gas = isinstance(phase_obj, CEOSGas)
        kind = _classify(is_gas, water_fraction)
        density = float(phase_obj.rho_mass())  # kg/m3
        mw = float(phase_obj.MW())  # g/mol
        z_factor: float | None = None
        if is_gas:
            # z = P / (rho_molar * R * T), ideal-gas definition of compressibility
            rho_molar = density / (mw / 1000.0)
            z_factor = P / (rho_molar * R_IDEAL * T)
            vapor_fraction += beta
        built.append(
            Phase(
                kind=kind,
                mole_fraction=beta,
                composition=_composition(zs, ids, full_keys),
                density=density,
                viscosity=_viscosity(phase_obj),
                z_factor=z_factor,
                molecular_weight=mw,
                enthalpy=float(phase_obj.H()),  # J/mol (spec P1-01)
                entropy=float(phase_obj.S()),  # J/(mol K) (spec P1-01)
                cp=float(phase_obj.Cp()),  # J/(mol K) (spec P1-01)
                ln_phi={cid: 0.0 for cid in full_keys}
                | dict(zip(ids, (float(v) for v in phase_obj.lnphis()), strict=True)),  # spec P1-01
            )
        )

    if not built:
        raise ValueError(f"flash returned no present phases at T={T}, P={P}")

    order = {k: i for i, k in enumerate(_KIND_ORDER)}
    built.sort(key=lambda p: order[p.kind])
    return StreamState(
        T=T,
        P=P,
        molar_flow=molar_flow,
        composition=dict(z),
        vapor_fraction=vapor_fraction,
        enthalpy=enthalpy,  # J/mol, thermo's ideal-gas formation reference
        entropy=entropy,  # J/(mol.K), same reference
        phases=built,
    )


def run_flash(flasher: Any, z: dict[str, float], molar_flow: float, **spec: float) -> StreamState:
    """Drop zero-fraction components, flash, and map the result back.

    Phase count is taken from the flash result's actually-present phases
    (FlashVLN may return fewer phases than a case "should" have); a single-phase
    result is re-verified by stability test in _stability_resolved, and
    classification happens per phase in _build_stream_state.
    """
    ids = tuple(sorted(cid for cid, x in z.items() if x > 0.0))
    if not ids:
        raise ValueError("composition has no positive mole fractions")
    zs = [float(z[cid]) for cid in ids]
    state = flasher.flash(zs=zs, **spec)
    T, P = float(state.T), float(state.P)
    phase_pairs: list[PhasePair] = [(p, float(p.beta)) for p in state.phases]
    enthalpy, entropy = float(state.H()), float(state.S())

    if sum(1 for _, beta in phase_pairs if beta > 0.0) == 1:
        verified, h2, s2 = _stability_resolved(flasher, zs, T, P)
        if verified:
            phase_pairs, enthalpy, entropy = verified, h2, s2

    return _build_stream_state(z, molar_flow, T, P, ids, phase_pairs, enthalpy, entropy)


# ------------------------------------------------------------------ contract v2 (spec P1-01)

#: Component id of water; its presence is what makes a second liquid phase possible.
WATER_ID = "H2O"

#: Property-cache size (PT flashes and phase_props, per package instance), spec P1-01.
PROPERTY_CACHE_SIZE = 4096

#: Initial-bracket factors: Psat-based brackets (pressure solve) and Psat-inversion brackets.
_P_LO, _P_HI = 0.5, 3.0
_T_LO, _T_HI = 0.9, 1.15

#: Saturation targets within this distance of 0 / 1 are solved as bubble / dew points.
_VF_EDGE = 1e-9


def support_ids(z: dict[str, float]) -> tuple[str, ...]:
    """Sorted ids of the components with positive mole fraction (the flash support)."""
    ids = tuple(sorted(cid for cid, x in z.items() if x > 0.0))
    if not ids:
        raise ValueError("composition has no positive mole fractions")
    return ids


def cache_key(z: dict[str, float], T: float, P: float) -> tuple[Any, ...]:
    """Property-cache key: composition rounded to 1e-10, T to 1e-6, P to 1e-3."""
    return (tuple(sorted((cid, round(x, 10)) for cid, x in z.items())), round(T, 6), round(P, 3))


def build_flasher_vl(ids: tuple[str, ...], eos: Any, kij_table: str) -> Any:
    """Build a two-phase FlashVL flasher over exactly this sorted component set.

    The saturation fast path (spec P1-01): when the feed cannot form a second
    liquid (no water), a VLE-only FlashVL over the same EOS objects reaches the
    same equilibrium without liquid-liquid stability work.
    """
    records = _records(ids)
    constants, correlations = _constants_package(records)
    kijs = _kij_matrix(records, kij_table)
    eos_kwargs: dict[str, Any] = {
        "Tcs": constants.Tcs,
        "Pcs": constants.Pcs,
        "omegas": constants.omegas,
        "kijs": kijs,
    }
    heat_caps = correlations.HeatCapacityGases
    gas = CEOSGas(eos, eos_kwargs, HeatCapacityGases=heat_caps)
    liquid = CEOSLiquid(eos, eos_kwargs, HeatCapacityGases=heat_caps)
    # N=1 is never flashed through this path: thermo's FlashVL stability guess
    # divides by N-1, so pure feeds short-circuit to the databank Psat curve in
    # _saturation and the full flasher maps their states.
    return FlashVL(constants, correlations, gas=gas, liquid=liquid)


def _pt_phase_pairs(flasher: Any, zs: list[float], T: float, P: float) -> list[PhasePair]:
    """(phase, beta) pairs at (T, P) — the run_flash flow without StreamState mapping.

    Single-phase results are re-verified by the stability test exactly as
    run_flash does, so the vapour fraction the saturation solver sees has the
    same semantics as StreamState.vapor_fraction.
    """
    state = flasher.flash(zs=zs, T=T, P=P)
    phase_pairs: list[PhasePair] = [(p, float(p.beta)) for p in state.phases]
    if sum(1 for _, beta in phase_pairs if beta > 0.0) == 1:
        verified, _h, _s = _stability_resolved(flasher, zs, T, P)
        if verified:
            phase_pairs = verified
    return phase_pairs


def _vapor_fraction(pairs: list[PhasePair]) -> float:
    """Molar vapour fraction of (phase, beta) pairs — non-vapor phases count as liquid."""
    return sum(beta for phase, beta in pairs if isinstance(phase, CEOSGas))


def _thermal_conductivity(phase: Any) -> float | None:
    """Thermal conductivity in W/(m K), None where thermo has no correlation."""
    try:
        return float(phase.k())
    except Exception:
        return None


# ------------------------------------------------------------------ pure Psat


@cache
def _psat_data(cid: str) -> tuple[Any, float, float, float]:
    """(vapor-pressure correlation, Tc, Pc, omega) for one component id, cached.

    Databank-resolved ids use the same from_IDs path as the flashers (identical
    constants); pseudos use the generalized Tb/Tc/Pc/omega VaporPressure.
    """
    record = resolve(cid)
    if record.cas is None:
        return _pseudo_vapor_pressure(record), record.Tc, record.Pc, record.omega
    constants, correlations = ChemicalConstantsPackage.from_IDs([str(record.cas)])
    return (
        correlations.VaporPressures[0],
        float(constants.Tcs[0]),
        float(constants.Pcs[0]),
        float(constants.omegas[0]),
    )


def pure_psat(cid: str, T: float) -> float | None:
    """Pure-component vapour pressure (Pa) at T (K); None at or above Tc."""
    vp, tc, _pc, _omega = _psat_data(cid)
    if T >= tc:
        return None
    value = vp.T_dependent_property(T)
    if value is None:
        raise ValueError(f"no vapour-pressure correlation for {cid} at T={T} K")
    return float(value)


def _wilson_psat(cid: str, T: float) -> float:
    """Wilson-correlation vapour-pressure estimate (Pa) at T.

    Deliberately rough but defined past Tc — used only to bound saturation
    brackets, where supercritical components still push the mixture bubble
    pressure up (methane raises a C1/H2O feed's bubble pressure at 300 K far
    above any subcritical component's real Psat).
    """
    _vp, tc, pc, omega = _psat_data(cid)
    return pc * math.exp(5.373 * (1.0 + omega) * (1.0 - tc / T))


def _wilson_T(cid: str, P: float) -> float:
    """Wilson-correlation saturation-temperature estimate (K) at P, same caveat as _wilson_psat."""
    _vp, tc, pc, omega = _psat_data(cid)
    denom = 1.0 - math.log(P / pc) / (5.373 * (1.0 + omega))
    if denom <= 0.05:  # far above the component's Psat ceiling: no usable T bound
        raise ValueError(f"{cid} has no Wilson T bound at P={P} Pa")
    return tc / denom


def _wilson_T_safe(cid: str, P: float) -> float | None:
    """_wilson_T with unusable bounds (denominator collapse) mapped to None."""
    try:
        return _wilson_T(cid, P)
    except ValueError:
        return None


def _psat_T(cid: str, P: float) -> float | None:
    """Saturation temperature (K) of one component at P (Pa); None when P >= Pc.

    Wilson initial guess (ln Pr = 5.373 (1 + omega) (1 - 1/Tr)) refined by
    secant iteration on the databank vapour-pressure correlation.
    """
    vp, tc, pc, omega = _psat_data(cid)
    if P >= pc:
        return None
    tr = 1.0 / (1.0 - math.log(P / pc) / (5.373 * (1.0 + omega)))
    t = min(max(tr * tc, 0.35 * tc), 0.9999 * tc)

    def f(temp: float) -> float:
        value = vp.T_dependent_property(temp)
        return float(value) - P if value is not None else math.inf

    t0, t1 = t * 0.99, t * 1.01
    f0, f1 = f(t0), f(t1)
    for _ in range(30):
        if abs(f1) <= 1e-10 * P:
            break
        denom = f1 - f0
        if denom == 0.0:
            break
        t2 = t1 - f1 * (t1 - t0) / denom
        t2 = min(max(t2, 0.3 * tc), 0.9999 * tc)
        t0, f0, t1 = t1, f1, t2
        f1 = f(t1)
    return t1


# ------------------------------------------------------------------ saturation solver


def _saturation(
    flasher: Any,
    z: dict[str, float],
    kind: Literal["bubble", "dew"],
    *,
    T: float | None = None,
    P: float | None = None,
) -> SaturationPoint:
    """Bubble or dew point via a bracketed secant on the PT flash's vapour fraction.

    FlashVLN.flash(VF=...) is unreliable on the slice feed (IndexError /
    UnboundLocalError, verified 2026-10-20), so the unknown (P at fixed T, T at
    fixed P) is solved on the PT flash's vapour fraction instead: brackets from
    pure-component vapour-pressure bounds, secant iterations safeguarded by
    bisection inside the bracket, 1e-8 relative tolerance on the unknown, 60
    iteration cap. Michelsen & Mollerup, Thermodynamic Models: Fundamentals and
    Computational Aspects, ch. 10 (saturation).

    The plateau-scan-then-bracketed-secant algorithm lives in the shared
    ``thermo.saturation`` solver (spec P1-08); this wrapper builds ``vf_at``
    from ``_pt_phase_pairs``, keeps the Wilson bounds (defined past Tc) and the
    pure-feed Psat short-circuit, and recovers the incipient composition from
    the solver's recorded interior evaluation.  The vapour fraction is
    continuous inside the two-phase envelope but plateaus at 1 below the dew
    point and at 0 above the bubble point.
    """
    if (T is None) == (P is None):
        raise ValueError("specify exactly one of T and P")
    ids = support_ids(z)
    zs = [float(z[cid]) for cid in ids]
    full_keys = tuple(z.keys())

    if len(ids) == 1:
        # Pure feed: bubble and dew coincide with the databank vapour-pressure
        # curve, and the N=1 reduced FlashVL is unusable (thermo's stability
        # guessing divides by N-1 and misclassifies the single phase), so both
        # solvers short-circuit to Psat / its inverse.
        cid = ids[0]
        if T is not None:
            p_sat = pure_psat(cid, T)
            if p_sat is None:
                raise SaturationError(f"{cid} is supercritical at T={T} K: no saturation point")
            return SaturationPoint(T=T, P=p_sat, kind=kind, incipient_composition={cid: 1.0})
        assert P is not None
        t_sat = _psat_T(cid, P)
        if t_sat is None:
            raise SaturationError(f"{cid} is supercritical at P={P} Pa: no saturation point")
        return SaturationPoint(T=t_sat, P=P, kind=kind, incipient_composition={cid: 1.0})

    if T is not None:
        psats = [p for cid in ids if (p := pure_psat(cid, T)) is not None]
        if not psats:
            raise SaturationError(
                f"no two-phase region at T={T} K: every component of {sorted(z)} is supercritical"
            )
        bounds = [_wilson_psat(cid, T) for cid in ids]
        lo, hi = _P_LO * min(bounds), _P_HI * max(bounds)
        label = f"T={T} K"
        unknown: Literal["P", "T"] = "P"

        def pairs_at(x: float) -> list[PhasePair]:
            return _pt_phase_pairs(flasher, zs, T, x)

    else:
        ts = [t for cid in ids if (t := _psat_T(cid, P)) is not None]  # type: ignore[arg-type]
        if not ts:
            raise SaturationError(
                f"no two-phase region at P={P} Pa: every component of {sorted(z)} is supercritical"
            )
        assert P is not None
        p_given: float = P
        bounds_t = [t for cid in ids if (t := _wilson_T_safe(cid, P)) is not None]
        lo, hi = _T_LO * min(bounds_t), _T_HI * max(bounds_t)
        label = f"P={p_given} Pa"
        unknown = "T"

        def pairs_at(x: float) -> list[PhasePair]:
            return _pt_phase_pairs(flasher, zs, x, p_given)

    def vf_at(x: float) -> float:
        return _vapor_fraction(pairs_at(x))

    solution = _solve_saturation(vf_at, kind=kind, unknown=unknown, bounds=(lo, hi), label=label)

    incipient = dict(z)
    if solution.interior_x is not None:
        # The shared solver sees vapour fractions only; one deterministic
        # re-flash at its recorded interior evaluation recovers the (phase,
        # beta) pairs the incipient composition is taken from.
        want_gas = kind == "bubble"
        for phase, beta in pairs_at(solution.interior_x):
            if beta > 0.0 and isinstance(phase, CEOSGas) == want_gas:
                incipient = _composition([float(v) for v in phase.zs], ids, full_keys)
                break

    return SaturationPoint(
        T=T if T is not None else solution.x,
        P=P if P is not None else solution.x,
        kind=kind,
        incipient_composition=incipient,
    )


def bubble_point(
    flasher: Any, z: dict[str, float], *, T: float | None = None, P: float | None = None
) -> SaturationPoint:
    """Bubble point of the feed: exactly one of T (K) and P (Pa) given."""
    return _saturation(flasher, z, "bubble", T=T, P=P)


def dew_point(
    flasher: Any, z: dict[str, float], *, T: float | None = None, P: float | None = None
) -> SaturationPoint:
    """Dew point of the feed: exactly one of T (K) and P (Pa) given."""
    return _saturation(flasher, z, "dew", T=T, P=P)


def flash_tvf(pkg: Any, z: dict[str, float], T: float, vf: float, molar_flow: float) -> StreamState:
    """TVF flash: secant on P through the PT flash, bracketed by the dew and bubble pressures."""
    if not 0.0 <= vf <= 1.0:
        raise ValueError(f"vapour fraction {vf} outside [0, 1]")
    ids = support_ids(z)
    flasher = pkg._sat_flasher(ids)
    if vf <= _VF_EDGE:
        P = _saturation(flasher, z, "bubble", T=T).P
    elif vf >= 1.0 - _VF_EDGE:
        P = _saturation(flasher, z, "dew", T=T).P
    else:
        p_dew = _saturation(flasher, z, "dew", T=T).P
        p_bub = _saturation(flasher, z, "bubble", T=T).P
        zs = [float(z[cid]) for cid in ids]

        def vf_at(x: float) -> float:
            return _vapor_fraction(_pt_phase_pairs(flasher, zs, T, x))

        P = interior_vf_solve(vf_at, vf, p_dew, p_bub)
    # Final state through the package's own (cached) PT flash: the full flasher
    # and the VL fast path agree at the converged point (verified 2026-10-20 on
    # the C1/C3/nC5 feed, identical VF and G), so the stream a caller gets back
    # is the same object a flash_pt at (T, P) would return.
    return cast(StreamState, pkg.flash_pt(z, T, P, molar_flow))


def flash_pvf(pkg: Any, z: dict[str, float], P: float, vf: float, molar_flow: float) -> StreamState:
    """PVF flash: secant on T through the PT flash, bracketed by the bubble and dew temperatures."""
    if not 0.0 <= vf <= 1.0:
        raise ValueError(f"vapour fraction {vf} outside [0, 1]")
    ids = support_ids(z)
    flasher = pkg._sat_flasher(ids)
    if vf <= _VF_EDGE:
        T = _saturation(flasher, z, "bubble", P=P).T
    elif vf >= 1.0 - _VF_EDGE:
        T = _saturation(flasher, z, "dew", P=P).T
    else:
        t_bub = _saturation(flasher, z, "bubble", P=P).T
        t_dew = _saturation(flasher, z, "dew", P=P).T
        zs = [float(z[cid]) for cid in ids]

        def vf_at(x: float) -> float:
            return _vapor_fraction(_pt_phase_pairs(flasher, zs, x, P))

        T = interior_vf_solve(vf_at, vf, t_bub, t_dew)
    return cast(StreamState, pkg.flash_pt(z, T, P, molar_flow))  # as in flash_tvf


# ------------------------------------------------------------------ K-values, phase props, derivatives


def k_values(flasher: Any, z: dict[str, float], T: float, P: float) -> dict[str, float] | None:
    """K_i = y_i/x_i from a PT flash; None when single-phase.

    Same semantics the column uses today (units/column.py _ThermoBox.k_values):
    the first non-vapour phase is the reference liquid, and a state whose vapour
    fraction sits within 1e-6 of 0 or 1 counts as single-phase.
    """
    state = run_flash(flasher, z, 1.0, T=T, P=P)
    if not 1e-6 < state.vapor_fraction < 1.0 - 1e-6:
        return None
    vapor = next(p for p in state.phases if p.kind == PhaseKind.VAPOR)
    liquid = next(p for p in state.phases if p.kind != PhaseKind.VAPOR)
    out: dict[str, float] = {}
    for cid, xl in liquid.composition.items():
        yl = max(vapor.composition.get(cid, 0.0), 0.0)
        out[cid] = yl / xl if xl > 0.0 else 0.0
    return out


def _single_phase_object(
    flasher: Any, z: dict[str, float], T: float, P: float, kind: PhaseKind
) -> tuple[Any, tuple[str, ...], list[float], tuple[str, ...]]:
    """One phase object of the requested kind at (composition, T, P) — no flash."""
    ids = support_ids(z)
    zs = [float(z[cid]) for cid in ids]
    base = flasher.gas if kind == PhaseKind.VAPOR else flasher.liquids[0]
    phase = base.to(T=T, P=P, zs=zs)
    if getattr(base, "constants", None) is not None and not hasattr(phase, "constants"):
        # ``Phase.to`` copies HeatCapacityGases but not the component constants,
        # which MW() needs; flash-built phases always carry them.
        phase.constants = base.constants
    return phase, ids, zs, tuple(z.keys())


def phase_props(flasher: Any, z: dict[str, float], T: float, P: float, kind: PhaseKind) -> PhaseProps:
    """Properties of one phase at (composition, T, P), built without flashing."""
    phase, ids, zs, full_keys = _single_phase_object(flasher, z, T, P, kind)
    density = float(phase.rho_mass())
    mw = float(phase.MW())
    v_molar = (mw / 1000.0) / density  # m3/mol
    ln_phi = {cid: 0.0 for cid in full_keys}
    ln_phi.update(zip(ids, (float(v) for v in phase.lnphis()), strict=True))
    return PhaseProps(
        kind=kind,
        mole_fraction=1.0,
        composition=_composition(zs, ids, full_keys),
        molecular_weight=mw,
        density=density,
        enthalpy=float(phase.H()),
        entropy=float(phase.S()),
        cp=float(phase.Cp()),
        gibbs=float(phase.G()),
        z_factor=P * v_molar / (R_IDEAL * T),
        viscosity=_viscosity(phase),
        thermal_conductivity=_thermal_conductivity(phase),
        ln_phi=ln_phi,
    )


def derivatives(
    flasher: Any, z: dict[str, float], T: float, P: float, kind: PhaseKind
) -> PropertyDerivatives:
    """d ln phi / dT and d ln phi / dP per component, for one phase at (composition, T, P)."""
    phase, ids, _zs, full_keys = _single_phase_object(flasher, z, T, P, kind)
    dT = {cid: 0.0 for cid in full_keys}
    dP = {cid: 0.0 for cid in full_keys}
    dT.update(zip(ids, (float(v) for v in phase.dlnphis_dT()), strict=True))
    dP.update(zip(ids, (float(v) for v in phase.dlnphis_dP()), strict=True))
    return PropertyDerivatives(dlnphi_dT=dT, dlnphi_dP=dP)
