"""Per-component stream splitting (spec U-A step 1).

The shared split physics behind `component_splitter` (U-A) and the U-D
separation units (hydrocyclone, filter, membrane): each component is sent to
the first outlet by its own fraction; components missing from the fraction map
go entirely to the second outlet. Each outlet is flashed at its own
``(outlet_T, outlet_P)``, which default to the inlet's T and P.

The caller reports the duty as ``sum(n*h) over outlets - n_in*h_in`` (J/s);
the helper returns the flashed pair so the identity is evaluated on the flash
enthalpies. Units consume the `Thermo` protocol only (plan §0 principle 3).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from ngdesign.contracts.stream import StreamState

if TYPE_CHECKING:
    from ngdesign.contracts.plugins import Thermo

#: Outlet-state spec: one value for both outlets, one per outlet ("top"/"bottom"),
#: or omitted (= the inlet's value).
OutletSpec = float | Mapping[str, float] | None


class SplittingError(ValueError):
    """Raised when a split request is ill-posed; the message names the input."""


def _per_outlet(spec: OutletSpec, fallback: float, key: str, what: str) -> float:
    """Resolve one outlet's T or P from a scalar, a per-outlet mapping, or None."""
    if spec is None:
        return fallback
    if isinstance(spec, Mapping):
        value = spec.get(key, fallback)
    else:
        value = spec
    value = float(value)
    if value <= 0.0:
        raise SplittingError(f"outlet {what} for '{key}' must be > 0, got {value}")
    return value


def split_by_component(
    state: StreamState,
    fractions: Mapping[str, float],
    thermo: Thermo,
    outlet_T: OutletSpec = None,
    outlet_P: OutletSpec = None,
) -> tuple[StreamState, StreamState]:
    """Split ``state`` into (top, bottom) by per-component fractions.

    ``fractions`` maps a component id to the fraction of its flow sent to the
    first (top) outlet; components missing from the map go entirely to the
    bottom outlet. Every fraction must lie in [0, 1] and name a component of
    the feed — anything else raises :class:`SplittingError` naming it (no
    silent clamping). Zero-flow outlets are assembled directly (the one
    hand-built `StreamState` the unit conventions allow).

    ``outlet_T``/``outlet_P`` flash each outlet at its own conditions: a
    scalar applies to both outlets, a mapping keys them as ``"top"`` and
    ``"bottom"``, and ``None`` keeps the inlet's value. Duty for the unit
    result: ``sum(n*h) out - n_in*h_in``.
    """
    for cid, f in fractions.items():
        if cid not in state.composition:
            raise SplittingError(f"fraction for {cid!r}: component is not in the feed")
        if not 0.0 <= f <= 1.0:
            raise SplittingError(f"fraction for {cid!r} is {f}, outside [0, 1]")

    n_in = state.molar_flow
    n_top = sum(state.composition[cid] * n_in * float(f) for cid, f in fractions.items())
    n_bottom = n_in - n_top

    top_T = _per_outlet(outlet_T, state.T, "top", "T")
    bottom_T = _per_outlet(outlet_T, state.T, "bottom", "T")
    top_P = _per_outlet(outlet_P, state.P, "top", "P")
    bottom_P = _per_outlet(outlet_P, state.P, "bottom", "P")

    top: StreamState
    bottom: StreamState
    if n_top <= 0.0:
        top = state.model_copy(update={"molar_flow": 0.0, "composition": dict(state.composition)})
    else:
        z_top = {
            cid: state.composition[cid] * float(fractions.get(cid, 0.0)) * n_in / n_top
            for cid in state.composition
        }
        top = thermo.flash_pt(z_top, top_T, top_P, n_top)
    if n_bottom <= 0.0:
        bottom = state.model_copy(update={"molar_flow": 0.0, "composition": dict(state.composition)})
    else:
        z_bottom = {
            cid: state.composition[cid] * (1.0 - float(fractions.get(cid, 0.0))) * n_in / n_bottom
            for cid in state.composition
        }
        bottom = thermo.flash_pt(z_bottom, bottom_T, bottom_P, n_bottom)
    return top, bottom
