"""One cubic-EOS base; PR, SRK and PR78 become registrations (spec P0-04).

:class:`CubicEOS` implements the ``Thermo`` protocol (plugin kind "thermo")
over Caleb Bell's `thermo` library: a FlashVLN flasher with two liquid phases
(free water forms a separate aqueous phase), CEOSGas / CEOSLiquid phase
wrappers, and a Michelsen-style stability re-check for single-phase results.
It is parameterised by the `thermo`-library mixture EOS class (``PRMIX``,
``SRKMIX``, ``PR78MIX``) and the k_ij source used today — the embedded
'ChemSep PR' IPDB table, 0 where the table has no pair.

The flash surface, phase behaviour, stability logic and StreamState mapping are
unchanged; they live in ``ngdesign.thermo._state``. Pure refactor: no change in
tolerances, iteration caps, stability logic or phase labelling. SI units
throughout: K, Pa, kg/m3, Pa.s, J/mol, J/(mol K).
"""

from __future__ import annotations

from functools import cache
from typing import Any

from ngdesign.contracts import StreamState
from ngdesign.thermo import _state

#: The IPDB's fitted cubic-EOS kijs (no SRK/PR78-specific table exists in thermo).
_CHEMSEP_CUBIC_TABLE = "ChemSep PR"


class CubicEOS:
    """Cubic-EOS Thermo package; subclasses pin the EOS class as ``eos``."""

    #: `thermo`-library mixture EOS class (PRMIX, SRKMIX, PR78MIX).
    eos: Any

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
        ids = tuple(sorted(cid for cid, x in z.items() if x > 0.0))
        if not ids:
            raise ValueError("composition has no positive mole fractions")
        return _state.run_flash(_flasher_for(self.eos, _CHEMSEP_CUBIC_TABLE, ids), z, molar_flow, **spec)


@cache
def _flasher_for(eos: Any, kij_table: str, ids: tuple[str, ...]) -> Any:
    """Build (and cache) a FlashVLN flasher over exactly this sorted component set.

    Zero-fraction components are dropped by the caller before this is reached, so
    the cache key is the reduced, sorted support of the feed composition (plus the
    EOS class and k_ij table, which pin the package variant).
    """
    return _state.build_flasher(ids, eos, kij_table)
