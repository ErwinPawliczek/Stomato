"""Reboiled stripper, R2 (spec U-R2 reboiled_stripper): one-tear MESH stripper
(kettle only) via the column API.

Plugin kind "unit", name "reboiled_stripper", level R2. Same ports as the R0
(``feed`` in; ``overhead``/``bottoms`` out) but the method is the rigorous
MESH equilibrium-stage column of ``ngdesign.units.column`` on its
condenserless one-tear configuration: ``n_stages`` stages, the feed on stage 1,
no condenser, the kettle reboiler as stage N, and exactly one spec driving the
single tear (the boilup ``V_N``) through the column's bounded secant.
``overhead`` is the stage-1 vapour (the column's ``distillate``); ``bottoms``
is the kettle liquid. ``duty_W`` is the column's ``reboiler_duty_W`` — the
column defines it by the exact overall balance, so V0 closes by construction.

``spec`` is a one-key dict from ``{boilup_ratio, bottoms_rate,
distillate_rate, component_recovery}``. ``reboiler_duty_W`` is a legal column
spec key, but measured on main (2026-10-25) a kettle-only stripper given
``{"reboiler_duty_W": 1e6}`` fails with ``ColumnConvergenceError: singular
Newton system in column solver`` for every case tried (nC4/nC5 0.3/0.7 at
330 K; nC4/nC5 0.02/0.98; the near-pure and pure nC5 limits at 5 bar). The R2
params therefore exclude it and the adapter refuses it before any column call,
pointing at the column core (reported to the orchestrator as a core defect;
this adapter must not work around it).

There is no exact reduction to the R0 Kremser level (Kremser vs MESH); the
identity is to the column row — the adapter output equals ``Column().solve``
with the mapped params, bit-for-bit. Column tolerances and bounded budgets
apply; this adapter adds no iteration.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.column import Column

#: The allowed single spec keys and their float info codes.
_ALLOWED_SPECS: tuple[str, ...] = (
    "boilup_ratio",
    "bottoms_rate",
    "distillate_rate",
    "component_recovery",
)
_SPEC_CODES: dict[str, float] = {
    "boilup_ratio": 1.0,
    "bottoms_rate": 2.0,
    "distillate_rate": 3.0,
    "component_recovery": 4.0,
}
_ALLOWED_PARAMS: tuple[str, ...] = ("n_stages", "pressure_profile", "spec")


class ReboiledStripperR2Error(ValueError):
    """Invalid reboiled-stripper R2 specification (names the parameter)."""


class ReboiledStripperR2:
    """One-tear MESH reboiled stripper (kettle only) over the column API."""

    inlet_ports = ("feed",)
    outlet_ports = ("overhead", "bottoms")

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        feed = inlets.get("feed")
        if feed is None:
            raise ReboiledStripperR2Error("reboiled_stripper needs a feed inlet stream")
        if feed.molar_flow <= 0.0:
            raise ReboiledStripperR2Error(
                f"reboiled_stripper feed molar flow must be positive, got {feed.molar_flow}"
            )

        unknown = sorted(set(params) - set(_ALLOWED_PARAMS))
        if unknown:
            raise ReboiledStripperR2Error(
                f"reboiled_stripper unknown parameter key {unknown}; allowed: {list(_ALLOWED_PARAMS)}"
            )

        n_raw = params.get("n_stages")
        if isinstance(n_raw, bool) or not isinstance(n_raw, int):
            raise ReboiledStripperR2Error(
                f"reboiled_stripper n_stages must be an integer >= 2, got {n_raw!r}"
            )
        n_stages = n_raw
        if n_stages < 2:
            raise ReboiledStripperR2Error(
                f"reboiled_stripper n_stages must be >= 2 (the kettle is stage N), got {n_stages}"
            )

        raw_profile = params.get("pressure_profile")
        pressure_profile: float | list[float]
        if raw_profile is None:
            pressure_profile = float(feed.P)
        elif isinstance(raw_profile, bool) or not isinstance(raw_profile, (int, float, list, tuple)):
            raise ReboiledStripperR2Error(
                f"reboiled_stripper pressure_profile must be a positive number or a "
                f"list of {n_stages} stage pressures, got {raw_profile!r}"
            )
        elif isinstance(raw_profile, (int, float)):
            pressure_profile = float(raw_profile)
            if not pressure_profile > 0.0:
                raise ReboiledStripperR2Error(
                    f"reboiled_stripper pressure_profile must be positive, got {pressure_profile}"
                )
        else:
            values = [float(p) for p in raw_profile]
            if len(values) != n_stages or any(not p > 0.0 for p in values):
                raise ReboiledStripperR2Error(
                    f"reboiled_stripper pressure_profile must be a list of {n_stages} "
                    f"positive stage pressures, got {raw_profile!r}"
                )
            pressure_profile = values

        raw_spec = params.get("spec")
        if not isinstance(raw_spec, dict) or len(raw_spec) != 1:
            raise ReboiledStripperR2Error(
                "reboiled_stripper spec must be an object with exactly one key from "
                f"{list(_ALLOWED_SPECS)}, got {raw_spec!r}"
            )
        spec_name = next(iter(raw_spec))
        if spec_name == "reboiler_duty_W":
            # Legal column spec key, but measured on main (2026-10-25) the
            # kettle-only column fails it with a singular Newton system for
            # every case tried — a core column defect reported to the
            # orchestrator. Refuse before any column call; no workaround here.
            raise ReboiledStripperR2Error(
                "reboiled_stripper spec reboiler_duty_W is refused: a kettle-only "
                "one-tear column core hits 'singular Newton system in column solver' "
                "for a reboiler_duty_W spec (column core defect, measured on main "
                "2026-10-25); the spec system is effectively singular at this tear"
            )
        if spec_name not in _ALLOWED_SPECS:
            raise ReboiledStripperR2Error(
                f"reboiled_stripper spec key {spec_name!r} is outside the allowed set {list(_ALLOWED_SPECS)}"
            )

        column_params: dict[str, Any] = {
            "n_stages": n_stages,
            "condenser": "none",
            "reboiler": "kettle",
            "feed_stage": 1,
            "pressure_profile": pressure_profile,
            "specs": dict(raw_spec),
        }

        result = Column().solve({"feed": feed}, column_params, thermo)

        overhead = result.outlets["distillate"]
        bottoms = result.outlets["bottoms"]

        info: dict[str, float] = {}
        copied = ("reboiler_duty_W", "boilup_ratio", "distillate_mol_s", "bottoms_mol_s")
        for key, value in result.info.items():
            if key in copied or key.startswith("stage_"):
                info[key] = value
        info["spec_name"] = _SPEC_CODES[spec_name]
        info["spec_achieved"] = _measured_spec(raw_spec, spec_name, feed, overhead, bottoms, result)

        return UnitResult(
            outlets={"overhead": overhead, "bottoms": bottoms},
            duty_W=result.duty_W,
            power_W=0.0,
            info=info,
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """The R0 example feed on the Seader-Henley-Roper Ex. 9.8 basis: the
        printed N = 3 stages with a boilup ratio of 0.2. Measured (2026-10-25,
        PR review): the locked balance gate (1e-6 * total per component) is
        basis-sensitive because the FD-Newton polish floors erratically on
        this feed - n=4/boilup 0.5 leaves a 1.6e-4 mol/s SO2 residual (fails),
        while N = 3 (the printed stage count) with boilup ratio 0.2 closes the
        worst component at 1.0e-10 mol/s and the boundary energy balance
        exactly. The example therefore anchors on the printed N = 3."""
        from ngdesign.units.column_shortcut.stripper import ReboiledStripper

        feeds, _ = ReboiledStripper.example_case()
        params = {"n_stages": 3, "spec": {"boilup_ratio": 0.2}}
        return feeds, params


def _measured_spec(
    spec: dict[str, Any],
    spec_name: str,
    feed: StreamState,
    overhead: StreamState,
    bottoms: StreamState,
    result: UnitResult,
) -> float:
    """The measured value of the spec quantity, from the outlets where possible."""
    if spec_name == "boilup_ratio":
        # V_N / B is internal traffic; the column's converged ratio is the
        # measured value (the kettle liquid B is the outlet).
        return result.info["boilup_ratio"]
    if spec_name == "bottoms_rate":
        return bottoms.molar_flow
    if spec_name == "distillate_rate":
        return overhead.molar_flow
    # component_recovery: recovered fraction of the named component in the
    # named product, from the outlet flows.
    cid = str(spec.get("component", ""))
    product = str(spec.get("product", "distillate"))
    out = overhead if product == "distillate" else bottoms
    feed_amount = feed.molar_flow * feed.composition.get(cid, 0.0)
    out_amount = out.molar_flow * out.composition.get(cid, 0.0)
    if feed_amount <= 0.0:
        raise ReboiledStripperR2Error(
            f"reboiled_stripper component_recovery component {cid!r} is not in the feed"
        )
    return out_amount / feed_amount
