"""Rate-based (non-equilibrium) column stages: the Krishna-Taylor formulation.

The solver behind the R3 levels of the ``absorber`` and ``reboiled_stripper``
catalogue rows (adapters in :mod:`ngdesign.units.column.rate_based_units`).

Method - Taylor & Krishna, *Multicomponent Mass Transfer* (Wiley, 1993), ch. 14, and
Taylor, Kooijman & Hung, "A second generation nonequilibrium model for computer
simulation of multicomponent separation processes", Comput. Chem. Eng. 18 (1994)
205-217. Each packed segment j (numbered 1..n top to bottom, vapour up, liquid down,
both phases perfectly mixed) carries separate vapour and liquid balances coupled by
interphase fluxes ``N_ij`` (positive vapour -> liquid) and an energy flux ``E_j``:

* vapour component balance   ``v_ij - v_i,j+1 - fV_ij + N_ij = 0``
* liquid component balance   ``l_ij - l_i,j-1 - fL_ij - N_ij = 0``
* interface equilibrium      ``yI_ij = K_ij(TI_j, P_j, xI_j, yI_j) xI_ij``, with
  ``sum yI = sum xI = 1``; ``K = phi_L/phi_V`` from the flowsheet package's
  ``phase_props`` fugacity coefficients (``ln_phi``) and their temperature derivatives
  (``derivatives``) - the package's own equilibrium, not a separate model.
* vapour-film rates (c-1)    ``N_i = J^V_i + y_i N_t``,
  ``J^V_i = G^V_i (y_i - yI_i) - y_i sum_k G^V_k (y_k - yI_k)``
* liquid-film rates (c-1)    ``N_i = J^L_i + x_i N_t``,
  ``J^L_i = G^L_i (xI_i - x_i) - x_i sum_k G^L_k (xI_k - x_k)``
* vapour energy balance      ``H^V_out - H^V_in - H_fV + E^V = 0``
* liquid energy balance      ``H^L_out - H^L_in - H_fL - E^L = 0``
* interface energy           ``E^V = E^L``, with
  ``E^V = (hA)^V (T^V - T^I) + sum N_i Hbar^V_i(T^V)`` and
  ``E^L = (hA)^L (T^I - T^L) + sum N_i Hbar^L_i(T^L)``.

That is 5c+3 equations in ``v, l, yI, xI, N`` (c each) and ``T^V, T^L, T^I``.
``G_i = c_t k_i a_w A h`` is the film conductance (mol/s per unit mole-fraction
difference) from the Onda (1968) coefficients and wetted area
(:mod:`.rate_based_transport`). The film model is the **effective-diffusivity (Fick)**
form (Taylor & Krishna 1993, the effective-diffusivity method, each species with its
own mixture diffusivity); the subtracted ``y_i sum_k ...`` term is the
mixture-averaged "correction flux" that makes the diffusion fluxes sum to zero exactly
(``sum_i J_i = 0`` for any composition), so the c-th rate equation is the identity sum
of the others and the result does not depend on which component is dropped. It is not
the Maxwell-Stefan matrix model; diffusional interaction (Toor) effects are absent.

A kettle reboiler (stripper) is an equilibrium stage below the packing, as in the
rate-based literature (condensers and reboilers stay equilibrium stages): ``v_i + l_i
- l_i,in - f_i = 0``, ``y_i = K_i(T) x_i`` and one spec equation (boilup ratio, bottoms
or distillate rate, or reboiler duty through its energy balance).

A condenser (distillation, the ``column`` R3) is the mirror end above the top stage:

* **partial** - an equilibrium stage: ``v_i + l_i - v_i,in - f_i = 0``,
  ``y_i = K_i(T) x_i``, one top spec; ``v`` is the vapour distillate, ``l`` the reflux.
* **total** - the whole top vapour condenses to saturated liquid: unknowns the
  distillate ``d`` and reflux ``l`` (liquid, c each) and ``T``; ``d_i + l_i - v_i,in =
  0``, equal compositions ``l_i/L - d_i/D = 0`` (i < c), the bubble condition
  ``sum_i K_i(T) x_i - 1 = 0`` (``K`` at the incipient vapour), one top spec.

Top specs (:data:`CONDENSER_SPECS`): reflux ratio ``L/D``, distillate rate ``D``, or
condenser duty (heat removed) ``H_in - H_D - H_L``.

The middle stages may instead be equilibrium-stage trays with a Murphree vapour
efficiency (``RateColumnSpec.murphree``; Murphree, E. V., "Rectifying column
calculations", Ind. Eng. Chem. 17 (1925) 747-750): ``v_i + l_i - v_i,in - l_i,in - f_i
= 0``, ``y_i = y_i,in + E (y*_i - y_i,in)`` with ``y* = K(T) x`` and ``K`` anchored at
(``x``, ``y*``) - a fixed point on ``y* = norm(K x)`` - and the adiabatic tray energy
balance. ``y_in`` is the vapour entering the tray (from below, plus any vapour feed to
the tray), the convention :func:`murphree_vapour` reports. Summing the c Murphree rows
gives ``E (sum K x - 1) = 0``: each tray sits at its liquid's bubble point and both
phases leave at the tray ``T``. At ``E = 1`` the tray is the R2 MESH stage.

Solution: inside-out on the property models. The **outer** loop anchors, at the
current state, per-stage frozen models - ``ln K_i(T) = ln K_i0 + (dlnK_i/dT)(T - T0)``
at the interface compositions; per-phase partial molar enthalpies
``Hbar_i(T) = Hbar_i0 + c_p (T - T0)`` at the bulk compositions (numerical composition
derivatives of ``phase_props`` enthalpy, Euler-corrected so ``sum z_i Hbar_i0 = H``);
the film conductances and heat-transfer coefficients. The **inner** loop solves the
whole column simultaneously by Newton (block-tridiagonal structure, finite-difference
Jacobian by three-colour stage grouping) with those models frozen. Converged when the
residual evaluated with freshly anchored models - i.e. the exact package K-values and
enthalpies at the state - is below :data:`_TOL` (scaled: balance rows by the total
feed, energy balances by total feed x 1 kJ/mol; the film-rate rows and the rows
carrying ``hA (T - T_I)`` by the larger of that and their own conductance, whose
round-off floor grows with it). In the vapour/liquid/interface energy triple the
liquid row is replaced by the equivalent total stage balance, which carries no
``E`` and so closes to the absolute tolerance at any transfer rate.

``transfer_factor`` multiplies every film conductance and heat-transfer coefficient
(the correction factor Perry's *Chemical Engineers' Handbook* 8th ed., Sec. 14, text
after eq. 14-75, notes commercial rate-based software provides); as it grows the
interface resistances vanish and the stage reduces to an equilibrium stage - the R2
column's model - which the tests check.

All SI: K, Pa abs, mol/s, J/mol, W, m. Pure functions; no I/O; no global state.
"""

from __future__ import annotations

import math
import warnings
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray
from scipy.sparse import csc_matrix
from scipy.sparse.linalg import MatrixRankWarning, spsolve

from ngdesign.contracts import PhaseKind, StreamState
from ngdesign.contracts.plugins import Thermo

from .rate_based_transport import (
    ONDA_RE_G_RANGE,
    ONDA_RE_L_RANGE,
    ComponentTransport,
    PackingGeometry,
    chilton_colburn_h,
    component_transport,
    liquid_effective_diffusivities,
    onda_1968,
    penetration_h,
    vapour_effective_diffusivities,
)

Vec = NDArray[np.float64]

#: Converged when the scaled residual (exact models) max-norm is below this.
_TOL = 1e-8
#: Inner Newton tolerance (frozen models).
_INNER_TOL = 1e-11
_MAX_OUTER = 60
_MAX_INNER = 60
#: Energy-row scale, J/mol (times the total feed).
_E_SCALE = 1e3
#: Largest temperature change per Newton step, K.
_DT_MAX = 15.0
#: Composition-derivative step for partial molar enthalpies.
_H_EPS = 1e-5

KETTLE_SPECS = ("boilup_ratio", "bottoms_rate", "distillate_rate", "reboiler_duty_W")
CONDENSER_SPECS = ("reflux_ratio", "distillate_rate", "condenser_duty_W")
CONDENSER_KINDS = ("total", "partial")
#: Incipient-vapour fixed point (K anchored at y* = norm(K x)): tolerance and budget.
_YSTAR_TOL = 1e-13
_YSTAR_MAX = 60


class RateBasedConvergenceError(RuntimeError):
    """The rate-based column did not converge within its bounded budget."""


@dataclass(frozen=True)
class StageFeed:
    """A feed split by phase onto one stage (0-based, top = 0)."""

    stage: int
    vap: tuple[float, ...]  # component mol/s entering the vapour side
    liq: tuple[float, ...]  # component mol/s entering the liquid side
    h_vap_W: float
    h_liq_W: float


@dataclass(frozen=True)
class RateColumnSpec:
    """Everything the rate-based solve needs.

    Stages top to bottom: the condenser (when ``condenser`` is set), ``n_rate`` middle
    stages (packed segments, or Murphree trays when ``murphree`` is set, one efficiency
    per tray), the kettle (when ``kettle``). ``geometry`` may be None for Murphree trays.
    """

    cids: tuple[str, ...]
    pressures: tuple[float, ...]  # one per stage, condenser and kettle included
    n_rate: int  # middle stages
    kettle: bool  # an equilibrium kettle reboiler is the last stage
    feeds: tuple[StageFeed, ...]
    geometry: PackingGeometry | None
    surface_tension_N_m: float
    transfer_factor: float = 1.0
    kettle_spec: tuple[str, float] | None = None
    condenser: str | None = None  # "total" | "partial": stage 0
    condenser_spec: tuple[str, float] | None = None
    murphree: tuple[float, ...] | None = None


def stage_kinds(spec: RateColumnSpec) -> tuple[str, ...]:
    """Block kind per stage, top to bottom: ``total``/``partial``, ``rate``/``tray``, ``kettle``."""
    top = (spec.condenser,) if spec.condenser is not None else ()
    middle = ("tray" if spec.murphree is not None else "rate",) * spec.n_rate
    return (*top, *middle, *(("kettle",) if spec.kettle else ()))


@dataclass
class _RateModel:
    """Frozen per-segment models (one outer anchor)."""

    lnk0: Vec
    dlnk: Vec
    ti0: float
    hv0: Vec
    cpv: float
    tv0: float
    hl0: Vec
    cpl: float
    tl0: float
    gv: Vec
    gl: Vec
    hav: float
    hal: float
    diag: dict[str, float] = field(default_factory=dict)


@dataclass
class _KettleModel:
    """Frozen equilibrium-stage model (kettle, condenser, Murphree tray). For a total
    condenser the "vapour" slot carries the liquid distillate, so ``hv0``/``cpv`` are
    the liquid's (``_hv`` then returns the distillate's enthalpy flow)."""

    lnk0: Vec
    dlnk: Vec
    t0: float
    hv0: Vec
    cpv: float
    hl0: Vec
    cpl: float


@dataclass
class RateProfile:
    """Converged rate-based column."""

    cids: tuple[str, ...]
    v: list[Vec]  # vapour component flows leaving each stage
    liq: list[Vec]  # liquid component flows leaving each stage
    tv: list[float]
    tl: list[float]
    ti: list[float]  # interface T (kettle: its T)
    yi: list[Vec]  # interface vapour (rate stages)
    xi: list[Vec]  # interface liquid (rate stages)
    flux: list[Vec]  # N_ij, vapour -> liquid (rate stages)
    energy_flux_W: list[float]  # E_j (rate stages)
    h_vap_W: list[float]  # enthalpy flow of each stage's vapour (exact models)
    h_liq_W: list[float]
    reboiler_duty_W: float
    outer_iterations: int
    inner_iterations: int
    max_residual: float
    diagnostics: list[dict[str, float]]
    condenser_duty_W: float = 0.0  # heat removed by the condenser (0 without one)
    kinds: tuple[str, ...] = ()  # block kind per stage (see stage_kinds)


# --------------------------------------------------------------------------------------
# Layout
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Layout:
    c: int
    kinds: tuple[str, ...]
    offsets: tuple[int, ...]
    size: int

    @staticmethod
    def build(c: int, kinds: tuple[str, ...]) -> _Layout:
        offs: list[int] = []
        o = 0
        for kind in kinds:
            offs.append(o)
            o += 5 * c + 3 if kind == "rate" else 2 * c + 1
        return _Layout(c, kinds, tuple(offs), o)

    @property
    def n_stages(self) -> int:
        return len(self.kinds)

    def is_rate(self, j: int) -> bool:
        return self.kinds[j] == "rate"

    def block(self, j: int) -> int:
        return 5 * self.c + 3 if self.is_rate(j) else 2 * self.c + 1


def _norm(z: Vec) -> Vec:
    s = float(np.sum(z))
    return z / s if s > 0.0 else np.full_like(z, 1.0 / len(z))


def _as_comp(cids: tuple[str, ...], z: Vec) -> dict[str, float]:
    zn = _norm(np.maximum(z, 0.0))
    return {cid: float(v) for cid, v in zip(cids, zn, strict=True)}


# --------------------------------------------------------------------------------------
# Property anchoring (the only thermo calls)
# --------------------------------------------------------------------------------------


def _partial_molar(
    thermo: Thermo, cids: tuple[str, ...], z: Vec, T: float, P: float, kind: PhaseKind
) -> tuple[Vec, float, object]:
    """Partial molar enthalpies (Euler-corrected), mixture cp and the base PhaseProps.

    ``Hbar_i = d(nH)/dn_i`` by a forward mole-number perturbation of ``phase_props``.
    """
    zn = _norm(np.maximum(z, 0.0))
    base = thermo.phase_props(_as_comp(cids, zn), T, P, kind)
    h = base.enthalpy
    out = np.empty(len(cids))
    for i in range(len(cids)):
        zp = zn.copy()
        zp[i] += _H_EPS
        hp = thermo.phase_props(_as_comp(cids, zp), T, P, kind).enthalpy
        out[i] = ((1.0 + _H_EPS) * hp - h) / _H_EPS
    out -= float(np.dot(zn, out)) - h  # Euler: sum z_i Hbar_i = H exactly at the anchor
    return out, base.cp, base


def _k_model(thermo: Thermo, cids: tuple[str, ...], x: Vec, y: Vec, T: float, P: float) -> tuple[Vec, Vec]:
    """``ln K_i = ln phi_L,i - ln phi_V,i`` and its T-derivative at (x, y, T, P)."""
    xc, yc = _as_comp(cids, x), _as_comp(cids, y)
    pl = thermo.phase_props(xc, T, P, PhaseKind.HC_LIQUID)
    pv = thermo.phase_props(yc, T, P, PhaseKind.VAPOR)
    dl = thermo.derivatives(xc, T, P, PhaseKind.HC_LIQUID)
    dv = thermo.derivatives(yc, T, P, PhaseKind.VAPOR)
    try:
        lnk = np.array([pl.ln_phi[c] - pv.ln_phi[c] for c in cids])
        dlnk = np.array([dl.dlnphi_dT[c] - dv.dlnphi_dT[c] for c in cids])
    except KeyError as exc:
        raise RateBasedConvergenceError(
            f"rate-based column needs per-component fugacity coefficients from the thermo "
            f"package; missing {exc}"
        ) from exc
    return lnk, dlnk


def _rate_model(
    thermo: Thermo,
    spec: RateColumnSpec,
    comps: list[ComponentTransport],
    v: Vec,
    liq: Vec,
    yi: Vec,
    xi: Vec,
    tv: float,
    tl: float,
    ti: float,
    P: float,
) -> _RateModel:
    cids = spec.cids
    lnk, dlnk = _k_model(thermo, cids, xi, yi, ti, P)
    hv0, cpv, pv = _partial_molar(thermo, cids, v, tv, P, PhaseKind.VAPOR)
    hl0, cpl, pl = _partial_molar(thermo, cids, liq, tl, P, PhaseKind.HC_LIQUID)
    y = _norm(np.maximum(v, 0.0))
    x = _norm(np.maximum(liq, 0.0))
    geom = spec.geometry
    if geom is None:
        raise ValueError("rate-based segments need the packing geometry")
    area = geom.cross_section_m2
    mw_v, mw_l = pv.molecular_weight, pl.molecular_weight  # type: ignore[attr-defined]
    rho_v, rho_l = pv.density, pl.density  # type: ignore[attr-defined]
    mu_v, mu_l = pv.viscosity, pl.viscosity  # type: ignore[attr-defined]
    lam_v, lam_l = pv.thermal_conductivity, pl.thermal_conductivity  # type: ignore[attr-defined]
    if mu_v is None or mu_l is None or lam_v is None or lam_l is None:
        raise RateBasedConvergenceError(
            "rate-based column needs viscosity and thermal conductivity from the thermo "
            "package's phase_props; this package returns None"
        )
    big_g = float(np.sum(np.maximum(v, 0.0))) * mw_v / 1000.0 / area
    big_l = float(np.sum(np.maximum(liq, 0.0))) * mw_l / 1000.0 / area
    d_v = vapour_effective_diffusivities(list(y), tv, P, comps)
    d_l = liquid_effective_diffusivities(list(x), tl, float(mu_l), comps)
    onda = onda_1968(
        geom, big_g, big_l, rho_v, float(mu_v), rho_l, float(mu_l), spec.surface_tension_N_m, d_v, d_l
    )
    a_int = onda.a_w * area * geom.segment_height_m  # interfacial area of the segment, m2
    c_v = rho_v / (mw_v / 1000.0)
    c_l = rho_l / (mw_l / 1000.0)
    f = spec.transfer_factor
    gv = f * c_v * np.array(onda.k_gas) * a_int
    gl = f * c_l * np.array(onda.k_liq) * a_int
    kv_mean = float(np.dot(y, onda.k_gas))
    kl_mean = float(np.dot(x, onda.k_liq))
    dv_mean = float(np.dot(y, d_v))
    dl_mean = float(np.dot(x, d_l))
    hv = chilton_colburn_h(kv_mean, c_v, cpv, float(lam_v), rho_v, cpv / (mw_v / 1000.0), dv_mean)
    hl = penetration_h(kl_mean, c_l, cpl, float(lam_l), rho_l, cpl / (mw_l / 1000.0), dl_mean)
    diag = {
        "a_w_m2_m3": onda.a_w,
        "Re_L": onda.re_l,
        "Re_G": onda.re_g,
        "onda_in_range": float(
            ONDA_RE_L_RANGE[0] <= onda.re_l <= ONDA_RE_L_RANGE[1]
            and ONDA_RE_G_RANGE[0] <= onda.re_g <= ONDA_RE_G_RANGE[1]
        ),
        "h_V_W_m2K": hv,
        "h_L_W_m2K": hl,
    }
    for cid, kg, kl, dg, dli in zip(cids, onda.k_gas, onda.k_liq, d_v, d_l, strict=True):
        diag[f"kV_{cid}_m_s"] = kg
        diag[f"kL_{cid}_m_s"] = kl
        diag[f"DV_{cid}_m2_s"] = dg
        diag[f"DL_{cid}_m2_s"] = dli
    return _RateModel(
        lnk0=lnk,
        dlnk=dlnk,
        ti0=ti,
        hv0=hv0,
        cpv=cpv,
        tv0=tv,
        hl0=hl0,
        cpl=cpl,
        tl0=tl,
        gv=gv,
        gl=gl,
        hav=f * hv * a_int,
        hal=f * hl * a_int,
        diag=diag,
    )


def _kettle_model(
    thermo: Thermo, cids: tuple[str, ...], v: Vec, liq: Vec, T: float, P: float
) -> _KettleModel:
    lnk, dlnk = _k_model(thermo, cids, liq, v, T, P)
    hv0, cpv, _ = _partial_molar(thermo, cids, v, T, P, PhaseKind.VAPOR)
    hl0, cpl, _ = _partial_molar(thermo, cids, liq, T, P, PhaseKind.HC_LIQUID)
    return _KettleModel(lnk0=lnk, dlnk=dlnk, t0=T, hv0=hv0, cpv=cpv, hl0=hl0, cpl=cpl)


def _k_model_incipient(
    thermo: Thermo, cids: tuple[str, ...], x: Vec, y_seed: Vec, T: float, P: float
) -> tuple[Vec, Vec]:
    """``ln K`` and its T-derivative at (x, y*), y* the vapour in equilibrium with x:
    the fixed point ``y* = norm(K(x, y*, T) x)`` (successive substitution from
    ``y_seed``). A Murphree tray's or a total condenser's vapour is not ``K x``, so
    anchoring at the actual vapour would put phi_V at the wrong composition."""
    xn = _norm(np.maximum(x, 0.0))
    ys = _norm(np.maximum(y_seed, 0.0))
    for _ in range(_YSTAR_MAX):
        lnk, dlnk = _k_model(thermo, cids, xn, ys, T, P)
        y_new = _norm(np.exp(lnk) * xn)
        if float(np.max(np.abs(y_new - ys))) < _YSTAR_TOL:
            return lnk, dlnk
        ys = y_new
    raise RateBasedConvergenceError(
        f"incipient-vapour fixed point y* = norm(K x) did not converge in {_YSTAR_MAX} passes "
        f"at T = {T:.3f} K, P = {P:.0f} Pa"
    )


def _eq_model(
    thermo: Thermo, cids: tuple[str, ...], kind: str, v: Vec, liq: Vec, T: float, P: float
) -> _KettleModel:
    """Frozen model of an equilibrium-stage block (kettle, partial/total condenser, tray)."""
    if kind in ("kettle", "partial"):
        return _kettle_model(thermo, cids, v, liq, T, P)
    lnk, dlnk = _k_model_incipient(thermo, cids, liq, v, T, P)
    hl0, cpl, _ = _partial_molar(thermo, cids, liq, T, P, PhaseKind.HC_LIQUID)
    if kind == "total":  # the "vapour" slot is the liquid distillate (same composition)
        return _KettleModel(lnk0=lnk, dlnk=dlnk, t0=T, hv0=hl0.copy(), cpv=cpl, hl0=hl0, cpl=cpl)
    hv0, cpv, _ = _partial_molar(thermo, cids, v, T, P, PhaseKind.VAPOR)
    return _KettleModel(lnk0=lnk, dlnk=dlnk, t0=T, hv0=hv0, cpv=cpv, hl0=hl0, cpl=cpl)


# --------------------------------------------------------------------------------------
# Residuals (frozen models; pure numpy)
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Unpacked:
    v: list[Vec]
    liq: list[Vec]
    t_v: list[float]  # vapour T per stage (kettle: T)
    t_l: list[float]


def _unpack(lay: _Layout, X: Vec) -> _Unpacked:
    c = lay.c
    v: list[Vec] = []
    liq: list[Vec] = []
    tv: list[float] = []
    tl: list[float] = []
    for j in range(lay.n_stages):
        o = lay.offsets[j]
        v.append(X[o : o + c])
        liq.append(X[o + c : o + 2 * c])
        if lay.is_rate(j):
            tv.append(float(X[o + 5 * c]))
            tl.append(float(X[o + 5 * c + 1]))
        else:
            tv.append(float(X[o + 2 * c]))
            tl.append(float(X[o + 2 * c]))
    return _Unpacked(v, liq, tv, tl)


@dataclass(frozen=True)
class _FeedTable:
    fv: list[Vec]
    fl: list[Vec]
    hfv: list[float]
    hfl: list[float]
    total: float


def _feed_table(spec: RateColumnSpec, n: int) -> _FeedTable:
    c = len(spec.cids)
    fv = [np.zeros(c) for _ in range(n)]
    fl = [np.zeros(c) for _ in range(n)]
    hfv = [0.0] * n
    hfl = [0.0] * n
    for f in spec.feeds:
        fv[f.stage] += np.array(f.vap)
        fl[f.stage] += np.array(f.liq)
        hfv[f.stage] += f.h_vap_W
        hfl[f.stage] += f.h_liq_W
    total = float(sum(np.sum(a) for a in fv) + sum(np.sum(a) for a in fl))
    return _FeedTable(fv, fl, hfv, hfl, total)


def _hv(m: _RateModel | _KettleModel, v: Vec, T: float) -> float:
    if isinstance(m, _RateModel):
        return float(np.dot(v, m.hv0 + m.cpv * (T - m.tv0)))
    return float(np.dot(v, m.hv0 + m.cpv * (T - m.t0)))


def _hl(m: _RateModel | _KettleModel, liq: Vec, T: float) -> float:
    if isinstance(m, _RateModel):
        return float(np.dot(liq, m.hl0 + m.cpl * (T - m.tl0)))
    return float(np.dot(liq, m.hl0 + m.cpl * (T - m.t0)))


def _eq_block_residual(
    spec: RateColumnSpec,
    kind: str,
    feeds: _FeedTable,
    m: _KettleModel,
    j: int,
    t: float,
    v: Vec,
    liq: Vec,
    v_in: Vec,
    l_in: Vec,
    h_v_in: float,
    h_l_in: float,
    out: Vec,
) -> None:
    """Rows of a condenser (``total``/``partial``) or Murphree ``tray`` block, in place.

    ``v`` is the vapour leaving (for a total condenser: the liquid distillate). The row
    order matches the block's unknowns: c balances, c equilibrium/Murphree rows (a
    total condenser: c-1 composition equalities and the bubble condition), then the
    top spec (condensers) or the adiabatic energy balance (tray).
    """
    c = len(spec.cids)
    fs = feeds.total
    es = fs * _E_SCALE
    vt, lt = float(np.sum(v)), float(np.sum(liq))
    k = np.exp(m.lnk0 + m.dlnk * (t - m.t0))
    x = liq / lt
    h_f = feeds.hfv[j] + feeds.hfl[j]
    h_v, h_l = _hv(m, v, t), _hl(m, liq, t)
    out[:c] = (v + liq - v_in - l_in - feeds.fv[j] - feeds.fl[j]) / fs
    if kind == "tray":
        assert spec.murphree is not None
        eff = spec.murphree[j - (1 if spec.condenser is not None else 0)]
        y_in = _norm(v_in + feeds.fv[j])
        out[c : 2 * c] = v / vt - y_in - eff * (k * x - y_in)
        out[2 * c] = (h_v + h_l - h_v_in - h_l_in - h_f) / es
        return
    if kind == "partial":
        out[c : 2 * c] = v / vt - k * x
    else:  # total: the condensate's composition is shared; it sits at its bubble point
        out[c : 2 * c - 1] = x[: c - 1] - v[: c - 1] / vt
        out[2 * c - 1] = float(np.dot(k, x)) - 1.0
    assert spec.condenser_spec is not None
    name, value = spec.condenser_spec
    if name == "reflux_ratio":
        out[2 * c] = (lt - value * vt) / fs
    elif name == "distillate_rate":
        out[2 * c] = (vt - value) / fs
    else:  # condenser_duty_W, heat removed
        out[2 * c] = (h_v_in + h_f - h_v - h_l - value) / es


def _residual(
    spec: RateColumnSpec,
    lay: _Layout,
    feeds: _FeedTable,
    models: list[_RateModel | _KettleModel],
    X: Vec,
) -> Vec:
    c = lay.c
    n = lay.n_stages
    up = _unpack(lay, X)
    fs = feeds.total
    es = fs * _E_SCALE
    out = np.empty(lay.size)
    for j in range(n):
        o = lay.offsets[j]
        m = models[j]
        v, liq = up.v[j], up.liq[j]
        v_in = up.v[j + 1] if j + 1 < n else np.zeros(c)
        l_in = up.liq[j - 1] if j > 0 else np.zeros(c)
        h_v_in = _hv(models[j + 1], v_in, up.t_v[j + 1]) if j + 1 < n else 0.0
        h_l_in = _hl(models[j - 1], l_in, up.t_l[j - 1]) if j > 0 else 0.0
        if isinstance(m, _RateModel):
            yi = X[o + 2 * c : o + 3 * c]
            xi = X[o + 3 * c : o + 4 * c]
            nf = X[o + 4 * c : o + 5 * c]
            tv, tl, ti = X[o + 5 * c], X[o + 5 * c + 1], X[o + 5 * c + 2]
            vt, lt = float(np.sum(v)), float(np.sum(liq))
            y = v / vt
            x = liq / lt
            nt = float(np.sum(nf))
            k = np.exp(m.lnk0 + m.dlnk * (ti - m.ti0))
            r = o
            out[r : r + c] = (v - v_in - feeds.fv[j] + nf) / fs
            r += c
            out[r : r + c] = (liq - l_in - feeds.fl[j] - nf) / fs
            r += c
            out[r : r + c] = yi - k * xi
            r += c
            out[r] = float(np.sum(yi)) - 1.0
            out[r + 1] = float(np.sum(xi)) - 1.0
            r += 2
            dy = y - yi
            jv = m.gv * dy - y * float(np.dot(m.gv, dy))
            out[r : r + c - 1] = (nf[: c - 1] - jv[: c - 1] - y[: c - 1] * nt) / max(fs, float(np.sum(m.gv)))
            r += c - 1
            dx = xi - x
            jl = m.gl * dx - x * float(np.dot(m.gl, dx))
            out[r : r + c - 1] = (nf[: c - 1] - jl[: c - 1] - x[: c - 1] * nt) / max(fs, float(np.sum(m.gl)))
            r += c - 1
            hbar_v = m.hv0 + m.cpv * (tv - m.tv0)
            hbar_l = m.hl0 + m.cpl * (tl - m.tl0)
            e_v = m.hav * (tv - ti) + float(np.dot(nf, hbar_v))
            e_l = m.hal * (ti - tl) + float(np.dot(nf, hbar_l))
            # Equivalent energy rows: the vapour balance, the TOTAL stage balance (vapour
            # + liquid - interface rows, free of E so it closes to the absolute
            # tolerance whatever hA is) and the interface condition. The rows carrying
            # hA*(T - T_I) are scaled by hA*1 K: at large transfer factors their
            # round-off floor is hA*eps*T, not a stage-balance error.
            h_v_out = float(np.dot(v, hbar_v))
            h_l_out = float(np.dot(liq, hbar_l))
            out[r] = (h_v_out - h_v_in - feeds.hfv[j] + e_v) / max(es, m.hav)
            out[r + 1] = (h_v_out + h_l_out - h_v_in - h_l_in - feeds.hfv[j] - feeds.hfl[j]) / es
            out[r + 2] = (e_v - e_l) / max(es, m.hav + m.hal)
        elif lay.kinds[j] != "kettle":
            _eq_block_residual(spec, lay.kinds[j], feeds, m, j, X[o + 2 * c], v, liq, v_in, l_in, h_v_in, h_l_in, out[o : o + 2 * c + 1])
        else:
            t = X[o + 2 * c]
            vt, lt = float(np.sum(v)), float(np.sum(liq))
            k = np.exp(m.lnk0 + m.dlnk * (t - m.t0))
            r = o
            out[r : r + c] = (v + liq - l_in - feeds.fv[j] - feeds.fl[j]) / fs
            r += c
            out[r : r + c] = v / vt - k * liq / lt
            r += c
            assert spec.kettle_spec is not None
            name, value = spec.kettle_spec
            if name == "boilup_ratio":
                out[r] = (vt - value * lt) / fs
            elif name == "bottoms_rate":
                out[r] = (lt - value) / fs
            elif name == "distillate_rate":
                out[r] = (float(np.sum(up.v[0])) - value) / fs
            else:  # reboiler_duty_W
                h_out = _hv(m, v, t) + _hl(m, liq, t)
                out[r] = (h_out - h_l_in - feeds.hfv[j] - feeds.hfl[j] - value) / es
    return out


# --------------------------------------------------------------------------------------
# Newton on the frozen models
# --------------------------------------------------------------------------------------


_Meta = tuple[NDArray[np.int64], NDArray[np.int64], Vec, NDArray[np.bool_], NDArray[np.bool_]]


def _var_meta(lay: _Layout, fs: float) -> _Meta:
    """Per-variable stage index, local index, FD floor, positivity and temperature masks."""
    c = lay.c
    stage = np.empty(lay.size, dtype=np.int64)
    local = np.empty(lay.size, dtype=np.int64)
    floor = np.empty(lay.size)
    pos = np.zeros(lay.size, dtype=bool)
    temp = np.zeros(lay.size, dtype=bool)
    for j in range(lay.n_stages):
        o = lay.offsets[j]
        b = lay.block(j)
        stage[o : o + b] = j
        local[o : o + b] = np.arange(b)
        floor[o : o + 2 * c] = 1e-6 * fs
        pos[o : o + 2 * c] = True
        if lay.is_rate(j):
            floor[o + 2 * c : o + 4 * c] = 1e-6
            pos[o + 2 * c : o + 4 * c] = True
            floor[o + 4 * c : o + 5 * c] = 1e-6 * fs
            floor[o + 5 * c : o + 5 * c + 3] = 1e-2
            temp[o + 5 * c : o + 5 * c + 3] = True
        else:
            floor[o + 2 * c] = 1e-2
            temp[o + 2 * c] = True
    return stage, local, floor, pos, temp


def _jacobian(
    f: Callable[[Vec], Vec],
    X: Vec,
    f0: Vec,
    lay: _Layout,
    meta: _Meta,
    top_couples_kettle: bool,
) -> NDArray[np.float64]:
    """Forward-difference Jacobian with three-colour stage grouping (block-tridiagonal).

    A ``distillate_rate`` kettle spec reads the top stage's vapour, the one coupling
    outside the band: the top stage then gets a colour of its own and its columns
    also fill the kettle rows.
    """
    stage, local, floor, _, _ = meta
    jac = np.zeros((lay.size, lay.size))
    max_b = max(lay.block(j) for j in range(lay.n_stages))
    colour_of = stage % 3
    if top_couples_kettle:
        colour_of = np.where(stage == 0, 3, colour_of)
    last = lay.n_stages - 1
    for colour in range(4):
        for k in range(max_b):
            idx = np.nonzero((colour_of == colour) & (local == k))[0]
            if idx.size == 0:
                continue
            h = 1e-7 * np.maximum(np.abs(X[idx]), floor[idx])
            xp = X.copy()
            xp[idx] += h
            df = f(xp) - f0
            for p, hp in zip(idx, h, strict=True):
                s = stage[p]
                rows = (stage >= s - 1) & (stage <= s + 1)
                if top_couples_kettle and s == 0:
                    rows = rows | (stage == last)
                jac[rows, p] = df[rows] / hp
    return jac


def _newton(
    f: Callable[[Vec], Vec], X: Vec, lay: _Layout, fs: float, tol: float, top_couples_kettle: bool
) -> tuple[Vec, int, float]:
    meta = _var_meta(lay, fs)
    _, _, _, pos, temp = meta
    f0 = f(X)
    norm0 = float(np.linalg.norm(f0))
    its = 0
    for its in range(1, _MAX_INNER + 1):
        if float(np.max(np.abs(f0))) < tol:
            return X, its - 1, float(np.max(np.abs(f0)))
        jac = _jacobian(f, X, f0, lay, meta, top_couples_kettle)
        # Sparse LU (SuperLU): the block-tridiagonal system is ~95 % zeros, and a
        # dense BLAS solve of a few hundred unknowns is slow under thread contention.
        with warnings.catch_warnings():
            warnings.simplefilter("error", MatrixRankWarning)
            try:
                dx = np.asarray(spsolve(csc_matrix(jac), -f0), dtype=np.float64)
            except (MatrixRankWarning, RuntimeError) as exc:
                raise RateBasedConvergenceError("singular rate-based Newton system") from exc
        if not np.all(np.isfinite(dx)):
            raise RateBasedConvergenceError("non-finite rate-based Newton step")
        alpha = 1.0
        dt = float(np.max(np.abs(dx[temp]))) if np.any(temp) else 0.0
        if dt > _DT_MAX:
            alpha = _DT_MAX / dt
        accepted = False
        for _ in range(12):
            xn = X + alpha * dx
            # positive variables may shrink at most 100x per step (component-wise damping)
            xn[pos] = np.maximum(xn[pos], 1e-2 * X[pos])
            fn = f(xn)
            nn = float(np.linalg.norm(fn))
            if np.isfinite(nn) and nn < norm0 * (1.0 - 1e-4 * alpha):
                accepted = True
                break
            alpha *= 0.5
        if not accepted:
            if not np.isfinite(nn):
                raise RateBasedConvergenceError("rate-based Newton left the physical domain")
            # No descent along the Newton direction: the frozen-model system sits at its
            # round-off floor (or needs re-anchored models); hand back to the outer loop.
            return X, its, float(np.max(np.abs(f0)))
        X, f0, norm0 = xn, fn, nn
    final = float(np.max(np.abs(f0)))
    return X, its, final


# --------------------------------------------------------------------------------------
# Initial profile
# --------------------------------------------------------------------------------------


def _interface_seed(
    thermo: Thermo, spec: RateColumnSpec, v: Vec, liq: Vec, T: float, P: float
) -> tuple[Vec, Vec]:
    """Interface seed: the phase compositions of a PT flash of the stage's combined
    material; when that is single-phase, the bulk liquid and ``K x`` normalised."""
    cids = spec.cids
    z = _norm(v + liq)
    state = thermo.flash_pt(_as_comp(cids, z), T, P, 1.0)
    vap_ph = next((p for p in state.phases if p.kind is PhaseKind.VAPOR), None)
    liq_ph = next((p for p in state.phases if p.kind is not PhaseKind.VAPOR), None)
    if vap_ph is not None and liq_ph is not None and 1e-9 < state.vapor_fraction < 1.0 - 1e-9:
        xi = np.array([liq_ph.composition.get(cid, 0.0) for cid in cids])
        yi = np.array([vap_ph.composition.get(cid, 0.0) for cid in cids])
        return _norm(np.maximum(xi, 1e-12)), _norm(np.maximum(yi, 1e-12))
    x = _norm(liq)
    lnk, _ = _k_model(thermo, cids, x, _norm(v), T, P)
    return x, _norm(np.exp(lnk) * x)


def _bubble_T(thermo: Thermo, cids: tuple[str, ...], z: Vec, P: float, fallback: float) -> float:
    try:
        return float(thermo.bubble_point(_as_comp(cids, z), P=P).T)
    except Exception:  # noqa: BLE001 - a super-critical mixture has no bubble point; seed only
        return fallback


def _distillation_seed(
    thermo: Thermo, spec: RateColumnSpec, feeds: _FeedTable, feed_T: list[float]
) -> tuple[list[Vec], list[Vec], list[float]]:
    """Seed of a condenser + kettle column: product rates from the two specs (D from a
    rate spec, from ``V = (R+1) D = VB (F - D)`` when reflux and boilup ratios are
    given, else F/2), a sharp split by volatility at the feed, compositions and bubble
    temperatures interpolated linearly between the products, constant molar overflow
    traffic ``V`` with ``L = V - D`` above the first feed stage and ``V + B`` below."""
    c = len(spec.cids)
    n = len(spec.pressures)
    z_tot = sum((feeds.fv[k] + feeds.fl[k] for k in range(n)), np.zeros(c))
    f_tot = float(np.sum(z_tot))
    top = spec.condenser_spec if spec.condenser_spec is not None else ("", 0.0)
    bot = spec.kettle_spec if spec.kettle_spec is not None else ("", 0.0)
    d0: float | None = None
    if top[0] == "distillate_rate" or bot[0] == "distillate_rate":
        d0 = top[1] if top[0] == "distillate_rate" else bot[1]
    elif bot[0] == "bottoms_rate":
        d0 = f_tot - bot[1]
    r = top[1] if top[0] == "reflux_ratio" else None
    vb = bot[1] if bot[0] == "boilup_ratio" else None
    if d0 is None and r is not None and vb is not None:
        d0 = vb * f_tot / (r + 1.0 + vb)
    d0 = min(max(d0 if d0 is not None else 0.5 * f_tot, 0.02 * f_tot), 0.98 * f_tot)
    b0 = f_tot - d0
    if r is not None:
        v0 = (r + 1.0) * d0
    elif vb is not None:
        v0 = vb * b0
    else:
        v0 = 2.0 * d0
    v0 = max(v0, 1.2 * d0)
    t_feed = float(np.mean(feed_T))
    p_mid = 0.5 * (spec.pressures[0] + spec.pressures[-1])
    z = z_tot / f_tot
    try:
        lnk, _ = _k_model(thermo, spec.cids, z, z, t_feed, p_mid)
        order = list(np.argsort(-lnk))
    except RateBasedConvergenceError:
        order = list(range(c))
    d = np.zeros(c)
    room = d0
    for i in order:
        take = min(float(z_tot[i]), room)
        d[i] = take
        room -= take
    xd = _norm(d + 1e-3 * z_tot)
    xb = _norm(np.maximum(z_tot - d, 0.0) + 1e-3 * z_tot)
    t_top = _bubble_T(thermo, spec.cids, xd, spec.pressures[0], t_feed)
    t_bot = _bubble_T(thermo, spec.cids, xb, spec.pressures[-1], t_feed)
    j_feed = min(f.stage for f in spec.feeds)
    v_prof: list[Vec] = []
    l_prof: list[Vec] = []
    t_prof: list[float] = []
    for j in range(n):
        s = j / (n - 1)
        comp = _norm((1.0 - s) * xd + s * xb)
        if j == 0:
            v_prof.append(d0 * xd)
            l_prof.append((v0 - d0) * xd)
        elif j == n - 1:
            v_prof.append(v0 * xb)
            l_prof.append(b0 * xb)
        else:
            v_prof.append(v0 * comp)
            l_prof.append((v0 - d0 if j < j_feed else v0 + b0) * comp)
        t_prof.append((1.0 - s) * t_top + s * t_bot)
    return v_prof, l_prof, t_prof


def _initial_state(
    thermo: Thermo, spec: RateColumnSpec, lay: _Layout, feeds: _FeedTable, feed_T: list[float]
) -> Vec:
    c = lay.c
    n = lay.n_stages
    fs = feeds.total
    tiny = 1e-8 * fs
    X = np.zeros(lay.size)
    v_prof: list[Vec] = []
    l_prof: list[Vec] = []
    t_prof: list[float] = []
    if spec.condenser is not None:
        v_prof, l_prof, tv_prof = _distillation_seed(thermo, spec, feeds, feed_T)
        tl_prof = tv_prof
    elif not spec.kettle:
        t_v = float(np.mean(feed_T))
        vfeed_t = [t for f, t in zip(spec.feeds, feed_T, strict=True) if sum(f.vap) > 0]
        lfeed_t = [t for f, t in zip(spec.feeds, feed_T, strict=True) if sum(f.liq) > 0]
        t_v = float(np.mean(vfeed_t)) if vfeed_t else t_v
        t_l = float(np.mean(lfeed_t)) if lfeed_t else t_v
        for j in range(n):
            v_prof.append(sum((feeds.fv[k] for k in range(j, n)), np.zeros(c)) + tiny)
            l_prof.append(sum((feeds.fl[k] for k in range(0, j + 1)), np.zeros(c)) + tiny)
        tv_prof = [t_v] * n
        tl_prof = [t_l] * n
    else:
        z_tot = sum((feeds.fv[k] + feeds.fl[k] for k in range(n)), np.zeros(c))
        f_tot = float(np.sum(z_tot))
        z = z_tot / f_tot
        p_bot = spec.pressures[-1]
        try:
            bub = thermo.bubble_point(_as_comp(spec.cids, z), P=p_bot)
            t_b = float(bub.T)
            y_inc = np.array([bub.incipient_composition.get(cid, 0.0) for cid in spec.cids])
        except Exception:  # noqa: BLE001 - a super-critical feed has no bubble point; use the feed T
            t_b = float(np.mean(feed_T))
            y_inc = z.copy()
        y_inc = _norm(np.maximum(y_inc, 0.0))
        name, value = spec.kettle_spec if spec.kettle_spec is not None else ("boilup_ratio", 1.0)
        if name == "boilup_ratio":
            v0 = f_tot * value / (1.0 + value)
        elif name == "bottoms_rate":
            v0 = f_tot - value
        elif name == "distillate_rate":
            v0 = value
        else:
            v0 = 0.3 * f_tot
        v0 = min(max(v0, 0.02 * f_tot), 0.98 * f_tot)
        b = np.maximum(z_tot - v0 * y_inc, 0.0) + tiny
        for j in range(n):
            v_prof.append(v0 * y_inc + tiny)
            l_prof.append(b + (v0 * y_inc if j < n - 1 else 0.0))
            t_prof.append(t_b)
        tv_prof = t_prof
        tl_prof = t_prof
    for j in range(n):
        o = lay.offsets[j]
        X[o : o + c] = v_prof[j]
        X[o + c : o + 2 * c] = l_prof[j]
        if lay.is_rate(j):
            t_i = 0.5 * (tv_prof[j] + tl_prof[j])
            xi, yi = _interface_seed(thermo, spec, v_prof[j], l_prof[j], t_i, spec.pressures[j])
            X[o + 2 * c : o + 3 * c] = yi
            X[o + 3 * c : o + 4 * c] = xi
            X[o + 4 * c : o + 5 * c] = 0.0
            X[o + 5 * c] = tv_prof[j]
            X[o + 5 * c + 1] = tl_prof[j]
            X[o + 5 * c + 2] = t_i
        else:
            X[o + 2 * c] = tv_prof[j]
    return X


# --------------------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------------------


def _models(
    thermo: Thermo, spec: RateColumnSpec, lay: _Layout, comps: list[ComponentTransport], X: Vec
) -> list[_RateModel | _KettleModel]:
    c = lay.c
    out: list[_RateModel | _KettleModel] = []
    for j in range(lay.n_stages):
        o = lay.offsets[j]
        v, liq = X[o : o + c], X[o + c : o + 2 * c]
        if lay.is_rate(j):
            out.append(
                _rate_model(
                    thermo,
                    spec,
                    comps,
                    v,
                    liq,
                    X[o + 2 * c : o + 3 * c],
                    X[o + 3 * c : o + 4 * c],
                    float(X[o + 5 * c]),
                    float(X[o + 5 * c + 1]),
                    float(X[o + 5 * c + 2]),
                    spec.pressures[j],
                )
            )
        else:
            out.append(_eq_model(thermo, spec.cids, lay.kinds[j], v, liq, float(X[o + 2 * c]), spec.pressures[j]))
    return out


def solve_rate_based(thermo: Thermo, spec: RateColumnSpec, feed_T: list[float]) -> RateProfile:
    """Solve the rate-based column (see module docstring). ``feed_T`` seeds temperatures."""
    c = len(spec.cids)
    if c < 2:
        raise ValueError("rate-based column needs at least two components")
    lay = _Layout.build(c, stage_kinds(spec))
    if len(spec.pressures) != lay.n_stages:
        raise ValueError(f"rate-based column needs {lay.n_stages} stage pressures, got {len(spec.pressures)}")
    if spec.kettle and spec.kettle_spec is None:
        raise ValueError("a kettle reboiler needs one kettle spec")
    if spec.condenser is not None and (
        spec.condenser not in CONDENSER_KINDS
        or spec.condenser_spec is None
        or spec.condenser_spec[0] not in CONDENSER_SPECS
        or not spec.kettle
    ):
        raise ValueError(
            f"a condenser ({list(CONDENSER_KINDS)}) needs a kettle and one top spec from {list(CONDENSER_SPECS)}"
        )
    if spec.murphree is not None and len(spec.murphree) != spec.n_rate:
        raise ValueError(f"Murphree trays need {spec.n_rate} efficiencies, got {len(spec.murphree)}")
    comps = [component_transport(cid) for cid in spec.cids] if "rate" in lay.kinds else []
    feeds = _feed_table(spec, lay.n_stages)
    X = _initial_state(thermo, spec, lay, feeds, feed_T)
    inner_total = 0
    max_res = math.inf
    couples = spec.kettle_spec is not None and spec.kettle_spec[0] == "distillate_rate"
    models = _models(thermo, spec, lay, comps, X)
    for outer in range(1, _MAX_OUTER + 1):
        frozen = models

        def fun(z: Vec, frozen: list[_RateModel | _KettleModel] = frozen) -> Vec:
            return _residual(spec, lay, feeds, frozen, z)

        X, its, _ = _newton(fun, X, lay, feeds.total, _INNER_TOL, couples)
        inner_total += its
        models = _models(thermo, spec, lay, comps, X)
        max_res = float(np.max(np.abs(_residual(spec, lay, feeds, models, X))))
        if max_res < _TOL:
            return _profile(spec, lay, feeds, models, X, outer, inner_total, max_res)
    raise RateBasedConvergenceError(
        f"rate-based column did not converge in {_MAX_OUTER} outer iterations "
        f"(scaled residual {max_res:.3e} > {_TOL:.0e})"
    )


def _profile(
    spec: RateColumnSpec,
    lay: _Layout,
    feeds: _FeedTable,
    models: list[_RateModel | _KettleModel],
    X: Vec,
    outer: int,
    inner: int,
    max_res: float,
) -> RateProfile:
    c = lay.c
    up = _unpack(lay, X)
    yi: list[Vec] = []
    xi: list[Vec] = []
    flux: list[Vec] = []
    ef: list[float] = []
    ti: list[float] = []
    diags: list[dict[str, float]] = []
    for j in range(lay.n_stages):
        o = lay.offsets[j]
        m = models[j]
        if isinstance(m, _RateModel):
            yi.append(X[o + 2 * c : o + 3 * c].copy())
            xi.append(X[o + 3 * c : o + 4 * c].copy())
            nf = X[o + 4 * c : o + 5 * c].copy()
            flux.append(nf)
            tv, t_i = float(X[o + 5 * c]), float(X[o + 5 * c + 2])
            ef.append(m.hav * (tv - t_i) + float(np.dot(nf, m.hv0 + m.cpv * (tv - m.tv0))))
            ti.append(t_i)
            diags.append(dict(m.diag))
        else:
            ti.append(up.t_v[j])
    h_v = [_hv(models[j], up.v[j], up.t_v[j]) for j in range(lay.n_stages)]
    h_l = [_hl(models[j], up.liq[j], up.t_l[j]) for j in range(lay.n_stages)]
    q_reb = 0.0
    if spec.kettle:
        k = lay.n_stages - 1
        q_reb = h_v[k] + h_l[k] - h_l[k - 1] - feeds.hfv[k] - feeds.hfl[k]
    q_cond = 0.0
    if spec.condenser is not None:  # heat removed; h_v[0] is the distillate (liquid if total)
        q_cond = h_v[1] + feeds.hfv[0] + feeds.hfl[0] - h_v[0] - h_l[0]
    return RateProfile(
        cids=spec.cids,
        v=[a.copy() for a in up.v],
        liq=[a.copy() for a in up.liq],
        tv=list(up.t_v),
        tl=list(up.t_l),
        ti=ti,
        yi=yi,
        xi=xi,
        flux=flux,
        energy_flux_W=ef,
        h_vap_W=h_v,
        h_liq_W=h_l,
        reboiler_duty_W=q_reb,
        outer_iterations=outer,
        inner_iterations=inner,
        max_residual=max_res,
        diagnostics=diags,
        condenser_duty_W=q_cond,
        kinds=lay.kinds,
    )


# --------------------------------------------------------------------------------------
# Feeds and post-processing helpers for the adapters
# --------------------------------------------------------------------------------------


def split_feed(stage: int, cids: tuple[str, ...], state: StreamState) -> StageFeed:
    """Split a flashed feed by phase: vapour to the vapour side, liquids to the liquid side.

    Enthalpy flows are the phases' own (``Phase.enthalpy``), so they sum to the
    stream's ``molar_flow * enthalpy``.
    """
    c = len(cids)
    vap = np.zeros(c)
    liq = np.zeros(c)
    hv = 0.0
    hl = 0.0
    if not state.phases:
        raise ValueError("rate-based column needs flashed feeds (StreamState.phases is empty)")
    for ph in state.phases:
        moles = state.molar_flow * ph.mole_fraction
        comp = np.array([ph.composition.get(cid, 0.0) for cid in cids])
        if ph.kind is PhaseKind.VAPOR:
            vap += moles * comp
            hv += moles * ph.enthalpy
        else:
            liq += moles * comp
            hl += moles * ph.enthalpy
    return StageFeed(stage=stage, vap=tuple(vap), liq=tuple(liq), h_vap_W=hv, h_liq_W=hl)


def murphree_vapour(thermo: Thermo, prof: RateProfile, spec: RateColumnSpec) -> list[dict[str, float]]:
    """Component Murphree vapour efficiencies per middle stage (packed segment or tray),
    top to bottom, the condenser and kettle excluded.

    ``E_MV,ij = (y_ij - y_i,in) / (y*_ij - y_i,in)`` (Murphree 1925): ``y_in`` the
    vapour entering the segment (from the stage below plus any vapour feed to the
    segment), ``y*`` the vapour in equilibrium with the liquid leaving the segment -
    the incipient vapour of ``thermo.bubble_point(x_j, P_j)``. Components whose
    driving force ``|y* - y_in|`` is below 1e-9 are omitted (the ratio is undefined),
    as are segments with no entering vapour. In a multicomponent mixture a component
    efficiency need not lie in [0, 1] (Toor 1957); the tests check the case examples.
    """
    cids = prof.cids
    c = len(cids)
    feeds = _feed_table(spec, len(prof.v))
    out: list[dict[str, float]] = []
    top = 1 if spec.condenser is not None else 0
    for j in range(top, top + spec.n_rate):
        v_in = (prof.v[j + 1] if j + 1 < len(prof.v) else np.zeros(c)) + feeds.fv[j]
        if float(np.sum(v_in)) <= 0.0:
            out.append({})
            continue
        y_in = _norm(v_in)
        x = _norm(np.maximum(prof.liq[j], 0.0))
        y = _norm(np.maximum(prof.v[j], 0.0))
        bub = thermo.bubble_point(_as_comp(cids, x), P=spec.pressures[j])
        ys = np.array([bub.incipient_composition.get(cid, 0.0) for cid in cids])
        eff: dict[str, float] = {}
        for i, cid in enumerate(cids):
            den = float(ys[i] - y_in[i])
            if abs(den) > 1e-9:
                eff[cid] = float((y[i] - y_in[i]) / den)
        out.append(eff)
    return out
