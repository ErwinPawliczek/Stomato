"""SR-POLAR (VTBMSR-III) density-only equation of state (Mangold et al. 2019).

The Schwartzentruber-Renon polar cubic with temperature-dependent volume
translation, as parameterised by Mangold, Pilz, Bjelic & Vogel, "Equation of
state and thermodynamic properties for mixtures of H2O, O2, N2, and CO2 from
ambient up to 1000 K and 280 MPa", J. Supercritical Fluids 153 (2019) 104476
(doi:10.1016/j.supflu.2019.02.016, open CC BY 4.0). Their "VTBMSR-III" model
is RKS + the SR polar alpha (eq. 22) + the c_i(T) volume translation (eqs
17-21) + the SR non-quadratic b-mixing with k_b_ij(T) (eqs 23-24, 26, 28).

**Density-only by design.** The published parameters were regressed in Aspen
Plus to density AND caloric data (enthalpy, Cp) — never to vapour pressure —
and water carries separate liquid and vapour/supercritical p-sets, so the
model cannot drive a VLE flash (docs/thermo-catalogue-plan.md records the
gap; the T3 pack notes document it). This package therefore claims exactly
one surface: the single-phase molar volume / density from the cubic in
u = v + c. Every VLE-style or caloric operation refuses with
:class:`SRPolarError` naming the gap; nothing returns a silently ideal or
zero-therefore-wrong number. The ``Thermo``-protocol ``StreamState``/``Phase``
caloric fields carry the contract defaults (0.0), which for this row mean
*not computed* — a flowsheet must not use this row for energy balances.

Equations as published (transcribed from the open paper and its SI):

- EOS (eq. 14): ``p = R T / (v + c - b) - a_c alpha / ((v + c)(v + c + b))``
  with the RKS constants ``Omega_a = 1 / (9 (2^(1/3) - 1))`` and
  ``Omega_b = (2^(1/3) - 1) / 3``, so ``a_c = Omega_a R^2 Tc^2 / Pc``
  (eq. 15 — a flattened fraction, *not* ``(1/9)(2^(1/3)-1) R^2 Tc^2 / Pc``)
  and ``b = Omega_b R Tc / Pc`` (eq. 16).
- alpha (eq. 22a-e): for ``Tr <= 1`` the polar Soave form
  ``alpha = [1 + m (1 - sqrt(Tr)) - p0 (1 - Tr)(1 + p1 Tr + p2 Tr^2)]^2``;
  for ``Tr > 1`` the Boston-Mathias-style extrapolation
  ``alpha = exp(2 cd (1 - Tr^d))`` with ``cd = 1 - 1/d`` and
  ``d = 1 + m/2 - p0 (1 + p1 + p2)``. The multiplicative ``d`` form is the
  reading that reproduces the paper's own Table 8 error column (the division
  reading ``p0 / (1 + p1 + p2)`` diverges to +68 % errors); ``m = 0.48508 +
  1.55191 omega - 0.15613 omega^2`` (eq. 22e).
- Volume translation (eqs. 17-21): ``Tr <= 1``: ``c = c0 + c1/(1 + c2 - Tr)``
  (``c0`` when the denominator vanishes); ``Tr > 1`` with ``c1 = 0``: ``c =
  c0`` (eq. 19); ``Tr > 1`` with ``c1 != 0`` (SI eq. S1.44):
  ``A = (c0 - b) c2 / c1 + 1``, ``c = b + A^2 c1 / (1 + c2 A - Tr)``
  (``c0`` when the denominator vanishes).
- Mixing (eqs. 23-24, 28): ``a_mix = (sum_i x_i sqrt(a_i))^2`` (the k_a
  correction is unused in the paper), ``b_mix = sum_i sum_j 0.5 x_i x_j
  (b_i + b_j)(1 - k_b,ij(T))`` with ``k_b,ij(T) = kb0 + kb1 T + kb2 / T``
  (eq. 26), and ``c_mix = sum_i x_i c_i`` (arithmetic mean).

The pure-component constants (Tc, Pc, omega) are the paper's Table 2 values
(Refprop 10 as cited there) — part of the published parameter set, stored in
``data/thermo_params/sr_polar/params.yaml`` with the databank-independent
provenance: the databank's own Tc/Pc differ in the last digits, and using
them would break reproduction of the published fit. Only the four published
components (H2O, O2, N2, CO2) are supported; anything else refuses with the
component named.

Validation: the paper's worked ternary example (Table 8, water-air,
experimental molar volumes from Japas & Franck [30]) is bound in
``tests/thermo/test_sr_polar.py`` against the open parameter pack
``data/validation/packs/T3/`` (board task T3): per-point agreement with the
paper's own VTBMSR-III error column within 1 percentage point, on all nine
published points.

SI units throughout: K, Pa, m3/mol, kg/m3.
"""

from __future__ import annotations

import math
from functools import cache
from pathlib import Path

import yaml

from ngdesign.contracts.stream import Phase, PhaseKind, StreamState
from ngdesign.contracts.thermo import PhaseProps, PropertyDerivatives, SaturationPoint
from ngdesign.thermo._state import R_IDEAL as R

__all__ = [
    "SRPolarError",
    "SRPolarPackage",
    "SRPolarPureParams",
    "SRPolarBinaryParams",
    "sr_polar_m",
    "sr_polar_alpha",
    "sr_polar_c_translation",
    "sr_polar_molar_volume",
]

#: The published parameter file, relative to the repo ``data/`` directory.
_PARAMS_REL = Path("thermo_params") / "sr_polar" / "params.yaml"

#: Omega_a = 1 / (9 (2^(1/3) - 1)) = 0.4274824... (Mangold eq. 15 constant).
_OMEGA_A = 1.0 / (9.0 * (2.0 ** (1.0 / 3.0) - 1.0))
#: Omega_b = (2^(1/3) - 1) / 3 = 0.0866407... (Mangold eq. 16 constant).
_OMEGA_B = (2.0 ** (1.0 / 3.0) - 1.0) / 3.0


class SRPolarError(ValueError):
    """An SR-POLAR call was outside the density-only surface, with the gap named."""


class SRPolarPureParams:
    """One component's published constants (frozen value object)."""

    __slots__ = ("cid", "tc_k", "pc_pa", "omega", "p0", "p1", "p2", "c0", "c1", "c2")

    def __init__(
        self,
        cid: str,
        tc_k: float,
        pc_pa: float,
        omega: float,
        p0: float,
        p1: float,
        p2: float,
        c0: float,
        c1: float,
        c2: float,
    ) -> None:
        self.cid = cid
        self.tc_k = tc_k
        self.pc_pa = pc_pa
        self.omega = omega
        self.p0 = p0
        self.p1 = p1
        self.p2 = p2
        self.c0 = c0
        self.c1 = c1
        self.c2 = c2

    @property
    def b(self) -> float:
        """Covolume b = Omega_b R Tc / Pc (eq. 16) [m3/mol]."""
        return _OMEGA_B * R * self.tc_k / self.pc_pa

    @property
    def a_c(self) -> float:
        """Attraction a_c = Omega_a R^2 Tc^2 / Pc (eq. 15) [Pa (m3/mol)^2]."""
        return _OMEGA_A * R * R * self.tc_k * self.tc_k / self.pc_pa


class SRPolarBinaryParams:
    """One binary pair's k_b(T) coefficients (eq. 26), order-independent key."""

    __slots__ = ("pair", "kb0", "kb1", "kb2")

    def __init__(self, pair: frozenset[str], kb0: float, kb1: float, kb2: float) -> None:
        self.pair = pair
        self.kb0 = kb0
        self.kb1 = kb1
        self.kb2 = kb2

    def kb(self, T: float) -> float:
        """k_b,ij(T) = kb0 + kb1 T + kb2 / T (eq. 26)."""
        return self.kb0 + self.kb1 * T + self.kb2 / T


@cache
def _load_params() -> tuple[dict[str, SRPolarPureParams], dict[frozenset[str], SRPolarBinaryParams]]:
    """The published parameter table (static data), loaded once."""
    from ngdesign.data import DATA_DIR

    path = DATA_DIR / _PARAMS_REL
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    pure: dict[str, SRPolarPureParams] = {}
    for cid, entry in (raw.get("pure") or {}).items():
        pure[cid] = SRPolarPureParams(
            cid=cid,
            tc_k=float(entry["tc_K"]),
            pc_pa=float(entry["pc_Pa"]),
            omega=float(entry["omega"]),
            p0=float(entry["p0"]),
            p1=float(entry["p1"]),
            p2=float(entry["p2"]),
            c0=float(entry["c0"]),
            c1=float(entry["c1"]),
            c2=float(entry["c2"]),
        )
    binary: dict[frozenset[str], SRPolarBinaryParams] = {}
    for key, entry in (raw.get("binary") or {}).items():
        a, _, b = key.partition("/")
        binary[frozenset((a, b))] = SRPolarBinaryParams(
            pair=frozenset((a, b)),
            kb0=float(entry["kb0"]),
            kb1=float(entry["kb1"]),
            kb2=float(entry["kb2"]),
        )
    return pure, binary


def sr_polar_m(omega: float) -> float:
    """m(omega) = 0.48508 + 1.55191 omega - 0.15613 omega^2 (Mangold eq. 22e)."""
    return 0.48508 + 1.55191 * omega - 0.15613 * omega * omega


def sr_polar_alpha(Tr: float, m: float, p0: float, p1: float, p2: float) -> float:
    """alpha(Tr) for one component: polar Soave below Tr = 1, extrapolation above.

    ``Tr <= 1``: ``alpha = [1 + m (1 - sqrt(Tr)) - p0 (1 - Tr)(1 + p1 Tr
    + p2 Tr^2)]^2`` (eq. 22a). ``Tr > 1``: ``alpha = exp(2 cd (1 - Tr^d))``
    with ``cd = 1 - 1/d`` (eq. 22c) and ``d = 1 + m/2 - p0 (1 + p1 + p2)``
    (eq. 22d, multiplicative form — the reading that reproduces the paper's
    Table 8; see the module docstring).
    """
    if Tr <= 1.0:
        bracket = 1.0 + m * (1.0 - math.sqrt(Tr)) - p0 * (1.0 - Tr) * (1.0 + p1 * Tr + p2 * Tr * Tr)
        return bracket * bracket
    d = 1.0 + 0.5 * m - p0 * (1.0 + p1 + p2)
    if d == 0.0:
        raise SRPolarError("alpha extrapolation: d = 0 (degenerate p-set); refusing to divide")
    cd = 1.0 - 1.0 / d
    return math.exp(2.0 * cd * (1.0 - Tr**d))


def sr_polar_c_translation(Tr: float, b: float, c0: float, c1: float, c2: float) -> float:
    """Volume translation c(T) for one component (Mangold eqs. 17-21) [m3/mol].

    ``Tr <= 1``: ``c0 + c1 / (1 + c2 - Tr)`` (eq. 17, ``c0`` when the
    denominator vanishes). ``Tr > 1``, ``c1 = 0``: ``c0`` (eq. 19).
    ``Tr > 1``, ``c1 != 0``: ``A = (c0 - b) c2 / c1 + 1`` and
    ``c = b + A^2 c1 / (1 + c2 A - Tr)`` (SI eq. S1.44, ``c0`` when the
    denominator vanishes).
    """
    if Tr <= 1.0:
        denom = 1.0 + c2 - Tr
        if denom == 0.0:
            return c0
        return c0 + c1 / denom
    if c1 == 0.0:
        return c0
    a_coef = (c0 - b) * c2 / c1 + 1.0
    denom = 1.0 + c2 * a_coef - Tr
    if denom == 0.0:
        return c0
    return b + a_coef * a_coef * c1 / denom


@cache
def _cubic_real_roots(a: float, b: float, c: float, d: float) -> tuple[float, ...]:
    """Real roots of a x^3 + b x^2 + c x + d = 0 (Cardano), ascending.

    Coefficients are normalised by ``a`` first; the depressed cubic
    ``t^3 + p t + q`` with ``x = t - b/(3a)`` is solved by the trigonometric
    method for the three-real-root case and by the cube-root formula otherwise.
    """
    bn = b / a
    cn = c / a
    dn = d / a
    shift = bn / 3.0
    p = cn - bn * bn / 3.0
    q = 2.0 * bn**3 / 27.0 - cn * bn / 3.0 + dn
    disc = (q / 2.0) ** 2 + (p / 3.0) ** 3
    if disc > 0.0:
        sq = math.sqrt(disc)
        s1 = -q / 2.0 + sq
        s2 = -q / 2.0 - sq
        root = math.copysign(abs(s1) ** (1.0 / 3.0), s1) + math.copysign(abs(s2) ** (1.0 / 3.0), s2)
        return (root - shift,)
    if disc < 0.0:
        r = math.sqrt(-(p**3) / 27.0)
        phi = math.acos(max(-1.0, min(1.0, -q / (2.0 * r))))
        m = 2.0 * math.sqrt(-p / 3.0)
        return tuple(sorted(m * math.cos((phi + 2.0 * math.pi * k) / 3.0) - shift for k in range(3)))
    if p == 0.0 and q == 0.0:
        return (-shift,)
    sq = math.copysign(abs(-q / 2.0) ** (1.0 / 3.0), -q / 2.0)
    return tuple(sorted((2.0 * sq - shift, -sq - shift)))


def sr_polar_molar_volume(z: dict[str, float], T: float, P: float) -> float:
    """Single-phase molar volume [m3/mol] of the published four-component slate.

    Solves the translated cubic in ``u = v + c`` (module docstring, eq. 14)
    for the smallest physical root (``u > b_mix``; liquid-like at subcritical
    states) and returns ``u - c_mix``. The composition must come from the
    published component table; anything else is refused with the id named.
    """
    if T <= 0.0 or P <= 0.0:
        raise SRPolarError(f"SR-POLAR needs T > 0 and P > 0, got T={T} K, P={P} Pa")
    pure, binary = _load_params()
    unknown = sorted(set(z) - set(pure))
    if unknown:
        raise SRPolarError(
            f"SR-POLAR has published parameters for H2O/O2/N2/CO2 only "
            f"(Mangold et al. 2019); no entry for {unknown}"
        )
    ids = sorted(z)
    # Mixture amix (eqs. 23, 28 with k_a unused), bmix (eqs. 24, 26), cmix (eq. 21 mix).
    a_mix = 0.0
    b_mix = 0.0
    c_mix = 0.0
    for i, ci in enumerate(ids):
        pi = pure[ci]
        ti = T / pi.tc_k
        ai = pi.a_c * sr_polar_alpha(ti, sr_polar_m(pi.omega), pi.p0, pi.p1, pi.p2)
        ci_trans = sr_polar_c_translation(ti, pi.b, pi.c0, pi.c1, pi.c2)
        c_mix += z[ci] * ci_trans
        # amix = (sum x_i sqrt(a_i))^2: diagonal x_i^2 a_i, cross 2 x_i x_j sqrt(a_i a_j).
        a_mix += z[ci] * z[ci] * ai
        b_mix += z[ci] * z[ci] * pi.b  # (1 - kb_ii) = 1
        for cj in ids[i + 1 :]:
            pj = pure[cj]
            tj = T / pj.tc_k
            aj = pj.a_c * sr_polar_alpha(tj, sr_polar_m(pj.omega), pj.p0, pj.p1, pj.p2)
            a_mix += 2.0 * z[ci] * z[cj] * math.sqrt(ai * aj)
            # The double sum counts each pair twice: the formula's 0.5 factor times
            # symmetry is one x_i x_j (b_i + b_j)(1 - kb) term per ordered pair.
            kbij = binary[frozenset((ci, cj))].kb(T)
            b_mix += z[ci] * z[cj] * (pi.b + pj.b) * (1.0 - kbij)
    # Cubic in u = v + c (expand p = RT/(u - b_mix) - a/(u (u + b_mix)) over the
    # common denominator u (u + b_mix) (u - b_mix)):
    #   P u^3 - R T u^2 + (a - P b_mix^2 - R T b_mix) u - a b_mix = 0
    roots_u = _cubic_real_roots(
        P,
        -R * T,
        a_mix - P * b_mix * b_mix - R * T * b_mix,
        -a_mix * b_mix,
    )
    physical = [u for u in roots_u if u > b_mix]
    if not physical:
        raise SRPolarError(
            f"SR-POLAR found no physical volume root (u > b_mix = {b_mix:.6g} m3/mol) at T={T} K, P={P} Pa"
        )
    u = min(physical)  # single-phase: the smallest physical root (liquid-like below Tr)
    return u - c_mix


def _molar_mass(z: dict[str, float]) -> float:
    """Mixture molar mass [g/mol] from the curated component records."""
    from ngdesign.data import component_record

    return sum(x * float(component_record(cid)["mw"]) for cid, x in z.items())


class SRPolarPackage:
    """SR-POLAR (VTBMSR-III) density-only property package (kind ``thermo``).

    Exposes exactly one surface on the ``Thermo`` protocol: the single-phase
    (T, P) flash — one dense phase at the smallest physical cubic root — and
    its :meth:`phase_props` density/Z. Saturation, two-phase and H/S-driven
    flashes, fugacity derivatives and K-values refuse with
    :class:`SRPolarError` (the parameters are density/caloric-regressed with
    separate water liquid and vapour p-sets; no vapour-pressure model exists
    to flash against — see the module docstring). ``pure_psat`` and
    ``k_values`` return ``None`` (not applicable). Caloric fields on the
    returned states carry the contract defaults (0.0) meaning *not computed*:
    this row must never be used for energy balances.
    """

    name = "sr-polar"

    def __init__(self, components: tuple[str, ...] | None = None) -> None:
        """Build the package; ``components`` resolves parameters eagerly."""
        super().__init__()
        if components:
            pure, _ = _load_params()
            unknown = sorted(set(components) - set(pure))
            if unknown:
                raise SRPolarError(
                    f"sr-polar has published parameters for H2O/O2/N2/CO2 only "
                    f"(Mangold et al. 2019); no entry for {unknown}"
                )

    # -- the density surface -------------------------------------------------

    def _phase(self, z: dict[str, float], T: float, P: float) -> Phase:
        """The single dense phase at (z, T, P), labelled by composition.

        Water-dominant states (the paper's applicability) label AQUEOUS —
        the T3 pack's binder note for the supercritical water-rich cases —
        everything else VAPOR. One root exists; the label is a naming
        convention, not a phase split.
        """
        v = sr_polar_molar_volume(z, T, P)
        mw = _molar_mass(z)
        density = mw / 1000.0 / v
        kind = PhaseKind.AQUEOUS if z.get("H2O", 0.0) == max(z.values()) else PhaseKind.VAPOR
        return Phase(
            kind=kind,
            mole_fraction=1.0,
            composition=dict(z),
            density=density,
            molecular_weight=mw,
            z_factor=P * v / (R * T),
        )

    # -- Thermo protocol -----------------------------------------------------

    def flash_pt(self, z: dict[str, float], T: float, P: float, molar_flow: float) -> StreamState:
        """Single-phase PT state: one phase at the smallest physical root."""
        ph = self._phase(z, T, P)
        return StreamState(
            T=T,
            P=P,
            molar_flow=molar_flow,
            composition=dict(z),
            vapor_fraction=1.0 if ph.kind is PhaseKind.VAPOR else 0.0,
            enthalpy=0.0,  # not computed: density-only row (docstring caveat)
            entropy=0.0,  # not computed: density-only row
            phases=[ph],
        )

    def flash_ph(self, z: dict[str, float], P: float, H: float, molar_flow: float) -> StreamState:
        raise SRPolarError(
            "sr-polar is density-only: the published parameters were regressed to "
            "density and caloric data, never to vapour pressure, so no enthalpy "
            "inversion exists - use a VLE-capable row for PH flashes"
        )

    def flash_ps(self, z: dict[str, float], P: float, S: float, molar_flow: float) -> StreamState:
        raise SRPolarError(
            "sr-polar is density-only: no entropy surface exists - use a VLE-capable row for PS flashes"
        )

    def flash_tvf(self, z: dict[str, float], T: float, vf: float, molar_flow: float) -> StreamState:
        raise SRPolarError(
            "sr-polar is density-only: water carries separate liquid and "
            "vapour/supercritical p-sets, so no two-phase split can be formed"
        )

    def flash_pvf(self, z: dict[str, float], P: float, vf: float, molar_flow: float) -> StreamState:
        raise SRPolarError(
            "sr-polar is density-only: water carries separate liquid and "
            "vapour/supercritical p-sets, so no two-phase split can be formed"
        )

    def bubble_point(
        self, z: dict[str, float], *, T: float | None = None, P: float | None = None
    ) -> SaturationPoint:
        raise SRPolarError(
            "sr-polar is density-only: no vapour-pressure model was regressed, "
            "so no saturation boundary exists"
        )

    def dew_point(
        self, z: dict[str, float], *, T: float | None = None, P: float | None = None
    ) -> SaturationPoint:
        raise SRPolarError(
            "sr-polar is density-only: no vapour-pressure model was regressed, "
            "so no saturation boundary exists"
        )

    def k_values(self, z: dict[str, float], T: float, P: float) -> dict[str, float] | None:
        return None

    def phase_props(self, composition: dict[str, float], T: float, P: float, kind: PhaseKind) -> PhaseProps:
        if kind not in (PhaseKind.VAPOR, PhaseKind.AQUEOUS):
            raise SRPolarError(
                f"sr-polar computes the single dense phase only (AQUEOUS for "
                f"water-dominant states, VAPOR otherwise); got {kind}"
            )
        ph = self._phase(composition, T, P)
        return PhaseProps(
            kind=kind,
            mole_fraction=1.0,
            composition=dict(composition),
            molecular_weight=ph.molecular_weight,
            density=ph.density,
            enthalpy=0.0,  # not computed: density-only row (docstring caveat)
            entropy=0.0,  # not computed: density-only row
            cp=0.0,  # not computed: density-only row
            gibbs=0.0,  # not computed: density-only row
            z_factor=ph.z_factor,
        )

    def derivatives(
        self, composition: dict[str, float], T: float, P: float, kind: PhaseKind
    ) -> PropertyDerivatives:
        raise SRPolarError(
            "sr-polar exposes no fugacity model (no vapour-pressure regression): "
            "ln phi derivatives are not part of the density-only surface"
        )

    def pure_psat(self, cid: str, T: float) -> float | None:
        return None
