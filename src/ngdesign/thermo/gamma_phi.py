"""Gamma-phi adapter: activity-coefficient liquids x vapour models (spec T-03).

One adapter class, :class:`GammaPhiPackage`, wires a liquid-phase gE model and a
vapour-phase model together over the shared FlashVLN/FlashVL wiring (the same
pattern the pre-existing NRTL row used). The catalogue rows in
data/thermo_models/gamma_phi.yaml declare the pairing in typed options
(``liquid``/``vapour``, values in ngdesign.thermo.options); the flasher is
cached per (liquid, vapour, sorted support, slate pseudos).

Liquids (12): nrtl, uniquac and wilson consume the ChemSep tables bundled in
thermo 0.6.1's IPDB (as the original NRTL adapter did), with in-house fitted
overrides from data/thermo_params/<model>/pairs.yaml where the databank is
zero-filled or disagrees with the T-12 cases; vanlaar and margules use the
in-house energy-form gE models in ngdesign.thermo.ge_models with case-fitted
parameters from their pairs.yaml; regular_solution derives pure solubility
parameters from the thermo correlations at 298.15 K; and the six UNIFAC
variants resolve curated subgroup assignments from
data/thermo_params/unifac/groups.yaml.

Refusals, never silent ideal fallbacks: a binary pair with zero-filled (absent)
databank parameters raises naming the pair; a component without a UNIFAC group
assignment for the variant raises naming the component; pseudo-components raise
naming them; a correlation returning None (regular solution) raises naming the
component. A missing parameter is an error, not an ideal gas.

Three liquid phases (VLLE) are wired for the models whose parameterizations
support liquid-liquid splits (NRTL, UNIQUAC, UNIFAC-LLE); the remaining models
flash two-phase (VLE) through the same saturation path.

Vapour models: ideal, RK and PR (ChemSep PR kijs, zero-filled where the table
has no pair - a kij of 0 is pr.py's existing convention and does not affect
liquid non-ideality). The Hayden-O'Connell and Nothnagel virial rows register
as experimental and refuse to build (ngdesign.thermo.virial).

Component ids map to CAS via ngdesign.data.components() (C6+ = n-hexane per the
reference-data note). SI units throughout: K, Pa, kg/m3, Pa.s, J/mol,
J/(mol K).
"""

from __future__ import annotations

import math
from collections import OrderedDict
from collections.abc import Callable
from functools import cache
from pathlib import Path
from typing import Any, cast

import yaml
from thermo import (
    PRMIX,
    SRKMIX,
    CEOSGas,
    ChemicalConstantsPackage,
    FlashVL,
    FlashVLN,
    GibbsExcessLiquid,
    IdealGas,
)
from thermo.activity import GibbsExcess
from thermo.interaction_parameters import IPDB
from thermo.nrtl import NRTL
from thermo.regular_solution import RegularSolution
from thermo.unifac import UNIFAC, UNIFAC_RQ, load_unifac_ip
from thermo.uniquac import UNIQUAC
from thermo.wilson import Wilson

from ngdesign.data import DATABANK_LOCK
from ngdesign.data import PseudoDefinition as DataPseudoDefinition
from ngdesign.thermo import _state, virial
from ngdesign.thermo.cubic import ThermoSurfaceMixin
from ngdesign.thermo.ge_models import Margules, VanLaar

# The ideal-gas vapour is not a CEOS class; without this registration the
# shared state layer counts an all-ideal-gas state as liquid (vf stuck at 0).
_state.register_vapour_phase_class(IdealGas)

PARAMS_DIR = Path(__file__).resolve().parents[3] / "data" / "thermo_params"

_CHEMSEP_PR_TABLE = "ChemSep PR"
#: liquid option value -> (display name, ChemSep IPDB table)
_CHEMSEP_LIQUIDS: dict[str, tuple[str, str]] = {
    "nrtl": ("NRTL", "ChemSep NRTL"),
    "uniquac": ("UNIQUAC", "ChemSep UNIQUAC"),
    "wilson": ("Wilson", "ChemSep Wilson"),
}
#: liquids whose parameterizations support liquid-liquid splits (FlashVLN wiring)
_THREE_PHASE_LIQUIDS = frozenset({"nrtl", "uniquac", "unifac_lle"})
_DISPLAY: dict[str, str] = {
    "vanlaar": "van Laar",
    "margules": "Margules",
    "regular_solution": "the regular-solution model",
}


def _display(liquid: str) -> str:
    if liquid in _CHEMSEP_LIQUIDS:
        return _CHEMSEP_LIQUIDS[liquid][0]
    if liquid in _DISPLAY:
        return _DISPLAY[liquid]
    return liquid


@cache
def _pairs_config(model: str) -> dict[str, Any]:
    """The pairs mapping of data/thermo_params/<model>/pairs.yaml ({} when absent)."""
    path = PARAMS_DIR / model / "pairs.yaml"
    if not path.exists():
        return {}
    parsed = yaml.safe_load(path.read_text()) or {}
    return parsed.get("pairs", {}) or {}


@cache
def _unifac_groups_config() -> dict[str, Any]:
    """The variants mapping of data/thermo_params/unifac/groups.yaml."""
    path = PARAMS_DIR / "unifac" / "groups.yaml"
    parsed = yaml.safe_load(path.read_text()) or {}
    return parsed.get("variants", {}) or {}


@cache
def _uniquac_groups_config() -> dict[str, Any]:
    """Parsed data/thermo_params/uniquac/groups.yaml (r,q group contributions)."""
    path = PARAMS_DIR / "uniquac" / "groups.yaml"
    return yaml.safe_load(path.read_text()) or {}


def _fitted_pair_params(model: str, ids: tuple[str, ...]) -> dict[tuple[int, int], tuple[float, float]]:
    """Fitted binary overrides from pairs.yaml for this support.

    Returns {(i, j): (p_1->2, p_2->1)} with i < j indexing the sorted ids, for
    every fitted entry whose declared pair is inside this support. Entries for
    other supports are ignored (the same file serves every catalogue row of the
    model).
    """
    out: dict[tuple[int, int], tuple[float, float]] = {}
    for key, entry in _pairs_config(model).items():
        entry = entry or {}
        if not entry.get("fitted"):
            continue
        pair = entry.get("pair")
        if not pair or len(pair) != 2:
            raise ValueError(
                f"{model}/pairs.yaml entry {key!r}: fitted entries declare "
                "'pair: [<id1>, <id2>]'; the orientation of params [1->2, 2->1] "
                "follows that order"
            )
        a, b = str(pair[0]), str(pair[1])
        if a not in ids or b not in ids:
            continue
        params = entry.get("params")
        if not params or len(params) != 2:
            raise ValueError(f"{model}/pairs.yaml entry {key!r}: params must be [p_1->2, p_2->1]")
        i, j = ids.index(a), ids.index(b)
        if i > j:
            i, j = j, i
            out[(i, j)] = (float(params[1]), float(params[0]))
        else:
            out[(i, j)] = (float(params[0]), float(params[1]))
    return out


def _require_no_pseudos(display: str, reason: str, records: list[Any]) -> None:
    """Raise naming the pseudo ids; every liquid model here is databank/correlation keyed."""
    pseudo_ids = [r.id for r in records if r.cas is None]
    if pseudo_ids:
        raise ValueError(
            f"{display} has no binary parameters for pseudo-components {pseudo_ids} "
            f"({reason}); refusing to flash an ideal pseudo matrix - register no "
            "pseudos or select an EOS model"
        )


def _chemsep_matrix(
    liquid: str, ip_name: str, ids: tuple[str, ...], cas_list: list[str]
) -> list[list[float]]:
    """IPDB asymmetric matrix with fitted overrides applied; zero-filled pairs raise.

    The IPDB getters replace a databank-missing pair with the table's declared
    default (bij 0) without any signal, so bij == 0 for an ordered pair is the
    one reliable marker that the pair was never fitted. Overridden pairs skip
    the check: their fitted values replace the zero-fill.
    """
    table = _CHEMSEP_LIQUIDS[liquid][1]
    matrix = IPDB.get_ip_asymmetric_matrix(name=table, CASs=cas_list, ip=ip_name)
    fitted = _fitted_pair_params(liquid, ids)
    n = len(ids)
    for i in range(n):
        for j in range(i + 1, n):
            if (i, j) in fitted:
                p12, p21 = fitted[(i, j)]
                matrix[i][j], matrix[j][i] = p12, p21
                continue
            if matrix[i][j] == 0.0 or matrix[j][i] == 0.0:
                raise ValueError(
                    f"{table} databank has no fitted binary parameters for pair "
                    f"{ids[i]} ({cas_list[i]}) / {ids[j]} ({cas_list[j]}); refusing to "
                    "flash a zero-filled (ideal) pair matrix - select a thermo model "
                    "whose databank covers this component support"
                )
    return [[float(v) for v in row] for row in matrix]


def _wilson_matrices(
    ids: tuple[str, ...], cas_list: list[str]
) -> tuple[list[list[float]], list[list[float]]]:
    """(lambda_as, lambda_bs) for thermo's Wilson from the ChemSep table.

    ChemSep writes Lambda_ij = (V_j / V_i) exp(-A_ij / (R T)); thermo stores it
    as ln Lambda_ij = a_ij + b_ij / T with a_ij = ln(V_j / V_i) (table ip
    ``aij``) and b_ij = -A_ij / R (ip ``bij``). Both matrices are needed: with
    ``bij`` alone the EtOH/H2O activity coefficients at 343.15 K come out
    [2.20, 1.08] instead of thermo's documented [1.957, 1.160] (measured, review
    of PR #150). Fitted overrides in data/thermo_params/wilson/pairs.yaml were
    fitted in the two-parameter form ln Lambda_ij = b_ij / T, so their a_ij is
    zero by construction.
    """
    lambda_bs = _chemsep_matrix("wilson", "bij", ids, cas_list)
    lambda_as = [
        [float(v) for v in row]
        for row in IPDB.get_ip_asymmetric_matrix(name=_CHEMSEP_LIQUIDS["wilson"][1], CASs=cas_list, ip="aij")
    ]
    for i, j in _fitted_pair_params("wilson", ids):
        lambda_as[i][j] = lambda_as[j][i] = 0.0
    return lambda_as, lambda_bs


def _fitted_only_matrix(liquid: str, ids: tuple[str, ...], cas_list: list[str]) -> list[list[float]]:
    """Full binary matrix from the fitted pairs.yaml entries; a missing pair raises."""
    display = _display(liquid)
    fitted = _fitted_pair_params(liquid, ids)
    n = len(ids)
    matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            if (i, j) not in fitted:
                raise ValueError(
                    f"{display} binary parameters for pair {ids[i]} ({cas_list[i]}) / "
                    f"{ids[j]} ({cas_list[j]}) are not available in "
                    f"data/thermo_params/{liquid}/pairs.yaml; refusing to flash a "
                    "zero-filled (ideal) pair matrix - select a thermo model whose "
                    "parameter tables cover this component support"
                )
            p12, p21 = fitted[(i, j)]
            matrix[i][j], matrix[j][i] = p12, p21
    return matrix


@cache
def _unifac_variant_tables(
    variant: str,
) -> tuple[int, Any, Any, dict[str, int], dict[str, dict[str, float]]]:
    """(version, interaction table, subgroup table, name->id map, component maps)."""
    load_unifac_ip()
    import thermo.unifac as UF

    cfg = _unifac_groups_config().get(variant)
    if cfg is None:
        raise ValueError(
            f"unknown UNIFAC variant {variant!r} (no entry in data/thermo_params/unifac/groups.yaml)"
        )
    sg = getattr(UF, cfg["subgroups"])
    interaction = getattr(UF, cfg["interaction"])
    name_to_id = {g.group: g.group_id for g in sg.values()}
    components = {
        cid: {str(name): float(count) for name, count in counts.items()}
        for cid, counts in cfg["components"].items()
    }
    return int(cfg["version"]), interaction, sg, name_to_id, components


def _resolve_groups(
    cid: str,
    cas: str,
    counts: dict[str, float] | None,
    name_to_id: dict[str, int],
    file_hint: str,
) -> dict[int, float]:
    """Resolve subgroup names to thermo subgroup ids; a missing assignment raises."""
    if counts is None:
        raise ValueError(
            f"no UNIFAC group assignment for {cid} ({cas}) in {file_hint}; refusing to "
            "predict - the curated maps cover the component support of this variant's "
            "catalogue rows (the Magnussen LLE set, for example, is not parameterized "
            "for alcohol/glycol systems)"
        )
    resolved: dict[int, float] = {}
    for name, count in counts.items():
        gid = name_to_id.get(name)
        if gid is None:
            raise ValueError(
                f"subgroup {name!r} for {cid} is not in the referenced thermo subgroup "
                f"table - fix {file_hint}"
            )
        resolved[gid] = count
    return resolved


def _unifac_factory(variant: str, ids: tuple[str, ...], cas_list: list[str]) -> Any:
    """Callable(xs) building one UNIFAC model of this variant over the support."""
    version, interaction, sg, name_to_id, components = _unifac_variant_tables(variant)
    chemgroups: list[dict[int, float]] = []
    for cid, cas in zip(ids, cas_list, strict=True):
        counts = components.get(cid)
        chemgroups.append(
            _resolve_groups(cid, cas, counts, name_to_id, "data/thermo_params/unifac/groups.yaml")
        )

    def make(xs: list[float]) -> GibbsExcess:
        return UNIFAC.from_subgroups(
            chemgroups=chemgroups,
            T=298.15,
            xs=list(xs),
            version=version,
            interaction_data=interaction,
            subgroups=sg,
        )

    return make


def _uniquac_rq(ids: tuple[str, ...], cas_list: list[str]) -> tuple[list[float], list[float]]:
    """UNIFAC group-contribution r,q surface parameters for the support."""
    cfg = _uniquac_groups_config()
    components = cfg.get("components") or {}
    sg_name = str(cfg.get("subgroups") or "UFSG")
    load_unifac_ip()
    import thermo.unifac as UF

    sg = getattr(UF, sg_name)
    name_to_id = {g.group: g.group_id for g in sg.values()}
    rs: list[float] = []
    qs: list[float] = []
    for cid, cas in zip(ids, cas_list, strict=True):
        counts = components.get(cid)
        if counts is None:
            raise ValueError(
                f"no UNIQUAC r,q group assignment for {cid} ({cas}) in "
                "data/thermo_params/uniquac/groups.yaml; refusing to predict - the "
                "curated maps cover the component support of the uniquac catalogue rows"
            )
        resolved: dict[int, float] = {}
        for name, count in counts.items():
            gid = name_to_id.get(str(name))
            if gid is None:
                raise ValueError(
                    f"UNIQUAC r,q: subgroup {name!r} for {cid} is not in the {sg_name} "
                    "table - fix data/thermo_params/uniquac/groups.yaml"
                )
            resolved[gid] = float(count)
        r, q = UNIFAC_RQ(resolved, sg)
        rs.append(float(r))
        qs.append(float(q))
    return rs, qs


def _regular_solution_factory(ids: tuple[str, ...], cas_list: list[str], correlations: Any) -> Any:
    """Callable(xs) building one RegularSolution model over the support.

    Pure solubility parameters SP_i = sqrt(dHvap_i / V_i) come from the thermo
    pure-component correlations at the 298.15 K reference state (EnthalpyVapori-
    zations takes T only, VolumeLiquids takes T and P). A None correlation value
    is a missing parameter: raise naming the component, never default.
    """
    t_ref = 298.15
    p_ref = 101325.0
    vs: list[float] = []
    sps: list[float] = []
    for i, (cid, cas) in enumerate(zip(ids, cas_list, strict=True)):
        hvap = correlations.EnthalpyVaporizations[i](t_ref)
        vol = correlations.VolumeLiquids[i](t_ref, p_ref)
        if hvap is None or vol is None:
            missing = "enthalpy of vaporization" if hvap is None else "liquid molar volume"
            raise ValueError(
                f"the regular-solution solubility parameter for {cid} ({cas}) cannot be "
                f"formed: the thermo pure-component correlation returns no {missing} at "
                "298.15 K; refusing rather than defaulting - select a model whose "
                "parameters cover this component support"
            )
        vs.append(float(vol))
        sps.append(math.sqrt(float(hvap) / float(vol)))

    def make(xs: list[float]) -> GibbsExcess:
        return RegularSolution(xs=list(xs), T=298.15, Vs=list(vs), SPs=list(sps))

    return make


def _ge_model_factory(liquid: str, ids: tuple[str, ...], cas_list: list[str], correlations: Any) -> Any:
    """Callable(xs) building one gE model of the liquid over this exact support.

    The flasher calls to_T_xs at the flash state, so every instance is pinned at
    the 298.15 K construction default, matching the NRTL adapter's convention.
    """
    n = len(ids)

    if liquid in _CHEMSEP_LIQUIDS:
        if liquid == "nrtl":
            tau_bs = _chemsep_matrix(liquid, "bij", ids, cas_list)
            alpha_cs = IPDB.get_ip_asymmetric_matrix(
                name=_CHEMSEP_LIQUIDS[liquid][1], CASs=cas_list, ip="alphaij"
            )

            def make(xs: list[float]) -> GibbsExcess:
                return NRTL(xs=list(xs), T=298.15, tau_bs=tau_bs, alpha_cs=alpha_cs)

            return make
        if liquid == "uniquac":
            tau_bs = _chemsep_matrix(liquid, "bij", ids, cas_list)
            rs, qs = _uniquac_rq(ids, cas_list)

            def make(xs: list[float]) -> GibbsExcess:
                return UNIQUAC(xs=list(xs), rs=rs, qs=qs, T=298.15, tau_bs=tau_bs)

            return make
        if liquid == "wilson":
            lambda_as, lambda_bs = _wilson_matrices(ids, cas_list)

            def make(xs: list[float]) -> GibbsExcess:
                return Wilson(xs=list(xs), T=298.15, lambda_as=lambda_as, lambda_bs=lambda_bs)

            return make
        raise ValueError(f"unhandled ChemSep liquid {liquid!r}")  # pragma: no cover

    if liquid in ("vanlaar", "margules"):
        matrix = _fitted_only_matrix(liquid, ids, cas_list)
        cls = VanLaar if liquid == "vanlaar" else Margules
        a12 = matrix[0][1] if n > 1 else 0.0
        a21 = matrix[1][0] if n > 1 else 0.0

        def make(xs: list[float]) -> GibbsExcess:
            return cls(xs=list(xs), T=298.15, A12=a12, A21=a21)

        return make

    if liquid == "regular_solution":
        return _regular_solution_factory(ids, cas_list, correlations)

    if liquid.startswith("unifac"):
        return _unifac_factory(liquid, ids, cas_list)

    raise ValueError(f"unknown gamma-phi liquid model {liquid!r}")


def _gas_phase(vapour: str, cas_list: list[str], constants: Any, correlations: Any) -> Any:
    """The vapour phase for the pairing; virial models refuse (ngdesign.thermo.virial)."""
    virial.refuse_not_implemented(vapour)
    heat_caps = correlations.HeatCapacityGases
    if vapour == "ideal":
        return IdealGas(HeatCapacityGases=heat_caps)
    kijs = IPDB.get_ip_symmetric_matrix(name=_CHEMSEP_PR_TABLE, CASs=cas_list, ip="kij")
    eos_kwargs: dict[str, Any] = {
        "Tcs": constants.Tcs,
        "Pcs": constants.Pcs,
        "omegas": constants.omegas,
        "kijs": kijs,
    }
    if vapour == "pr":
        return CEOSGas(PRMIX, eos_kwargs, HeatCapacityGases=heat_caps)
    if vapour == "rk":
        return CEOSGas(SRKMIX, eos_kwargs, HeatCapacityGases=heat_caps)
    raise ValueError(f"unknown gamma-phi vapour model {vapour!r}")


@cache
def _constants_for(cas_list: tuple[str, ...]) -> tuple[Any, Any]:
    """(constants, correlations) per CAS slate.

    ``from_IDs`` is pure given the databank (fixed at runtime), and the L4 audit
    pair loop rebuilds each refusing support once per partner - without this
    memo the provenance refusal path re-pays the full property-package build
    every time, because functools.cache does not memoize the raising call.
    """
    return cast("tuple[Any, Any]", ChemicalConstantsPackage.from_IDs(list(cas_list)))


def _build_flasher_inner(
    liquid: str,
    vapour: str,
    ids: tuple[str, ...],
    three_phase: bool,
    pseudos: tuple[DataPseudoDefinition, ...] = (),
) -> Any:
    """Build a (liquid, vapour) flasher over exactly this sorted component set.

    Every provenance check (pseudo components, missing binary parameters,
    missing group assignments, unavailable correlations) runs here, at flasher
    construction, before any flash exists - a support the model cannot describe
    can never produce a silently ideal result.
    """
    with DATABANK_LOCK:
        records = _state._records(ids, pseudos)
        if liquid in _CHEMSEP_LIQUIDS:
            display, table = _CHEMSEP_LIQUIDS[liquid]
            _require_no_pseudos(display, f"the {table} databank is keyed by CAS", records)
        elif liquid.startswith("unifac"):
            _require_no_pseudos("UNIFAC", "UNIFAC subgroups are curated per real component", records)
        else:
            _require_no_pseudos(
                _display(liquid),
                "pure-component correlations and parameters are keyed by CAS",
                records,
            )
        cas_list = [str(r.cas) for r in records]
        constants, correlations = _constants_for(tuple(cas_list))
        make_ge = _ge_model_factory(liquid, ids, cas_list, correlations)
        gas = _gas_phase(vapour, cas_list, constants, correlations)

        def ge_liquid() -> Any:
            """One liquid phase; each gets its own gE instance (the model carries T/xs state)."""
            model = make_ge([1.0 / len(ids)] * len(ids))
            return GibbsExcessLiquid(
                VaporPressures=correlations.VaporPressures,
                HeatCapacityGases=correlations.HeatCapacityGases,
                HeatCapacityLiquids=correlations.HeatCapacityLiquids,
                EnthalpyVaporizations=correlations.EnthalpyVaporizations,
                VolumeLiquids=correlations.VolumeLiquids,
                GibbsExcessModel=model,
            )

        if three_phase:
            return FlashVLN(constants, correlations, gas=gas, liquids=[ge_liquid(), ge_liquid()])
        return FlashVL(constants, correlations, gas=gas, liquid=ge_liquid())


@cache
def _flasher_outcome(
    liquid: str,
    vapour: str,
    ids: tuple[str, ...],
    three_phase: bool,
    pseudos: tuple[DataPseudoDefinition, ...],
) -> tuple[bool, Any]:
    """Build the flasher, or memoize the provenance refusal message.

    ``functools.cache`` cannot memoize exceptions, and the audit's L4 pair loop
    constructs each refusing (model, support) combination once per partner —
    without memoizing the refusal itself, every pair re-pays the full flasher
    build only to raise the same provenance error again.
    """
    try:
        return True, _build_flasher_inner(liquid, vapour, ids, three_phase, pseudos)
    except ValueError as exc:
        return False, str(exc)


def _flasher_for(
    liquid: str,
    vapour: str,
    ids: tuple[str, ...],
    pseudos: tuple[DataPseudoDefinition, ...] = (),
) -> Any:
    """Build (and cache) the full flasher over this sorted support.

    Zero-fraction components are dropped by the caller before this is reached,
    so the cache key is the reduced, sorted support of the feed composition plus
    the slate's flowsheet-owned pseudo definitions (spec P1-07). Three liquid
    phases are wired only for the models whose parameterizations support
    liquid-liquid splits.
    """
    ok, got = _flasher_outcome(liquid, vapour, ids, liquid in _THREE_PHASE_LIQUIDS, pseudos)
    if ok:
        return got
    raise ValueError(got)


def _flasher_vl_for(
    liquid: str,
    vapour: str,
    ids: tuple[str, ...],
    pseudos: tuple[DataPseudoDefinition, ...] = (),
) -> Any:
    """Build (and cache) the two-phase FlashVL saturation fast path."""
    ok, got = _flasher_outcome(liquid, vapour, ids, False, pseudos)
    if ok:
        return got
    raise ValueError(got)


_SHARED_RESULTS: OrderedDict[tuple[Any, ...], Any] = OrderedDict()
_SHARED_RESULT_CAP = 512


def _shared_cached(self_key: tuple[Any, ...], key: tuple[Any, ...], compute: Callable[[], Any]) -> Any:
    """Cross-instance memo for pure per-support results.

    Flash results are pure functions of (model pair, slate pseudos, key), yet the
    base cache is per-instance — so a caller that builds a fresh package per
    request (the audit's L4 pair loop builds each model once per partner)
    re-flashes the identical (z, T, P) every time. Share the memo module-wide.
    """
    full = (self_key, *key)
    hit = _SHARED_RESULTS.get(full)
    if hit is not None:
        _SHARED_RESULTS.move_to_end(full)
        return hit
    value = compute()
    _SHARED_RESULTS[full] = value
    while len(_SHARED_RESULTS) > _SHARED_RESULT_CAP:
        _SHARED_RESULTS.popitem(last=False)
    return value


class GammaPhiPackage(ThermoSurfaceMixin):
    """Activity-coefficient liquid x vapour package over the `thermo` library.

    Registered through the thermo catalogue (data/thermo_models/gamma_phi.yaml)
    as a factory: the catalogue row's typed options pin the liquid and vapour
    models; the class stays the single adapter.
    """

    def __init__(
        self,
        liquid: str,
        vapour: str,
        components: tuple[str, ...] | None = None,
    ) -> None:
        """Build the package; `components` runs the provenance checks eagerly.

        The registry/API path constructs with no argument, because the solver's
        component support is only known at flash time; the checks then run inside
        the cached flasher factory before that support's first flash. Either way a
        pair, component or correlation the model cannot describe raises before any
        state is returned - never silently as ideal.
        """
        self.liquid = liquid
        self.vapour = vapour
        super().__init__()
        if components:
            _flasher_for(liquid, vapour, tuple(sorted(components)))

    def _cached(self, key: tuple[Any, ...], compute: Callable[[], Any]) -> Any:
        return _shared_cached((self.liquid, self.vapour, self._slate_pseudos), key, compute)

    def _build_flasher(self, ids: tuple[str, ...]) -> Any:
        return _flasher_for(self.liquid, self.vapour, ids, self._slate_pseudos)

    def _build_flasher_vl(self, ids: tuple[str, ...]) -> Any:
        return _flasher_vl_for(self.liquid, self.vapour, ids, self._slate_pseudos)
