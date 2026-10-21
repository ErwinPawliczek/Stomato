"""One cubic-EOS base; PR, SRK and PR78 become registrations (spec P0-04).

:class:`CubicEOS` implements the ``Thermo`` protocol (plugin kind "thermo")
over Caleb Bell's `thermo` library: a FlashVLN flasher with two liquid phases
(free water forms a separate aqueous phase), CEOSGas / CEOSLiquid phase
wrappers, and a Michelsen-style stability re-check for single-phase results.
It is parameterised by the `thermo`-library mixture EOS class (``PRMIX``,
``SRKMIX``, ``PR78MIX``) and the k_ij source used today — the embedded
'ChemSep PR' IPDB table, 0 where the table has no pair. Component ids resolve
through the open component registry (spec P1-02): constants build in
:mod:`ngdesign.thermo._state` from the resolved Component records, so any
curated id, databank CAS/name or registered pseudo-components flash here.

The contract-v2 surface (flashes, saturation, K-values, single-phase
properties, derivatives, property cache) lives in
:class:`ThermoSurfaceMixin` (spec P1-01) and is shared with the NRTL package.
SI units throughout: K, Pa, kg/m3, Pa.s, J/mol, J/(mol K).
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from functools import cache
from typing import Any, cast

from ngdesign.contracts import StreamState
from ngdesign.contracts.components import ComponentSet, data_definitions
from ngdesign.contracts.thermo import PhaseProps, PropertyDerivatives, SaturationPoint
from ngdesign.data import PseudoDefinition as DataPseudoDefinition
from ngdesign.thermo import _state

#: The IPDB's fitted cubic-EOS kijs (no SRK/PR78-specific table exists in thermo).
_CHEMSEP_CUBIC_TABLE = "ChemSep PR"


class ThermoSurfaceMixin:
    """The Thermo-protocol v2 surface shared by every property package (spec P1-01).

    Implements the flashes, saturation points, K-values, single-phase
    properties, derivatives and the property cache on top of two
    package-provided flasher factories: ``_build_flasher`` (the full three-phase
    FlashVLN flasher) and ``_build_flasher_vl`` (the FlashVL fast path the
    saturation solvers use when the feed cannot form a second liquid).

    The cache is a per-instance LRU of PROPERTY_CACHE_SIZE entries keyed on
    (tag, composition rounded to 1e-10, T to 1e-6, P to 1e-3) for PT flashes and
    phase_props; molar_flow is part of the PT-flash key because StreamState
    carries it. StreamState and Phase are frozen models, so a cached object
    can be handed to every caller without copying.
    """

    def __init__(self) -> None:
        self._lru_cache: OrderedDict[tuple[Any, ...], Any] = OrderedDict()
        # The solving slate's flowsheet-owned pseudo definitions (spec P1-07),
        # set once per solve through set_component_set. Empty = no flowsheet
        # context: pseudo ids resolve through the module register_pseudo default.
        self._slate_pseudos: tuple[DataPseudoDefinition, ...] = ()
        super().__init__()

    def set_component_set(self, cs: ComponentSet) -> None:
        """Receive the slate resolved once at solve entry (spec P1-07).

        The solver hands over the ComponentSet it built from
        ``Flowsheet.components``; flasher and Psat constants for
        flowsheet-owned pseudo-components then build from the flowsheet's own
        definitions, never from the module-level register_pseudo default. The
        solver calls this once per solve, before any flash.
        """
        self._slate_pseudos = data_definitions(cs.pseudo_definitions)

    def _build_flasher(self, ids: tuple[str, ...]) -> Any:
        """The package's full FlashVLN flasher over this sorted component support."""
        raise NotImplementedError

    def _build_flasher_vl(self, ids: tuple[str, ...]) -> Any:
        """The package's two-phase FlashVL flasher over this sorted component support."""
        raise NotImplementedError

    def _flasher(self, z: dict[str, float]) -> Any:
        return self._build_flasher(_state.support_ids(z))

    def _sat_flasher(self, ids: tuple[str, ...]) -> Any:
        """FlashVL fast path when no second liquid can exist (no water in the feed)."""
        if _state.WATER_ID in ids:
            return self._build_flasher(ids)
        return self._build_flasher_vl(ids)

    def _cached(self, key: tuple[Any, ...], compute: Callable[[], Any]) -> Any:
        # The slate's flowsheet-owned pseudo definitions (spec P1-07) scope every
        # per-instance result cache entry: pseudo constants change with the
        # solving slate, so a cached flash or phase-prop result from one
        # flowsheet must never satisfy another's request for the same (z, T, P).
        cache = self._lru_cache
        key = (self._slate_pseudos, *key)
        hit = cache.get(key)
        if hit is not None:
            cache.move_to_end(key)
            return hit
        value = compute()
        cache[key] = value
        while len(cache) > _state.PROPERTY_CACHE_SIZE:
            cache.popitem(last=False)
        return value

    # -- flashes ------------------------------------------------------------

    def flash_pt(self, z: dict[str, float], T: float, P: float, molar_flow: float) -> StreamState:
        """PT flash: full phase split at temperature T (K) and pressure P (Pa abs)."""
        key = ("pt", *_state.cache_key(z, T, P), round(molar_flow, 9))
        return cast(
            StreamState,
            self._cached(key, lambda: _state.run_flash(self._flasher(z), z, molar_flow, T=T, P=P)),
        )

    def flash_ph(self, z: dict[str, float], P: float, H: float, molar_flow: float) -> StreamState:
        """PH flash: solve T from pressure P (Pa abs) and enthalpy H (J/mol)."""
        return _state.run_flash(self._flasher(z), z, molar_flow, P=P, H=H)

    def flash_ps(self, z: dict[str, float], P: float, S: float, molar_flow: float) -> StreamState:
        """PS flash: solve T from pressure P (Pa abs) and entropy S (J/(mol K))."""
        return _state.run_flash(self._flasher(z), z, molar_flow, P=P, S=S)

    def flash_tvf(self, z: dict[str, float], T: float, vf: float, molar_flow: float) -> StreamState:
        """TVF flash: vapour fraction vf in [0, 1] at temperature T (K)."""
        return _state.flash_tvf(self, z, T, vf, molar_flow)

    def flash_pvf(self, z: dict[str, float], P: float, vf: float, molar_flow: float) -> StreamState:
        """PVF flash: vapour fraction vf in [0, 1] at pressure P (Pa abs)."""
        return _state.flash_pvf(self, z, P, vf, molar_flow)

    # -- saturation ----------------------------------------------------------

    def bubble_point(
        self, z: dict[str, float], *, T: float | None = None, P: float | None = None
    ) -> SaturationPoint:
        """Bubble point; exactly one of T (K) and P (Pa) given."""
        return _state.bubble_point(
            self._sat_flasher(_state.support_ids(z)), z, T=T, P=P, pseudos=self._slate_pseudos
        )

    def dew_point(
        self, z: dict[str, float], *, T: float | None = None, P: float | None = None
    ) -> SaturationPoint:
        """Dew point; exactly one of T (K) and P (Pa) given."""
        return _state.dew_point(
            self._sat_flasher(_state.support_ids(z)), z, T=T, P=P, pseudos=self._slate_pseudos
        )

    def pure_psat(self, cid: str, T: float) -> float | None:
        """Pure-component vapour pressure (Pa) at T (K); None at or above Tc."""
        return _state.pure_psat(cid, T, self._slate_pseudos)

    # -- properties -----------------------------------------------------------

    def k_values(self, z: dict[str, float], T: float, P: float) -> dict[str, float] | None:
        """K_i = y_i/x_i from a PT flash; None when single-phase."""
        return _state.k_values(self._flasher(z), z, T, P)

    def phase_props(self, composition: dict[str, float], T: float, P: float, kind: Any) -> PhaseProps:
        """Single-phase properties at (composition, T, P) — no flash."""
        key = ("pp", str(kind), *_state.cache_key(composition, T, P))
        return cast(
            PhaseProps,
            self._cached(
                key, lambda: _state.phase_props(self._flasher(composition), composition, T, P, kind)
            ),
        )

    def derivatives(
        self, composition: dict[str, float], T: float, P: float, kind: Any
    ) -> PropertyDerivatives:
        """d ln phi / dT and d ln phi / dP per component, for one phase."""
        return _state.derivatives(self._flasher(composition), composition, T, P, kind)


class CubicEOS(ThermoSurfaceMixin):
    """Cubic-EOS Thermo package; subclasses pin the EOS class as ``eos``."""

    #: `thermo`-library mixture EOS class (PRMIX, SRKMIX, PR78MIX).
    eos: Any

    def _build_flasher(self, ids: tuple[str, ...]) -> Any:
        return _flasher_for(self.eos, _CHEMSEP_CUBIC_TABLE, ids, self._slate_pseudos)

    def _build_flasher_vl(self, ids: tuple[str, ...]) -> Any:
        return _flasher_vl_for(self.eos, _CHEMSEP_CUBIC_TABLE, ids, self._slate_pseudos)


@cache
def _flasher_for(
    eos: Any, kij_table: str, ids: tuple[str, ...], pseudos: tuple[DataPseudoDefinition, ...] = ()
) -> Any:
    """Build (and cache) a FlashVLN flasher over exactly this sorted component set.

    Zero-fraction components are dropped by the caller before this is reached, so
    the cache key is the reduced, sorted support of the feed composition (plus the
    EOS class and k_ij table, which pin the package variant, plus the slate's
    flowsheet-owned pseudo definitions - spec P1-07: two flowsheets with
    different definitions of the same pseudo id never share a flasher).
    """
    return _state.build_flasher(ids, eos, kij_table, pseudos)


@cache
def _flasher_vl_for(
    eos: Any, kij_table: str, ids: tuple[str, ...], pseudos: tuple[DataPseudoDefinition, ...] = ()
) -> Any:
    """Build (and cache) the two-phase FlashVL saturation fast path (spec P1-01).

    Cache key carries the slate's flowsheet-owned pseudo definitions (spec P1-07).
    """
    return _state.build_flasher_vl(ids, eos, kij_table, pseudos)
