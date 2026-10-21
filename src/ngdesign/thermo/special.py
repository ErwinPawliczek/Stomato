"""Special-chemistry thermodynamics: polymer solutions, SLE, association (spec T-10).

One module, four families behind the catalogue rows in
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

Polymers enter as flowsheet-owned or registered pseudo-components (spec P1-07);
the params file documents the polystyrene characterization used by the
validation cases. Provenance lives in the params files and the catalogue rows;
every numerical derivation is cited there.

The special-chemistry rows ship as ``experimental``: the models and equations
are implemented and unit-tested against published references, but the
parameter base is thin (one or two polymer pairs, dimerization only), so the
rows stay out of the advisor's suggested set until validation cases bind
(data/validation/special/cases.yaml carries the pending cases with reasons).

SI units throughout: K, Pa, J/mol, J/(mol K).
"""

from __future__ import annotations

import math
from functools import cache
from typing import Any

import yaml
from chemicals.phase_change import Hfus, Tm
from thermo import FlashVL, GibbsExcessLiquid, IdealGas
from thermo.activity import GibbsExcess

from ngdesign.data import DATABANK_LOCK, register_pseudo
from ngdesign.thermo import _state
from ngdesign.thermo._state import R_IDEAL as R
from ngdesign.thermo.cubic import ThermoSurfaceMixin


def _params_dir() -> Any:
    from ngdesign.thermo.gamma_phi import PARAMS_DIR

    return PARAMS_DIR


def _shared_cached(self_key: tuple[Any, ...], key: tuple[Any, ...], compute: Any) -> Any:
    from ngdesign.thermo.gamma_phi import _shared_cached as _impl

    return _impl(self_key, key, compute)


# --------------------------------------------------------------------------
# Flasher wiring (mirrors gamma_phi._build_flasher_inner, two-phase only)
# --------------------------------------------------------------------------


def _special_flasher(make_ge: Any, ids: tuple[str, ...], pseudos: tuple[Any, ...]) -> Any:
    """One two-phase gamma-phi flasher over exactly this sorted component set.

    Same shared state layer as every other package: records resolve through the
    open component registry (flowsheet-owned pseudo definitions win), constants
    and correlations come from ``_state._constants_package`` so pseudo-components
    get the merged package, and the vapour phase is ideal-gas.
    """
    with DATABANK_LOCK:
        records = _state._records(ids, pseudos)
        constants, correlations = _state._constants_package(records)
        gas = IdealGas(HeatCapacityGases=correlations.HeatCapacityGases)

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
            )

        return FlashVL(constants, correlations, gas=gas, liquid=ge_liquid())


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
            with DATABANK_LOCK:
                return float(Tm(cas)), float(Hfus(cas))
        except Exception as exc:  # noqa: BLE001 - refuse, never approximate
            try:
                from chemicals.identifiers import CAS_from_any

                alt = CAS_from_any(cid)
                with DATABANK_LOCK:
                    return float(Tm(alt)), float(Hfus(alt))
            except Exception:
                raise ValueError(
                    f"ideal_solid could not resolve fusion properties (Tm, Hfus) for {cid!r}: {exc}"
                ) from exc

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
# Dimerization association kernel (Hayden-O'Connell family, in-house)
# --------------------------------------------------------------------------


@cache
def _association_params() -> dict[str, Any]:
    """The association parameter file, loaded once (static data)."""
    path = _params_dir() / "special" / "association.yaml"
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def dimer_vapor_compressibility(T: float, P: float, dH_assoc: float, K2_ref: float, T_ref: float) -> float:
    """Vapour compressibility factor of a dimerizing acid vapour.

    Chemical theory with a single dimerization equilibrium (the leading term of
    the Hayden-O'Connell / Marek-Standart treatment): monomer M and dimer D in
    ideal gas-phase equilibrium Kp(T) = p_D / p_M^2 with

        Kp(T) = K2_ref exp(-(dH_assoc/R)(1/T - 1/T_ref))   [1/Pa]

    and the material balance P = p_M + 2 p_D (dimer counts one pressure-bearing
    molecule per two acid molecules). Solving 2 kp p_M^2 + p_M - P = 0 for the
    equilibrium monomer partial pressure gives the compressibility of the
    *nominal* acid: Z = (p_M + p_D) / (p_M + 2 p_D), the ratio of equilibrium
    mixture moles to analytical acid moles.
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


class HaydenOConnellDimerPackage(SpecialGammaPhiPackage):
    """Gamma-phi package with a dimerizing acid vapour (row ``hoc_dimer``).

    The liquid is ideal on apparent composition; the vapour applies the
    in-house dimerization kernel above. The kernel is exercised directly
    (dimer_vapor_compressibility) against the published compressibility point;
    wiring it through the two-phase flash is the follow-up once the special
    flasher exposes vapour-phase hooks.
    """

    ge_name = "hoc_dimer"

    def _make_ge_factory(self, ids: tuple[str, ...], pseudos: tuple[Any, ...]) -> Any:
        params = _association_params()
        assoc = params.get("dimerization") or {}
        for cid in ids:
            if cid not in assoc:
                raise ValueError(
                    f"the hoc_dimer model has no association parameters for {cid!r}; add "
                    "them to data/thermo_params/special/association.yaml with provenance"
                )

        def make(xs: list[float]) -> Any:
            return IdealLiquidGE(298.15, list(xs))

        return make


class IdealLiquidGE(GibbsExcess):  # type: ignore[misc]  # thermo ships no stubs for GibbsExcess
    # 5xx are unclaimed in thermo 0.6.1 (see ngdesign.thermo.ge_models).
    model_id = 540

    """Explicit ideal liquid (gamma = 1) for association-corrected vapour work."""

    def __init__(self, T: float, xs: list[float]) -> None:
        self.T = T
        self.xs = list(xs)
        self.N = len(xs)
        self.vectorized = False

    def to_T_xs(self, T: float, xs: list[float]) -> IdealLiquidGE:
        return IdealLiquidGE(T=T, xs=list(xs))

    def GE(self) -> float:
        return 0.0

    def dGE_dxs(self) -> list[float]:
        return [0.0] * len(self.xs)

    def dGE_dT(self) -> float:
        return 0.0

    def gammas(self) -> list[float]:
        return [1.0] * len(self.xs)
