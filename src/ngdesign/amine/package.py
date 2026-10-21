"""Amine reactive property package (spec P1-04).

:class:`AmineReactivePackage` is a direct ``Thermo`` implementation for
CO2/H2S reactive absorption into aqueous amines.  It wraps the validated
P0-02 speciation chemistry untouched — Kent-Eisenberg (MDEA/MEA/DEA,
CO2+H2S) or electrolyte-NRTL (MDEA/MEA, CO2-only; an H2S-bearing liquid
raises the enrtl module's own typed rejection) — behind the contract-v2
surface:

- PT/PH/PS flashes with a Rachford-Rice vapour split whose acid-gas
  K-values come from the speciation model's equilibrium partial pressure
  at the flashed liquid's own loading (the VLE data convention: y_i * P
  == p_eq_i at convergence), water and amine K-values from databank
  Psat / P (Raoult), and hydrocarbon K-values from Henry's law in water.
- Saturation (bubble/dew/TVF/PVF) solved on the package's own vapour
  fraction: the shared ``thermo.saturation`` plateau solver (spec P1-08)
  applied to this package's vf.
- Per-phase properties: the vapour phase is the carrier's; the liquid
  phase is the carrier's aqueous properties plus the heat of absorption
  of the dissolved acid gases, obtained by Gibbs-Helmholtz differentiation
  of the speciation equilibrium at fixed loading (no liquid heat-capacity
  data exists for the bound species, so the absorption enthalpy is the
  chemistry's own van 't Hoff content).
- ``acid_gas_partial_pressures`` and ``heat_of_absorption`` helpers for
  the units and tests.

Hydrocarbon/insoluble-gas K-values use Henry's law in water with H_i(T)
from the Sander 2015 compilation as shipped with the ``thermo`` library
("Interaction Parameters/Sander_henry_const.json", pressure-form
coefficients evaluated with ``chemicals.solubility.Henry_pressure`` —
the ``chemicals`` 1.5.2 package itself has no Henry table).  Species the
table lacks fall back to Raoult's law (Psat/P).  Water and the amine use
databank vapour pressures (present for MDEA/MEA/DEA and water).

Feeds without an amine flash entirely on the carrier package, so mixed
flowsheets (sweet gas on a cubic EOS, solvent on the reactive package)
keep their plain-cubic behaviour byte-identical.

SI units throughout: K, Pa, kg/m3, Pa.s, J/mol, J/(mol K).
"""

from __future__ import annotations

import json
import math
import os
from collections import OrderedDict
from collections.abc import Callable
from functools import cache
from typing import Any, Literal, cast

from chemicals.solubility import Henry_pressure
from thermo.interaction_parameters import source_path

from ngdesign.amine.enrtl import (
    equilibrium_loadings as _enrtl_loadings,
)
from ngdesign.amine.enrtl import equilibrium_partial_pressures as _enrtl_pressures
from ngdesign.amine.equilibrium import ENRTL, KENT_EISENBERG
from ngdesign.amine.kent_eisenberg import (
    _MAX_LOADING,
    AMINES,
)
from ngdesign.amine.kent_eisenberg import (
    equilibrium_loadings as _ke_loadings,
)
from ngdesign.amine.kent_eisenberg import (
    equilibrium_partial_pressures as _ke_pressures,
)
from ngdesign.amine.roots import brent_root
from ngdesign.contracts import Phase, PhaseKind, StreamState
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.thermo import (
    PhaseProps,
    PropertyDerivatives,
    SaturationError,
    SaturationPoint,
)
from ngdesign.data import components
from ngdesign.registry import register
from ngdesign.thermo import _state
from ngdesign.thermo.saturation import solve_saturation

__all__ = [
    "AmineENRTLPackage",
    "AmineKEPackage",
    "AmineReactivePackage",
]

#: Acid gases handled by the speciation chemistry.
_ACID_GAS_IDS: tuple[str, ...] = ("CO2", "H2S")

#: Water id and CAS (Sander table solvent key).
_WATER_ID = "H2O"
_WATER_CAS = "7732-18-5"

#: Numeric-derivative half step, K (the spec's 0.5 K Gibbs-Helmholtz step).
_DERIV_D_T = 0.5

#: Loading fixed-point tolerance (max loading change) and iteration cap.
#: Tight enough that the reported vapour phase satisfies y_i * P == p_eq_i to
#: better than 1e-6 relative (the spec's flash-consistency anchor); the state
#: normalization amplifies the loading residual ~1e4x into that identity.
_LOADING_TOL = 1e-12
_LOADING_MAX_ITER = 50

#: Relative tolerance on the saturation unknown (also the brent_root xtol base
#: for the interior TVF/PVF root).
_SATURATION_REL_TOL = 1e-8

#: Interior vapour-fraction targets within this of 0/1 solve as bubble/dew.
_VF_EDGE = 1e-9

#: Per-package property-cache size (P1-01's per-package LRU size).
_CACHE_SIZE = _state.PROPERTY_CACHE_SIZE

#: K-value ceiling for an acid gas the liquid carries none of (its equilibrium
#: partial pressure is exactly zero): treated as effectively all-vapor instead
#: of zero, which would divide by zero in the Rachford-Rice terms.
_ALL_VAPOR_K = 1e12

#: Loading-residual at which the best-seen iterate is accepted when the fixed
#: point stalls (extreme scan pressures where the liquid is a trace phase).
_LOADING_ACCEPT_RESIDUAL = 1e-4

#: Amine mole fraction below which the feed is treated as amine-free and the
#: caller delegates to the carrier. The loading (acid gas / amine) is undefined
#: there and the speciation fixed point cannot converge on it; a trace amine
#: contributes nothing physical to the phase split (measured P1-09: a column's
#: purified top vapour carried MDEA ~1e-9 and burned the 50-iteration cap on
#: it). Six orders of magnitude below any real solvent charge.
_TRACE_AMINE_FRAC = 1e-6


def _wegstein_w(a_used: list[float], a_raws: list[float]) -> float:
    """Under-relaxation weight for one loading from the measured map slope.

    The classical Wegstein weight 1/(1 - s) on the secant slope of the last two
    substitution iterates: an oscillating map (s < 0) gets the near-optimal mid
    weight, a crawling map (0 < s < 1) accelerates toward full substitution,
    and a diverging map (s -> 1) is floored. Before two iterates exist the
    plain 0.5 half-step applies.
    """
    if len(a_used) < 2 or a_used[-1] == a_used[-2]:
        return 0.5
    slope = (a_raws[-1] - a_raws[-2]) / (a_used[-1] - a_used[-2])
    slope = min(max(slope, -50.0), 0.95)
    return min(max(1.0 / (1.0 - slope), 0.05), 1.0)


class AmineChemistryError(ValueError):
    """The amine speciation left its fitted chemistry window.

    Typed subclass of ValueError (the contract's flash-failure type) so callers
    can distinguish a chemistry-window excursion from other flash failures; the
    message names T and the speciation bracket that failed.
    """


@cache
def _sander_henry_table() -> dict[str, dict[str, float]]:
    """Sander 2015 Henry coefficients, keyed "soluteCAS solventCAS".

    Named A..F pressure-form coefficients (H in Pa, p = H * x on a liquid
    mole-fraction base) evaluated with ``chemicals.solubility.Henry_pressure``.
    """
    path = os.path.join(source_path, "Interaction Parameters", "Sander_henry_const.json")
    with open(path) as f:
        data = json.load(f)
    table: dict[str, dict[str, float]] = data["data"]
    return table


@cache
def _mw(cid: str) -> float:
    """Molecular weight of a databanked component, g/mol."""
    return float(components()[cid]["mw"])


@cache
def _cas(cid: str) -> str:
    """CAS number of a databanked component id."""
    return str(components()[cid]["cas"])


#: Pure-component liquid densities at 298.15 K, kg/m3 (GPSA / handbook values;
#: water 997.05, MDEA 1039, MEA 1016, DEA 1097).  The speciation anchors are
#: quoted against the true solution molarity, so the molarity basis needs a
#: physical liquid density: the carrier's PR aqueous density is known poor for
#: water-rich liquids (840 kg/m3 for water at 313 K vs 992 measured) and would
#: bias the partial-pressure anchors ~13% low, and ``thermo``'s
#: ``Chemical.rhol`` for MDEA (954) is an estimated value that disagrees with
#: the measured 1039.  The KE chemistry module likewise carries its constants
#: in code with citations.
_PURE_LIQUID_DENSITIES: dict[str, float] = {
    _WATER_ID: 997.05,
    "MDEA": 1039.0,
    "MEA": 1016.0,
    "DEA": 1097.0,
}


@cache
def _pure_liquid_density(cid: str) -> float:
    """Pure-component liquid density (kg/m3) of the molarity-basis species."""
    try:
        return _PURE_LIQUID_DENSITIES[cid]
    except KeyError:
        raise ValueError(
            f"no liquid density for {cid} (molarity basis covers water and the amines)"
        ) from None


@cache
def _sander_henry(cas: str) -> dict[str, float] | None:
    """Henry coefficients of one solute in water; None when the table lacks it."""
    return _sander_henry_table().get(f"{cas} {_WATER_CAS}")


def _wilson_psat(cid: str, T: float) -> float:
    """Wilson-correlation Psat estimate (Pa) from databank criticals (bracket helper)."""
    comps = components()[cid]
    return float(comps["pc_Pa"]) * math.exp(
        5.373 * (1.0 + float(comps["omega"])) * (1.0 - float(comps["tc_K"]) / T)
    )


def _wilson_T(cid: str, P: float) -> float | None:
    """Wilson-correlation saturation-temperature estimate (K); None when unusable."""
    comps = components()[cid]
    tc, pc, omega = float(comps["tc_K"]), float(comps["pc_Pa"]), float(comps["omega"])
    if P >= pc:
        return None
    denom = 1.0 - math.log(P / pc) / (5.373 * (1.0 + omega))
    if denom <= 0.05:
        return None
    return tc / denom


class AmineReactivePackage(Thermo):
    """Amine reactive absorption property package over a plain-cubic carrier.

    Subclasses pin the speciation model via the ``model`` class attribute
    (registered as ``amine_ke`` for Kent-Eisenberg and ``amine_enrtl`` for
    electrolyte-NRTL).  ``carrier_name`` selects the plain-cubic ``Thermo``
    plugin that provides the physical-phase properties (default PR).
    """

    #: Speciation chemistry model (``ngdesign.amine.equilibrium`` names).
    model: str = KENT_EISENBERG

    #: Duck-typing marker the amine units probe (plain cubic packages lack it).
    is_amine_reactive_package = True

    def __init__(self, model: str | None = None, carrier_name: str = "pr") -> None:
        self._model = model or type(self).model
        if self._model not in (KENT_EISENBERG, ENRTL):
            raise ValueError(f"unknown amine model {self._model!r}; use {KENT_EISENBERG} or {ENRTL}")
        carrier_cls = cast(type[Thermo], _registry_get("thermo", carrier_name))
        self._carrier: Thermo = carrier_cls()
        self._lru_cache: OrderedDict[tuple[Any, ...], Any] = OrderedDict()

    # -- plumbing -------------------------------------------------------------

    def _cached(self, key: tuple[Any, ...], compute: Callable[[], Any]) -> Any:
        """Per-package LRU property cache (P1-01's semantics)."""
        cache_ = self._lru_cache
        hit = cache_.get(key)
        if hit is not None:
            cache_.move_to_end(key)
            return hit
        value = compute()
        cache_[key] = value
        while len(cache_) > _CACHE_SIZE:
            cache_.popitem(last=False)
        return value

    def _support(self, z: dict[str, float]) -> tuple[str, ...]:
        """Sorted positive-fraction ids (the _state helpers' support semantics)."""
        return _state.support_ids(z)

    def _amine_id(self, ids: tuple[str, ...]) -> str | None:
        """The one supported amine, or None; multiple amines raise."""
        present = [cid for cid in ids if cid in AMINES]
        if not present:
            return None
        if len(present) > 1:
            raise ValueError(
                f"multiple amines in one stream ({', '.join(present)}); the reactive "
                "package supports a single amine solvent"
            )
        return present[0]

    def _reactive_domain(self, z: dict[str, float]) -> str | None:
        """The amine id when z carries enough solvent for the reactive chemistry.

        None means the caller must delegate to the carrier: either no supported
        amine at all, or only a trace (below _TRACE_AMINE_FRAC) where the
        loadings are undefined and the speciation fixed point cannot converge.
        """
        amine_id = self._amine_id(self._support(z))
        if amine_id is None or z.get(amine_id, 0.0) < _TRACE_AMINE_FRAC:
            return None
        return amine_id

    def _pressures(
        self, T: float, c_a: float, a_co2: float, a_h2s: float, amine_id: str
    ) -> tuple[float, float]:
        """(p_CO2, p_H2S) in Pa from the pinned speciation model at fixed loadings.

        A root find leaving its bracket means the state left the fitted
        chemistry window (spec E2): surface it as the typed error naming T and
        the failed bracket, never as a bare bracketing failure.
        """
        try:
            if self._model == ENRTL:
                return _enrtl_pressures(T, c_a, a_co2, a_h2s, amine=amine_id)
            return _ke_pressures(T, c_a, a_co2, a_h2s, amine=amine_id)
        except ValueError as exc:
            raise AmineChemistryError(
                f"amine speciation left its chemistry window at T={T} K (speciation bracket: {exc})"
            ) from exc

    def _amine_molarity(self, x: dict[str, float], amine_id: str) -> float:
        """Amine molarity of the liquid (mol/m3) on the solvent (amine + water) basis.

        The speciation anchors are quoted as solution-strength molarities (mol
        amine per solvent volume), so the mole-fraction basis excludes the
        dissolved acid gases, and the solution density is an ideal mass mixing
        of the pure-component liquid densities (:data:`_PURE_LIQUID_DENSITIES`)
        — not the carrier's PR aqueous density, which is known poor for
        water-rich liquids and would bias the anchors ~13% low.  This matches
        the units' ``amine_molarity`` convention (mass fraction times density
        over molecular weight), with a physical rather than PR density.
        """
        x_a = x[amine_id]
        x_w = x.get(_WATER_ID, 0.0)
        if x_a + x_w <= 0.0:
            raise ValueError(f"liquid carries no {amine_id}/water solvent to compute a molarity for")
        mw_a, mw_w = _mw(amine_id), _mw(_WATER_ID)
        w_a = (x_a * mw_a) / (x_a * mw_a + x_w * mw_w)
        rho = (
            1.0 / (w_a / _pure_liquid_density(amine_id) + (1.0 - w_a) / _pure_liquid_density(_WATER_ID))
            if x_w > 0.0
            else _pure_liquid_density(amine_id)
        )
        return w_a * rho / mw_a * 1000.0

    def _liquid_chemistry(
        self, x: dict[str, float], T: float, P: float
    ) -> tuple[str, float, float, float, float, float]:
        """Chemistry state of one liquid composition at (T, P).

        Returns (amine_id, c_amine, alpha_co2, alpha_h2s, p_co2, p_h2s); the
        loadings are the liquid's CO2/H2S-to-amine mole ratios clamped to the
        chemistry window (the fitted isotherm data end near 1.1, window 1.5).
        """
        amine_id = self._amine_id(self._support(x))
        if amine_id is None:  # pragma: no cover - callers gate on amine presence
            raise ValueError("no amine in the liquid composition")
        x_a = x[amine_id]
        a_co2 = min(max(x.get("CO2", 0.0) / x_a, 0.0), _MAX_LOADING)
        a_h2s = min(max(x.get("H2S", 0.0) / x_a, 0.0), _MAX_LOADING)
        c_a = self._amine_molarity(x, amine_id)
        p_co2, p_h2s = self._pressures(T, c_a, a_co2, a_h2s, amine_id)
        return amine_id, c_a, a_co2, a_h2s, p_co2, p_h2s

    def _k_values_internal(
        self, z: dict[str, float], T: float, P: float, x: dict[str, float]
    ) -> dict[str, float]:
        """K-values of the full key set at liquid composition ``x``.

        Acid gases: K_i = p_eq_i(T, loading of x) / (P * x_i) — the speciation
        model's partial pressure IS the equilibrium y_i * P (the VLE data
        convention), so K_i = y_i/x_i puts y_i * P == p_eq_i exactly at the
        converged liquid composition.  Water and the amine: databank Psat / P
        (Raoult).  Volatiles: Henry's law in water, K_i = H_i(T) / P (Sander
        2015 table; species it lacks fall back to Raoult's law Psat / P).
        """
        amine_id = self._amine_id(self._support(x))
        if amine_id is None:  # pragma: no cover - callers gate on amine presence
            raise ValueError("K-values require an amine in the liquid composition")
        p_co2 = p_h2s = 0.0
        if x.get("CO2", 0.0) > 0.0 or x.get("H2S", 0.0) > 0.0:
            _aid, _c, _a1, _a2, p_co2, p_h2s = self._liquid_chemistry(x, T, P)
        k: dict[str, float] = {}
        for cid in z:
            if cid in _ACID_GAS_IDS:
                p_eq = p_co2 if cid == "CO2" else p_h2s
                x_i = max(x.get(cid, 0.0), 1e-12)
                k[cid] = p_eq / (P * x_i)
                if k[cid] <= 0.0:  # zero loading: absent from the liquid, effectively all-vapor
                    k[cid] = _ALL_VAPOR_K
            elif cid in (_WATER_ID, amine_id):
                psat = _state.pure_psat(cid, T)
                k[cid] = (psat if psat is not None else _wilson_psat(cid, T)) / P
            else:
                k[cid] = self._henry_k(cid, T, P)
        return k

    def _henry_k(self, cid: str, T: float, P: float) -> float:
        """K-value of an insoluble volatile: Henry's law in water (Sander) or Raoult."""
        coefs = _sander_henry(_cas(cid))
        if coefs is None:
            psat = _state.pure_psat(cid, T)
            return (psat if psat is not None else _wilson_psat(cid, T)) / P
        return float(Henry_pressure(T, **coefs)) / P

    def _equilibrium_internal(
        self, z: dict[str, float], T: float, P: float
    ) -> tuple[Literal["liquid", "vapor", "two_phase"], float, dict[str, float], dict[str, float]]:
        """Phase split at (T, P) on the reactive K-values.

        Returns (state, vapour_fraction, liquid_x, vapour_y) with state one of
        "liquid" (single liquid, x == z), "vapor" (single vapour, y == z) or
        "two_phase" (x, y the phase compositions, full key set).

        Rachford-Rice on the current K-values gives the split; the acid-gas
        K-values depend on the liquid's own loading, so the liquid composition
        is iterated to a fixed point (tolerance 1e-12 on the loadings, cap 50
        iterations).  At convergence y_CO2 * P == p_CO2(loading) exactly.
        """
        amine_id = self._amine_id(self._support(z))
        if amine_id is None:  # pragma: no cover - callers gate on amine presence
            raise ValueError("the reactive flash requires an amine in the feed")
        # Seed the liquid from the SOLVENT basis: a stage's mixed overall is
        # gas-dominated (the spec's solvent-lean case) and seeding x at z makes
        # the first K set a hydrocarbon-as-liquid fantasy whose fixed point the
        # iteration never escapes (measured P1-09: the loadings two-cycled
        # 0.63-0.80 from the raw seed; from the solvent basis the same state
        # splits at a real beta ~0.74).
        solvent_total = z.get(amine_id, 0.0) + z.get("H2O", 0.0)
        if solvent_total > 0.0:
            x = {cid: f / solvent_total for cid, f in z.items() if cid in (amine_id, "H2O", "CO2", "H2S")}
            sx = sum(x.values())
            x = {cid: v / sx for cid, v in x.items()}
        else:  # pragma: no cover - callers gate on amine presence
            x = dict(z)
        x_a0 = x.get(amine_id, 0.0)
        a_use = (
            min(max(x.get("CO2", 0.0) / x_a0, 0.0), _MAX_LOADING) if x_a0 > 0.0 else 0.0,
            min(max(x.get("H2S", 0.0) / x_a0, 0.0), _MAX_LOADING) if x_a0 > 0.0 else 0.0,
        )
        hist: list[tuple[tuple[float, float], tuple[float, float]]] = []
        best: tuple[float, float, dict[str, float], dict[str, float]] | None = None
        for _ in range(_LOADING_MAX_ITER):
            k = self._k_values_internal(z, T, P, x)
            if sum(f * k[cid] for cid, f in z.items()) <= 1.0:
                return "liquid", 0.0, dict(x), dict(x)
            if sum(f / k[cid] for cid, f in z.items()) <= 1.0:
                return "vapor", 1.0, dict(z), dict(z)

            def rr(beta: float, k: dict[str, float] = k) -> float:
                return sum(f * (k[cid] - 1.0) / (1.0 + beta * (k[cid] - 1.0)) for cid, f in z.items())

            beta = brent_root(rr, 0.0, 1.0)
            y_raw: dict[str, float] = {}
            x_new: dict[str, float] = {}
            for cid, f in z.items():
                denom = 1.0 + beta * (k[cid] - 1.0)
                y_raw[cid] = max(f * k[cid] / denom, 0.0)
                x_new[cid] = max(y_raw[cid] / k[cid], 0.0)
            sy, sx = sum(y_raw.values()), sum(x_new.values())
            y = {cid: v / sy for cid, v in y_raw.items()}
            x_new = {cid: v / sx for cid, v in x_new.items()}
            x_a = x_new[amine_id]
            a_raw = (
                min(max(x_new.get("CO2", 0.0) / x_a, 0.0), _MAX_LOADING),
                min(max(x_new.get("H2S", 0.0) / x_a, 0.0), _MAX_LOADING),
            )
            residual = max(abs(a_raw[0] - a_use[0]), abs(a_raw[1] - a_use[1]))
            if residual <= _LOADING_TOL:
                return "two_phase", beta, x_new, y
            if best is None or residual < best[0]:
                best = (residual, beta, x_new, y)
            # Under-relaxed LOADING walk: the raw fixed point oscillates in the
            # trace-liquid regions saturation scans and solvent-lean stage
            # overalls pass through - the composition-substitution map there has
            # an unstable fixed point (an amine K of ~1e-5 next to an acid-gas K
            # of ~1e4 swings the loadings wildly). Walking the LOADING itself
            # and rebuilding the liquid from the damped loading folds the
            # two-cycle monotonically. Rebuild keeps the solvent and inert
            # fractions of the RR liquid and rescales the acid gases to the
            # damped loading.
            #
            # Wegstein-measured under-relaxation: a fixed weight cannot serve
            # both regimes the loading walk sees (measured P1-09: w=0.5 closed
            # a solvent-lean stage overall in ~8 iterations but crawled at
            # 0.905/iteration on the trace-gas two-cycle; w=0.05 the reverse).
            # The weight comes from the secant slope of the last two iterates
            # per loading component.
            hist.append((a_use, a_raw))
            w_co2 = _wegstein_w([h[0][0] for h in hist], [h[1][0] for h in hist])
            w_h2s = _wegstein_w([h[0][1] for h in hist], [h[1][1] for h in hist])
            a_use = (
                a_use[0] + w_co2 * (a_raw[0] - a_use[0]),
                a_use[1] + w_h2s * (a_raw[1] - a_use[1]),
            )
            if x_a > 0.0:
                x = dict(x_new)
                x["CO2"] = a_use[0] * x_a
                x["H2S"] = a_use[1] * x_a
                sx = sum(x.values())
                x = {cid: v / sx for cid, v in x.items()}
            else:  # pragma: no cover - degenerate amine-free liquid
                x = x_new
        if best is not None and best[0] <= _LOADING_ACCEPT_RESIDUAL:
            _r, beta_b, x_b, y_b = best
            return "two_phase", beta_b, x_b, y_b
        z_str = ", ".join(f"{cid}: {v:.6g}" for cid, v in sorted(z.items()))
        raise ValueError(
            f"amine reactive flash did not converge at T={T} K, P={P} Pa, z={{{z_str}}} "
            f"({_LOADING_MAX_ITER} loading fixed-point iterations)"
        )

    # -- flashes --------------------------------------------------------------

    def flash_pt(self, z: dict[str, float], T: float, P: float, molar_flow: float) -> StreamState:
        """PT flash: reactive equilibrium at temperature T (K), pressure P (Pa abs)."""
        if self._reactive_domain(z) is None:
            return self._carrier.flash_pt(z, T, P, molar_flow)
        key = ("pt", *_state.cache_key(z, T, P), round(molar_flow, 9))
        return cast(StreamState, self._cached(key, lambda: self._build_state(z, T, P, molar_flow)))

    def flash_ph(self, z: dict[str, float], P: float, H: float, molar_flow: float) -> StreamState:
        """PH flash: secant on T through the reactive flash enthalpy (carrier T guess)."""
        if self._reactive_domain(z) is None:
            return self._carrier.flash_ph(z, P, H, molar_flow)
        t = self._carrier.flash_ph(z, P, H, molar_flow).T

        def h_of(t_try: float) -> float:
            return self.flash_pt(z, t_try, P, molar_flow).enthalpy

        t_prev, h_prev = t, h_of(t)
        t_try = t_prev + _DERIV_D_T
        h_try = h_of(t_try)
        for _ in range(_LOADING_MAX_ITER):
            if abs(h_try - H) <= 1e-8 * max(abs(H), 1.0):
                return self.flash_pt(z, t_try, P, molar_flow)
            denom = h_try - h_prev
            if denom == 0.0:
                break
            t_next = t_try - (h_try - H) * (t_try - t_prev) / denom
            t_prev, h_prev = t_try, h_try
            t_try = t_next
            h_try = h_of(t_try)
        raise ValueError(f"amine reactive PH flash did not converge at P={P} Pa, H={H} J/mol")

    def flash_ps(self, z: dict[str, float], P: float, S: float, molar_flow: float) -> StreamState:
        """PS flash: secant on T through the reactive flash entropy (carrier T guess)."""
        if self._reactive_domain(z) is None:
            return self._carrier.flash_ps(z, P, S, molar_flow)
        t = self._carrier.flash_ps(z, P, S, molar_flow).T

        def s_of(t_try: float) -> float:
            return self.flash_pt(z, t_try, P, molar_flow).entropy

        t_prev, s_prev = t, s_of(t)
        t_try = t_prev + _DERIV_D_T
        s_try = s_of(t_try)
        for _ in range(_LOADING_MAX_ITER):
            if abs(s_try - S) <= 1e-8 * max(abs(S), 1.0):
                return self.flash_pt(z, t_try, P, molar_flow)
            denom = s_try - s_prev
            if denom == 0.0:
                break
            t_next = t_try - (s_try - S) * (t_try - t_prev) / denom
            t_prev, s_prev = t_try, s_try
            t_try = t_next
            s_try = s_of(t_try)
        raise ValueError(f"amine reactive PS flash did not converge at P={P} Pa, S={S} J/(mol K)")

    def flash_tvf(self, z: dict[str, float], T: float, vf: float, molar_flow: float) -> StreamState:
        """TVF flash: vapour fraction vf in [0, 1] at temperature T (K)."""
        if self._reactive_domain(z) is None:
            return self._carrier.flash_tvf(z, T, vf, molar_flow)
        if not 0.0 <= vf <= 1.0:
            raise ValueError(f"vapour fraction {vf} outside [0, 1]")
        p_bub = None if vf <= _VF_EDGE else self._boundary(z, "bubble", T=T).P
        p_dew = None if vf >= 1.0 - _VF_EDGE else self._boundary(z, "dew", T=T).P
        if p_bub is None and p_dew is None:
            return self.flash_pt(z, T, max(p_bub or 0.0, p_dew or 0.0), molar_flow)
        if p_bub is None or p_dew is None:
            return self.flash_pt(z, T, cast(float, p_bub or p_dew), molar_flow)

        def g(p: float) -> float:
            return self._equilibrium_internal(z, T, p)[1] - vf

        p = brent_root(g, min(p_dew, p_bub), max(p_dew, p_bub), xtol=_SATURATION_REL_TOL * 1e-2)
        return self.flash_pt(z, T, p, molar_flow)

    def flash_pvf(self, z: dict[str, float], P: float, vf: float, molar_flow: float) -> StreamState:
        """PVF flash: vapour fraction vf in [0, 1] at pressure P (Pa abs)."""
        if self._reactive_domain(z) is None:
            return self._carrier.flash_pvf(z, P, vf, molar_flow)
        if not 0.0 <= vf <= 1.0:
            raise ValueError(f"vapour fraction {vf} outside [0, 1]")
        t_bub = None if vf <= _VF_EDGE else self._boundary(z, "bubble", P=P).T
        t_dew = None if vf >= 1.0 - _VF_EDGE else self._boundary(z, "dew", P=P).T
        if t_bub is None and t_dew is None:
            return self.flash_pt(z, max(t_bub or 0.0, t_dew or 0.0), P, molar_flow)
        if t_bub is None or t_dew is None:
            return self.flash_pt(z, cast(float, t_bub or t_dew), P, molar_flow)

        def g(t: float) -> float:
            return self._equilibrium_internal(z, t, P)[1] - vf

        t = brent_root(g, min(t_dew, t_bub), max(t_dew, t_bub), xtol=_SATURATION_REL_TOL * 1e-2)
        return self.flash_pt(z, t, P, molar_flow)

    # -- saturation -----------------------------------------------------------

    def bubble_point(
        self, z: dict[str, float], *, T: float | None = None, P: float | None = None
    ) -> SaturationPoint:
        """Bubble point of an amine-bearing feed: exactly one of T (K) and P (Pa)."""
        if self._reactive_domain(z) is None:
            return self._carrier.bubble_point(z, T=T, P=P)
        return self._boundary(z, "bubble", T=T, P=P)

    def dew_point(
        self, z: dict[str, float], *, T: float | None = None, P: float | None = None
    ) -> SaturationPoint:
        """Dew point of an amine-bearing feed: exactly one of T (K) and P (Pa)."""
        if self._reactive_domain(z) is None:
            return self._carrier.dew_point(z, T=T, P=P)
        return self._boundary(z, "dew", T=T, P=P)

    def _boundary(
        self,
        z: dict[str, float],
        kind: Literal["bubble", "dew"],
        *,
        T: float | None = None,
        P: float | None = None,
    ) -> SaturationPoint:
        """Bubble/dew point solved on the package's own vapour fraction.

        The vapour fraction is continuous inside the two-phase envelope and
        plateaus at 1 (below the dew point / above the dew temperature) and 0
        (above the bubble point / below the bubble temperature).  The shared
        plateau-scan-then-bracketed-secant solver (``thermo.saturation``,
        spec P1-08) runs on this package's vf between Wilson-correlation
        bounds (defined past Tc).
        """
        if (T is None) == (P is None):
            raise ValueError("specify exactly one of T and P")
        non_acid = [cid for cid in self._support(z) if cid not in _ACID_GAS_IDS]

        def vf_at(x: float) -> float:
            return self._equilibrium_internal(z, T if T is not None else x, P if P is not None else x)[1]

        if T is not None:
            w = [_wilson_psat(cid, T) for cid in non_acid]
            bounds = (0.5 * min(w), 3.0 * max(w))
            label = f"T={T} K"
            unknown: Literal["P", "T"] = "P"
        else:
            p_given = cast(float, P)
            bounds_t = [t for cid in non_acid if (t := _wilson_T(cid, p_given)) is not None]
            if not bounds_t:
                raise SaturationError(f"no Wilson T bound at P={p_given} Pa for {sorted(z)}")
            bounds = (0.9 * min(bounds_t), 1.15 * max(bounds_t))
            label = f"P={p_given} Pa"
            unknown = "T"

        x_star = solve_saturation(vf_at, kind=kind, unknown=unknown, bounds=bounds, label=label)
        if T is not None:
            return SaturationPoint(T=T, P=x_star, kind=kind, incipient_composition=dict(z))
        return SaturationPoint(T=x_star, P=cast(float, P), kind=kind, incipient_composition=dict(z))

    # -- properties -----------------------------------------------------------

    def k_values(self, z: dict[str, float], T: float, P: float) -> dict[str, float] | None:
        """K_i = y_i/x_i at (T, P); None when the reactive flash is single-phase."""
        if self._reactive_domain(z) is None:
            return self._carrier.k_values(z, T, P)
        state, _vf, x, y = self._equilibrium_internal(z, T, P)
        if state != "two_phase":
            return None
        return {cid: (y[cid] / x[cid] if x[cid] > 0.0 else 0.0) for cid in z}

    def pure_psat(self, cid: str, T: float) -> float | None:
        """Pure-component vapour pressure (Pa) at T (K); None at or above Tc."""
        return _state.pure_psat(cid, T)

    def phase_props(self, composition: dict[str, float], T: float, P: float, kind: Any) -> PhaseProps:
        """Single-phase properties at (composition, T, P), built without flashing.

        Vapour and hydrocarbon-liquid phases are the carrier's.  The aqueous
        phase of an amine-bearing composition carries the heat of absorption of
        its dissolved acid gases (Gibbs-Helmholtz on the speciation equilibrium
        at fixed loading) and acid-gas fugacity-fraction ln_phi values.
        """
        key = ("pp", str(kind), *_state.cache_key(composition, T, P))
        return cast(
            PhaseProps,
            self._cached(key, lambda: self._phase_props(composition, T, P, kind)),
        )

    def _phase_props(self, composition: dict[str, float], T: float, P: float, kind: Any) -> PhaseProps:
        amine_id = self._amine_id(self._support(composition))
        if kind != PhaseKind.AQUEOUS or amine_id is None:
            return self._carrier.phase_props(composition, T, P, kind)
        base = self._carrier.phase_props(composition, T, P, PhaseKind.AQUEOUS)
        _aid, c_a, a_co2, a_h2s, p_co2, p_h2s = self._liquid_chemistry(composition, T, P)
        dh = self._absorption_enthalpies(amine_id, T, c_a, a_co2, a_h2s)
        extra_h = sum(composition.get(cid, 0.0) * dh[cid] for cid in _ACID_GAS_IDS)
        ln_phi = dict(base.ln_phi)
        for cid, p_eq in (("CO2", p_co2), ("H2S", p_h2s)):
            if composition.get(cid, 0.0) > 0.0:
                # f_i = p_eq_i * phi_i^V(p_eq_i); phi^V from the carrier at the
                # pure acid gas at its own partial pressure (zero-BIP limit).
                phi_v = self._carrier.phase_props({cid: 1.0}, T, p_eq, PhaseKind.VAPOR).ln_phi[cid]
                ln_phi[cid] = math.log(p_eq * math.exp(phi_v) / P)
        return base.model_copy(
            update={
                "enthalpy": base.enthalpy + extra_h,
                "cp": self._liquid_cp(composition, amine_id, T, P, c_a, a_co2, a_h2s),
                "ln_phi": ln_phi,
            }
        )

    def derivatives(
        self, composition: dict[str, float], T: float, P: float, kind: Any
    ) -> PropertyDerivatives:
        """d ln phi / dT and d ln phi / dP per component for one phase.

        Acid-gas derivatives on the aqueous phase are numeric central
        differences of d ln p_eq_i / dT at fixed loading and amine molarity
        (f_i is pressure-independent at fixed liquid state, so
        d ln phi_i / dP = -1/P).
        """
        amine_id = self._amine_id(self._support(composition))
        if kind != PhaseKind.AQUEOUS or amine_id is None:
            return self._carrier.derivatives(composition, T, P, kind)
        base = self._carrier.derivatives(composition, T, P, kind)
        d_t = dict(base.dlnphi_dT)
        d_p = dict(base.dlnphi_dP)
        _aid, c_a, a_co2, a_h2s, _p1, _p2 = self._liquid_chemistry(composition, T, P)
        for idx, cid in enumerate(_ACID_GAS_IDS):
            if composition.get(cid, 0.0) <= 0.0:
                continue
            p_hi = self._pressures(T + _DERIV_D_T, c_a, a_co2, a_h2s, amine_id)[idx]
            p_lo = self._pressures(T - _DERIV_D_T, c_a, a_co2, a_h2s, amine_id)[idx]
            if min(p_hi, p_lo) > 0.0:
                d_t[cid] = (math.log(p_hi) - math.log(p_lo)) / (2.0 * _DERIV_D_T)
            d_p[cid] = -1.0 / P
        return PropertyDerivatives(dlnphi_dT=d_t, dlnphi_dP=d_p)

    # -- state construction ---------------------------------------------------

    def _build_state(self, z: dict[str, float], T: float, P: float, molar_flow: float) -> StreamState:
        state, beta, x, y = self._equilibrium_internal(z, T, P)
        if state == "vapor":
            props = self._carrier.phase_props(z, T, P, PhaseKind.VAPOR)
            phase = _phase(PhaseKind.VAPOR, 1.0, z, props)
            return StreamState(
                T=T,
                P=P,
                molar_flow=molar_flow,
                composition=dict(z),
                vapor_fraction=1.0,
                enthalpy=props.enthalpy,
                entropy=props.entropy,
                phases=[phase],
            )
        liquid_props = self.phase_props(x, T, P, PhaseKind.AQUEOUS)
        liquid = _phase(PhaseKind.AQUEOUS, 1.0 - beta, x, liquid_props)
        if state == "liquid":
            return StreamState(
                T=T,
                P=P,
                molar_flow=molar_flow,
                composition=dict(z),
                vapor_fraction=0.0,
                enthalpy=liquid_props.enthalpy,
                entropy=liquid_props.entropy,
                phases=[liquid],
            )
        vapor_props = self._carrier.phase_props(y, T, P, PhaseKind.VAPOR)
        vapor = _phase(PhaseKind.VAPOR, beta, y, vapor_props)
        return StreamState(
            T=T,
            P=P,
            molar_flow=molar_flow,
            composition=dict(z),
            vapor_fraction=beta,
            enthalpy=beta * vapor_props.enthalpy + (1.0 - beta) * liquid_props.enthalpy,
            entropy=beta * vapor_props.entropy + (1.0 - beta) * liquid_props.entropy,
            phases=[vapor, liquid],
        )

    def _liquid_cp(
        self,
        x: dict[str, float],
        amine_id: str,
        T: float,
        P: float,
        c_a: float,
        a_co2: float,
        a_h2s: float,
    ) -> float:
        """Liquid cp by numeric dH/dT of the absorption-augmented enthalpy.

        The absorption contribution is evaluated at the nominal amine molarity
        and loadings (the Gibbs-Helmholtz derivative holds them fixed).
        """

        def h_of(t_try: float) -> float:
            base = self._carrier.phase_props(x, t_try, P, PhaseKind.AQUEOUS).enthalpy
            dh = self._absorption_enthalpies(amine_id, t_try, c_a, a_co2, a_h2s)
            return base + sum(x.get(cid, 0.0) * dh[cid] for cid in _ACID_GAS_IDS)

        return (h_of(T + _DERIV_D_T) - h_of(T - _DERIV_D_T)) / (2.0 * _DERIV_D_T)

    def _absorption_enthalpies(
        self, amine_id: str, T: float, c_a: float, a_co2: float, a_h2s: float
    ) -> dict[str, float]:
        """Heat of absorption (J/mol acid gas) by Gibbs-Helmholtz at fixed loading.

        -R * d ln p_eq / d(1/T) at constant amine molarity and loading — the
        speciation equilibrium's own van 't Hoff content (Kent-Eisenberg /
        electrolyte-NRTL apparent constants).  Central difference in 1/T with
        a 0.5 K half step (the spec's numeric procedure).
        """
        half = _DERIV_D_T / (T * T)
        t_hi = 1.0 / (1.0 / T - half)
        t_lo = 1.0 / (1.0 / T + half)
        out: dict[str, float] = {}
        for idx, cid in enumerate(_ACID_GAS_IDS):
            alpha = a_co2 if cid == "CO2" else a_h2s
            if alpha <= 0.0:
                out[cid] = 0.0
                continue
            p_hi = self._pressures(t_hi, c_a, a_co2, a_h2s, amine_id)[idx]
            p_lo = self._pressures(t_lo, c_a, a_co2, a_h2s, amine_id)[idx]
            if min(p_hi, p_lo) <= 0.0:
                raise ValueError(f"speciation pressure vanished for {cid} at T={T} K")
            out[cid] = -_state.R_IDEAL * (math.log(p_hi) - math.log(p_lo)) / (1.0 / t_hi - 1.0 / t_lo)
        return out

    # -- public helpers (units, tests) ----------------------------------------

    def acid_gas_partial_pressures(
        self, z_liquid: dict[str, float], T: float, P: float = 101325.0
    ) -> dict[str, float]:
        """Equilibrium (p_CO2, p_H2S) in Pa over the liquid composition at T (K).

        The liquid's own loadings (clamped to the chemistry window) and
        solvent-basis amine molarity (physical liquid densities, ideal mass
        mixing — see :func:`_amine_molarity`).
        """
        _aid, _c, _a1, _a2, p_co2, p_h2s = self._liquid_chemistry(z_liquid, T, P)
        return {"CO2": p_co2, "H2S": p_h2s}

    def _solvent_basis(self, x: dict[str, float]) -> tuple[str, float]:
        """(amine id, amine molarity mol/m3) of the liquid's amine + water solvent."""
        amine_id = self._amine_id(self._support(x))
        if amine_id is None:
            raise ValueError("no amine in the liquid composition")
        return amine_id, self._amine_molarity(x, amine_id)

    def equilibrium_pressures(
        self, x_liquid: dict[str, float], T: float, co2_loading: float, h2s_loading: float
    ) -> dict[str, float]:
        """Equilibrium (p_CO2, p_H2S) in Pa over the liquid's amine at the GIVEN loadings.

        The unit-facing chemistry call: like :meth:`acid_gas_partial_pressures`
        but with the loadings supplied (feasibility floors and ceilings use
        loadings that differ from the liquid's own).  Loadings are clamped to
        the chemistry window; an e-NRTL package raises its typed H2S error for
        h2s_loading > 0.
        """
        amine_id, c_a = self._solvent_basis(x_liquid)
        a_co2 = min(max(co2_loading, 0.0), _MAX_LOADING)
        a_h2s = min(max(h2s_loading, 0.0), _MAX_LOADING)
        p_co2, p_h2s = self._pressures(T, c_a, a_co2, a_h2s, amine_id)
        return {"CO2": p_co2, "H2S": p_h2s}

    def equilibrium_loadings(
        self, x_liquid: dict[str, float], T: float, p_co2: float, p_h2s: float
    ) -> tuple[float, float]:
        """Max (CO2, H2S) loadings the liquid's amine supports at the given partial pressures (Pa).

        Inverse of the speciation equilibrium at the liquid's own amine
        molarity — the circulation ceiling a contacting gas imposes.
        """
        amine_id, c_a = self._solvent_basis(x_liquid)
        if self._model == ENRTL:
            try:
                return _enrtl_loadings(T, c_a, p_co2, p_h2s, amine=amine_id)
            except ValueError as exc:
                raise AmineChemistryError(
                    f"amine speciation left its chemistry window at T={T} K (speciation bracket: {exc})"
                ) from exc
        try:
            return _ke_loadings(T, c_a, p_co2, p_h2s, amine=amine_id)
        except ValueError as exc:
            raise AmineChemistryError(
                f"amine speciation left its chemistry window at T={T} K (speciation bracket: {exc})"
            ) from exc

    def heat_of_absorption(
        self, z_liquid: dict[str, float], T: float, P: float = 101325.0
    ) -> dict[str, float]:
        """Heat of absorption (J/mol) of each acid gas held by the liquid at T (K)."""
        amine_id, c_a, a_co2, a_h2s, _p1, _p2 = self._liquid_chemistry(z_liquid, T, P)
        return self._absorption_enthalpies(amine_id, T, c_a, a_co2, a_h2s)


# -- module-level numeric helpers -------------------------------------------------


def _registry_get(kind: str, name: str) -> Any:
    """Late registry lookup (the carrier class, at instance-creation time)."""
    from ngdesign.registry import get as registry_get

    return registry_get(kind, name)


def _phase(kind: PhaseKind, mole_fraction: float, composition: dict[str, float], props: PhaseProps) -> Phase:
    """Contract-v2 Phase from a PhaseProps build (P1-01's state assembly)."""
    return Phase(
        kind=kind,
        mole_fraction=mole_fraction,
        composition=dict(composition),
        density=props.density,
        viscosity=props.viscosity,
        z_factor=props.z_factor,
        molecular_weight=props.molecular_weight,
        enthalpy=props.enthalpy,
        entropy=props.entropy,
        cp=props.cp,
        ln_phi=dict(props.ln_phi),
    )


# -- registrations ----------------------------------------------------------------
#
# The spec's registration layout (ngdesign/thermo/amine_ke.py etc.) would need
# ngdesign.thermo -> ngdesign.amine imports, which the Phase-0 layers contract
# (.importlinter) forbids — lower layers never import higher ones, and
# ignore_imports lines are locked out by AGENTS.md.  Registration therefore
# lives here, next to the class, and reaches every consumer because the amine
# package's __init__ re-exports these plugins.


@register("thermo", "amine_ke")
class AmineKEPackage(AmineReactivePackage):
    """Amine reactive absorption on the Kent-Eisenberg chemistry (MDEA/MEA/DEA, CO2+H2S)."""


@register("thermo", "amine_enrtl")
class AmineENRTLPackage(AmineReactivePackage):
    """Amine reactive absorption on electrolyte-NRTL (MDEA/MEA, CO2-only)."""

    model = ENRTL
