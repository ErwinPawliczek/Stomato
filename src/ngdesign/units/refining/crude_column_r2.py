"""Atmospheric crude column, R2 (plan U-H 3, unit ``crude_column``).

Plugin kind "unit", name "crude_column", level R2. Ports as R0: ``crude_in``
and ``stripping_steam`` -> ``overhead`` + ``kero_out`` + ``diesel_out`` +
``ago_out`` + ``bottoms``. Where R0 splits the crude at sharp TBP cut points,
this level solves every stage of the main column and of its three steam side
strippers as one MESH system on the column row's stage graph (Russell 1983,
"A flexible and reliable method solves single-tower and crude-distillation-
column problems", Comput. Chem. Eng. 7, 571; Naphtali & Sandholm 1971):

- the heated crude enters the flash-zone stage ``feed_stage``; the stage-1
  partial condenser's vapour is ``overhead`` (its one degree of freedom is
  the overhead rate ``distillate_rate_mol_s``, the condenser duty its
  outcome); the bottom stage's liquid is ``bottoms``;
- each side product (kerosene, diesel, AGO) is the bottoms of a steam side
  stripper: liquid drawn from ``draw_stage``, stripped over ``n_stages``
  stages by ``steam_mol_s`` of the stripping steam, vapour returned to
  ``return_stage``; its product rate fixes the stripper (the draw is its
  outcome);
- the ``stripping_steam`` inlet is the steam header: each stripper takes its
  ``steam_mol_s`` of it at the header state, the rest enters under the
  bottom stage. The steam must be pure water (H2O);
- the overflash - the liquid falling from the stage above the flash zone
  into it, the vaporisation in excess of the products above the feed - is
  reported (``overflash_mol_s`` and its fraction of the crude feed), an
  outcome of the specs.

The stage liquid is the pooled overall liquid (the column's ``pool_liquids``;
Block & Hegner, AIChE J. 22 (1976) 582): on the PR package the crude slate's
heaviest pseudos split off a second liquid on the flash-zone and bottom
stages (measured on the example: 9 % of the flash-zone liquid). A one-liquid
stage there misses the stage balance by tens of kilowatts, reported as a
reboiler duty on a column without a reboiler; pooled, the stage K and
liquid enthalpy are the pooled liquid's own split (``_ThermoBox.k_pooled``)
and the boundary closure agrees with the stage balances. The column
cold-starts by relaxation (``initialization: relaxation``; Rose, Sweeny &
Schrodt 1958; Ketchum 1979).

Optional ``pumparounds`` are the column core's fixed loops (spec S0-1:
``name``, ``draw_stage``, ``return_stage`` at or above it, ``flow_mol_s``,
and one of ``return_T_K`` / ``duty_W``), drawn above the flash zone. Their
cooler duties enter the return stages' energy balances and take heat the
condenser would otherwise remove; each is reported as ``pa_<name>_*``. A
zero-flow loop is an exact no-op.

The overhead is bounded by the flash zone: with no reboiler, the products
above it are crude vaporised by the feed's heat and the bottom steam, and
an overhead past the zero-overflash point is refused (``_check_overflash``)
before the column solve. Measured on the example: overflash 31.8 mol/s at
430 mol/s overhead, 14.2 at 440, 5.93 at 445, zero at 448.72; the former "stall" at
>= 455 mol/s was this physical limit (the solve hunted for a column with
negative overflash, then failed inside the thermo).

``duty_W`` is the column's net duty: the (negative) condenser duty plus the
pumparound coolers'; the stream table closes on it. All SI: K, Pa abs,
mol/s, J/mol, W.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.column import ColumnConvergenceError, solve_column_full
from ngdesign.units.column.spec import _parse_pressure_profile, _parse_pumparounds
from ngdesign.units.refining._cuts import RefiningSpecError

#: Side-product ports, top to bottom, and the stripper name each carries in
#: the column's info keys.
_SIDE_PORTS = {"kero_out": "kero", "diesel_out": "diesel", "ago_out": "ago"}
_ALLOWED_KEYS = frozenset(
    {"n_stages", "feed_stage", "distillate_rate_mol_s", "strippers", "pressure_profile", "pumparounds"}
)
_STRIPPER_KEYS = frozenset({"draw_stage", "return_stage", "n_stages", "steam_mol_s", "product_rate_mol_s"})
#: Water mole fraction the steam header must carry (pure water).
_STEAM_PURITY = 1.0 - 1e-9
#: Equal-percent pseudo cuts of the example slate (preflash R2's slate).
_EXAMPLE_CUTS = 16


def _number(raw: object, name: str, *, positive: bool) -> float:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise RefiningSpecError(f"{name} must be a number, got {raw!r}")
    value = float(raw)
    if positive and not value > 0.0:
        raise RefiningSpecError(f"{name} must be positive, got {raw!r}")
    if not positive and value < 0.0:
        raise RefiningSpecError(f"{name} must be >= 0, got {raw!r}")
    return value


def _integer(raw: object, name: str, lo: int, hi: int) -> int:
    if not isinstance(raw, int) or isinstance(raw, bool) or not lo <= raw <= hi:
        raise RefiningSpecError(f"{name} must be an integer in [{lo}, {hi}], got {raw!r}")
    return raw


class CrudeColumnR2:
    """Steam-stripped atmospheric column with three side strippers over the column API."""

    inlet_ports: tuple[str, ...] = ("crude_in", "stripping_steam")
    outlet_ports: tuple[str, ...] = ("overhead", "kero_out", "diesel_out", "ago_out", "bottoms")

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """The R0 example crude (the light crude of Bagajewicz & Ji 2001 at its
        631.75 K, 2 bar flash zone) cut into 16 equal-percent pseudos (22
        species with the light ends, preflash R2's slate), 12 stages with the
        flash zone on stage 10. Side products at the R0 cut-point rates of
        that slate (kero 267.82, diesel 98.15, AGO 62.15 mol/s), each stripped
        over 3 stages by 3 mol/s of steam; 10 mol/s of steam under the bottom
        stage, the header superheated at 500 K (saturation at 2 bar: 393 K).
        Overhead 430 mol/s: the R0 overhead's hydrocarbon less the column's
        fractionation overlap, plus the steam water.
        """
        from ngdesign.data.assay import CutScheme
        from ngdesign.units.refining.assay_feeder import _EXAMPLE_ASSAY
        from ngdesign.units.refining.slate import assay_slate, register_slate

        scheme = CutScheme.equal_count(_EXAMPLE_CUTS)
        register_slate(_EXAMPLE_ASSAY, scheme)
        _, mole = assay_slate(_EXAMPLE_ASSAY, scheme)
        feeds = {
            "crude_in": {"T": 631.75, "P": 2.0e5, "molar_flow": 1000.0, "composition": dict(mole)},
            "stripping_steam": {"T": 500.0, "P": 2.0e5, "molar_flow": 19.0, "composition": {"H2O": 1.0}},
        }

        def stripper(draw: int, rate: float) -> dict[str, Any]:
            return {
                "draw_stage": draw,
                "return_stage": draw - 1,
                "n_stages": 3,
                "steam_mol_s": 3.0,
                "product_rate_mol_s": rate,
            }

        return feeds, {
            "n_stages": 12,
            "feed_stage": 10,
            "distillate_rate_mol_s": 430.0,
            "strippers": {
                "kero_out": stripper(4, 267.82),
                "diesel_out": stripper(7, 98.15),
                "ago_out": stripper(9, 62.15),
            },
        }

    def solve(self, inlets: dict[str, StreamState], params: dict[str, Any], thermo: Thermo) -> UnitResult:
        feed = inlets.get("crude_in")
        if feed is None or feed.molar_flow <= 0.0:
            raise RefiningSpecError("crude_in: a crude inlet stream with positive flow is required")
        for key in params:
            if key not in _ALLOWED_KEYS:
                raise RefiningSpecError(f"crude_column R2 refuses unknown parameter {key!r}")
        n_stages = _integer(params.get("n_stages"), "n_stages", 4, 200)
        feed_stage = _integer(params.get("feed_stage"), "feed_stage", 3, n_stages)
        rate = _number(params.get("distillate_rate_mol_s"), "distillate_rate_mol_s", positive=True)
        steam = inlets.get("stripping_steam")
        steam_flow = steam.molar_flow if steam is not None else 0.0
        if steam is not None and steam_flow > 0.0 and steam.composition.get("H2O", 0.0) < _STEAM_PURITY:
            raise RefiningSpecError("stripping_steam must be pure water (H2O)")
        strippers, stripper_steam = _strippers(params.get("strippers"), feed_stage, steam, feed)
        bottom_steam = steam_flow - stripper_steam
        if bottom_steam < -1e-12 * max(steam_flow, 1.0):
            raise RefiningSpecError(
                f"the strippers take {stripper_steam} mol/s of steam; the stripping_steam inlet carries "
                f"only {steam_flow} mol/s"
            )
        column_params: dict[str, Any] = {
            "n_stages": n_stages,
            "condenser": "partial",
            "reboiler": "none",
            "feed_stage": feed_stage,
            "pressure_profile": params.get("pressure_profile", feed.P),
            "specs": {"distillate_rate": rate},
            "side_strippers": strippers,
            "pool_liquids": True,
            "initialization": "relaxation",
        }
        if "pumparounds" in params:
            # The column core's pumparound loops (spec S0-1), parsed and
            # validated there (ColumnSpecError on a bad loop); here they must
            # sit above the flash zone, whose envelope bounds the overhead.
            column_params["pumparounds"] = params["pumparounds"]
            for pa in _parse_pumparounds(column_params, n_stages):
                if pa.draw_stage >= feed_stage:
                    raise RefiningSpecError(
                        f"pumparounds: loop {pa.name!r} draws on stage {pa.draw_stage}; a crude-column "
                        f"pumparound draws above the flash zone (stage {feed_stage})"
                    )
        if steam is not None and bottom_steam > 0.0:
            column_params["feeds"] = [
                {
                    "stage": n_stages,
                    "T": steam.T,
                    "P": steam.P,
                    "molar_flow": bottom_steam,
                    "composition": {"H2O": 1.0},
                }
            ]
        pressures = _parse_pressure_profile(column_params["pressure_profile"], n_stages)
        products_above = rate + sum(st["product_rate_mol_s"] for st in strippers)
        envelope = pressures[feed_stage - 1 :]
        _check_overflash(feed, steam, bottom_steam, steam_flow, products_above, envelope, thermo)
        result, products = solve_column_full({"feed": feed}, column_params, thermo)
        outlets = {"overhead": result.outlets["distillate"], "bottoms": result.outlets["bottoms"]}
        for port, name in _SIDE_PORTS.items():
            outlets[port] = products[name]
        info = {
            key: value
            for key, value in result.info.items()
            if key.startswith(("stage_", "stripper_", "pa_")) or key == "n_graph_stages"
        }
        # The liquid falling into the flash zone from the stage above it.
        overflash = result.info[f"stage_{feed_stage - 2}_L_mol_s"]
        info.update(
            n_stages=float(n_stages),
            ns_used=result.info["ns_used"],
            condenser_duty_W=result.info["condenser_duty_W"],
            closure_residual_W=result.info["reboiler_duty_W"],
            overflash_mol_s=overflash,
            overflash_frac=overflash / feed.molar_flow,
            bottom_steam_mol_s=max(bottom_steam, 0.0),
            stripping_steam_mol_s=steam_flow,
        )
        for port, state in outlets.items():
            info[f"{port}_mol_s"] = state.molar_flow
        return UnitResult(outlets=outlets, duty_W=result.duty_W, power_W=0.0, info=info)


def _strippers(
    raw: object, feed_stage: int, steam: StreamState | None, feed: StreamState
) -> tuple[list[dict[str, Any]], float]:
    """The column's ``side_strippers`` list for the three side ports, and their total steam.

    Without a stripping_steam inlet every stripper runs dry (no steam); the
    column still wants a steam state then, so the feed's T and P stand in at
    zero flow.
    """
    steam_t, steam_p = (steam.T, steam.P) if steam is not None else (feed.T, feed.P)
    if not isinstance(raw, dict) or set(raw) != set(_SIDE_PORTS):
        raise RefiningSpecError(f"strippers must map each of {sorted(_SIDE_PORTS)} to a stripper spec")
    out: list[dict[str, Any]] = []
    total_steam = 0.0
    for port, name in _SIDE_PORTS.items():
        spec = raw[port]
        if not isinstance(spec, dict):
            raise RefiningSpecError(f"strippers.{port} must be a mapping")
        unknown = set(spec) - _STRIPPER_KEYS
        if unknown:
            raise RefiningSpecError(f"strippers.{port} refuses unknown keys {sorted(unknown)}")
        draw = _integer(spec.get("draw_stage"), f"strippers.{port}.draw_stage", 2, feed_stage - 1)
        ret = _integer(spec.get("return_stage"), f"strippers.{port}.return_stage", 1, draw)
        n_sec = _integer(spec.get("n_stages"), f"strippers.{port}.n_stages", 2, 50)
        rate = _number(spec.get("product_rate_mol_s"), f"strippers.{port}.product_rate_mol_s", positive=True)
        steam_rate = _number(spec.get("steam_mol_s", 0.0), f"strippers.{port}.steam_mol_s", positive=False)
        if steam_rate > 0.0 and steam is None:
            raise RefiningSpecError(f"strippers.{port}.steam_mol_s needs the stripping_steam inlet")
        total_steam += steam_rate
        out.append(
            {
                "name": name,
                "draw_stage": draw,
                "return_stage": ret,
                "n_stages": n_sec,
                "steam": {"flow_mol_s": steam_rate, "T_K": steam_t, "P_Pa": steam_p},
                "product_rate_mol_s": rate,
            }
        )
    return out, total_steam


def _check_overflash(
    feed: StreamState,
    steam: StreamState | None,
    bottom_steam: float,
    steam_flow: float,
    products_above: float,
    pressures: list[float],
    thermo: Thermo,
) -> None:
    """Refuse products above the flash zone that the crude cannot vaporise.

    The column has no reboiler: everything leaving above the flash zone (the
    overhead and the side products) is crude vaporised by the feed's own heat
    and the bottom steam. The flash zone and the stages under it form an
    envelope fed by the crude, the bottom steam and the overflash L_o (the
    liquid falling in from the stage above). At L_o = 0 the envelope is
    decoupled from the column above it, so solved alone (the same stages,
    pressures and pooled-liquid stage model; no condenser, no reboiler) it
    leaves exactly the bottoms B_0 the full column has at zero overflash.
    The overall balance B = F + S - D - sum(P) then bounds the products
    above the flash zone by F + S - B_0; more needs L_o < 0, a column with
    no solution. Measured on the example: the limit is D = 448.72 mol/s, and
    the overflash falls 1.76 mol/s per mol/s of overhead towards it (31.8 at
    D = 430, 14.2 at 440).

    Inconclusive when the envelope itself does not converge: the full solve
    then stands on its own gates.
    """
    if len(pressures) == 1:
        # The flash zone is the bottom stage: the envelope is one adiabatic
        # flash of the crude and the bottom steam.
        total = feed.molar_flow + bottom_steam
        z = {cid: frac * feed.molar_flow / total for cid, frac in feed.composition.items()}
        h = feed.enthalpy * feed.molar_flow
        if steam is not None and bottom_steam > 0.0:
            z["H2O"] = z.get("H2O", 0.0) + bottom_steam / total
            h += steam.enthalpy * bottom_steam
        b0 = (1.0 - thermo.flash_ph(z, pressures[0], h / total, total).vapor_fraction) * total
    else:
        env: dict[str, Any] = {
            "n_stages": len(pressures),
            "condenser": "none",
            "reboiler": "none",
            "feed_stage": 1,
            "pressure_profile": pressures,
            "specs": {},
            "pool_liquids": True,
            "initialization": "relaxation",
        }
        if steam is not None and bottom_steam > 0.0:
            env["feeds"] = [
                {
                    "stage": len(pressures),
                    "T": steam.T,
                    "P": steam.P,
                    "molar_flow": bottom_steam,
                    "composition": {"H2O": 1.0},
                }
            ]
        try:
            result, _ = solve_column_full({"feed": feed}, env, thermo)
        except (ColumnConvergenceError, ValueError):
            return
        b0 = result.outlets["bottoms"].molar_flow
    limit = feed.molar_flow + steam_flow - b0
    if products_above > limit:
        raise RefiningSpecError(
            f"negative overflash: the overhead and side products take {products_above:.6g} mol/s, but "
            f"with no liquid falling into the flash zone (zero overflash) the crude and bottom steam "
            f"vaporise only enough for {limit:.6g} mol/s above it (bottoms {b0:.6g} mol/s). The column "
            f"has no reboiler: lower distillate_rate_mol_s or the side-product rates by "
            f"{products_above - limit:.6g} mol/s, or heat the crude or add bottom steam"
        )
