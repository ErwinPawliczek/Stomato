"""Stream duplicator unit plugin (spec U-A).

N outlets (``n_copies``, default 2), each an identical copy of the inlet.

**This breaks mole balance by design.** At R0 the copies are *reference
streams*: outlet ``outlet_1`` carries the material, and ``outlet_2`` carries
the same intensive state with ``molar_flow`` scaled by ``params.
copy_flow_scale`` (default 0.0, so the balance closes). The full-flow mirror
form — every copy carrying the full inlet flow — is refused at R0 unless
``allow_unbalanced: true``, which V0 never uses. The port names are the
catalogue row's (``outlet_1``/``outlet_2``), so a sheet wired from the palette
always connects ports the adapter produces; ``n_copies`` other than 2 is
refused for the same reason.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo


class StreamDuplicator:
    """Tees a stream into N identical copies (spec U-A)."""

    inlet_ports = ("inlet",)
    outlet_ports = ("outlet_1", "outlet_2")

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        del thermo  # copies share the inlet state; no flash
        inlet = inlets["inlet"]
        n_copies = int(params.get("n_copies", 2))
        if n_copies != 2:
            raise ValueError(
                f"n_copies must be 2 at R0: the catalogue row declares exactly two "
                f"outlets (outlet_1, outlet_2), got {n_copies}"
            )
        copy_scale = float(params.get("copy_flow_scale", 0.0))
        if copy_scale < 0.0:
            raise ValueError(f"copy_flow_scale must be >= 0, got {copy_scale}")
        if copy_scale > 0.0 and not params.get("allow_unbalanced", False):
            raise ValueError(
                "copy_flow_scale > 0 makes the copies carry material and breaks the "
                "mole balance; pass allow_unbalanced: true to permit the full-flow "
                "mirror form (V0 never uses it)"
            )

        outlets: dict[str, StreamState] = {"outlet_1": inlet.model_copy()}
        outlets["outlet_2"] = inlet.model_copy(
            update={"molar_flow": inlet.molar_flow * copy_scale, "composition": dict(inlet.composition)}
        )
        return UnitResult(outlets=outlets, duty_W=0.0, power_W=0.0, info={})

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Tee the dry-gas example into two reference copies."""
        from ngdesign.units.jt_valve import dry_gas_feed

        return {"inlet": dry_gas_feed(322.15, 7.0e6)}, {}
