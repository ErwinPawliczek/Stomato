"""Preflash column, R2 (plan U-H 6, unit ``preflash``).

Plugin kind "unit", name "preflash", level R2. Ports ``feed_in`` ->
``vapor_out`` + ``liquid_out``, as R0. Where R0 is one flash drum at (T, P),
this level is a short rectifying column on the column row's MESH solvers
(Boston & Sullivan 1974; Naphtali & Sandholm 1971): the heated crude enters
the bottom stage, its flashed vapour rises through ``n_stages - 1`` trays and
a partial condenser on stage 1 returns reflux; the condenser's vapour is
``vapor_out`` and the bottom stage's liquid is ``liquid_out``. The one degree
of freedom is the vapour product rate (``distillate_rate_mol_s``), the
condenser duty its outcome.

The stage liquid is the pooled overall liquid (the column's ``pool_liquids``,
the MESH-with-overall-liquid formulation of Block & Hegner, AIChE J. 22 (1976)
582): on the PR package the crude slate's heaviest pseudos split off a second
liquid (measured on the example: 2.3 % of the feed, 3.0 % of the bottom-stage
liquid). A one-liquid stage there reports a bottoms whose flashed enthalpy
misses the stage balance by 1.2 kJ/mol - a 1.05 MW phantom reboiler duty on a
column without a reboiler; pooled, the boundary closure and the stage balances
agree (measured 0.2 W). R0 pools the drum's liquids into ``liquid_out`` the
same way. What makes the column converge at all is the condenser's
temperature band reaching below the feed (see the column's ``_build_column``):
the converged top stage sits ~150 K under the 505 K feed.

``duty_W`` is the column's net duty, the (negative) condenser duty; the
stream table closes on it. All SI: K, Pa abs, mol/s, J/mol, W.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.column import Column
from ngdesign.units.refining._cuts import RefiningSpecError

_ALLOWED_KEYS = frozenset({"n_stages", "distillate_rate_mol_s", "pressure_profile"})
#: Equal-percent pseudo cuts of the example slate (ids distinct from the
#: default slate's, so both register side by side).
_EXAMPLE_CUTS = 16


class PreflashR2:
    """Partial-condenser rectifier over the public column API."""

    inlet_ports: tuple[str, ...] = ("feed_in",)
    outlet_ports: tuple[str, ...] = ("vapor_out", "liquid_out")

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """The R0 example crude (the light crude at 505.37 K and 2.5 bar, Gary et
        al. p. 66) cut into 16 equal-percent pseudos (22 species with the light
        ends), through 5 stages with 150 of its 1000 mol/s taken as vapour.

        Coarser than R0's 48-species default slate on cost alone: with pooled
        liquids every stage K is a PT flash of the stage contents, and the
        package's flash of the saturated 48-species slate spends up to ~45 s
        in Michelsen stability tests (measured on the products); on this
        slate the whole solve takes ~13 s.
        """
        from ngdesign.data.assay import CutScheme
        from ngdesign.units.refining.assay_feeder import _EXAMPLE_ASSAY
        from ngdesign.units.refining.slate import assay_slate, register_slate

        scheme = CutScheme.equal_count(_EXAMPLE_CUTS)
        register_slate(_EXAMPLE_ASSAY, scheme)
        _, mole = assay_slate(_EXAMPLE_ASSAY, scheme)
        feeds = {"feed_in": {"T": 505.37, "P": 2.5e5, "molar_flow": 1000.0, "composition": dict(mole)}}
        return feeds, {"n_stages": 5, "distillate_rate_mol_s": 150.0}

    def solve(self, inlets: dict[str, StreamState], params: dict[str, Any], thermo: Thermo) -> UnitResult:
        feed = inlets.get("feed_in")
        if feed is None or feed.molar_flow <= 0.0:
            raise RefiningSpecError("feed_in: a crude inlet stream with positive flow is required")
        for key in params:
            if key not in _ALLOWED_KEYS:
                raise RefiningSpecError(f"preflash R2 refuses unknown parameter {key!r}")
        n_stages = params.get("n_stages")
        if not isinstance(n_stages, int) or isinstance(n_stages, bool) or n_stages < 2:
            raise RefiningSpecError(f"n_stages must be an integer >= 2, got {n_stages!r}")
        rate = params.get("distillate_rate_mol_s")
        if isinstance(rate, bool) or not isinstance(rate, (int, float)) or not 0.0 < rate < feed.molar_flow:
            raise RefiningSpecError(
                f"distillate_rate_mol_s must lie strictly between 0 and the feed flow "
                f"{feed.molar_flow} mol/s, got {rate!r}"
            )
        result = Column().solve(
            {"feed": feed},
            {
                "n_stages": n_stages,
                "condenser": "partial",
                "reboiler": "none",
                "feed_stage": n_stages,
                "pressure_profile": params.get("pressure_profile", feed.P),
                "specs": {"distillate_rate": float(rate)},
                "pool_liquids": True,
            },
            thermo,
        )
        vapour, liquid = result.outlets["distillate"], result.outlets["bottoms"]
        info = {key: value for key, value in result.info.items() if key.startswith("stage_")}
        info.update(
            n_stages=float(n_stages),
            ns_used=result.info["ns_used"],
            condenser_duty_W=result.info["condenser_duty_W"],
            vapor_mol_s=vapour.molar_flow,
            liquid_mol_s=liquid.molar_flow,
            vapor_frac=vapour.molar_flow / feed.molar_flow,
        )
        return UnitResult(
            outlets={"vapor_out": vapour, "liquid_out": liquid},
            duty_W=result.duty_W,
            power_W=0.0,
            info=info,
        )
