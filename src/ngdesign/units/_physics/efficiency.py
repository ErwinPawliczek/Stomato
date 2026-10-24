"""Shared isentropic step physics (spec U-B).

One owner for the isentropic-stage arithmetic that several flow units repeat:
a PS flash for the isentropic outlet, then a PH flash at the
efficiency-corrected enthalpy. The existing ``compressor``/``expander``
adapters keep their own inlined copies this round (spec: migrating them is a
later byte-identical refactor); new U-B units call this module.

Sign convention follows :class:`UnitResult`: ``power_W`` is shaft power *into*
the process, positive for a compression step, negative for an expansion step.
"""

from __future__ import annotations

from typing import Literal

from ngdesign.contracts import StreamState
from ngdesign.contracts.plugins import Thermo

#: Compression expands pressure; expansion lowers it. Any other mode is a bug.
Mode = Literal["compress", "expand"]


def isentropic_step(
    state: StreamState,
    P_out: float,
    eta: float,
    thermo: Thermo,
    mode: Mode = "compress",
) -> tuple[StreamState, float]:
    """One isentropic-efficiency stage from ``state`` to ``P_out``.

    The isentropic outlet comes from a PS flash at the inlet entropy; the
    actual outlet enthalpy is

    - ``compress``: ``h_out = h_in + (h_is - h_in) / eta`` (only ``eta`` of the
      isentropic work is useful, so the machine must supply more);
    - ``expand``: ``h_out = h_in - eta * (h_in - h_is)`` (only ``eta`` of the
      isentropic drop is recovered).

    The outlet state is a PH flash at that enthalpy. Returns
    ``(outlet, power_W)`` with ``power_W = F * (h_out - h_in)`` — positive into
    the process for ``compress``, negative (recovered) for ``expand``.
    """
    if mode not in ("compress", "expand"):
        raise ValueError(f"mode {mode!r} must be 'compress' or 'expand'")
    if not 0.0 < eta <= 1.0:
        raise ValueError(f"eta {eta} outside (0, 1]")
    if P_out <= 0:
        raise ValueError(f"P_out {P_out} Pa must be > 0")
    if mode == "compress" and P_out <= state.P:
        raise ValueError(f"P_out {P_out} Pa must exceed the inlet pressure {state.P} Pa in compress mode")
    if mode == "expand" and P_out >= state.P:
        raise ValueError(f"P_out {P_out} Pa must be below the inlet pressure {state.P} Pa in expand mode")

    z, flow = state.composition, state.molar_flow
    isentropic = thermo.flash_ps(z, P_out, state.entropy, flow)
    if mode == "compress":
        h_out = state.enthalpy + (isentropic.enthalpy - state.enthalpy) / eta
    else:
        h_out = state.enthalpy - eta * (state.enthalpy - isentropic.enthalpy)
    outlet = thermo.flash_ph(z, P_out, h_out, flow)
    return outlet, flow * (outlet.enthalpy - state.enthalpy)
