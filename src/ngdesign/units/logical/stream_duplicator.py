"""Stream duplicator unit plugin (spec U-A).

N outlets (``n_copies``, default 2), each an identical copy of the inlet.

**This breaks mole balance by design.** At R0 the copies are *reference
streams*: outlet ``copy_0`` carries the material, and copies ``1..N-1`` carry
the same intensive state with ``molar_flow`` scaled by ``params.
copy_flow_scale`` (default 0.0, so the balance closes). The full-flow mirror
form — every copy carrying the full inlet flow — is refused at R0 unless
``allow_unbalanced: true``, which V0 never uses.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo


class StreamDuplicator:
    """Tees a stream into N identical copies (spec U-A)."""

    inlet_ports = ("inlet",)
    outlet_ports = ("copy_0", "copy_1")

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        del thermo  # copies share the inlet state; no flash
        inlet = inlets["inlet"]
        n_copies = int(params.get("n_copies", 2))
        if n_copies < 2:
            raise ValueError(f"n_copies must be >= 2, got {n_copies}")
        copy_scale = float(params.get("copy_flow_scale", 0.0))
        if copy_scale < 0.0:
            raise ValueError(f"copy_flow_scale must be >= 0, got {copy_scale}")
        if copy_scale > 0.0 and not params.get("allow_unbalanced", False):
            raise ValueError(
                "copy_flow_scale > 0 makes the copies carry material and breaks the "
                "mole balance; pass allow_unbalanced: true to permit the full-flow "
                "mirror form (V0 never uses it)"
            )

        outlets: dict[str, StreamState] = {"copy_0": inlet.model_copy()}
        for i in range(1, n_copies):
            outlets[f"copy_{i}"] = inlet.model_copy(
                update={"molar_flow": inlet.molar_flow * copy_scale, "composition": dict(inlet.composition)}
            )
        return UnitResult(outlets=outlets, duty_W=0.0, power_W=0.0, info={})

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Tee the dry-gas example into two reference copies."""
        from ngdesign.units.jt_valve import dry_gas_feed

        return {"inlet": dry_gas_feed(322.15, 7.0e6)}, {}
