"""Special-chemistry thermodynamics: polymer solutions, SLE, association (spec T-10).

One module, the special-chemistry families behind the catalogue rows in
data/thermo_models/special.yaml:

* :class:`FloryHugginsPackage` - Flory-Huggins gE for solvent/polymer solutions.
  Segment counts ``r`` and the interaction parameter ``chi`` per solvent/polymer
  pair come from data/thermo_params/special/polymer.yaml with provenance; a pair
  without parameters is a construction-time refusal, never a silent ideal.
* :class:`ChenPolymerNRTLPackage` - the Chen (1993, Fluid Phase Equilib. 83, 301)
  segment-based local-composition model: Flory-Huggins-style segment
  combinatorial plus segment-level NRTL residual. Segment counts, tau and alpha
  per pair from the same params file, same refusal rule.
* :class:`UnifacFvPackage` - Oishi-Prausnitz UNIFAC-FV: the solvent activity is
  the UNIFAC activity over the curated subgroup assignment plus the Flory
  free-volume term, for a binary solvent/polymer support. The polymer activity
  follows from the solvent activity by Gibbs-Duhem integration.
* :class:`IdealSolidPackage` - ideal-solubility solid-liquid equilibrium
  (van't Hoff from the fusion properties, activity coefficient 1). Not a flash
  package: it computes solubility directly and refuses VLE-style flashing.
* :class:`HaydenOConnellDimerPackage` - a gamma-phi flasher whose vapour phase is
  corrected by an in-house dimerization chemical-theory kernel (carboxylic-acid
  association). The curated ``nrtl_hoc``/``nrtl_nothnagel`` rows keep refusing
  (their wiring lives in ngdesign.thermo.gamma_phi, outside this spec's file
  list); this module ships the working kernel behind its own special-family row.
* :class:`HFHexamerPackage` - same structure, HF vapour associating to hexamers:
  the in-house hexamerization kernel on Jarry & Davis (1953) parameters, with
  Schotte (1980) as the oligomer-treatment reference.
* :class:`PolymerPCSAFT` - polymer PC-SAFT for solvent/polymer supports, built
  through the T-07 teqp bridge (ngdesign.thermo.teqp_bridge); segment
  parameters for POLY_PS and toluene carry citations, unsupported components
  and a missing teqp extra refuse at first use like every saft row.

Polymers enter as flowsheet-owned or registered pseudo-components (spec P1-07);
the params file documents the polystyrene characterization used by the
validation cases. Provenance lives in the params files and the catalogue rows;
every numerical derivation is cited there.

Status (re-decided 2026-11-03; the reasons live in each catalogue row's notes):
``ideal_solid`` is ``provisional`` (complete van't Hoff physics on tabulated
fusion properties, published IUPAC-NIST checks, a harness ``solubility`` case
type). The other six stay ``experimental`` and out of the advisor's set:
illustrative or secondary-sourced polymer parameters, the UNIFAC-FV residual's
fixed-298.15 K / repeat-unit-fraction gaps, the association kernels not being
wired into the dimer/hexamer flash (those rows flash with an ideal-gas vapour),
and no runnable published reference for polymer PC-SAFT.

SI units throughout: K, Pa, J/mol, J/(mol K).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import cache
from typing import Any, cast

import yaml
from chemicals.phase_change import Hfus, Tm
from thermo import FlashVL, GibbsExcessLiquid, IdealGas
from thermo.activity import GibbsExcess, IdealSolution

from ngdesign.data import DATABANK_LOCK, register_pseudo
from ngdesign.thermo import _state
from ngdesign.thermo._state import R_IDEAL as R
from ngdesign.thermo.cubic import ThermoSurfaceMixin
from ngdesign.thermo.teqp_bridge import TeqpPackage


def _params_dir() -> Any:
    from ngdesign.thermo.gamma_phi import PARAMS_DIR

    return PARAMS_DIR


def _shared_cached(self_key: tuple[Any, ...], key: tuple[Any, ...], compute: Any) -> Any:
    from ngdesign.thermo.gamma_phi import _shared_cached as _impl

    return _impl(self_key, key, compute)


# --------------------------------------------------------------------------
# Flasher wiring (mirrors gamma_phi._build_flasher_inner, two-phase only)
# --------------------------------------------------------------------------


def _special_flasher(
    make_ge: Any,
    ids: tuple[str, ...],
    pseudos: tuple[Any, ...],
    association: tuple[int, AssociationLaw] | None = None,
) -> Any:
    """One two-phase gamma-phi flasher over exactly this sorted component set.

    Same shared state layer as every other package: records resolve through the
    open component registry (flowsheet-owned pseudo definitions win), constants
    and correlations come from ``_state._constants_package`` so pseudo-components
    get the merged package. Without ``association`` the vapour is ideal-gas;
    with ``(index, law)`` it is the chemical-theory :class:`AssociatingGas` and
    the liquid takes the PhiSat basis (f_i^L = x_i gamma_i phi_i^sat P_i^sat)
    with the associating component's saturation fugacity coefficient, so a pure
    associating feed still boils exactly at its Psat.
    """
    with DATABANK_LOCK:
        records = _state._records(ids, pseudos)
        constants, correlations = _state._constants_package(records)
        basis: dict[str, Any] = {}
        if association is None:
            gas = IdealGas(HeatCapacityGases=correlations.HeatCapacityGases)
        else:
            idx, law = association
            gas = AssociatingGas(
                law, idx, HeatCapacityGases=correlations.HeatCapacityGases, zs=[1.0 / len(ids)] * len(ids)
            )
            sats: list[Any] = [
                _AssociationSaturation(law, correlations.VaporPressures[i], constants.Tcs[i])
                if i == idx
                else _InertSaturation(constants.Tcs[i])
                for i in range(len(ids))
            ]
            basis = {"equilibrium_basis": "PhiSat", "eos_pure_instances": sats}

        def ge_liquid() -> Any:
            """One liquid phase; each gets its own gE instance (T/xs state)."""
            model = make_ge([1.0 / len(ids)] * len(ids))
            return GibbsExcessLiquid(
                VaporPressures=correlations.VaporPressures,
                HeatCapacityGases=correlations.HeatCapacityGases,
                HeatCapacityLiquids=correlations.HeatCapacityLiquids,
                EnthalpyVaporizations=correlations.EnthalpyVaporizations,
                VolumeLiquids=correlations.VolumeLiquids,
                GibbsExcessModel=model,
                **basis,
            )

        if association is not None:
            return _AssociationFlashVL(constants, correlations, gas=gas, liquid=ge_liquid())
        return FlashVL(constants, correlations, gas=gas, liquid=ge_liquid())


class _AssociationFlashVL(FlashVL):  # type: ignore[misc]  # thermo ships no stubs
    """FlashVL whose PT stability test also decides a pure feed (N == 1).

    thermo 0.6.1's Michelsen trial generator (``incipient_guesses``) divides
    by N - 1, so a pure feed raises ZeroDivisionError inside every PT flash,
    including the ones its PH/PS secant solver makes (the shared layer
    recovers only the direct PT call, ``_state._flash_tp_with_stability_fallback``).
    A pure substance at fixed (T, P) cannot split, so the stable phase is the
    one with the lower Gibbs energy (departure basis, as thermo itself compares
    on an ideal-gas basis); mixtures take the library path unchanged.
    """

    def flash_TP_stability_test(
        self,
        T: float,
        P: float,
        zs: list[float],
        liquid: Any,
        gas: Any,
        solution: Any = None,
        LL: bool = False,
        phases_ready: bool = False,
    ) -> Any:
        if self.N != 1:
            return super().flash_TP_stability_test(
                T, P, zs, liquid, gas, solution=solution, LL=LL, phases_ready=phases_ready
            )
        if not phases_ready:
            gas, liquid = self.phases_at_TP_binary(T, P, zs, liquid, gas)
        if liquid.G_dep() <= gas.G_dep():
            return None, [liquid], [], [1.0], {"iterations": 0, "err": 0.0, "stab_info": None}
        return gas, [], [], [1.0], {"iterations": 0, "err": 0.0, "stab_info": None}


class SpecialGammaPhiPackage(ThermoSurfaceMixin):
    """Base for the special-chemistry gamma-phi packages (VLE, two-phase).

    The liquid gE model is supplied by ``_make_ge_factory``, which receives the
    sorted support and the resolved records and returns a factory mapping
    equimolar xs to a :class:`GibbsExcess` instance. Provenance checks run
    inside the cached flasher factory before the first flash.
    """

    ge_name = "override"

    def __init__(self, components: tuple[str, ...] | None = None) -> None:
        """Build the package; ``components`` runs the provenance checks eagerly."""
        super().__init__()
        if components:
            self._build_flasher(tuple(sorted(components)))

    def _cached(self, key: tuple[Any, ...], compute: Any) -> Any:
        return _shared_cached((self.ge_name, self._slate_pseudos), key, compute)

    def _build_flasher(self, ids: tuple[str, ...]) -> Any:
        make_ge = self._make_ge_factory(ids, self._slate_pseudos)
        return _special_flasher(make_ge, ids, self._slate_pseudos)

    def _build_flasher_vl(self, ids: tuple[str, ...]) -> Any:
        """Same two-phase flasher; special-chemistry rows do not declare VLLE."""
        return self._build_flasher(ids)

    def _make_ge_factory(self, ids: tuple[str, ...], pseudos: tuple[Any, ...]) -> Any:
        raise NotImplementedError


# --------------------------------------------------------------------------
# POLY_PS pseudo-component registration (P1-07)
# --------------------------------------------------------------------------


def _ensure_poly_ps_registered() -> None:
    """Idempotently register the POLY_PS polystyrene pseudo-component (P1-07).

    Parameters documented in data/thermo_params/special/polymer.yaml; Tb is an
    operational placeholder (polystyrene decomposes before boiling), sg is the
    amorphous density at 20 C.
    """
    register_pseudo("POLY_PS", "Polystyrene", Tb=871.0, sg=1.05)


# --------------------------------------------------------------------------
# Flory-Huggins
# --------------------------------------------------------------------------


@cache
def _polymer_params() -> dict[str, Any]:
    """The special polymer parameter file, loaded once (static data)."""
    path = _params_dir() / "special" / "polymer.yaml"
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data or {}


def _pair_param(params: dict[str, Any], key: str, a: str, b: str, section: str) -> Any:
    """Pairwise parameter lookup; a missing pair refuses, naming the pair."""
    table = params.get(section) or {}
    entry = table.get(f"{a}/{b}") or table.get(f"{b}/{a}")
    if entry is None:
        raise ValueError(
            f"the special {key} model has no {section} parameters for the pair "
            f"{a}/{b}; add them to data/thermo_params/special/polymer.yaml with "
            "provenance - missing parameters are an error, never an ideal assumption"
        )
    return entry


class FloryHugginsGE(GibbsExcess):  # type: ignore[misc]  # thermo ships no stubs for GibbsExcess
    # 5xx are unclaimed in thermo 0.6.1 (see ngdesign.thermo.ge_models).
    model_id = 510

    """Flory-Huggins gE: segment-mixing entropy plus a chi phi1 phi2 enthalpy.

    gE/RT = sum_i x_i ln(phi_i/x_i) + sum_{i<j} chi_ij phi_i phi_j with volume
    fractions phi_i = x_i r_i / sum_j x_j r_j (Flory 1953; the solvent activity
    form ln a1 = ln phi1 + (1 - 1/r) phi2 + chi phi2^2 is eq. 3.34 of the
    reference text and eq. 4 of Lindvig et al. 2002). chi is composition- and
    temperature-independent (the original FH form; dGE_dT = 0 by construction).
    """

    def __init__(self, T: float, xs: list[float], rs: list[float], chi: list[list[float]]) -> None:
        self.T = T
        self.xs = list(xs)
        self.N = len(xs)
        self.rs = rs
        self.chi = chi
        self.vectorized = False

    def to_T_xs(self, T: float, xs: list[float]) -> FloryHugginsGE:
        return FloryHugginsGE(T=T, xs=list(xs), rs=self.rs, chi=self.chi)

    def _phis(self) -> list[float]:
        rbar = sum(x * r for x, r in zip(self.xs, self.rs, strict=False))
        return [x * r / rbar for x, r in zip(self.xs, self.rs, strict=False)]

    def _solvent(self) -> int:
        return getattr(self, "solvent_idx", 0)

    def GE(self) -> float:
        """gE with the solvent-weighted enthalpy: g/RT = sum x_i ln phi_i
        + chi x_solvent phi_polymer.

        The enthalpy counts solvent-polymer contacts (chi per mole of solvent);
        this normalization is the one whose solvent chemical potential reproduces
        the canonical closed form ln a1 = ln phi1 + (1 - r1/r2) phi2 + chi
        phi2^2 exactly (verified by hand reduction this session; a symmetric
        chi phi1 phi2 term does not).
        """
        xs, phis = self.xs, self._phis()
        s = self._solvent()
        g = sum(x * math.log(phi) for x, phi in zip(xs, phis, strict=False) if x > 0.0)
        g += self.chi[s][1 - s] * xs[s] * phis[1 - s]
        return R * self.T * g

    def dGE_dxs(self) -> list[float]:
        """Unconstrained partials d(gE)/dx_m (central difference, J/mol).

        The analytic reduced form accumulates rbar bookkeeping errors easily;
        the GE itself is closed-form, so the partials are numerical. Checked
        against the closed-form solvent activity via the identity
        ln a_i = g + sum_m (delta_im - x_m) dg/dx_m in the tests.
        """
        h = 1e-7
        out = []
        for j in range(len(self.xs)):
            orig = self.xs[j]
            self.xs[j] = orig + h
            up = self.GE()
            self.xs[j] = orig - h
            dn = self.GE()
            self.xs[j] = orig
            out.append((up - dn) / (2.0 * h))
        return out

    def dGE_dT(self) -> float:
        """chi is temperature-independent in the original FH form."""
        return 0.0

    def gammas(self) -> list[float]:
        """Solvent gamma from the closed form; polymer gamma by Gibbs-Duhem.

        ln a_solvent = ln phi_s + (1 - r_s/r_p) phi_p + chi phi_p^2 exactly
        (hand-reduced from the GE above). The polymer activity follows from
        x_s dln a_s + x_p dln a_p = 0 integrated from pure polymer (a_p = 1).
        """
        s = self._solvent()
        p_idx = 1 - s
        rs, rp = self.rs[s], self.rs[p_idx]

        def ln_a_s(x1: float) -> float:
            phi1 = x1 * rs / (x1 * rs + (1.0 - x1) * rp)
            chi = self.chi[s][p_idx]
            return math.log(phi1) + (1.0 - rs / rp) * (1.0 - phi1) + chi * (1.0 - phi1) ** 2

        x_s = self.xs[s]
        ln_a1 = ln_a_s(x_s)
        ln_g_s = ln_a1 - math.log(x_s) if x_s > 0 else 0.0
        # polymer: dln a_p/dx_s = -(x_s/x_p) dln a_s/dx_s, a_p = 1 at x_s = 1
        h = 1e-5
        eps = 1e-9

        def slope(x: float) -> float:
            xa = max(min(x + h, 1.0 - eps), eps)
            xb = max(min(x - h, 1.0 - eps), eps)
            return (ln_a_s(xa) - ln_a_s(xb)) / (xa - xb)

        ln_a_p = 0.0
        n_steps = 64
        x_start = x_s
        x_end = 1.0 - eps
        if x_end > x_start:
            step = (x_end - x_start) / n_steps
            for k in range(n_steps):
                xm = x_start + step * (k + 0.5)
                xp = 1.0 - xm
                ln_a_p -= (xm / xp) * slope(xm) * step
        x_p = self.xs[p_idx]
        ln_g_p = ln_a_p - math.log(x_p) if x_p > 0 else 0.0
        out = [0.0, 0.0]
        out[s] = math.exp(ln_g_s)
        out[p_idx] = math.exp(max(min(ln_g_p, 700.0), -700.0))
        return out


class FloryHugginsPackage(SpecialGammaPhiPackage):
    """Flory-Huggins polymer-solution package (row ``flory_huggins``)."""

    ge_name = "flory_huggins"

    def _make_ge_factory(self, ids: tuple[str, ...], pseudos: tuple[Any, ...]) -> Any:
        _ensure_poly_ps_registered()
        if len(ids) != 2:
            raise ValueError(
                f"flory_huggins supports exactly one solvent and one polymer; got "
                f"{len(ids)} components (chi keys name the solvent first: "
                "'solvent/polymer')"
            )
        params = _polymer_params()
        segments = params.get("segments") or {}
        chi_table = params.get("chi") or {}
        chi_entry = None
        solvent = None
        for key, entry in chi_table.items():
            parts = key.split("/")
            if set(parts) == set(ids):
                solvent = parts[0]
                chi_entry = entry
                break
        if chi_entry is None:
            raise ValueError(
                f"the flory_huggins model has no chi for the pair {'/'.join(sorted(ids))}; "
                "add it to data/thermo_params/special/polymer.yaml with provenance - "
                "missing parameters are an error, never an ideal assumption"
            )
        rs: list[float] = []
        for cid in ids:
            seg = segments.get(cid)
            if seg is None or seg.get("r") is None:
                raise ValueError(
                    f"the flory_huggins model has no segment count r for {cid!r}; "
                    "add it to data/thermo_params/special/polymer.yaml with provenance"
                )
            rs.append(float(seg["r"]))
        chi = float(chi_entry["chi"])
        s = ids.index(solvent)
        chi_mat = [[0.0, 0.0], [0.0, 0.0]]
        chi_mat[s][1 - s] = chi
        chi_mat[1 - s][s] = chi

        def make(xs: list[float]) -> FloryHugginsGE:
            model = FloryHugginsGE(298.15, list(xs), rs, chi_mat)
            model.solvent_idx = s
            return model

        return make


# --------------------------------------------------------------------------
# Chen (1993) segment-based polymer NRTL
# --------------------------------------------------------------------------


class ChenPolymerNRTLGE(GibbsExcess):  # type: ignore[misc]  # thermo ships no stubs for GibbsExcess
    # 5xx are unclaimed in thermo 0.6.1 (see ngdesign.thermo.ge_models).
    model_id = 520

    """Chen 1993 segment-based local-composition gE for polymer solutions.

    ln gamma_I = ln gamma_I^comb + ln gamma_I^res with the segment combinatorial
    ln gamma_I^comb = ln(phi_I/x_I) + 1 - m_I sum_J x_J phi_J/m_J (phi from
    segment counts m) and the segment-level NRTL residual over segment
    fractions X_i with G_ji = exp(-alpha_ji tau_ji), both as published (Chen,
    Fluid Phase Equilib. 83, 301 (1993)). tau/alpha are temperature-independent
    here (dGE_dT = 0); composition dependence is exact.
    """

    def __init__(
        self,
        T: float,
        xs: list[float],
        segments: list[list[tuple[str, float]]],
        tau: list[list[float]],
        alpha: list[list[float]],
    ) -> None:
        self.T = T
        self.xs = list(xs)
        self.N = len(xs)
        self.segments = segments  # per component: [(segment type, count), ...]
        self.tau = tau
        self.alpha = alpha
        self.vectorized = False
        self.m = [sum(c for _, c in comp) for comp in segments]
        self.types = sorted({t for comp in segments for t, _ in comp})
        self.r_prime = []
        for comp in segments:
            counts = {t: 0.0 for t in self.types}
            for t, c in comp:
                counts[t] += c
            self.r_prime.append([counts[t] for t in self.types])

    def to_T_xs(self, T: float, xs: list[float]) -> ChenPolymerNRTLGE:
        return ChenPolymerNRTLGE(T=T, xs=list(xs), segments=self.segments, tau=self.tau, alpha=self.alpha)

    def _phis(self) -> list[float]:
        mbar = sum(x * m for x, m in zip(self.xs, self.m, strict=False))
        return [x * m / mbar for x, m in zip(self.xs, self.m, strict=False)]

    def _segment_fractions(self) -> list[float]:
        """X_i over segment types, from sum_I x_I r'_iI."""
        raw = [0.0] * len(self.types)
        for x, counts in zip(self.xs, self.r_prime, strict=False):
            for k in range(len(self.types)):
                raw[k] += x * counts[k]
        total = sum(raw)
        return [v / total for v in raw]

    def _ln_res_component(
        self, comp: int, seg_fracs: list[float], big_g: list[list[float]], i_idx: dict[str, int]
    ) -> float:
        """Segment-level NRTL residual for one component (Chen 1993, eqs. 12-14)."""
        X = seg_fracs
        ln_res = 0.0
        n = len(self.types)
        for t, count in self.segments[comp]:
            i = i_idx[t]
            s = 0.0
            for j in range(n):
                denom_ik = sum(X[k] * big_g[k][i] for k in range(n))
                denom_j = sum(X[k] * big_g[k][j] for k in range(n))
                inner = 0.0
                for m2 in range(n):
                    denom_m2 = sum(X[k] * big_g[k][m2] for k in range(n))
                    inner += X[m2] * self.tau[m2][j] * big_g[m2][j] / denom_m2
                s += X[j] * self.tau[j][i] * big_g[j][i] / denom_ik
                s += X[j] * big_g[i][j] / denom_j * (self.tau[i][j] - inner)
            ln_res += count * s
        return ln_res

    def gammas(self) -> list[float]:
        """Closed-form Chen activity coefficients (the primary output)."""
        xs, phis, m = self.xs, self._phis(), self.m
        seg_fracs = self._segment_fractions()
        n_types = len(self.types)
        big_g = [
            [math.exp(-self.alpha[i][j] * self.tau[i][j]) for j in range(n_types)] for i in range(n_types)
        ]
        i_idx = {t: k for k, t in enumerate(self.types)}
        out = []
        for comp in range(len(xs)):
            ln_comb = (
                math.log(phis[comp] / xs[comp])
                + 1.0
                - m[comp] * sum(xs[J] * phis[J] / m[J] for J in range(len(xs)))
            )
            ln_res = self._ln_res_component(comp, seg_fracs, big_g, i_idx)
            out.append(math.exp(ln_comb + ln_res))
        return out

    def GE(self) -> float:
        """gE consistent with the gammas (gE/RT = sum x_I ln gamma_I)."""
        gammas = self.gammas()
        return (
            R
            * self.T
            * sum(x * math.log(g) for x, g in zip(self.xs, gammas, strict=False) if x > 0.0 and g > 0.0)
        )

    def dGE_dxs(self) -> list[float]:
        """Central-difference partials of the analytic GE (smooth composition dependence)."""
        h = 1e-6
        out = []
        for j in range(len(self.xs)):
            orig = self.xs[j]
            self.xs[j] = orig + h
            up = self.GE()
            self.xs[j] = orig - h
            dn = self.GE()
            self.xs[j] = orig
            out.append((up - dn) / (2.0 * h))
        return out

    def dGE_dT(self) -> float:
        """tau/alpha are temperature-independent in this parameterization."""
        return 0.0


class ChenPolymerNRTLPackage(SpecialGammaPhiPackage):
    """Chen segment-based polymer NRTL package (row ``polymer_nrtl``)."""

    ge_name = "polymer_nrtl"

    def _make_ge_factory(self, ids: tuple[str, ...], pseudos: tuple[Any, ...]) -> Any:
        _ensure_poly_ps_registered()
        params = _polymer_params()
        segments_cfg = params.get("segments") or {}

        def segments_of(cid: str) -> list[tuple[str, float]]:
            entry = segments_cfg.get(cid)
            if entry is None or not entry.get("segments"):
                raise ValueError(
                    f"the polymer_nrtl model has no segment assignment for {cid!r}; add "
                    "it to data/thermo_params/special/polymer.yaml with provenance"
                )
            return [(str(t), float(c)) for t, c in entry["segments"]]

        segs = [segments_of(cid) for cid in ids]
        types = sorted({t for comp in segs for t, _ in comp})
        tau = [[0.0] * len(types) for _ in types]
        alpha = [[0.0] * len(types) for _ in types]
        for i, a in enumerate(types):
            for j, b in enumerate(types):
                if i == j:
                    continue
                entry = _pair_param(params, "polymer_nrtl", a, b, "segment_tau")
                # entries carry both directions: tau_ab is a->b, tau_ba is b->a
                tau[i][j] = float(entry["tau_ab"])
                tau[j][i] = float(entry["tau_ba"])
                alpha[i][j] = float(entry["alpha"])
                alpha[j][i] = float(entry["alpha"])

        def make(xs: list[float]) -> ChenPolymerNRTLGE:
            return ChenPolymerNRTLGE(298.15, list(xs), segs, tau, alpha)

        return make


# --------------------------------------------------------------------------
# Oishi-Prausnitz UNIFAC-FV
# --------------------------------------------------------------------------


@cache
def _unifac_fv_params() -> dict[str, Any]:
    """The UNIFAC-FV parameter file, loaded once (static data)."""
    path = _params_dir() / "special" / "unifac_fv.yaml"
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


class UnifacFvGE(GibbsExcess):  # type: ignore[misc]  # thermo ships no stubs for GibbsExcess
    # 5xx are unclaimed in thermo 0.6.1 (see ngdesign.thermo.ge_models).
    model_id = 530

    """UNIFAC-FV solvent activity for a binary solvent/polymer support.

    ln a1 = ln a1^C + ln a1^R + ln a1^FV: the Oishi-Prausnitz split with the
    segment combinatorial, the UNIFAC residual over the curated subgroup
    assignment, and the free-volume term (Ind. Eng. Chem. Process Des. Dev.
    17, 333 (1978); c1 = 1.1):

        ln a1^FV = 3 c1 ln[(v1^(1/3) - 1)/(vM^(1/3) - 1)]
                   - c1 (v1/vM - 1) (1 - v1^(-1/3))^(-1)

    with reduced volumes v = v_spec x M / (15.17 b rbar) (molar volume over the
    vdW segment volume, b = 1.28; rbar is the whole-molecule UNIFAC R and v_spec
    the liquid specific volume in cm3/g). The polymer activity follows by
    Gibbs-Duhem integration of ln a1 over composition (a2 = 1 at pure polymer).
    gammas are the primary output; GE is reported consistently with them.
    """

    C1 = 1.1
    B = 1.28

    def __init__(
        self,
        T: float,
        xs: list[float],
        solvent_idx: int,
        polymer_idx: int,
        m1: float,
        rbar1: float,
        v_spec1: float,
        m2: float,
        rbar2: float,
        v_spec2: float,
        ln_a_unifac_res: Any,
    ) -> None:
        self.T = T
        self.xs = list(xs)
        self.N = len(xs)
        self.solvent_idx = solvent_idx
        self.polymer_idx = polymer_idx
        self.m1 = m1
        self.rbar1 = rbar1
        self.v_spec1 = v_spec1
        self.m2 = m2
        self.rbar2 = rbar2
        self.v_spec2 = v_spec2
        self._ln_a_unifac_res = ln_a_unifac_res  # callable(x1) -> ln a1^UNIFAC
        self.vectorized = False

    def to_T_xs(self, T: float, xs: list[float]) -> UnifacFvGE:
        return UnifacFvGE(
            T=T,
            xs=list(xs),
            solvent_idx=self.solvent_idx,
            polymer_idx=self.polymer_idx,
            m1=self.m1,
            rbar1=self.rbar1,
            v_spec1=self.v_spec1,
            m2=self.m2,
            rbar2=self.rbar2,
            v_spec2=self.v_spec2,
            ln_a_unifac_res=self._ln_a_unifac_res,
        )

    def _ln_a1(self, x1: float) -> float:
        """Solvent activity: Flory combinatorial + UNIFAC residual + FV term.

        The Oishi-Prausnitz split: the combinatorial comes from the segment
        (rbar-weighted) volume fraction, the residual from the UNIFAC engine
        over the curated subgroup assignment, and the size asymmetry from the
        FV term. Taking UNIFAC's mole-fraction combinatorial too would
        misstate the polymer size (it sees only the repeat unit).
        """
        x2 = 1.0 - x1
        phi1 = x1 * self.rbar1 / (x1 * self.rbar1 + x2 * self.rbar2)
        ln_comb = math.log(phi1 / x1) + 1.0 - phi1 / x1
        ln_unifac = self._ln_a_unifac_res(x1)
        # reduced volumes: v_i = v_spec_i * M_i / (15.17 b rbar_i); the mixture
        # volume per R-unit uses weight-fraction-averaged specific volumes over
        # weight-fraction-averaged R-per-gram (Oishi-Prausnitz 1978).
        v1 = self.v_spec1 * self.m1 / (15.17 * self.B * self.rbar1)
        w1 = x1 * self.m1
        w2 = x2 * self.m2
        wtot = w1 + w2
        w1 /= wtot
        w2 /= wtot
        r_per_g = w1 * self.rbar1 / self.m1 + w2 * self.rbar2 / self.m2
        v_mix = (self.v_spec1 * w1 + self.v_spec2 * w2) / (15.17 * self.B * r_per_g)
        ln_fv = 3.0 * self.C1 * math.log((v1 ** (1 / 3) - 1.0) / (v_mix ** (1 / 3) - 1.0)) - self.C1 * (
            (v1 / v_mix - 1.0) * (1.0 - v1 ** (-1 / 3)) ** (-1)
        )
        return float(ln_comb + ln_unifac + ln_fv)

    def gammas(self) -> list[float]:
        """Solvent gamma directly; polymer gamma by Gibbs-Duhem integration."""
        x1 = self.xs[self.solvent_idx]
        ln_a1 = self._ln_a1(x1)
        ln_g1 = ln_a1 - math.log(x1)
        # dln a2/dx1 = -(x1/x2) dln a1/dx1; integrate from pure polymer (a2=1).
        n_steps = 64
        eps = 1e-9
        h = 1e-5
        ln_a2 = 0.0
        x_start = x1
        x_end = 1.0 - eps
        if x_end > x_start:
            step = (x_end - x_start) / n_steps
            for k in range(n_steps):
                xm = x_start + step * (k + 0.5)
                xm2 = 1.0 - xm
                integrand = (xm / xm2) * slope_mid(xm, self._ln_a1, h)
                ln_a2 += integrand * step
        x2 = 1.0 - x1
        ln_g2 = ln_a2 - math.log(x2) if x2 > 0 else 0.0
        out = [0.0] * len(self.xs)
        out[self.solvent_idx] = math.exp(ln_g1)
        out[self.polymer_idx] = math.exp(max(min(ln_g2, 700.0), -700.0))
        return out

    def GE(self) -> float:
        gammas = self.gammas()
        return (
            R
            * self.T
            * sum(x * math.log(g) for x, g in zip(self.xs, gammas, strict=False) if x > 0.0 and g > 0.0)
        )

    def dGE_dxs(self) -> list[float]:
        """Central-difference partials of the analytic GE (smooth composition dependence)."""
        h = 1e-6
        out = []
        for j in range(len(self.xs)):
            orig = self.xs[j]
            self.xs[j] = orig + h
            up = self.GE()
            self.xs[j] = orig - h
            dn = self.GE()
            self.xs[j] = orig
            out.append((up - dn) / (2.0 * h))
        return out

    def dGE_dT(self) -> float:
        """T-dependence enters only through the UNIFAC terms (neglected here)."""
        return 0.0


def slope_mid(x: float, ln_a1: Any, h: float) -> float:
    """Central-difference dln a1/dx1 at x (clamped inside (0, 1))."""
    xa = max(min(x + h, 1.0 - 1e-9), 1e-9)
    xb = max(min(x - h, 1.0 - 1e-9), 1e-9)
    return float((ln_a1(xa) - ln_a1(xb)) / (xa - xb))


class UnifacFvPackage(SpecialGammaPhiPackage):
    """UNIFAC-FV package (row ``unifac_fv``), binary solvent/polymer supports."""

    ge_name = "unifac_fv"

    def _make_ge_factory(self, ids: tuple[str, ...], pseudos: tuple[Any, ...]) -> Any:
        _ensure_poly_ps_registered()
        if len(ids) != 2:
            raise ValueError(
                f"unifac_fv supports exactly one solvent and one polymer; got {len(ids)} "
                "components (the polymer activity follows by Gibbs-Duhem integration)"
            )
        params = _unifac_fv_params()
        polymers = params.get("polymers") or {}
        solvents = params.get("solvents") or {}
        polymer = next((cid for cid in ids if cid in polymers), None)
        solvent = next((cid for cid in ids if cid in solvents), None)
        if polymer is None or solvent is None:
            raise ValueError(
                f"unifac_fv needs one parameterized solvent and one polymer; the support "
                f"{ids} has no entry in data/thermo_params/special/unifac_fv.yaml"
            )
        _state._records(ids, pseudos)  # registry check before the first flash
        ln_res = _unifac_fv_residual(solvent, polymer)

        def make(xs: list[float]) -> UnifacFvGE:
            poly = polymers[polymer]
            solv = solvents[solvent]
            return UnifacFvGE(
                298.15,
                list(xs),
                ids.index(solvent),
                ids.index(polymer),
                m1=float(solv["m"]),
                rbar1=float(solv["rbar"]),
                v_spec1=float(solv["v_spec"]),
                m2=float(poly["m"]),
                rbar2=float(poly["rbar"]),
                v_spec2=float(poly["v_spec"]),
                ln_a_unifac_res=ln_res,
            )

        return make


def _unifac_fv_residual(solvent: str, polymer: str) -> Any:
    """ln a1^UNIFAC (combinatorial + residual) for the solvent, from the thermo engine.

    A binary UNIFAC instance over [solvent, polymer-repeat-unit] is rebuilt per
    call with the solvent mole fraction (the UNIFAC class caches xs-dependent
    terms); its gamma gives the activity term ln(gamma_1 x_1).
    """
    from thermo.unifac import UNIFAC

    from ngdesign.thermo.gamma_phi import _unifac_variant_tables

    version, interaction, sg, _name_to_id, _components = _unifac_variant_tables("unifac")
    solv_groups = {int(g): int(n) for g, n in _fv_groups(solvent)}
    poly_groups = {int(g): int(n) for g, n in _fv_groups(polymer)}

    def ln_a_unifac(x1: float) -> float:
        model = UNIFAC.from_subgroups(
            chemgroups=[solv_groups, poly_groups],
            T=298.15,
            xs=[x1, 1.0 - x1],
            version=version,
            interaction_data=interaction,
            subgroups=sg,
        )
        return float(model.lngammas_r()[0])

    return ln_a_unifac


def _fv_groups(solvent: str) -> list[tuple[int, int]]:
    """Curated UNIFAC subgroup assignment for the solvent."""
    groups = _unifac_fv_params().get("unifac_groups") or {}
    entry = groups.get(solvent)
    if entry is None or not entry.get("groups"):
        raise ValueError(
            f"unifac_fv has no UNIFAC subgroup assignment for {solvent!r}; add it to "
            "data/thermo_params/special/unifac_fv.yaml with provenance"
        )
    return [(int(g), int(n)) for g, n in entry["groups"]]


# --------------------------------------------------------------------------
# Ideal-solubility SLE
# --------------------------------------------------------------------------


class IdealSolidPackage:
    """Ideal-solubility solid-liquid equilibrium (row ``ideal_solid``).

    The solubility of a solid in a liquid solvent at gamma = 1 follows the
    van't Hoff form from the fusion properties:

        ln x_solid = -(dH_fus / R) (1/T - 1/T_m)

    Fusion properties come from the chemicals databank by CAS (curated slate
    ids first, then the chemicals identifier layer for any other chemical
    name); a component without them (pseudo-components) refuses. This is not a
    VLE package: it exposes ``solubility`` directly and refuses flash-style
    calls, so a solid-bearing stream can never be silently flashed as
    vapor/liquid.
    """

    name = "ideal_solid"

    def __init__(self, components: tuple[str, ...] | None = None) -> None:
        self._fusion: dict[str, tuple[float, float]] = {}
        if components:
            for cid in components:
                self.solubility(cid, 298.15)

    @staticmethod
    def _fusion_props(cid: str) -> tuple[float, float]:
        """(Tm [K], Hfus [J/mol]) from the chemicals databank, with refusal."""
        from ngdesign.data import components as data_components

        # Curated databank first; anything else is resolved through the
        # chemicals identifier layer (chemical names, synonyms and CAS
        # numbers), so species like naphthalene work without being added to
        # the curated slate.
        cas = data_components().get(cid, {}).get("cas") or cid
        try:
            return IdealSolidPackage._measured_fusion(cas)
        except Exception as exc:  # noqa: BLE001 - refuse, never approximate
            try:
                from chemicals.identifiers import CAS_from_any

                return IdealSolidPackage._measured_fusion(CAS_from_any(cid))
            except Exception:
                raise ValueError(
                    f"ideal_solid could not resolve fusion properties (Tm, Hfus) for {cid!r}: {exc}"
                ) from exc

    @staticmethod
    def _measured_fusion(cas: str) -> tuple[float, float]:
        """(Tm, Hfus) from the chemicals databank's tabulated sources only.

        Tm: the first tabulated source chemicals ranks (Open Notebook melting
        points, CRC organic constants, CAS Common Chemistry, NIST WebBook,
        Wikidata); Hfus: the CRC Handbook of Chemistry and Physics table
        (chemicals method ``CRC``). The Joback group-contribution estimates
        chemicals also offers are excluded: an estimate is not a published
        fusion property, so a species without tabulated values refuses.
        """
        from chemicals.phase_change import Hfus_methods, Tm_methods

        with DATABANK_LOCK:
            tm_methods = [m for m in Tm_methods(cas) if m != "JOBACK"]
            if not tm_methods or "CRC" not in Hfus_methods(cas):
                raise ValueError(f"no tabulated Tm and CRC Hfus for CAS {cas!r}")
            return float(Tm(cas, method=tm_methods[0])), float(Hfus(cas, method="CRC"))

    def solubility(self, cid: str, T: float) -> float:
        """Ideal mole-fraction solubility of solid ``cid`` at ``T``.

        van't Hoff: ln x = -(dHfus/R)(1/T - 1/Tm). Below Tm the pure liquid
        standard state is metastable but the formula is the ideal-solubility
        definition; above Tm the component is liquid and solubility is not
        defined here (returns > 1).
        """
        if cid not in self._fusion:
            self._fusion[cid] = self._fusion_props(cid)
        tm, hfus = self._fusion[cid]
        if T <= 0.0:
            raise ValueError(f"solubility temperature must be positive, got {T!r}")
        return math.exp(-(hfus / R) * (1.0 / T - 1.0 / tm))

    def _build_flasher(self, ids: tuple[str, ...]) -> Any:
        raise ValueError(
            "ideal_solid is a solid-liquid equilibrium package and does not flash; "
            "use solubility(cid, T). A solid-bearing stream must be routed to the "
            "SLE surface, never silently flashed as vapor/liquid"
        )

    def _build_flasher_vl(self, ids: tuple[str, ...]) -> Any:
        self._build_flasher(ids)

    # -- Thermo protocol surface (P1-01): the row is registered under "thermo",
    # so it must structurally satisfy the contract. Every flash-style entry
    # point refuses - an SLE package must never answer a VLE question - while
    # k_values/pure_psat use the protocol's explicit None ("not applicable").

    def flash_pt(self, z: dict[str, float], T: float, P: float, molar_flow: float) -> Any:
        self._refuse_flash()

    def flash_ph(self, z: dict[str, float], P: float, H: float, molar_flow: float) -> Any:
        self._refuse_flash()

    def flash_ps(self, z: dict[str, float], P: float, S: float, molar_flow: float) -> Any:
        self._refuse_flash()

    def flash_tvf(self, z: dict[str, float], T: float, vf: float, molar_flow: float) -> Any:
        self._refuse_flash()

    def flash_pvf(self, z: dict[str, float], P: float, vf: float, molar_flow: float) -> Any:
        self._refuse_flash()

    def bubble_point(self, z: dict[str, float], *, T: float | None = None, P: float | None = None) -> Any:
        self._refuse_flash()

    def dew_point(self, z: dict[str, float], *, T: float | None = None, P: float | None = None) -> Any:
        self._refuse_flash()

    def k_values(self, z: dict[str, float], T: float, P: float) -> None:
        self._refuse_flash()

    def phase_props(self, composition: dict[str, float], T: float, P: float, kind: Any) -> Any:
        self._refuse_flash()

    def derivatives(self, composition: dict[str, float], T: float, P: float, kind: Any) -> Any:
        self._refuse_flash()

    def pure_psat(self, cid: str, T: float) -> None:
        return None  # an SLE package contributes no vapour-pressure correlation

    def _refuse_flash(self) -> None:
        raise ValueError(
            "ideal_solid is a solid-liquid equilibrium package and does not flash; "
            "use solubility(cid, T). A solid-bearing stream must be routed to the "
            "SLE surface, never silently flashed as vapor/liquid"
        )


# --------------------------------------------------------------------------
# Vapour-phase association: chemical theory (Marek-Standart), in-house
# --------------------------------------------------------------------------
#
# References for every equation in this section:
# - Marek & Standart, Collect. Czech. Chem. Commun. 19, 1074 (1954): vapour of
#   an associating substance as an ideal-gas mixture of true species in
#   chemical equilibrium; apparent fugacity of the associating component =
#   partial pressure of its monomer.
# - Prausnitz, Lichtenthaler & de Azevedo, Molecular Thermodynamics of
#   Fluid-Phase Equilibria, 3rd ed. (1999), sec. 5.8-5.9 (chemical theory of
#   association, dimerization of carboxylic acids): f_A = y_A0 P (true monomer
#   fraction times P), Kp = y_D / (y_A0^2 P), Z = n_true / n_apparent; the
#   same chemical-theory treatment carries over to the n-mer (HF hexamer,
#   Schotte, Ind. Eng. Chem. Process Des. Dev. 19, 432 (1980)).
# - Gamma-phi with a saturation fugacity coefficient (the "PhiSat" basis of
#   thermo's GibbsExcessLiquid): f_i^L = x_i gamma_i phi_i^sat P_i^sat
#   (Prausnitz et al. 3rd ed., eq. 10-4 with the Poynting factor at unity).


@cache
def _association_params() -> dict[str, Any]:
    """The association parameter file, loaded once (static data)."""
    path = _params_dir() / "special" / "association.yaml"
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


_LN10 = math.log(10.0)


@dataclass(frozen=True)
class AssociationLaw:
    """One-species n-mer association n A <=> A_n between ideal-gas true species.

    ln Kp(T) = ln_k_a + ln_k_b / T with Kp = p_(A_n) / p_A^n in Pa^(1-n): the
    van't Hoff form with a constant association enthalpy
    dH = -R ln_k_b (J per mole of n-mer formed; d ln Kp / dT = dH / (R T^2)).
    """

    n: int
    ln_k_a: float
    ln_k_b: float

    @property
    def dH(self) -> float:
        """Association enthalpy, J per mole of n-mer (negative: exothermic)."""
        return -R * self.ln_k_b

    def ln_k(self, T: float) -> float:
        """ln Kp(T), Kp in Pa^(1-n)."""
        return self.ln_k_a + self.ln_k_b / T

    @classmethod
    def dimer(cls, dH_assoc: float, K2_ref: float, T_ref: float) -> AssociationLaw:
        """Dimerization from a reference constant: ln K = ln K2_ref - (dH/R)(1/T - 1/T_ref)."""
        return cls(2, math.log(K2_ref) + dH_assoc / (R * T_ref), -dH_assoc / R)

    @classmethod
    def hexamer(cls, log10_k6_a: float, log10_k6_b: float) -> AssociationLaw:
        """Hexamerization from log10 Kp = a + b/T (Kp in Pa^-5)."""
        return cls(6, _LN10 * log10_k6_a, _LN10 * log10_k6_b)


@dataclass(frozen=True)
class AssociationState:
    """Chemical-theory vapour state at fixed (T, P, apparent composition).

    ``ln_w`` is the log apparent fugacity coefficient of the associating
    component (w = true monomer fraction over its apparent fraction,
    z_M / y_A); ``e`` is
    n_apparent / n_true = 1/Z, which is also the apparent fugacity coefficient
    of every non-associating component (phi_I = z_I / y_I); ``xi`` is the moles
    of n-mer per apparent mole. The ``d*`` fields are derivatives with respect
    to ln kappa (kappa = Kp P^(n-1)), the only route by which T and P enter.
    """

    ln_w: float
    e: float
    xi: float
    dlnw: float
    dlne: float
    dxi: float


def _softplus(t: float) -> float:
    """ln(1 + e^t) without overflow."""
    return t + math.log1p(math.exp(-t)) if t > 0.0 else math.log1p(math.exp(t))


def _logistic(t: float) -> float:
    """1 / (1 + e^-t) without overflow."""
    if t >= 0.0:
        return 1.0 / (1.0 + math.exp(-t))
    et = math.exp(t)
    return et / (1.0 + et)


def _solve_ln_monomer_ratio(ln_alpha: float, n: int) -> float:
    """v = ln w for the root of w + alpha w^n = 1, solved in log space.

    In v the root equation is f(v) = v + ln(1 + exp(ln_alpha + (n-1) v)) = 0,
    increasing and convex; Newton from v0 = min(0, -ln_alpha/n), where
    f(v0) > 0, therefore decreases monotonically onto the root (no overflow
    for any alpha the flash can reach, e.g. at the far T bounds of thermo's
    PH/PS secant).
    """
    v = min(0.0, -ln_alpha / n)
    for _ in range(200):
        t = ln_alpha + (n - 1) * v
        step = (v + _softplus(t)) / (1.0 + (n - 1) * _logistic(t))
        v_new = v - step
        if v_new >= v or abs(step) <= 1e-15 * max(1.0, abs(v)):
            return min(v, v_new)
        v = v_new
    return v


def association_state(y_a: float, ln_kappa: float, n: int) -> AssociationState:
    """Chemical-theory state of a vapour with one n-merizing component.

    True species: monomer M, n-mer A_n, and the non-associating components I,
    all ideal gases. With apparent fractions y (y_a for the associating
    component), the material balance and Kp = p_n / p_M^n reduce, for the
    monomer ratio w = z_M / y_a, to (Marek & Standart 1954; Prausnitz et al.
    3rd ed. sec. 5.9, generalized from n = 2):

        w + alpha w^n = 1,   alpha = c kappa y_a^(n-1),
        c = n - (n-1) y_a,   kappa = Kp P^(n-1)

    With r = w / (1 - w) (= 1/q, q = alpha w^(n-1)) the apparent properties
    are closed forms that stay finite as w -> 0:

        ln phi_a = ln w,   ln phi_I = ln E = -ln Z,   E = w + n (1 - w) / c
        xi = y_a / (c r + n)            (n-mer moles per apparent mole)

    (Z = 1/E = 1 - (n-1) xi). Derivatives in u = ln kappa (the only route by
    which T and P enter at fixed y) follow by implicit differentiation of the
    root equation: d ln w/du = -1/(n + r), d ln q/du = 1 + (n-1) d ln w/du,
    dE/du = w (1 - n/c) d ln w/du, dxi/du = y_a c r (d ln q/du) / (c r + n)^2.
    y_a = 0 is the exact infinite-dilution limit (w -> 1, no association).
    """
    if y_a <= 0.0:
        return AssociationState(0.0, 1.0, 0.0, 0.0, 0.0, 0.0)
    c = n - (n - 1) * y_a
    v = _solve_ln_monomer_ratio(math.log(c) + ln_kappa + (n - 1) * math.log(y_a), n)
    w = math.exp(v)
    one_minus_w = -math.expm1(v)
    if one_minus_w <= 0.0:  # kappa so small that w rounds to 1: no association
        return AssociationState(0.0, 1.0, 0.0, 0.0, 0.0, 0.0)
    r = w / one_minus_w
    dlnw = -1.0 / (n + r)
    dlnq = 1.0 + (n - 1) * dlnw
    e = w + n * one_minus_w / c
    dlne = w * (1.0 - n / c) * dlnw / e
    crn = c * r + n
    xi = y_a / crn
    dxi = y_a * c * r * dlnq / (crn * crn)
    return AssociationState(v, e, xi, dlnw, dlne, dxi)


def dimer_vapor_compressibility(T: float, P: float, dH_assoc: float, K2_ref: float, T_ref: float) -> float:
    """Vapour compressibility factor of a dimerizing acid vapour, NOMINAL pressure basis.

    Chemical theory with a single dimerization equilibrium (the leading term of
    the Hayden-O'Connell / Marek-Standart treatment): monomer M and dimer D in
    ideal gas-phase equilibrium Kp(T) = p_D / p_M^2 with

        Kp(T) = K2_ref exp(-(dH_assoc/R)(1/T - 1/T_ref))   [1/Pa]

    and the material balance P = p_M + 2 p_D, i.e. ``P`` is the NOMINAL
    pressure (all acid counted as monomer; the flash phase
    :class:`AssociatingGas` takes the true pressure instead). Solving
    2 kp p_M^2 + p_M - P = 0 for the equilibrium monomer partial pressure
    gives the compressibility of the nominal acid: Z = (p_M + p_D) /
    (p_M + 2 p_D), the ratio of equilibrium-mixture moles to analytical acid
    moles.
    """
    if T <= 0.0 or P <= 0.0:
        raise ValueError(f"association needs positive T and P, got T={T!r} P={P!r}")
    kp = K2_ref * math.exp(-(dH_assoc / R) * (1.0 / T - 1.0 / T_ref))  # 1/Pa
    # p_D = kp p_M^2, P = p_M + 2 p_D  ->  2 kp p_M^2 + p_M - P = 0
    # (the dimer carries TWO acid molecules per pressure-bearing molecule)
    disc = 1.0 + 8.0 * kp * P
    p_m = (-1.0 + math.sqrt(disc)) / (4.0 * kp)
    p_d = kp * p_m * p_m
    return (p_m + p_d) / (p_m + 2.0 * p_d)


def hexamer_vapor_compressibility(T: float, P: float, log10_k6_a: float, log10_k6_b: float) -> float:
    """Vapour compressibility factor of an HF vapour associating to hexamers (TRUE pressure).

    Chemical theory with the single hexamerization equilibrium (the oligomer
    association treatment of Schotte 1980; parameters from Jarry & Davis
    1953): 6 M <=> H with Kp(T) = p_H / p_M^6 = 10**(a + b/T) [1/Pa^5] and
    the true pressure P = p_M + p_H. Evaluated through
    :func:`association_state` for the pure vapour (y_a = 1): w = p_M / P
    solves w + Kp P^5 w^6 = 1 and Z = (p_M + p_H) / (p_M + 6 p_H) = 1/E.
    """
    if T <= 0.0 or P <= 0.0:
        raise ValueError(f"association needs positive T and P, got T={T!r} P={P!r}")
    law = AssociationLaw.hexamer(log10_k6_a, log10_k6_b)
    return 1.0 / association_state(1.0, law.ln_k(T) + (law.n - 1) * math.log(P), law.n).e


# Second-order and volume-explicit derivatives the association vapour does not
# implement. IdealGas defines each with its ideal closed form; inheriting those
# would silently report ideal-gas values for an associating vapour, so each is
# replaced by an explicit refusal (none is on the flash/property surface used).
_ASSOCIATING_GAS_UNSUPPORTED = (
    "d2P_dT2",
    "d2P_dT2_V",
    "d2P_dV2",
    "d2P_dV2_T",
    "d2P_dTdV",
    "d2T_dV2",
    "d2T_dV2_P",
    "d2V_dT2",
    "d2V_dT2_P",
    "d2V_dP2",
    "d2V_dP2_T",
    "d2T_dP2",
    "d2T_dP2_V",
    "PIP",
    "dV_dzs",
    "d2H_dT2",
    "d2H_dP2",
    "d2H_dTdP",
    "dH_dT_V",
    "dH_dP_V",
    "dH_dV_T",
    "dH_dV_P",
    "dH_dzs",
    "d2S_dP2",
    "dS_dT_V",
    "dS_dP_V",
    "d2P_dTdP",
    "d2P_dVdP",
    "d2P_dVdT_TP",
    "d2P_dT2_PV",
    "dS_dzs",
    "dlnphis_dzs",
)


class AssociatingGas(IdealGas):  # type: ignore[misc]  # thermo ships no stubs
    """Chemical-theory vapour: one n-merizing component plus non-associating ones.

    The true species (monomer, n-mer, every other component) form an ideal-gas
    mixture in association equilibrium (Marek & Standart 1954); the phase
    reports APPARENT-composition properties (per mole of apparent, i.e.
    nominal, species), which is what the flash balances:

        ln phi_A = ln(z_M / y_A),  ln phi_I = -ln Z (I non-associating)
        G_dep / RT = sum_i y_i ln phi_i
        H_dep = xi dH                 (n-mer moles per apparent mole x dH)
        V = Z R T / P,  Z = n_true / n_apparent = 1 - (n-1) xi
        S_dep = (H_dep - G_dep) / T

    (Prausnitz et al. 3rd ed. sec. 5.8-5.9; H_dep is -R T^2 d(G_dep/RT)/dT
    and V_dep is R T d(G_dep/RT)/dP - both identities are checked by finite
    differences in tests/thermo/test_special.py). Cp, the T/P derivatives of
    ln phi, V, H and S are analytic through d/d ln kappa. Ideal-gas parts come
    from the parent (HeatCapacityGases). Cross-association between the
    associating component and the others is not modelled (no parameters).
    """

    composition_independent = False  # never let FlashVL take the K-independent shortcut

    def __init__(
        self,
        association: AssociationLaw,
        assoc_index: int,
        HeatCapacityGases: Any = None,
        T: float = IdealGas.T_DEFAULT,
        P: float = IdealGas.P_DEFAULT,
        zs: list[float] | None = None,
    ) -> None:
        super().__init__(HeatCapacityGases=HeatCapacityGases, T=T, P=P, zs=zs)
        self.association = association
        self.assoc_index = assoc_index

    def __repr__(self) -> str:
        return (
            f"AssociatingGas(n={self.association.n}, assoc_index={self.assoc_index}, "
            f"T={self.T!r}, P={self.P!r}, zs={self.zs!r})"
        )

    def to_TP_zs(self, T: float, P: float, zs: list[float]) -> AssociatingGas:
        new = super().to_TP_zs(T, P, zs)
        new.association = self.association
        new.assoc_index = self.assoc_index
        return cast("AssociatingGas", new)

    def to(
        self, zs: list[float], T: float | None = None, P: float | None = None, V: float | None = None
    ) -> AssociatingGas:
        if V is not None:
            raise ValueError(
                "the association vapour is specified by (T, P) only; a volume specification "
                "would need V = Z(T, P) R T / P inverted, which this phase does not do"
            )
        if T is None or P is None:
            raise ValueError("Two of T, P, or V are needed")
        return self.to_TP_zs(T, P, zs)

    # -- association state --------------------------------------------------

    def _assoc(self) -> AssociationState:
        cached: AssociationState | None = self.__dict__.get("_assoc_state")
        if cached is not None:
            return cached
        state = association_state(float(self.zs[self.assoc_index]), self._ln_kappa(), self.association.n)
        self.__dict__["_assoc_state"] = state
        return state

    def _ln_kappa(self) -> float:
        """ln kappa = ln Kp(T) + (n-1) ln P."""
        law = self.association
        return float(law.ln_k(self.T) + (law.n - 1) * math.log(self.P))

    def _du_dT(self) -> float:
        """d ln kappa / dT at fixed P (van't Hoff)."""
        return float(self.association.dH / (R * self.T * self.T))

    def _du_dP(self) -> float:
        """d ln kappa / dP at fixed T."""
        return float((self.association.n - 1) / self.P)

    def _per_component(self, assoc_value: float, inert_value: float) -> list[float]:
        return [assoc_value if i == self.assoc_index else inert_value for i in range(self.N)]

    # -- fugacity -----------------------------------------------------------

    def lnphis(self) -> list[float]:
        st = self._assoc()
        return self._per_component(st.ln_w, math.log(st.e))

    lnphis_G_min = lnphis
    lnphis_lowest_Gibbs = lnphis

    def phis(self) -> list[float]:
        return [math.exp(v) for v in self.lnphis()]

    def fugacities(self) -> list[float]:
        P = self.P
        return [P * float(z) * phi for z, phi in zip(self.zs, self.phis(), strict=True)]

    def dlnphis_dT(self) -> list[float]:
        st, du = self._assoc(), self._du_dT()
        return self._per_component(st.dlnw * du, st.dlne * du)

    def dlnphis_dP(self) -> list[float]:
        st, du = self._assoc(), self._du_dP()
        return self._per_component(st.dlnw * du, st.dlne * du)

    def dphis_dT(self) -> list[float]:
        return [p * d for p, d in zip(self.phis(), self.dlnphis_dT(), strict=True)]

    def dphis_dP(self) -> list[float]:
        return [p * d for p, d in zip(self.phis(), self.dlnphis_dP(), strict=True)]

    def dlnphis_dns(self) -> list[list[float]]:
        """d ln phi_i / d n_j at fixed T, P (central difference on mole numbers).

        The closed form needs the derivative of the root w through y_a; the
        state itself is closed-form, so the partials are numerical (step 1e-6
        on a one-mole basis, as the polymer gE partials in this module).
        """
        h = 1e-6
        n, ln_kappa = self.association.n, self._ln_kappa()
        base = [float(z) for z in self.zs]
        a = self.assoc_index

        def lnphis_at(ns: list[float]) -> list[float]:
            total = sum(ns)
            st = association_state(ns[a] / total, ln_kappa, n)
            return self._per_component(st.ln_w, math.log(st.e))

        cols: list[list[float]] = []
        for j in range(self.N):
            up, dn = list(base), list(base)
            up[j] += h
            dn[j] -= h
            hi, lo = lnphis_at(up), lnphis_at(dn)
            cols.append([(u - d) / (2.0 * h) for u, d in zip(hi, lo, strict=True)])
        return [[cols[j][i] for j in range(self.N)] for i in range(self.N)]

    # -- volumetric ---------------------------------------------------------

    def V(self) -> float:
        return float(R * self.T / (self.P * self._assoc().e))

    def dV_dT(self) -> float:
        st = self._assoc()
        V = self.V()
        return float(V / self.T - V * st.dlne * self._du_dT())

    def dV_dP(self) -> float:
        st = self._assoc()
        V = self.V()
        return float(-V / self.P - V * st.dlne * self._du_dP())

    def dP_dT(self) -> float:
        return float(-self.dV_dT() / self.dV_dP())

    def dP_dV(self) -> float:
        return float(1.0 / self.dV_dP())

    def dT_dP(self) -> float:
        return float(1.0 / self.dP_dT())

    def dT_dV(self) -> float:
        return float(1.0 / self.dV_dT())

    dV_dT_P = dV_dT
    dV_dP_T = dV_dP
    dP_dT_V = dP_dT
    dP_dV_T = dP_dV
    dT_dP_V = dT_dP
    dT_dV_P = dT_dV

    # -- caloric ------------------------------------------------------------

    def H_dep(self) -> float:
        return float(self._assoc().xi * self.association.dH)

    def G_dep(self) -> float:
        g_rt = sum(float(z) * lnphi for z, lnphi in zip(self.zs, self.lnphis(), strict=True))
        return float(R * self.T * g_rt)

    def S_dep(self) -> float:
        return float((self.H_dep() - self.G_dep()) / self.T)

    def U_dep(self) -> float:
        return float(self.H_dep() - (self.P * self.V() - R * self.T))

    def A_dep(self) -> float:
        return float(self.U_dep() - self.T * self.S_dep())

    def H(self) -> float:
        return float(self.H_ideal_gas() + self.H_dep())

    def S(self) -> float:
        return float(self.S_ideal_gas() + self.S_dep())

    def Cp(self) -> float:
        st = self._assoc()
        return float(self.Cp_ideal_gas() + self.association.dH * st.dxi * self._du_dT())

    dH_dT = Cp
    dH_dT_P = Cp

    def Cp_dep(self) -> float:
        return float(self.Cp() - self.Cp_ideal_gas())

    def dH_dP(self) -> float:
        return float(self.association.dH * self._assoc().dxi * self._du_dP())

    dH_dP_T = dH_dP

    def dS_dT(self) -> float:
        return float(self.Cp() / self.T)

    dS_dT_P = dS_dT

    def dS_dP(self) -> float:
        return float(-self.dV_dT())  # Maxwell: (dS/dP)_T = -(dV/dT)_P

    dS_dP_T = dS_dP


def _refuse_unsupported(name: str) -> Any:
    def refuse(self: Any, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError(
            f"AssociatingGas.{name} is not implemented (the IdealGas closed form would be "
            "wrong for an associating vapour, so it is refused rather than inherited)"
        )

    refuse.__name__ = name
    return refuse


for _name in _ASSOCIATING_GAS_UNSUPPORTED:
    setattr(AssociatingGas, _name, _refuse_unsupported(_name))


class _AssociationSaturation:
    """Saturation fugacity coefficient of the pure associating component.

    phi_sat(T) = phi of the pure chemical-theory vapour at (T, Psat(T)), with
    Psat the liquid's own vapour-pressure correlation, so a pure feed boils
    exactly at Psat. With kappa_s = Kp(T) Psat(T)^(n-1) and w the pure-vapour
    root (w + kappa_s w^n = 1): ln phi_sat = ln w and

        d ln phi_sat/dT = L1 s1,  d2 ln phi_sat/dT2 = L2 s1^2 + L1 s2
        L1 = -1/(n + r),  L2 = dL1/du = L1^2 dr/du,  dr/du = r L1 / (1 - w),
        r = w / (1 - w)
        s1 = dH/(R T^2) + (n-1) Psat'/Psat
        s2 = -2 dH/(R T^3) + (n-1) (Psat''/Psat - (Psat'/Psat)^2)

    Duck-types the pure-EOS interface thermo's GibbsExcessLiquid reads under
    equilibrium_basis "PhiSat" (phi_sat / dphi_sat_dT / d2phi_sat_dT2, Tc);
    thermo's liquid H, S and Cp then carry the matching T derivatives.
    """

    def __init__(self, law: AssociationLaw, vapour_pressure: Any, Tc: float) -> None:
        self.law = law
        self.vapour_pressure = vapour_pressure
        self.Tc = Tc

    def _terms(self, T: float) -> tuple[float, float, float]:
        """(phi_sat, d ln phi_sat/dT, d2 ln phi_sat/dT2) at T."""
        law, vp = self.law, self.vapour_pressure
        n = law.n
        psat = float(vp.T_dependent_property(T))
        d1 = float(vp.T_dependent_property_derivative(T, order=1)) / psat
        d2 = float(vp.T_dependent_property_derivative(T, order=2)) / psat
        st = association_state(1.0, law.ln_k(T) + (n - 1) * math.log(psat), n)
        w, l1 = math.exp(st.ln_w), st.dlnw
        # L2 = d(L1)/du with L1 = -1/(n + r), r = w/(1 - w): dr/du = r L1 / (1 - w)
        r = w / -math.expm1(st.ln_w) if st.ln_w < 0.0 else math.inf
        l2 = 0.0 if math.isinf(r) else l1 * l1 * r * l1 / -math.expm1(st.ln_w)
        s1 = law.dH / (R * T * T) + (n - 1) * d1
        s2 = -2.0 * law.dH / (R * T**3) + (n - 1) * (d2 - d1 * d1)
        return w, l1 * s1, l2 * s1 * s1 + l1 * s2

    def phi_sat(self, T: float, polish: bool = True) -> float:
        return self._terms(T)[0]

    def dphi_sat_dT(self, T: float, polish: bool = True) -> float:
        phi, dln, _ = self._terms(T)
        return phi * dln

    def d2phi_sat_dT2(self, T: float, polish: bool = True) -> float:
        phi, dln, d2ln = self._terms(T)
        return phi * (dln * dln + d2ln)


class _InertSaturation:
    """phi_sat = 1 for a non-associating component (its pure vapour is ideal here)."""

    def __init__(self, Tc: float) -> None:
        self.Tc = Tc

    def phi_sat(self, T: float, polish: bool = True) -> float:
        return 1.0

    def dphi_sat_dT(self, T: float, polish: bool = True) -> float:
        return 0.0

    def d2phi_sat_dT2(self, T: float, polish: bool = True) -> float:
        return 0.0


class _AssociatingVapourPackage(SpecialGammaPhiPackage):
    """Gamma-phi package whose vapour is the chemical-theory :class:`AssociatingGas`.

    Exactly one component of the support must carry association parameters in
    data/thermo_params/special/association.yaml (section ``section``); the
    others are non-associating true species in the vapour. Two associating
    components refuse: their cross-association constant is not shipped. The
    liquid is ideal on apparent composition (gamma = 1) with the PhiSat basis,
    f_i^L = x_i phi_i^sat P_i^sat.
    """

    section = ""

    def _law(self, entry: dict[str, Any]) -> AssociationLaw:
        raise NotImplementedError

    def _association(self, ids: tuple[str, ...]) -> tuple[int, AssociationLaw]:
        table = _association_params().get(self.section) or {}
        found = [cid for cid in ids if cid in table]
        if not found:
            raise ValueError(
                f"the {self.ge_name} model needs one component with {self.section} parameters; "
                f"none of {list(ids)} has any - add them to "
                "data/thermo_params/special/association.yaml with provenance (missing "
                "parameters are an error, never an ideal assumption)"
            )
        if len(found) > 1:
            raise ValueError(
                f"the {self.ge_name} model supports one associating component; {found} all "
                "associate and their cross-association constants are not shipped"
            )
        return ids.index(found[0]), self._law(table[found[0]])

    def _make_ge_factory(self, ids: tuple[str, ...], pseudos: tuple[Any, ...]) -> Any:
        self._association(ids)

        def make(xs: list[float]) -> Any:
            return IdealSolution(T=298.15, xs=list(xs))

        return make

    def _build_flasher(self, ids: tuple[str, ...]) -> Any:
        association = self._association(ids)
        make_ge = self._make_ge_factory(ids, self._slate_pseudos)
        return _special_flasher(make_ge, ids, self._slate_pseudos, association=association)


class HaydenOConnellDimerPackage(_AssociatingVapourPackage):
    """Gamma-phi package with a dimerizing acid vapour (row ``hoc_dimer``).

    Vapour: :class:`AssociatingGas` with n = 2 on the per-acid Kp(T)
    (Ritter & Simons 1945 for acetic acid; association.yaml section
    ``dimerization``). Liquid: ideal on apparent composition with the
    saturation fugacity coefficient of the associating acid.
    """

    ge_name = "hoc_dimer"
    section = "dimerization"

    def _law(self, entry: dict[str, Any]) -> AssociationLaw:
        return AssociationLaw.dimer(float(entry["dH_assoc"]), float(entry["K2_ref"]), float(entry["T_ref"]))


class HFHexamerPackage(_AssociatingVapourPackage):
    """Gamma-phi package with an HF-hexamerizing vapour (row ``hf_hexamer``).

    Vapour: :class:`AssociatingGas` with n = 6 on the Jarry & Davis (1953)
    monomer-hexamer Kp(T) (association.yaml section ``hexamerization``).
    Liquid: ideal on apparent composition with the saturation fugacity
    coefficient of HF.
    """

    ge_name = "hf_hexamer"
    section = "hexamerization"

    def _law(self, entry: dict[str, Any]) -> AssociationLaw:
        return AssociationLaw.hexamer(float(entry["log10_k6_a"]), float(entry["log10_k6_b"]))


class PolymerPCSAFT(TeqpPackage):
    """Polymer PC-SAFT over the T-07 teqp bridge (row ``polymer_pc_saft``).

    Segment parameters (chain length ``m``, segment diameter ``sigma``,
    segment energy ``epsilon/k``) for the polystyrene pseudo-component
    POLY_PS and the solvent toluene come from
    data/thermo_params/special/polymer.yaml with citations; the kernel build
    lives in the bridge (``_build_kernel`` kind ``polymer_pc_saft``). The row
    constructs without teqp and refuses at first use like every saft row:
    :class:`SaftDependencyMissing` without the optional extra,
    :class:`SaftParameterError` naming any component without verified
    parameters.
    """

    model_kind = "polymer_pc_saft"
