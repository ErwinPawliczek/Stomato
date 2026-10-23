"""Helmholtz-family property packages (spec T-04): reference equations of state.

Four adapters implement the ``Thermo`` protocol directly (they share none of the
cubic ``ThermoSurfaceMixin`` flasher plumbing, which is bound to `thermo`-library
flasher objects):

- :class:`IAPWSPackage` — pure water, two formulations through options
  ``formulation``: ``IAPWS95`` (CoolProp ``HEOS`` water, the IAPWS-95
  formulation) and ``IF97`` (CoolProp ``IF97::Water``). thermo 0.6.1's
  ``IAPWS95Gas``/``IAPWS95Liquid`` wrappers pick identical EOS roots inside the
  two-phase region (measured), so they cannot express the requested-phase
  property surface the harness compares; the CoolProp water backends can via
  ``specify_phase``. The IF97 backend exposes no fugacity coefficients, so the
  IF97 row's ``ln_phi`` stays empty (documented, not hidden).
- :class:`CoolPropPackage` — CoolProp ``HEOS`` pure fluids and mixtures
  (multifluid Helmholtz equations with fitted binary interactions).
- :class:`GERGPackage` — the same engine restricted to the dry sour natural-gas
  slate: CoolProp's multifluid mixture model is the GERG-2008-quality path here;
  an exact GERG-2008 backend arrives with the teqp bridge (T-07).
- :class:`BWRSPackage` — in-house Starling (1973) BWRS over the ORO-5249-2
  (1976) Table 5 parameter set for the ten registry-reachable compounds,
  evaluated in imperial units (psia, °R, lb-mol/ft³) and converted at the
  boundary. Pure saturation comes from an equal-fugacity bisection on the EOS's
  own pressure function; mixtures flash by successive substitution on K values.

Each package refuses components outside its parameter set with the component
named (:class:`ComponentNotSupported`). CoolProp is imported lazily inside the
evaluation paths; the module imports cleanly without CoolProp installed.
Building a CoolProp-backed row without the extra raises
:class:`CoolPropUnavailable` naming the optional extra.

Absolute enthalpies/entropies: the CoolProp-backed packages use CoolProp's
per-fluid reference (the validation cases bound to them compare reference-free
properties: density, Cp, saturation pressures); BWRSPackage integrates the
`thermo` ideal-gas heat-capacity correlations with H_ig(298.15 K) = 0 and
S_ig(298.15 K, 1 bar) = 0 as its reference.

:func:`unavailable_package` backs the five family-D catalogue rows whose
backend has no implementation yet: the row loads (the catalogue records the
method, status and provenance) and every property call raises
:class:`UnavailableBackend` naming the row.
"""

from __future__ import annotations

import importlib.util
import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ClassVar, Final, Literal

from ngdesign.contracts import Phase, PhaseKind, StreamState
from ngdesign.contracts.thermo import PhaseProps, PropertyDerivatives, SaturationError, SaturationPoint
from ngdesign.thermo._state import R_IDEAL, _constants_package, _records

__all__ = [
    "ASMESteamPackage",
    "BWRSPackage",
    "CoolPropPackage",
    "CoolPropUnavailable",
    "ComponentNotSupported",
    "GERGPackage",
    "IAPWSPackage",
    "UnavailableBackend",
    "UnavailablePackage",
    "coolprop_available",
]

# ---------------------------------------------------------------------------
# Errors and CoolProp plumbing
# ---------------------------------------------------------------------------


class ComponentNotSupported(ValueError):
    """A package was asked for a component outside its parameter set."""


class CoolPropUnavailable(ImportError):
    """A CoolProp-backed row was built without the optional CoolProp extra."""


class UnavailableBackend(NotImplementedError):
    """A catalogue placeholder row's backend has no implementation yet."""


def coolprop_available() -> bool:
    """True when the optional CoolProp extra is importable (no heavy import)."""
    return importlib.util.find_spec("CoolProp") is not None


def _require_coolprop() -> None:
    if not coolprop_available():
        raise CoolPropUnavailable(
            "CoolProp is required for this helmholtz-family row; install the optional"
            " extra (uv sync --extra coolprop)"
        )


#: Registry component id -> CoolProp fluid name (HEOS backend).
_COOLPROP_NAMES: Final[dict[str, str]] = {
    "H2O": "Water",
    "N2": "Nitrogen",
    "CO2": "CarbonDioxide",
    "H2S": "H2S",
    "C1": "Methane",
    "C2": "Ethane",
    "C3": "Propane",
    "iC4": "Isobutane",
    "nC4": "n-Butane",
    "iC5": "Isopentane",
    "nC5": "n-Pentane",
}
# C6+ is deliberately absent: it is a lumped pseudo-component, not a CoolProp
# fluid. Mapping the cut to n-hexane fabricates dew points (the L4 slice-feed
# cross-check flagged a 27% deviation against the cubic rows); the HEOS row
# refuses C6+ by name, consistent with GERGPackage and the family's
# "never silently approximated" rule.

#: The natural-gas slate GERGPackage declares support for (water belongs to the
#: IAPWS rows; the L4 slice feed's H2O and C6+ are refused with those names).
_GERG_IDS: Final[frozenset[str]] = frozenset(
    ("N2", "CO2", "H2S", "C1", "C2", "C3", "iC4", "nC4", "iC5", "nC5")
)


def _import_coolprop() -> object:
    """Import CoolProp lazily; a clear error when the optional extra is absent."""
    try:
        import CoolProp  # noqa: PLC0415 - lazy by design (spec T-04)

        return CoolProp
    except ImportError as exc:  # pragma: no cover - exercised without the extra
        raise CoolPropUnavailable(
            "CoolProp is required for this helmholtz-family row; install the optional"
            " extra (uv sync --extra coolprop)"
        ) from exc


# ---------------------------------------------------------------------------
# Single-phase property container shared by every adapter
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _SinglePhase:
    """One phase's properties at (composition, T, P); SI units (P1-05)."""

    composition: dict[str, float]
    molecular_weight: float  # g/mol
    density: float  # kg/m3
    enthalpy: float  # J/mol
    entropy: float  # J/(mol K)
    cp: float  # J/(mol K)
    z_factor: float
    ln_phi: dict[str, float]

    def gibbs_at(self, T: float) -> float:
        """G = H - T*S (J/mol)."""
        return self.enthalpy - T * self.entropy


# ---------------------------------------------------------------------------
# Shared Thermo-protocol surface over per-package primitives
# ---------------------------------------------------------------------------


class _HelmholtzSurface:
    """The Thermo protocol over two primitives: ``_single_phase`` and ``_psat``.

    Flashes are root problems on the fugacity surface: bubble/dew pressures from
    successive substitution on K values (exact QT equilibria when the backend
    provides them), dome identification from those boundaries, two-phase splits
    from the Rachford-Rice equation, and T-solves by bracketed bisection. Pure
    feeds short-circuit to the package's own saturation pressure, so pure
    bubble/dew/flash paths are exact by construction (L0 pure_psat_limit).
    """

    SUPPORTED: ClassVar[frozenset[str]] = frozenset()
    #: PhaseKind reported for the liquid root (AQUEOUS for the water packages).
    LIQUID_KIND: ClassVar[PhaseKind] = PhaseKind.HC_LIQUID
    #: Memoized boundary temperatures, per instance: (ids, xs, P, kind) -> T.
    _constants_cache: tuple[tuple[str, ...], Any] | None = None
    _tsat_cache: dict[tuple[tuple[str, ...], tuple[float, ...], float, str], float]

    # -- primitives ---------------------------------------------------------

    def _single_phase(
        self, ids: tuple[str, ...], xs: tuple[float, ...], T: float, P: float, phase: str
    ) -> _SinglePhase:
        """Properties of the requested phase ("vapor" | "liquid") at the state."""
        raise NotImplementedError

    def _psat(self, cid: str, T: float) -> float | None:
        """Pure-component saturation pressure (Pa) or None above the critical."""
        raise NotImplementedError

    def _tsat(self, ids: tuple[str, ...], xs: tuple[float, ...], P: float, kind: str) -> float:
        """Saturation temperature (K) at P: bracketed bisection on the boundary pressure.

        The boundary curve exists only inside the two-phase region (it turns over
        at the cricondenbar). The scan walks a bounded log grid, treats a failed
        boundary solve past the first valid point as the end of the curve, and
        bisects the first sign change on valid points.
        """
        try:
            cache = self._tsat_cache
        except AttributeError:
            cache = self._tsat_cache = {}
        key = (ids, xs, P, kind)
        if key in cache:
            return cache[key]
        if kind == "bubble":

            def residual(t: float) -> float:
                return self._bubble_pressure(ids, xs, t) - P
        else:

            def residual(t: float) -> float:
                return self._dew_pressure(ids, xs, t) - P

        def try_residual(t: float) -> float | None:
            try:
                f = residual(t)
            except SaturationError:
                return None
            return f if math.isfinite(f) else None  # a NaN residual is "no boundary here"

        t_start, t_stop = 90.0, 900.0
        steps = 24
        prev_t: float | None = None
        prev_f: float | None = None
        bracket: tuple[float, float] | None = None
        for i in range(steps + 1):
            t = t_start * (t_stop / t_start) ** (i / steps)
            f = try_residual(t)
            if f is None:
                if prev_t is not None:
                    break  # the curve ended (cricondenbar / critical region)
                continue  # the curve has not started yet
            if prev_f is not None and prev_t is not None and prev_f * f < 0.0:
                bracket = (prev_t, t)
                break
            prev_t, prev_f = t, f
        if bracket is None:
            raise SaturationError(
                f"no {kind} boundary found for {ids} at P={P:g} Pa within {t_start:g}-{t_stop:g} K"
            )
        lo, hi = bracket
        f_lo = try_residual(lo)
        if f_lo is None:
            raise SaturationError(f"{kind} boundary vanished while bracketing {ids} at P={P:g} Pa")
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            f_mid = try_residual(mid)
            if f_mid is None:
                hi = mid  # the curve ended between lo and mid: pull the bracket in
                continue
            if f_lo * f_mid <= 0.0:
                hi = mid
            else:
                lo, f_lo = mid, f_mid
            if hi - lo < 1e-10:
                break
        t_result = 0.5 * (lo + hi)
        if len(cache) > 512:
            cache.clear()
        cache[key] = t_result
        return t_result

    # -- support checks -----------------------------------------------------

    def _support(self, z: dict[str, float]) -> tuple[tuple[str, ...], tuple[float, ...]]:
        """Sorted (ids, fractions); refuse unknown components with the name."""
        unknown = sorted(set(z) - self.SUPPORTED)
        if unknown:
            raise ComponentNotSupported(
                f"{type(self).__name__} has no parameters for component(s) {unknown};"
                f" supported: {sorted(self.SUPPORTED)}"
            )
        ids = tuple(sorted(cid for cid, x in z.items() if x > 0.0))
        xs = tuple(z[cid] for cid in ids)
        return ids, xs

    # -- pure-feed helpers --------------------------------------------------

    def _psat_or_raise(self, cid: str, T: float) -> float:
        psat = self._psat(cid, T)
        if psat is None:
            raise SaturationError(f"{cid} is supercritical at T={T} K; no saturation pressure")
        return psat

    def _is_pure(self, ids: tuple[str, ...]) -> bool:
        return len(ids) == 1

    # -- saturation points --------------------------------------------------

    def bubble_point(
        self, z: dict[str, float], *, T: float | None = None, P: float | None = None
    ) -> SaturationPoint:
        ids, xs = self._support(z)
        if T is not None and P is None:
            p = self._bubble_pressure(ids, xs, T)
            inc = self._incipient(ids, xs, T, p, "bubble")
            return SaturationPoint(T=T, P=p, kind="bubble", incipient_composition=inc)
        if P is not None and T is None:
            t = self._solve_T(lambda t: self._bubble_pressure(ids, xs, t) - P, P)
            inc = self._incipient(ids, xs, t, P, "bubble")
            return SaturationPoint(T=t, P=P, kind="bubble", incipient_composition=inc)
        raise ValueError("bubble_point needs exactly one of T, P")

    def dew_point(
        self, z: dict[str, float], *, T: float | None = None, P: float | None = None
    ) -> SaturationPoint:
        ids, xs = self._support(z)
        if T is not None and P is None:
            p = self._dew_pressure(ids, xs, T)
            inc = self._incipient(ids, xs, T, p, "dew")
            return SaturationPoint(T=T, P=p, kind="dew", incipient_composition=inc)
        if P is not None and T is None:
            t = self._solve_T(lambda t: self._dew_pressure(ids, xs, t) - P, P)
            inc = self._incipient(ids, xs, t, P, "dew")
            return SaturationPoint(T=t, P=P, kind="dew", incipient_composition=inc)
        raise ValueError("dew_point needs exactly one of T, P")

    def _bubble_pressure(self, ids: tuple[str, ...], xs: tuple[float, ...], T: float) -> float:
        """Bubble pressure at T: the package's Psat for pure feeds, SS for mixtures."""
        if self._is_pure(ids):
            return self._psat_or_raise(ids[0], T)
        return self._ss_boundary(ids, xs, T, "bubble")

    def _dew_pressure(self, ids: tuple[str, ...], xs: tuple[float, ...], T: float) -> float:
        if self._is_pure(ids):
            return self._psat_or_raise(ids[0], T)
        return self._ss_boundary(ids, xs, T, "dew")

    def _ss_boundary(self, ids: tuple[str, ...], xs: tuple[float, ...], T: float, kind: str) -> float:
        """Successive substitution on the K values at fixed T toward K-fraction sum 1."""
        p = self._wilson_pressure(ids, xs, T)
        k = [self._wilson_k(ids[i], T, p) for i in range(len(ids))]
        for _ in range(300):
            vapor = [min(max(ki * xsi, 1e-14), 1.0) for ki, xsi in zip(k, xs, strict=True)]
            vapor_sum = sum(vapor)
            y = [v / vapor_sum for v in vapor]
            try:
                phi_l = self._single_phase(ids, xs, T, p, "liquid").ln_phi
                phi_v = self._single_phase(ids, tuple(y), T, p, "vapor").ln_phi
            except (ValueError, ArithmeticError) as exc:
                raise SaturationError(
                    f"successive substitution left the single-root region for {ids} at T={T} K"
                ) from exc
            k_new = [math.exp(phi_l[c] - phi_v[c]) for c in ids]
            if kind == "bubble":
                step = sum(xsi * ki for xsi, ki in zip(xs, k_new, strict=True))
            else:
                step = sum(xsi / ki for xsi, ki in zip(xs, k_new, strict=True))
            p = min(max(p * step, 1e3), 2e9)
            err = max(abs(a / b - 1.0) for a, b in zip(k_new, k, strict=True))
            k = k_new
            if err < 1e-11 and abs(step - 1.0) < 1e-9:
                return p
        raise SaturationError(f"successive substitution did not converge for {ids} at T={T} K")

    def _incipient(
        self, ids: tuple[str, ...], xs: tuple[float, ...], T: float, P: float, kind: str
    ) -> dict[str, float]:
        """Composition of the appearing phase at a converged saturation point."""
        if self._is_pure(ids):
            return {ids[0]: 1.0}
        if kind == "bubble":
            phi_l = self._single_phase(ids, xs, T, P, "liquid").ln_phi
            phi_v = self._single_phase(ids, xs, T, P, "vapor").ln_phi
            k = [math.exp(phi_l[c] - phi_v[c]) for c in ids]
            raw = [xsi * ki for xsi, ki in zip(xs, k, strict=True)]
        else:
            phi_l = self._single_phase(ids, xs, T, P, "liquid").ln_phi
            phi_v = self._single_phase(ids, xs, T, P, "vapor").ln_phi
            k = [math.exp(phi_l[c] - phi_v[c]) for c in ids]
            raw = [xsi / ki for xsi, ki in zip(xs, k, strict=True)]
        total = sum(raw)
        if total <= 0.0:
            raise SaturationError(f"incipient composition collapsed for {ids} at T={T} K")
        return {c: v / total for c, v in zip(ids, raw, strict=True)}

    def _wilson_k(self, cid: str, T: float, P: float) -> float:
        """Wilson-correlation K initialiser; needs the component's critical data."""
        constants = self._constants(ids=(cid,))
        tc = float(constants.Tcs[0])
        pc = float(constants.Pcs[0])
        omega = float(constants.omegas[0])
        tr = T / tc
        return pc / P * math.exp(5.373 * (1.0 + omega) * (1.0 - 1.0 / tr))

    def _wilson_pressure(self, ids: tuple[str, ...], xs: tuple[float, ...], T: float) -> float:
        p = 0.0
        for i, cid in enumerate(ids):
            constants = self._constants(ids=(cid,))
            tc, pc, omega = constants.Tcs[0], constants.Pcs[0], constants.omegas[0]
            tr = T / tc
            p += xs[i] * pc * math.exp(5.373 * (1.0 + omega) * (1.0 - 1.0 / tr))
        return min(max(p, 1e3), 2e9)

    def _constants(self, ids: tuple[str, ...]) -> Any:
        """Component constants package (thermo databank) for Wilson initialisers."""
        cache = getattr(self, "_constants_cache", None)
        if cache is None or cache[0] != ids:
            constants, _ = _constants_package(_records(ids, ()))
            cache = (ids, constants)
            self._constants_cache = cache
        return cache[1]

    def _solve_T(self, residual: Callable[[float], float], P: float) -> float:
        """Bracketed bisection on a saturation residual in T (residual(T) - P form)."""
        del P
        t_lo, t_hi = 200.0, 400.0
        f_lo = residual(t_lo)
        # geometric expansion for a bracket, then bisection to machine precision
        for _ in range(40):
            f_hi = residual(t_hi)
            if f_lo * f_hi < 0.0:
                break
            t_hi *= 1.3
        else:
            raise SaturationError("no saturation temperature bracket found below the expansion cap")
        for _ in range(200):
            mid = 0.5 * (t_lo + t_hi)
            f_mid = residual(mid)
            if f_lo * f_mid <= 0.0:
                t_hi = mid
            else:
                t_lo, f_lo = mid, f_mid
            if t_hi - t_lo < 1e-10:
                return 0.5 * (t_lo + t_hi)
        return 0.5 * (t_lo + t_hi)

    # -- PT flash -----------------------------------------------------------

    def flash_pt(self, z: dict[str, float], T: float, P: float, molar_flow: float) -> StreamState:
        ids, xs = self._support(z)
        try:
            p_bub = self._bubble_pressure(ids, xs, T)
            p_dew = self._dew_pressure(ids, xs, T)
        except SaturationError:
            # above the mixture critical temperature no two-phase region exists at
            # this T: keep the single phase with the lower molar Gibbs free energy
            return self._stable_stream(ids, xs, T, P, molar_flow)
        if P >= p_bub:
            return self._single_stream(ids, xs, T, P, "liquid", molar_flow)
        if P <= p_dew:
            return self._single_stream(ids, xs, T, P, "vapor", molar_flow)
        beta, x, y, ln_phi_l, ln_phi_v = self._rr_split(ids, xs, T, P)
        return self._two_phase_stream(ids, x, y, beta, ln_phi_l, ln_phi_v, T, P, molar_flow)

    def _stable_stream(
        self, ids: tuple[str, ...], xs: tuple[float, ...], T: float, P: float, molar_flow: float
    ) -> StreamState:
        """Single-phase fallback when no saturation exists at T (supercritical mixture)."""
        gibbs: list[tuple[float, str]] = []
        for phase in ("liquid", "vapor"):
            try:
                props = self._single_phase(ids, xs, T, P, phase)
            except SaturationError:
                continue
            gibbs.append((props.enthalpy - T * props.entropy, phase))
        if not gibbs:
            raise SaturationError(f"no stable single phase at T={T} K, P={P} Pa for {ids}")
        return self._single_stream(ids, xs, T, P, min(gibbs)[1], molar_flow)

    def _rr_split(
        self, ids: tuple[str, ...], xs: tuple[float, ...], T: float, P: float
    ) -> tuple[float, tuple[float, ...], tuple[float, ...], dict[str, float], dict[str, float]]:
        """Two-phase split at (T, P) inside the dome: beta, x, y and both ln_phi maps."""
        k = [self._wilson_k(cid, T, P) for cid in ids]
        for _ in range(200):
            beta = self._rr_beta(xs, k)
            x = [xsi / (1.0 + beta * (ki - 1.0)) for xsi, ki in zip(xs, k, strict=True)]
            y_raw = [ki * xi for ki, xi in zip(k, x, strict=True)]
            y_sum = sum(y_raw)
            y = [v / y_sum for v in y_raw]
            phi_l = self._single_phase(ids, tuple(x), T, P, "liquid").ln_phi
            phi_v = self._single_phase(ids, tuple(y), T, P, "vapor").ln_phi
            k_new = [math.exp(phi_l[c] - phi_v[c]) for c in ids]
            err = max(abs(a / b - 1.0) for a, b in zip(k_new, k, strict=True))
            k = k_new
            if err < 1e-11:
                break
        beta = self._rr_beta(xs, k)
        x = [xsi / (1.0 + beta * (ki - 1.0)) for xsi, ki in zip(xs, k, strict=True)]
        y_raw = [ki * xi for ki, xi in zip(k, x, strict=True)]
        y_sum = sum(y_raw)
        y = [v / y_sum for v in y_raw]
        phi_l = self._single_phase(ids, tuple(x), T, P, "liquid").ln_phi
        phi_v = self._single_phase(ids, tuple(y), T, P, "vapor").ln_phi
        return beta, tuple(x), tuple(y), phi_l, phi_v

    @staticmethod
    def _rr_beta(xs: tuple[float, ...], k: list[float]) -> float:
        """Rachford-Rice vapour fraction by bisection on [0, 1]."""
        lo, hi = 0.0, 1.0

        def f(beta: float) -> float:
            return sum(xsi * (ki - 1.0) / (1.0 + beta * (ki - 1.0)) for xsi, ki in zip(xs, k, strict=True))

        f_lo, f_hi = f(lo), f(hi)
        if f_lo <= 0.0:
            return 0.0
        if f_hi >= 0.0:
            return 1.0
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            f_mid = f(mid)
            if abs(f_mid) < 1e-12:
                return mid
            if f_lo * f_mid <= 0.0:
                hi = mid
            else:
                lo, f_lo = mid, f_mid
        return 0.5 * (lo + hi)

    # -- PH / PS flashes ----------------------------------------------------

    def flash_ph(self, z: dict[str, float], P: float, H: float, molar_flow: float) -> StreamState:
        return self._flash_H_or_S(z, P, H, molar_flow, "enthalpy")

    def flash_ps(self, z: dict[str, float], P: float, S: float, molar_flow: float) -> StreamState:
        return self._flash_H_or_S(z, P, S, molar_flow, "entropy")

    def _flash_H_or_S(
        self, z: dict[str, float], P: float, target: float, molar_flow: float, which: str
    ) -> StreamState:
        ids, xs = self._support(z)
        t_bub = self._tsat(ids, xs, P, "bubble")
        t_dew = self._tsat(ids, xs, P, "dew")

        def quantity(T: float, phase: str) -> float:
            props = self._single_phase(ids, xs, T, P, phase)
            return props.enthalpy if which == "enthalpy" else props.entropy

        h_liq_sat = quantity(t_bub, "liquid")
        h_vap_sat = quantity(t_dew, "vapor")
        if min(h_liq_sat, h_vap_sat) <= target <= max(h_liq_sat, h_vap_sat):
            # inside the two-phase envelope: pure feeds sit exactly at Tsat, mixtures
            # bisect T on the two-phase enthalpy (monotonic from the RR split)
            if abs(t_bub - t_dew) < 1e-9:
                beta = (target - h_liq_sat) / (h_vap_sat - h_liq_sat)
                beta = min(max(beta, 0.0), 1.0)
                p_sat = self._bubble_pressure(ids, xs, t_bub)
                props_l = self._single_phase(ids, xs, t_bub, p_sat, "liquid")
                props_v = self._single_phase(ids, xs, t_bub, p_sat, "vapor")
                return self._two_phase_stream(
                    ids, xs, xs, beta, props_l.ln_phi, props_v.ln_phi, t_bub, p_sat, molar_flow
                )
            lo, hi = min(t_bub, t_dew), max(t_bub, t_dew)

            def residual(T: float) -> float:
                state = self._dome_state(ids, xs, T, P)
                q = state.enthalpy if which == "enthalpy" else state.entropy
                return q - target

            f_lo = residual(lo)
            for _ in range(200):
                mid = 0.5 * (lo + hi)
                f_mid = residual(mid)
                if f_lo * f_mid <= 0.0:
                    hi = mid
                else:
                    lo, f_lo = mid, f_mid
                if hi - lo < 1e-10:
                    break
            t_mid = 0.5 * (lo + hi)
            return self._dome_state(ids, xs, t_mid, P, molar_flow=molar_flow)
        # single phase: bisect T on the branch the target lies on (a target below
        # the bubble-line quantity is subcooled liquid, above the dew-line is superheated vapour).
        # Brackets expand from the saturation edge where the requested root exists.
        branch = "liquid" if target < h_liq_sat else "vapor"
        if branch == "liquid":
            t_hi = t_bub
            t_lo = t_bub
            for _ in range(60):
                if quantity(t_lo, branch) <= target:
                    break
                t_lo -= max(1.0, 0.02 * t_lo)
            else:
                raise SaturationError(f"no subcooled {which} bracket for {ids} at P={P}")
        else:
            t_lo = t_dew
            t_hi = t_dew
            for _ in range(60):
                if quantity(t_hi, branch) >= target:
                    break
                t_hi += max(1.0, 0.02 * t_hi)
            else:
                raise SaturationError(f"no superheated {which} bracket for {ids} at P={P}")
        if t_hi < t_lo:
            t_lo, t_hi = t_hi, t_lo

        def residual_branch(T: float) -> float:
            return quantity(T, branch) - target

        f_lo = residual_branch(t_lo)
        for _ in range(200):
            mid = 0.5 * (t_lo + t_hi)
            f_mid = residual_branch(mid)
            if f_lo * f_mid <= 0.0:
                t_hi = mid
            else:
                t_lo, f_lo = mid, f_mid
            if t_hi - t_lo < 1e-10:
                break
        t_final = 0.5 * (t_lo + t_hi)
        return self._single_stream(ids, xs, t_final, P, branch, molar_flow)

    # -- TVF / PVF flashes --------------------------------------------------

    def flash_tvf(self, z: dict[str, float], T: float, vf: float, molar_flow: float) -> StreamState:
        if not 0.0 <= vf <= 1.0:
            raise ValueError(f"vapour fraction {vf} outside [0, 1]")
        ids, xs = self._support(z)
        p_bub = self._bubble_pressure(ids, xs, T)
        p_dew = self._dew_pressure(ids, xs, T)
        if vf >= 1.0:
            return self._single_stream(ids, xs, T, p_dew, "vapor", molar_flow)
        if vf <= 0.0:
            return self._single_stream(ids, xs, T, p_bub, "liquid", molar_flow)
        if self._is_pure(ids):
            props_l = self._single_phase(ids, xs, T, p_bub, "liquid")
            props_v = self._single_phase(ids, xs, T, p_bub, "vapor")
            return self._two_phase_stream(
                ids, xs, xs, vf, props_l.ln_phi, props_v.ln_phi, T, p_bub, molar_flow
            )
        # mixtures: bisect P on the RR split's beta across the dome
        lo, hi = p_dew, p_bub

        def beta_at(P: float) -> float:
            beta, _, _, _, _ = self._rr_split(ids, xs, T, P)
            return beta

        b_lo, _ = 1.0, 0.0
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            b_mid = beta_at(mid)
            if abs(b_mid - vf) < 1e-10:
                lo = mid
                break
            if (b_lo - vf) * (b_mid - vf) <= 0.0:
                hi = mid
            else:
                lo, b_lo = mid, b_mid
            if hi - lo < 1e-9:
                break
        p_final = 0.5 * (lo + hi)
        beta, x, y, ln_phi_l, ln_phi_v = self._rr_split(ids, xs, T, p_final)
        return self._two_phase_stream(ids, x, y, beta, ln_phi_l, ln_phi_v, T, p_final, molar_flow)

    def flash_pvf(self, z: dict[str, float], P: float, vf: float, molar_flow: float) -> StreamState:
        if not 0.0 <= vf <= 1.0:
            raise ValueError(f"vapour fraction {vf} outside [0, 1]")
        ids, xs = self._support(z)
        t_bub = self._tsat(ids, xs, P, "bubble")
        t_dew = self._tsat(ids, xs, P, "dew")
        if vf >= 1.0:
            return self._single_stream(ids, xs, t_dew, P, "vapor", molar_flow)
        if vf <= 0.0:
            return self._single_stream(ids, xs, t_bub, P, "liquid", molar_flow)
        if self._is_pure(ids):
            props_l = self._single_phase(ids, xs, t_bub, P, "liquid")
            props_v = self._single_phase(ids, xs, t_bub, P, "vapor")
            return self._two_phase_stream(
                ids, xs, xs, vf, props_l.ln_phi, props_v.ln_phi, t_bub, P, molar_flow
            )
        lo, hi = t_bub, t_dew

        def beta_at(T: float) -> float:
            beta, _, _, _, _ = self._rr_split(ids, xs, T, P)
            return beta

        b_lo, _ = 0.0, 1.0
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            b_mid = beta_at(mid)
            if abs(b_mid - vf) < 1e-10:
                lo = mid
                break
            if (b_lo - vf) * (b_mid - vf) <= 0.0:
                hi = mid
            else:
                lo, b_lo = mid, b_mid
            if hi - lo < 1e-9:
                break
        t_final = 0.5 * (lo + hi)
        beta, x, y, ln_phi_l, ln_phi_v = self._rr_split(ids, xs, t_final, P)
        return self._two_phase_stream(ids, x, y, beta, ln_phi_l, ln_phi_v, t_final, P, molar_flow)

    # -- properties ---------------------------------------------------------

    def k_values(self, z: dict[str, float], T: float, P: float) -> dict[str, float] | None:
        """The helmholtz surface exposes K values through saturation points and
        flashes; a bare (T, P) K map needs the composition split to be defined."""
        del z, T, P
        return None

    def phase_props(self, composition: dict[str, float], T: float, P: float, kind: PhaseKind) -> PhaseProps:
        ids, xs = self._support(composition)
        if kind == PhaseKind.VAPOR:
            props = self._single_phase(ids, xs, T, P, "vapor")
        elif kind in (PhaseKind.HC_LIQUID, PhaseKind.AQUEOUS):
            props = self._single_phase(ids, xs, T, P, "liquid")
        else:  # pragma: no cover - PhaseKind is closed
            raise ValueError(f"unknown phase kind {kind}")
        return PhaseProps(
            kind=kind,
            mole_fraction=1.0,
            composition=dict(composition),
            molecular_weight=props.molecular_weight,
            density=props.density,
            enthalpy=props.enthalpy,
            entropy=props.entropy,
            cp=props.cp,
            gibbs=props.gibbs_at(T),
            z_factor=props.z_factor,
            viscosity=None,
            thermal_conductivity=None,
            ln_phi=props.ln_phi,
        )

    def derivatives(
        self, composition: dict[str, float], T: float, P: float, kind: PhaseKind
    ) -> PropertyDerivatives:
        """Central finite differences of ln phi on the requested-phase surface."""
        ids, xs = self._support(composition)
        phase = "vapor" if kind == PhaseKind.VAPOR else "liquid"
        h_t = 0.01
        h_p = max(1.0, 1e-7 * P)
        ln_phi_t0 = self._single_phase(ids, xs, T - h_t, P, phase).ln_phi
        ln_phi_t1 = self._single_phase(ids, xs, T + h_t, P, phase).ln_phi
        ln_phi_p0 = self._single_phase(ids, xs, T, P - h_p, phase).ln_phi
        ln_phi_p1 = self._single_phase(ids, xs, T, P + h_p, phase).ln_phi
        return PropertyDerivatives(
            dlnphi_dT={c: (ln_phi_t1[c] - ln_phi_t0[c]) / (2.0 * h_t) for c in ids},
            dlnphi_dP={c: (ln_phi_p1[c] - ln_phi_p0[c]) / (2.0 * h_p) for c in ids},
        )

    def pure_psat(self, cid: str, T: float) -> float | None:
        if cid not in self.SUPPORTED:
            raise ComponentNotSupported(
                f"{type(self).__name__} has no parameters for component {cid!r};"
                f" supported: {sorted(self.SUPPORTED)}"
            )
        return self._psat(cid, T)

    # -- StreamState assembly ----------------------------------------------

    def _single_stream(
        self, ids: tuple[str, ...], xs: tuple[float, ...], T: float, P: float, phase: str, molar_flow: float
    ) -> StreamState:
        props = self._single_phase(ids, xs, T, P, phase)
        kind = PhaseKind.VAPOR if phase == "vapor" else self.LIQUID_KIND
        phase_obj = Phase(
            kind=kind,
            mole_fraction=1.0,
            composition={c: xsi for c, xsi in zip(ids, xs, strict=True)},
            density=props.density,
            viscosity=None,
            z_factor=props.z_factor,
            molecular_weight=props.molecular_weight,
            enthalpy=props.enthalpy,
            entropy=props.entropy,
            cp=props.cp,
            ln_phi=props.ln_phi,
        )
        return StreamState(
            T=T,
            P=P,
            molar_flow=molar_flow,
            composition={c: xsi for c, xsi in zip(ids, xs, strict=True)},
            vapor_fraction=1.0 if phase == "vapor" else 0.0,
            enthalpy=props.enthalpy,
            entropy=props.entropy,
            phases=[phase_obj],
        )

    def _two_phase_stream(
        self,
        ids: tuple[str, ...],
        x: tuple[float, ...],
        y: tuple[float, ...],
        beta: float,
        ln_phi_l: dict[str, float],
        ln_phi_v: dict[str, float],
        T: float,
        P: float,
        molar_flow: float,
        *,
        props_l: _SinglePhase | None = None,
        props_v: _SinglePhase | None = None,
    ) -> StreamState:
        if props_l is None:
            props_l = self._single_phase(ids, x, T, P, "liquid")
        if props_v is None:
            props_v = self._single_phase(ids, y, T, P, "vapor")
        liq = Phase(
            kind=self.LIQUID_KIND,
            mole_fraction=1.0 - beta,
            composition={c: xi for c, xi in zip(ids, x, strict=True)},
            density=props_l.density,
            viscosity=None,
            z_factor=props_l.z_factor,
            molecular_weight=props_l.molecular_weight,
            enthalpy=props_l.enthalpy,
            entropy=props_l.entropy,
            cp=props_l.cp,
            ln_phi=ln_phi_l,
        )
        vap = Phase(
            kind=PhaseKind.VAPOR,
            mole_fraction=beta,
            composition={c: yi for c, yi in zip(ids, y, strict=True)},
            density=props_v.density,
            viscosity=None,
            z_factor=props_v.z_factor,
            molecular_weight=props_v.molecular_weight,
            enthalpy=props_v.enthalpy,
            entropy=props_v.entropy,
            cp=props_v.cp,
            ln_phi=ln_phi_v,
        )
        h_mix = (1.0 - beta) * props_l.enthalpy + beta * props_v.enthalpy
        s_mix = (1.0 - beta) * props_l.entropy + beta * props_v.entropy
        return StreamState(
            T=T,
            P=P,
            molar_flow=molar_flow,
            composition={c: xsi for c, xsi in zip(ids, self._mix(x, y, beta), strict=True)},
            vapor_fraction=beta,
            enthalpy=h_mix,
            entropy=s_mix,
            phases=[liq, vap],
        )

    @staticmethod
    def _mix(x: tuple[float, ...], y: tuple[float, ...], beta: float) -> tuple[float, ...]:
        return tuple((1.0 - beta) * xi + beta * yi for xi, yi in zip(x, y, strict=True))

    def _dome_state(
        self,
        ids: tuple[str, ...],
        xs: tuple[float, ...],
        T: float,
        P: float,
        molar_flow: float = 1.0,
    ) -> StreamState:
        """The two-phase state at (T, P) inside the dome."""
        beta, x, y, ln_phi_l, ln_phi_v = self._rr_split(ids, xs, T, P)
        return self._two_phase_stream(ids, x, y, beta, ln_phi_l, ln_phi_v, T, P, molar_flow)


# ---------------------------------------------------------------------------
# IAPWS steam-table packages (pure water; CoolProp water backends)
# ---------------------------------------------------------------------------


class IAPWSPackage(_HelmholtzSurface):
    """Pure water on IAPWS-95 or IAPWS-IF97 (options ``formulation``).

    Refuses every component except H2O by name; the liquid root reports as
    AQUEOUS so the harness's water-liquid comparisons land on one kind.
    """

    SUPPORTED: ClassVar[frozenset[str]] = frozenset({"H2O"})
    LIQUID_KIND: ClassVar[PhaseKind] = PhaseKind.AQUEOUS

    def __init__(self, formulation: Literal["IAPWS95", "IF97"] = "IAPWS95") -> None:
        if formulation not in ("IAPWS95", "IF97"):
            raise ValueError(f"unknown IAPWS formulation {formulation!r}")
        self.formulation = formulation

    def _single_phase(
        self, ids: tuple[str, ...], xs: tuple[float, ...], T: float, P: float, phase: str
    ) -> _SinglePhase:
        self._support(dict(zip(ids, xs, strict=True)))
        _require_coolprop()
        import CoolProp  # noqa: PLC0415
        from CoolProp.CoolProp import AbstractState  # noqa: PLC0415

        backend = "HEOS" if self.formulation == "IAPWS95" else "IF97"
        state = AbstractState(backend, "Water")
        if self.formulation == "IF97":
            # The IF97 backend ignores specify_phase at PT inputs: at a saturation
            # state (T, Psat(T)) both phase requests resolve to one root, so the
            # saturated-liquid/vapour labels come out swapped or collapsed
            # (issue #177). Near the saturation isobar, resolve the root through
            # the backend's PQ flash instead, which pins it by quality.
            psat = self._psat("H2O", T)
            if psat is not None and abs(P - psat) <= 1e-4 * psat:
                state.update(CoolProp.QT_INPUTS, 0.0 if phase == "liquid" else 1.0, T)
            else:
                state.specify_phase(CoolProp.iphase_liquid if phase == "liquid" else CoolProp.iphase_gas)
                state.update(CoolProp.PT_INPUTS, P, T)
        else:
            state.specify_phase(CoolProp.iphase_liquid if phase == "liquid" else CoolProp.iphase_gas)
            state.update(CoolProp.PT_INPUTS, P, T)
        mm = state.molar_mass()  # kg/mol
        density = state.rhomass()
        h = state.hmass() * mm  # J/kg -> J/mol
        s = state.smass() * mm
        cp = state.cpmass() * mm
        # z from the state's own pressure: the PQ route evaluates at Psat(T), not P.
        z_factor = state.p() / (state.rhomolar() * R_IDEAL * T)
        if self.formulation == "IAPWS95":
            ln_phi = {"H2O": math.log(state.fugacity_coefficient(0))}
        else:
            # the IF97 backend implements no fugacity coefficient (CoolProp 8)
            ln_phi = {}
        mw = mm * 1000.0
        return _SinglePhase(
            composition={"H2O": 1.0},
            molecular_weight=mw,
            density=density,
            enthalpy=h,
            entropy=s,
            cp=cp,
            z_factor=z_factor,
            ln_phi=ln_phi,
        )

    def _psat(self, cid: str, T: float) -> float | None:
        if cid != "H2O":  # pragma: no cover - _support already refuses
            raise ComponentNotSupported(f"IAPWSPackage has no parameters for component {cid!r}")
        _require_coolprop()
        import CoolProp  # noqa: PLC0415
        from CoolProp.CoolProp import AbstractState  # noqa: PLC0415

        backend = "HEOS" if self.formulation == "IAPWS95" else "IF97"
        state = AbstractState(backend, "Water")
        try:
            state.update(CoolProp.QT_INPUTS, 0.0, T)
        except Exception:
            return None
        return float(state.p())

    def _tsat(self, ids: tuple[str, ...], xs: tuple[float, ...], P: float, kind: str) -> float:
        """CoolProp's PQ flash gives the exact saturation temperature at P."""
        del xs
        if ids != ("H2O",):  # pragma: no cover - _support already refuses
            raise ComponentNotSupported(f"IAPWSPackage has no parameters for components {ids!r}")
        _require_coolprop()
        import CoolProp  # noqa: PLC0415
        from CoolProp.CoolProp import AbstractState  # noqa: PLC0415

        backend = "HEOS" if self.formulation == "IAPWS95" else "IF97"
        state = AbstractState(backend, "Water")
        try:
            state.update(CoolProp.PQ_INPUTS, P, 0.0 if kind == "bubble" else 1.0)
            return float(state.T())
        except Exception as exc:
            raise SaturationError(f"no {kind} temperature for water at P={P} Pa: {exc}") from exc


class ASMESteamPackage(IAPWSPackage):
    """ASME-labelled steam tables over the IAPWS-IF97 kernel.

    The modern ASME Steam Tables (7th ed., 2000) are computed from IAPWS-IF97,
    so this package is the IF97 kernel under the ASME label — not a separate
    formulation. The historical (pre-2000) ASME tables are based on IFC-67 and
    differ slightly; they are out of scope here. Verification values for the
    ``asme_steam`` row are bound from the IAPWS R7-97(2012) check tables that
    pin the shared kernel (helmholtz/cases.yaml, ``asme-steam-*`` cases).
    """

    def __init__(self) -> None:
        super().__init__(formulation="IF97")


# ---------------------------------------------------------------------------
# CoolProp HEOS pure/mixture packages
# ---------------------------------------------------------------------------


class CoolPropPackage(_HelmholtzSurface):
    """CoolProp ``HEOS`` pure fluids and mixtures over the mapped component set."""

    SUPPORTED: ClassVar[frozenset[str]] = frozenset(_COOLPROP_NAMES)
    #: Per-instance HEOS state cache: AbstractState construction dominates the
    #: evaluation cost (~0.5 s for a 2-fluid mixture), so states are reused across
    #: calls and recomposed (set_mole_fractions) before every update by callers.
    _heos_cache: dict[str, Any]

    def _heos(self, fluids: list[str]) -> Any:
        """A reusable HEOS state for these fluids; set composition before update."""
        from CoolProp.CoolProp import AbstractState  # noqa: PLC0415

        cache = getattr(self, "_heos_cache", None)
        if cache is None:
            cache = self._heos_cache = {}
        key = "&".join(fluids)
        state = cache.get(key)
        if state is None:
            state = cache[key] = AbstractState("HEOS", key)
        return state

    def _single_phase(
        self, ids: tuple[str, ...], xs: tuple[float, ...], T: float, P: float, phase: str
    ) -> _SinglePhase:
        _require_coolprop()
        import CoolProp  # noqa: PLC0415

        fluids = [_COOLPROP_NAMES[c] for c in ids]
        state = self._heos(fluids)
        if len(fluids) > 1:
            state.set_mole_fractions(list(xs))
        state.specify_phase(CoolProp.iphase_liquid if phase == "liquid" else CoolProp.iphase_gas)
        state.update(CoolProp.PT_INPUTS, P, T)
        mws = self._mws(ids)
        mw = sum(xsi * mw_i for xsi, mw_i in zip(xs, mws, strict=True))
        ln_phi = {c: math.log(state.fugacity_coefficient(i)) for i, c in enumerate(ids)}
        return _SinglePhase(
            composition={c: xsi for c, xsi in zip(ids, xs, strict=True)},
            molecular_weight=mw,
            density=state.rhomass(),
            enthalpy=state.hmolar(),
            entropy=state.smolar(),
            cp=state.cpmolar(),
            z_factor=P / (state.rhomolar() * R_IDEAL * T),
            ln_phi=ln_phi,
        )

    def _psat(self, cid: str, T: float) -> float | None:
        if cid not in _COOLPROP_NAMES:  # pragma: no cover - _support already refuses
            raise ComponentNotSupported(f"CoolPropPackage has no parameters for component {cid!r}")
        _require_coolprop()
        import CoolProp  # noqa: PLC0415

        state = self._heos([_COOLPROP_NAMES[cid]])
        try:
            state.update(CoolProp.QT_INPUTS, 0.0, T)
        except Exception:
            return None
        return float(state.p())

    def _bubble_pressure(self, ids: tuple[str, ...], xs: tuple[float, ...], T: float) -> float:
        """CoolProp gives exact two-phase equilibria via QT; near-critical states where
        its internal successive substitution stalls fall back to our own SS loop."""
        if self._is_pure(ids):
            return self._psat_or_raise(ids[0], T)
        _require_coolprop()
        import CoolProp  # noqa: PLC0415

        fluids = [_COOLPROP_NAMES[c] for c in ids]
        state = self._heos(fluids)
        state.set_mole_fractions(list(xs))
        try:
            state.update(CoolProp.QT_INPUTS, 0.0, T)
            return float(state.p())
        except Exception:
            return super()._bubble_pressure(ids, xs, T)

    def _dew_pressure(self, ids: tuple[str, ...], xs: tuple[float, ...], T: float) -> float:
        if self._is_pure(ids):
            return self._psat_or_raise(ids[0], T)
        _require_coolprop()
        import CoolProp  # noqa: PLC0415

        fluids = [_COOLPROP_NAMES[c] for c in ids]
        state = self._heos(fluids)
        state.set_mole_fractions(list(xs))
        try:
            state.update(CoolProp.QT_INPUTS, 1.0, T)
            return float(state.p())
        except Exception:
            return super()._dew_pressure(ids, xs, T)

    def _incipient(
        self, ids: tuple[str, ...], xs: tuple[float, ...], T: float, P: float, kind: str
    ) -> dict[str, float]:
        """Exact incipient compositions from CoolProp's QT equilibrium."""
        del P
        if self._is_pure(ids):
            return {ids[0]: 1.0}
        _require_coolprop()
        import CoolProp  # noqa: PLC0415

        fluids = [_COOLPROP_NAMES[c] for c in ids]
        state = self._heos(fluids)
        state.set_mole_fractions(list(xs))
        try:
            state.update(CoolProp.QT_INPUTS, 0.0 if kind == "bubble" else 1.0, T)
            phase_fractions = (
                state.mole_fractions_vapor() if kind == "bubble" else state.mole_fractions_liquid()
            )
        except Exception as exc:
            raise SaturationError(f"no {kind} incipient composition for {ids} at T={T} K: {exc}") from exc
        return {c: float(v) for c, v in zip(ids, phase_fractions, strict=True)}

    def _tsat(self, ids: tuple[str, ...], xs: tuple[float, ...], P: float, kind: str) -> float:
        """CoolProp's PQ flash gives the exact saturation temperature at P."""
        _require_coolprop()
        import CoolProp  # noqa: PLC0415

        if self._is_pure(ids):
            state = self._heos([_COOLPROP_NAMES[ids[0]]])
        else:
            state = self._heos([_COOLPROP_NAMES[c] for c in ids])
            state.set_mole_fractions(list(xs))
        try:
            state.update(CoolProp.PQ_INPUTS, P, 0.0 if kind == "bubble" else 1.0)
            return float(state.T())
        except Exception as exc:
            raise SaturationError(f"no {kind} temperature for {ids} at P={P} Pa: {exc}") from exc

    def _mws(self, ids: tuple[str, ...]) -> list[float]:
        """Component molar masses (g/mol) from the resolved records (thermo databank)."""
        constants = self._constants(ids)
        return [float(m) for m in constants.MWs]


class GERGPackage(CoolPropPackage):
    """CoolProp's multifluid mixture model restricted to the natural-gas slate.

    Refuses water (the IAPWS rows own steam-water states) and any component
    outside the slate by name; the L4 slice feed's C6+ is refused likewise.
    """

    SUPPORTED: ClassVar[frozenset[str]] = _GERG_IDS


# ---------------------------------------------------------------------------
# In-house Starling (1973) BWRS
# ---------------------------------------------------------------------------

#: BWRS imperial units: P psia, T °R, rho lb-mol/ft3, H/S in psia-ft3/lbmol.
_BWRS_R: Final[float] = 10.73159  # psia-ft3/(lbmol-R)
_PSIA_FT3_TO_J_PER_MOL: Final[float] = 6894.757293168 * 0.028316846592 / 453.59237
_BWRS_COMPONENTS: Final[dict[str, str]] = {
    "C1": "methane",
    "C2": "ethane",
    "C3": "propane",
    "iC4": "isobutane",
    "nC4": "n-butane",
    "iC5": "isopentane",
    "nC5": "n-pentane",
    "N2": "nitrogen",
    "CO2": "carbon dioxide",
    "H2S": "hydrogen sulfide",
}

#: Starling's eleven BWRS parameters per compound, imperial basis, transcribed
#: from ORO-5249-2 (1976) Table 5 (column scale factors applied): the table's
#: C0 and c are x1e-8, D0 and E0 are x1e-10, d is x1e-4. Methane and nitrogen
#: rows were additionally verified against the scratch Helmholtz implementation
#: this package ports (a_res vs numerical density integral, ln phi_i vs finite
#: differences of N*a_res at fixed T, V).
#: Order: (B0, A0, C0, gamma, b, a, alpha, c, D0, d, E0).
_BWRS_PAR: Final[dict[str, tuple[float, ...]]] = {
    "methane": (
        0.723251,
        7520.29,
        2.71092e8,
        1.48640,
        0.925404,
        2574.89,
        0.468828,
        4.37222e8,
        1.07737e10,
        4.74891e4,
        3.01122e10,
    ),
    "ethane": (
        0.826059,
        13439.3,
        29.5195e8,
        2.99656,
        3.11206,
        22404.5,
        0.909681,
        68.1826e8,
        25.7477e10,
        70.2189e4,
        1468.19e10,
    ),
    "propane": (
        0.964762,
        18634.7,
        79.6178e8,
        4.56182,
        5.46248,
        40066.4,
        2.01402,
        274.461e8,
        45.3708e10,
        1505.20e4,
        2560.53e10,
    ),
    "isobutane": (
        2.02615,
        38980.2,
        106.581e8,
        9.21378,
        6.70763,
        38864.4,
        6.87727,
        328.220e8,
        147.046e10,
        618.303e4,
        8981.52e10,
    ),
    "n-butane": (
        1.56588,
        32544.7,
        137.436e8,
        7.54122,
        9.14066,
        71181.8,
        4.00985,
        700.044e8,
        33.3159e10,
        3642.38e4,
        230.902e10,
    ),
    "isopentane": (
        1.27752,
        35742.0,
        228.430e8,
        11.7384,
        19.8384,
        204344.0,
        6.16154,
        1290.83e8,
        142.115e10,
        3492.20e4,
        2413.26e10,
    ),
    "n-pentane": (
        2.44417,
        51108.2,
        223.931e8,
        11.8593,
        16.6070,
        162185.0,
        7.06702,
        1352.86e8,
        101.769e10,
        3885.21e4,
        3908.60e10,
    ),
    "nitrogen": (
        0.677022,
        4185.05,
        1.37936e8,
        1.10011,
        0.833470,
        1404.59,
        0.302696,
        0.844317e8,
        1.95183e10,
        3.11894e4,
        121.648e10,
    ),
    "carbon dioxide": (
        0.394117,
        6592.03,
        29.5902e8,
        1.64916,
        0.971443,
        5632.85,
        0.395525,
        27.4668e8,
        40.9151e10,
        5.99297e4,
        1.02898e10,
    ),
    "hydrogen sulfide": (
        0.297508,
        10586.3,
        21.1496e8,
        1.20447,
        2.53315,
        20511.0,
        0.165961,
        43.6132e8,
        4.86518e10,
        1.99731e4,
        3.93226e10,
    ),
}

_IBO, _IAO, _ICO, _IGA, _IB, _IA, _IAL, _IC, _IDO, _ID, _IEO = range(11)


def _bwrs_mix(ids: tuple[str, ...], xs: tuple[float, ...]) -> dict[str, float]:
    """Starling's mixing rules with k_ij = 0 (no fitted BWRS BIPs adopted)."""
    names = [_BWRS_COMPONENTS[c] for c in ids]
    par = _BWRS_PAR
    bo = sum(xsi * par[n][_IBO] for xsi, n in zip(xs, names, strict=True))
    a3 = sum(xsi * par[n][_IA] ** (1.0 / 3.0) for xsi, n in zip(xs, names, strict=True)) ** 3
    b3 = sum(xsi * par[n][_IB] ** (1.0 / 3.0) for xsi, n in zip(xs, names, strict=True)) ** 3
    c3 = sum(xsi * par[n][_IC] ** (1.0 / 3.0) for xsi, n in zip(xs, names, strict=True)) ** 3
    d3 = sum(xsi * par[n][_ID] ** (1.0 / 3.0) for xsi, n in zip(xs, names, strict=True)) ** 3
    al3 = sum(xsi * par[n][_IAL] ** (1.0 / 3.0) for xsi, n in zip(xs, names, strict=True)) ** 3
    ga2 = sum(xsi * par[n][_IGA] ** 0.5 for xsi, n in zip(xs, names, strict=True)) ** 2
    ao = co = do_ = eo = 0.0
    for i, xsi in enumerate(xs):
        for j, xsj in enumerate(xs):
            ao += xsi * xsj * math.sqrt(par[names[i]][_IAO] * par[names[j]][_IAO])
            co += xsi * xsj * math.sqrt(par[names[i]][_ICO] * par[names[j]][_ICO])
            do_ += xsi * xsj * math.sqrt(par[names[i]][_IDO] * par[names[j]][_IDO])
            eo += xsi * xsj * math.sqrt(par[names[i]][_IEO] * par[names[j]][_IEO])
    return {
        "Bo": bo,
        "Ao": ao,
        "Co": co,
        "Do": do_,
        "Eo": eo,
        "a": a3,
        "b": b3,
        "c": c3,
        "d": d3,
        "al": al3,
        "ga": ga2,
    }


def _bwrs_pressure(rho: float, T: float, p: dict[str, float]) -> float:
    """BWRS pressure (psia) at density (lbmol/ft3) and temperature (°R)."""
    return (
        _BWRS_R * T * rho
        + (p["Bo"] * _BWRS_R * T - p["Ao"] - p["Co"] / T**2 + p["Do"] / T**3 - p["Eo"] / T**4) * rho**2
        + (p["b"] * _BWRS_R * T - p["a"] - p["d"] / T) * rho**3
        + p["al"] * (p["a"] + p["d"] / T) * rho**6
        + p["c"] / T**2 * rho**3 * (1.0 + p["ga"] * rho**2) * math.exp(-p["ga"] * rho**2)
    )


def _bwrs_a_res(rho: float, T: float, p: dict[str, float]) -> float:
    """Dimensionless residual Helmholtz a_res/(R T); integrates P = rho^2 R T da/drho."""
    f = p["Bo"] * _BWRS_R * T - p["Ao"] - p["Co"] / T**2 + p["Do"] / T**3 - p["Eo"] / T**4
    g = p["b"] * _BWRS_R * T - p["a"] - p["d"] / T
    big_j = p["al"] * (p["a"] + p["d"] / T)
    ga, x2 = p["ga"], p["ga"] * rho**2
    m = 2.0 - (2.0 + x2) * math.exp(-x2)
    return (
        f * rho / (_BWRS_R * T)
        + g * rho**2 / (2.0 * _BWRS_R * T)
        + big_j * rho**5 / (5.0 * _BWRS_R * T)
        + p["c"] / T**2 * m / (2.0 * ga * _BWRS_R * T)
    )


def _bwrs_h_dep(rho: float, T: float, p: dict[str, float]) -> float:
    """Enthalpy departure H^res/(R T) in psia-ft3/lbmol-consistent dimensionless form."""
    bo, ao, co, do_, eo = p["Bo"], p["Ao"], p["Co"], p["Do"], p["Eo"]
    a_, b_, c_, d_, al, ga = p["a"], p["b"], p["c"], p["d"], p["al"], p["ga"]
    return (
        (bo * _BWRS_R * T - 2.0 * ao - 4.0 * co / T**2 + 5.0 * do_ / T**3 - 6.0 * eo / T**4) * rho
        + (b_ * _BWRS_R * T - 1.5 * a_ - 2.0 * d_ / T) * rho**2
        + al * (6.0 / 5.0 * a_ + 7.0 / 5.0 * d_ / T) * rho**5
        + c_ / ga / T**2 * (3.0 - (3.0 + ga / 2.0 * rho**2 - ga**2 * rho**4) * math.exp(-ga * rho**2))
    )


def _bwrs_lnphi(
    ids: tuple[str, ...], xs: tuple[float, ...], rho: float, T: float, P: float
) -> dict[str, float]:
    """Analytic ln phi_i (verified against finite differences of n*a_res, 1.2e-9)."""
    p = _bwrs_mix(ids, xs)
    names = [_BWRS_COMPONENTS[c] for c in ids]
    par = _BWRS_PAR
    z = P / (rho * _BWRS_R * T)
    base = _bwrs_a_res(rho, T, p) + z - 1.0 - math.log(z)
    ga = p["ga"]
    x2 = ga * rho**2
    m = 2.0 - (2.0 + x2) * math.exp(-x2)
    dm_dga = rho**2 * (1.0 + x2) * math.exp(-x2)
    comps = []
    for name in names:
        sum_quad = 0.0
        for j in range(len(ids)):
            sum_quad += xs[j] * (
                -math.sqrt(par[name][_IAO] * par[names[j]][_IAO])
                - math.sqrt(par[name][_ICO] * par[names[j]][_ICO]) / T**2
                + math.sqrt(par[name][_IDO] * par[names[j]][_IDO]) / T**3
                - math.sqrt(par[name][_IEO] * par[names[j]][_IEO]) / T**4
            )
        df_i = _BWRS_R * T * par[name][_IBO] + 2.0 * sum_quad
        dg_i = (
            _BWRS_R * T * 3.0 * p["b"] ** (2.0 / 3.0) * par[name][_IB] ** (1.0 / 3.0)
            - 3.0 * p["a"] ** (2.0 / 3.0) * par[name][_IA] ** (1.0 / 3.0)
            - 3.0 * p["d"] ** (2.0 / 3.0) * par[name][_ID] ** (1.0 / 3.0) / T
        )
        dJ_i = 3.0 * p["al"] ** (2.0 / 3.0) * par[name][_IAL] ** (1.0 / 3.0) * (p["a"] + p["d"] / T) + p[
            "al"
        ] * (
            3.0 * p["a"] ** (2.0 / 3.0) * par[name][_IA] ** (1.0 / 3.0)
            + 3.0 * p["d"] ** (2.0 / 3.0) * par[name][_ID] ** (1.0 / 3.0) / T
        )
        dc_i = 3.0 * p["c"] ** (2.0 / 3.0) * par[name][_IC] ** (1.0 / 3.0)
        dga_i = 2.0 * math.sqrt(ga) * math.sqrt(par[name][_IGA])
        da_i = (
            rho / (_BWRS_R * T) * df_i
            + rho**2 / (2.0 * _BWRS_R * T) * dg_i
            + rho**5 / (5.0 * _BWRS_R * T) * dJ_i
            + (
                dc_i * m / (2.0 * ga)
                + p["c"] * dm_dga * dga_i / (2.0 * ga)
                - p["c"] * m * dga_i / (2.0 * ga**2)
            )
            / (_BWRS_R * T**3)
        )
        comps.append(da_i)
    mean = sum(x * d for x, d in zip(xs, comps, strict=True))
    return {cid: base + d - mean for cid, d in zip(ids, comps, strict=True)}


def _bwrs_h_dep_j(rho: float, T: float, p: dict[str, float]) -> float:
    """H^res in J/mol (imperial dimensionless form converted at the boundary)."""
    return _bwrs_h_dep(rho, T, p) * _BWRS_R * T * _PSIA_FT3_TO_J_PER_MOL


def _bwrs_roots(ids: tuple[str, ...], xs: tuple[float, ...], T: float, P: float) -> list[float]:
    """All density roots (lbmol/ft3) of P(rho) = P on a log scan of (1e-12, 3)."""
    p = _bwrs_mix(ids, xs)
    p_psia = P / 6894.757293168
    roots: list[float] = []
    prev = 1e-12
    f_prev = _bwrs_pressure(prev, T * 1.8, p) - p_psia
    steps = 400
    for i in range(1, steps + 1):
        r = 10.0 ** (-12.0 + (math.log10(3.0) + 12.0) * i / steps)
        f_r = _bwrs_pressure(r, T * 1.8, p) - p_psia
        if f_prev * f_r < 0.0:
            lo, hi = prev, r
            for _ in range(120):
                mid = 0.5 * (lo + hi)
                f_mid = _bwrs_pressure(mid, T * 1.8, p) - p_psia
                if f_prev * f_mid <= 0.0:
                    hi = mid
                else:
                    lo, f_prev = mid, f_mid
            roots.append(0.5 * (lo + hi))
        prev, f_prev = r, f_r
    return roots


class BWRSPackage(_HelmholtzSurface):
    """Starling (1973) BWRS over the ORO-5249-2 (1976) Table 5 parameter set."""

    SUPPORTED: ClassVar[frozenset[str]] = frozenset(_BWRS_COMPONENTS)

    def _single_phase(
        self, ids: tuple[str, ...], xs: tuple[float, ...], T: float, P: float, phase: str
    ) -> _SinglePhase:
        roots = _bwrs_roots(ids, xs, T, P)
        if not roots:
            raise SaturationError(f"BWRS found no density root at T={T} K, P={P} Pa for {ids}")
        rho = roots[0] if phase == "vapor" else roots[-1]
        return self._props_at_root(ids, xs, T, P, rho, phase)

    def _props_at_root(
        self, ids: tuple[str, ...], xs: tuple[float, ...], T: float, P: float, rho: float, phase: str
    ) -> _SinglePhase:
        t_r = T * 1.8
        p_psia = P / 6894.757293168
        p_mix = _bwrs_mix(ids, xs)
        z = p_psia / (rho * _BWRS_R * t_r)
        a_res = _bwrs_a_res(rho, t_r, p_mix)
        h_dep_j = _bwrs_h_dep_j(rho, t_r, p_mix)
        u_dep_over_rt = _bwrs_h_dep(rho, t_r, p_mix) - (z - 1.0)
        s_dep_over_r = u_dep_over_rt - 2.0 * a_res
        cp_ig = self._cp_ig(ids, xs, T)
        h_ig = self._h_ig(ids, xs, T)
        s_ig = self._s_ig(ids, xs, T, P)
        r_j = 8.31446261815324
        # ideal-gas reference H_ig(298.15 K) = 0; departures in R*T units converted via R
        h = h_ig + h_dep_j
        s = s_ig + s_dep_over_r * r_j
        cp = cp_ig + self._cp_dep(ids, xs, T, P, phase)
        ln_phi = _bwrs_lnphi(ids, xs, rho, t_r, p_psia)
        mws = self._mws(ids)
        mw = sum(xsi * mw_i for xsi, mw_i in zip(xs, mws, strict=True))
        return _SinglePhase(
            composition={c: xsi for c, xsi in zip(ids, xs, strict=True)},
            molecular_weight=mw,
            density=rho * mw / 0.06242796,  # lbmol/ft3 -> kg/m3 (times g/mol / 1000 * 1000)
            enthalpy=h,
            entropy=s,
            cp=cp,
            z_factor=z,
            ln_phi=ln_phi,
        )

    def _cp_dep(self, ids: tuple[str, ...], xs: tuple[float, ...], T: float, P: float, phase: str) -> float:
        """Residual Cp as the central-difference slope of the departure enthalpy on the same branch."""
        d_t = 0.5
        h0 = self._hdep_on_branch(ids, xs, T - d_t, P, phase)
        h1 = self._hdep_on_branch(ids, xs, T + d_t, P, phase)
        return (h1 - h0) / (2.0 * d_t)

    def _hdep_on_branch(
        self, ids: tuple[str, ...], xs: tuple[float, ...], T: float, P: float, phase: str
    ) -> float:
        """Departure enthalpy (J/mol) on the requested branch; the ideal part is cp_ig's slope."""
        roots = _bwrs_roots(ids, xs, T, P)
        if not roots:
            raise SaturationError(f"BWRS found no density root at T={T} K, P={P} Pa for {ids}")
        rho = roots[0] if phase == "vapor" else roots[-1]
        t_r = T * 1.8
        return _bwrs_h_dep_j(rho, t_r, _bwrs_mix(ids, xs))

    def _psat(self, cid: str, T: float) -> float | None:
        if cid not in _BWRS_COMPONENTS:  # pragma: no cover - _support already refuses
            raise ComponentNotSupported(f"BWRSPackage has no parameters for component {cid!r}")
        ids = (cid,)
        xs = (1.0,)
        t_r = T * 1.8
        p_mix = _bwrs_mix(ids, xs)
        # scan P(rho) for the vapor and liquid spinodals, then bisect the
        # equal-fugacity (a_res + Z - 1 equal) pressure between their bounds
        grid = [10.0 ** (-12.0 + 15.0 * i / 1200.0) for i in range(1201)]
        p_grid = [_bwrs_pressure(r, t_r, p_mix) for r in grid]
        # local extrema: vapor spinodal (max at low rho), liquid spinodal (min at high rho)
        i_max: int | None = None
        i_min: int | None = None
        for i in range(1, len(grid) - 1):
            if p_grid[i] > p_grid[i - 1] and p_grid[i] > p_grid[i + 1] and i_max is None:
                i_max = i
            if p_grid[i] < p_grid[i - 1] and p_grid[i] < p_grid[i + 1]:
                i_min = i
        if i_max is None or i_min is None or i_min <= i_max:
            return None
        p_vsp = p_grid[i_max]
        p_lsp = p_grid[i_min]
        if p_vsp <= 0.0:
            return None

        def g(p_psia: float) -> float:
            rho_v = _bwrs_root_between(p_mix, t_r, p_psia, grid[0], grid[i_max])
            rho_l = _bwrs_root_between(p_mix, t_r, p_psia, grid[i_min], grid[-1])
            zv = p_psia / (rho_v * _BWRS_R * t_r)
            zl = p_psia / (rho_l * _BWRS_R * t_r)
            # equal fugacity: ln phi = a_res + Z - 1 - ln Z on each root
            lnphi_v = _bwrs_a_res(rho_v, t_r, p_mix) + zv - 1.0 - math.log(zv)
            lnphi_l = _bwrs_a_res(rho_l, t_r, p_mix) + zl - 1.0 - math.log(zl)
            return lnphi_l - lnphi_v

        p_lo, p_hi = max(p_lsp, 1e-4), p_vsp
        if g(p_lo) * g(p_hi) > 0.0:
            return None
        for _ in range(200):
            mid = 0.5 * (p_lo + p_hi)
            g_mid = g(mid)
            if abs(g_mid) < 1e-12:
                return mid * 6894.757293168
            if g(p_lo) * g_mid <= 0.0:
                p_hi = mid
            else:
                p_lo = mid
        return 0.5 * (p_lo + p_hi) * 6894.757293168

    # -- ideal-gas reference integrals (thermo HeatCapacityGas correlations) --

    def _cp_ig(self, ids: tuple[str, ...], xs: tuple[float, ...], T: float) -> float:
        correlations = self._correlations(ids)
        total = 0.0
        for i, correlation in enumerate(correlations.HeatCapacityGases):
            total += xs[i] * float(correlation.T_dependent_property(T))
        return total

    def _h_ig(self, ids: tuple[str, ...], xs: tuple[float, ...], T: float) -> float:
        """Integrated Cp_ig from 298.15 K (reference H_ig(298.15) = 0)."""
        correlations = self._correlations(ids)
        total = 0.0
        for i, correlation in enumerate(correlations.HeatCapacityGases):
            total += xs[i] * float(correlation.T_dependent_property_integral(298.15, T))
        return total

    def _s_ig(self, ids: tuple[str, ...], xs: tuple[float, ...], T: float, P: float) -> float:
        """S_ig(T, P) = int Cp/T dT from 298.15 K minus R ln(P/1e5); S_ig(298.15, 1e5) = 0."""
        correlations = self._correlations(ids)
        total = 0.0
        for i, correlation in enumerate(correlations.HeatCapacityGases):
            total += xs[i] * float(correlation.T_dependent_property_integral_over_T(298.15, T))
        return total - R_IDEAL * math.log(P / 1e5)

    def _correlations(self, ids: tuple[str, ...]) -> Any:
        cache = getattr(self, "_correlations_cache", None)
        if cache is None or cache[0] != ids:
            _, correlations = _constants_package(_records(ids, ()))
            cache = (ids, correlations)
            self._correlations_cache = cache
        return cache[1]

    def _mws(self, ids: tuple[str, ...]) -> list[float]:
        constants = self._constants(ids)
        return [float(m) for m in constants.MWs]

    def _constants(self, ids: tuple[str, ...]) -> Any:
        cache = getattr(self, "_constants_cache", None)
        if cache is None or cache[0] != ids:
            constants, _ = _constants_package(_records(ids, ()))
            cache = (ids, constants)
            self._constants_cache = cache
        return cache[1]


def _bwrs_root_between(p_mix: dict[str, float], t_r: float, p_psia: float, lo: float, hi: float) -> float:
    """Density root of P(rho) = p_psia inside (lo, hi) by bisection."""
    f_lo = _bwrs_pressure(lo, t_r, p_mix) - p_psia
    f_hi = _bwrs_pressure(hi, t_r, p_mix) - p_psia
    if f_lo * f_hi > 0.0:
        raise SaturationError("BWRS saturation root not bracketed")
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        f_mid = _bwrs_pressure(mid, t_r, p_mix) - p_psia
        if f_lo * f_mid <= 0.0:
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    return 0.5 * (lo + hi)


# ---------------------------------------------------------------------------
# Placeholder adapter for not-yet-implemented family-D backends
# ---------------------------------------------------------------------------


class UnavailablePackage:
    """Catalogue placeholder for family-D backends with no implementation yet.

    The row loads so the catalogue records the method, status and provenance;
    every property call raises :class:`UnavailableBackend` naming the row.
    """

    def flash_pt(self, z: dict[str, float], T: float, P: float, molar_flow: float) -> StreamState:
        raise self._unimplemented("flash_pt")

    def flash_ph(self, z: dict[str, float], P: float, H: float, molar_flow: float) -> StreamState:
        raise self._unimplemented("flash_ph")

    def flash_ps(self, z: dict[str, float], P: float, S: float, molar_flow: float) -> StreamState:
        raise self._unimplemented("flash_ps")

    def flash_tvf(self, z: dict[str, float], T: float, vf: float, molar_flow: float) -> StreamState:
        raise self._unimplemented("flash_tvf")

    def flash_pvf(self, z: dict[str, float], P: float, vf: float, molar_flow: float) -> StreamState:
        raise self._unimplemented("flash_pvf")

    def bubble_point(
        self, z: dict[str, float], *, T: float | None = None, P: float | None = None
    ) -> SaturationPoint:
        raise self._unimplemented("bubble_point")

    def dew_point(
        self, z: dict[str, float], *, T: float | None = None, P: float | None = None
    ) -> SaturationPoint:
        raise self._unimplemented("dew_point")

    def k_values(self, z: dict[str, float], T: float, P: float) -> dict[str, float] | None:
        raise self._unimplemented("k_values")

    def phase_props(self, composition: dict[str, float], T: float, P: float, kind: PhaseKind) -> PhaseProps:
        raise self._unimplemented("phase_props")

    def derivatives(
        self, composition: dict[str, float], T: float, P: float, kind: PhaseKind
    ) -> PropertyDerivatives:
        raise self._unimplemented("derivatives")

    def pure_psat(self, cid: str, T: float) -> float | None:
        raise self._unimplemented("pure_psat")

    def _unimplemented(self, method: str) -> UnavailableBackend:
        return UnavailableBackend(
            f"helmholtz-family placeholder row has no {method} implementation;"
            " the backend lands with a later spec (teqp bridge, T-07)"
        )
