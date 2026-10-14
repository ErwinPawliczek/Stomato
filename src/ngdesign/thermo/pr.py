"""Peng-Robinson thermo package (spec S-01). Plugin kind "thermo", name "pr".

Wraps Caleb Bell's `thermo` library:
- Peng-Robinson cubic EOS (Peng & Robinson 1976, "A New Equation of State and Its
  Application to Binary Mixtures", Ind. Eng. Chem. Fundam. 15(1), 59-64) via PRMIX,
- CEOSGas / CEOSLiquid phase wrappers (never raw PRMIX objects),
- FlashVLN with two liquid phases so free water forms a separate aqueous phase,
- binary interaction parameters kijs from the embedded 'ChemSep PR' table
  (thermo.interaction_parameters.IPDB), 0 where the table has no pair.

Component ids map to CAS via ngdesign.data.components() (C6+ = n-hexane per the
reference-data note). SI units throughout: K, Pa, kg/m3, Pa.s, J/mol, J/(mol K).
"""

from __future__ import annotations

from functools import cache
from typing import Any

from thermo import PRMIX, CEOSGas, CEOSLiquid, ChemicalConstantsPackage, FlashVLN
from thermo.interaction_parameters import IPDB

from ngdesign.contracts import Phase, PhaseKind, StreamState
from ngdesign.data import components
from ngdesign.registry import register

#: CODATA 2018 molar gas constant, J/(mol.K).
R_IDEAL = 8.31446261815324

#: A liquid phase is the aqueous phase when its water mole fraction exceeds this.
AQUEOUS_WATER_FRACTION = 0.5

_CHEMSEP_PR_TABLE = "ChemSep PR"

_KIND_ORDER = (PhaseKind.VAPOR, PhaseKind.HC_LIQUID, PhaseKind.AQUEOUS)

# (phase object, phase mole fraction) as carried through state construction.
PhasePair = tuple[Any, float]


def _cas_list(ids: tuple[str, ...]) -> list[str]:
    """CAS numbers for component ids, in the given (sorted) order."""
    comps = components()
    return [str(comps[cid]["cas"]) for cid in ids]


@cache
def _flasher_for(ids: tuple[str, ...]) -> Any:
    """Build (and cache) a FlashVLN flasher over exactly this sorted component set.

    Zero-fraction components are dropped by the caller before this is reached, so
    the cache key is the reduced, sorted support of the feed composition.
    """
    cas_list = _cas_list(ids)
    constants, correlations = ChemicalConstantsPackage.from_IDs(cas_list)
    kijs = IPDB.get_ip_symmetric_matrix(name=_CHEMSEP_PR_TABLE, CASs=cas_list, ip="kij")
    eos_kwargs: dict[str, Any] = {
        "Tcs": constants.Tcs,
        "Pcs": constants.Pcs,
        "omegas": constants.omegas,
        "kijs": kijs,
    }
    heat_caps = correlations.HeatCapacityGases
    gas = CEOSGas(PRMIX, eos_kwargs, HeatCapacityGases=heat_caps)
    liquids = [
        CEOSLiquid(PRMIX, eos_kwargs, HeatCapacityGases=heat_caps),
        CEOSLiquid(PRMIX, eos_kwargs, HeatCapacityGases=heat_caps),
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


@register("thermo", "pr")
class PengRobinsonThermo:
    """Peng-Robinson package over the `thermo` library (spec S-01)."""

    def flash_pt(self, z: dict[str, float], T: float, P: float, molar_flow: float) -> StreamState:
        """PT flash: full phase split at temperature T (K) and pressure P (Pa abs)."""
        return self._flash(z, molar_flow, T=T, P=P)

    def flash_ph(self, z: dict[str, float], P: float, H: float, molar_flow: float) -> StreamState:
        """PH flash: solve T from pressure P (Pa abs) and enthalpy H (J/mol)."""
        return self._flash(z, molar_flow, P=P, H=H)

    def flash_ps(self, z: dict[str, float], P: float, S: float, molar_flow: float) -> StreamState:
        """PS flash: solve T from pressure P (Pa abs) and entropy S (J/(mol.K))."""
        return self._flash(z, molar_flow, P=P, S=S)

    def _flash(self, z: dict[str, float], molar_flow: float, **spec: float) -> StreamState:
        """Drop zero-fraction components, flash, and map the result back.

        Phase count is taken from the flash result's actually-present phases
        (FlashVLN may return fewer phases than a case "should" have); a single-phase
        result is re-verified by stability test in _stability_resolved, and
        classification happens per phase in _build_stream_state.
        """
        ids = tuple(sorted(cid for cid, x in z.items() if x > 0.0))
        if not ids:
            raise ValueError("composition has no positive mole fractions")
        flasher = _flasher_for(ids)
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
