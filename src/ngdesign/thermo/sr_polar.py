"""SR-POLAR (Schwartzentruber-Renon polar + volume translation) thermo package.

Registration of the VTBMSR-III formulation of Mangold, Pilz, Bjelic & Vogel,
"Equation of state and thermodynamic properties for mixtures of H2O, O2, N2, and
CO2 from ambient up to 1000 K and 280 MPa", J. Supercrit. Fluids 153 (2019)
104476 (doi:10.1016/j.supflu.2019.02.016): a Redlich-Kwong-Soave cubic EOS with

- the Schwartzentruber-Renon polar alpha function, printed in Mangold eq. (22a)
  and SI eq. (S1.38) (both sources agree on the (1-Tr) form);
- a temperature-dependent volume translation, Mangold eq. (17)
  ``c = c0 + c1 / (1 + c2 - Tr)`` for Tr <= 1, constant ``c = c0`` for Tr > 1
  (eq. 19 for the c1 = 0 case, eq. S1.44 for the general branch);
- the Schwartzentruber-Renon non-quadratic mixing rules (Mangold eqs. 25-26),
  with k_a_ij and l_ij unused by the paper ("k_a_ij(z) and l_ij(z) are not
  used"), so k_b_ij = kb0 + kb1*T + kb2/T carries all binaries.

Parameters live in ``data/thermo_models/sr_polar.yaml``, transcribed from
Mangold et al. 2019 Tables 2/5/7 and SI Tables S1.1-S1.6; every value cites its
table. Nothing here is fitted, tuned or interpolated.

Density-only scope: the paper regressed the parameters on DENSITY and CALORIC
data, never on vapour pressure, and prints no VLE validation. Until a VLE
assessment lands, the model is registered as a DENSITY-ONLY package: it
computes the cubic+translation molar volume and reports VLE-type properties as
``NotImplementedError`` rather than silently returning unvalidated numbers.

References:
- Mangold, F.; Pilz, St.; Bjelic, S.; Vogel, F. J. Supercrit. Fluids 153 (2019)
  104476. doi:10.1016/j.supflu.2019.02.016 (open CC BY 4.0).
- Schwartzentruber, J.; Renon, H. Ind. Eng. Chem. Res. 28 (1989) 1049.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

#: Gas constant [J/(mol K)] — CODATA, the value Mangold's RKS constants build on.
R = 8.31446261815324

# --- Mangold 2019 eq. 22e: m(omega) for the Soave alpha base term -------------

_M0 = 0.48508
_M1 = 1.55191
_M2 = -0.15613


def sr_alpha_m(omega: float) -> float:
    """Soave m parameter, Mangold 2019 eq. 22e.

    m = 0.48508 + 1.55191 omega - 0.15613 omega^2.
    """
    return _M0 + _M1 * omega + _M2 * omega * omega


def sr_alpha(omega: float, p0: float, p1: float, p2: float, tr: float) -> float:
    """Schwartzentruber-Renon polar alpha, Mangold 2019 eq. 22a / SI eq. S1.38.

    alpha = [1 + m (1 - sqrt(Tr)) - p0 (1 - Tr)(1 + p1 Tr + p2 Tr^2)]^2 for Tr <= 1;
    alpha = [exp(cd (1 - Tr^d))]^2 for Tr > 1, with d = 1 + 0.5 m - p0/(1 + p1 + p2)
    (eq. 22d) and cd = 1 - 1/d (eq. 22c).
    """
    if tr <= 0.0:
        raise ValueError(f"Tr must be positive, got {tr!r}")
    m = sr_alpha_m(omega)
    if tr <= 1.0:
        polar = p0 * (1.0 - tr) * (1.0 + p1 * tr + p2 * tr * tr)
        return (1.0 + m * (1.0 - math.sqrt(tr)) - polar) ** 2
    d = 1.0 + 0.5 * m - p0 / (1.0 + p1 + p2)
    cd = 1.0 - 1.0 / d
    return math.exp(2.0 * cd * (1.0 - tr**d))


def translated_volume_c(c0: float, c1: float, c2: float, tr: float) -> float:
    """Volume translation c(T), Mangold 2019 eq. 17 (Tr <= 1) and eq. 19 (Tr > 1).

    c = c0 + c1 / (1 + c2 - Tr) for Tr <= 1 — the SI's own derivative c' =
    c1/((1 + c2 - T/Tc)^2 Tc) (eq. S1.45) fixes the reciprocal reading of the
    main text's ambiguous "c0 + c1 1 + c2 - Tr". For Tr > 1, c = c0.
    """
    if tr <= 1.0:
        return c0 + c1 / (1.0 + c2 - tr)
    return c0


@dataclass(frozen=True)
class SRPolarComponent:
    """Pure-component SR-POLAR parameters, cited per Mangold 2019 table.

    ``omega`` is the acentric factor the paper's Table 2 prints; ``p0/p1/p2``
    are the Schwartzentruber-Renon polar parameters (Table 5 / SI S1.2) and
    ``c0/c1/c2`` the volume-translation constants (Table 5 / SI S1.1), all in
    SI units. ``source`` carries the table citation for traceability.
    """

    name: str
    tc: float  # critical temperature [K]
    pc: float  # critical pressure [Pa]
    omega: float  # acentric factor [-]
    c0: float  # volume translation, constant term [m3/mol]
    c1: float  # volume translation, Tr-dependent term [m3/mol]
    c2: float  # volume translation, Tr scale [-]
    p0: float  # polar alpha parameter [-]
    p1: float  # polar alpha parameter [-]
    p2: float  # polar alpha parameter [-]
    source: str  # table citation, e.g. "Mangold 2019 Table 5 / SI S1.1-S1.2"


@dataclass(frozen=True)
class SRPolarBinary:
    """One binary-interaction pair, Mangold 2019 eq. 26 / Table 7.

    k_b_ij = kb0 + kb1*T + kb2/T for the pair (i, j); symmetric.
    """

    i: str
    j: str
    kb0: float
    kb1: float
    kb2: float
    source: str


class SRPolarThermo:
    """SR-POLAR density-only package (Mangold 2019 VTBMSR-III).

    Computes the RKS + polar alpha + volume translation molar volume for a
    single phase at given T, P, composition. Every property except density /
    molar volume raises ``NotImplementedError``: the parameters were regressed
    on density and caloric data only, and the paper prints no VLE validation,
    so no other property is citable from this source yet.
    """

    def __init__(
        self,
        components: tuple[SRPolarComponent, ...],
        binaries: tuple[SRPolarBinary, ...] = (),
    ) -> None:
        self.components = tuple(components)
        self.binaries = tuple(binaries)
        self._kb = {(b.i, b.j): b for b in binaries}
        self._kb |= {(b.j, b.i): b for b in binaries}

    def k_b(self, i: str, j: str, temperature: float) -> float:
        """Binary interaction k_b_ij(T), Mangold 2019 eq. 26; 0 for unregressed pairs."""
        if i == j:
            return 0.0
        binary = self._kb.get((i, j))
        if binary is None:
            return 0.0
        return binary.kb0 + binary.kb1 * temperature + binary.kb2 / temperature

    def pure_a_b(self, component: SRPolarComponent, temperature: float) -> tuple[float, float]:
        """Pure-component RKS ``a_c alpha`` [Pa m6/mol2] and ``b`` [m3/mol].

        a_c = (1/9)(2^(1/3) - 1) R^2 Tc^2 / pc and b = (1/3)(2^(1/3) - 1) R Tc / pc
        (Mangold 2019 eqs. 15-16), a = a_c alpha with alpha from eq. 22a.
        """
        a_c = (2.0 ** (1.0 / 3.0) - 1.0) / 9.0 * R**2 * component.tc**2 / component.pc
        b = (2.0 ** (1.0 / 3.0) - 1.0) / 3.0 * R * component.tc / component.pc
        tr = temperature / component.tc
        alpha = sr_alpha(component.omega, component.p0, component.p1, component.p2, tr)
        return a_c * alpha, b

    def mixture_a_b(self, zs: dict[str, float], temperature: float) -> tuple[float, float]:
        """Mixture a and b with the Schwartzentruber-Renon mixing rules.

        a_mix = sum_i sum_j x_i x_j sqrt(a_i a_j) (1 - k_a_ij - (x_i - x_j) l_ij) and
        b_mix = sum_i sum_j x_i x_j (b_i + b_j)/2 (1 - k_b_ij) — Mangold 2019
        eqs. 25-26 with k_a_ij = l_ij = 0 (the paper states they are not used).
        """
        comps = list(self.components)
        n = len(comps)
        if len(zs) != n or not math.isclose(sum(zs.values()), 1.0, rel_tol=1e-9, abs_tol=1e-12):
            raise ValueError(f"zs must cover exactly the {n} components and sum to 1")
        ab = {c.name: self.pure_a_b(c, temperature) for c in comps}
        b = {c.name: ab[c.name][1] for c in comps}
        a = 0.0
        bmix = 0.0
        for i in range(n):
            ci = comps[i]
            xi = zs[ci.name]
            for j in range(n):
                cj = comps[j]
                xj = zs[cj.name]
                a_ij = math.sqrt(ab[ci.name][0] * ab[cj.name][0]) * (1.0 - self.k_b(ci.name, cj.name, temperature))
                a += xi * xj * a_ij
                bmix += xi * xj * 0.5 * (b[ci.name] + b[cj.name]) * (1.0 - self.k_b(ci.name, cj.name, temperature))
        return a, bmix

    def molar_volume(self, zs: dict[str, float], temperature: float, pressure: float) -> float:
        """Molar volume [m3/mol] of the single phase at (T, P), translated RKS.

        Solves the translated cubic p = RT/((v+c)-b) - a_c alpha/((v+c)(v+c+b))
        (Mangold 2019 eq. 14) for the real root, then reports v (not v+c): the
        translation moves the RKS volume by the constant c.
        """
        a, b = self.mixture_a_b(zs, temperature)
        c = self.translated_c(zs, temperature)
        return self._solve_volume(a, b, c, temperature, pressure)

    def translated_c(self, zs: dict[str, float], temperature: float) -> float:
        """Mixture volume translation c(T) [m3/mol], mole-fraction-weighted c0/c1/c2."""
        trs = {comp.name: temperature / comp.tc for comp in self.components}
        c0 = sum(zs[comp.name] * comp.c0 for comp in self.components)
        c1 = sum(zs[comp.name] * comp.c1 for comp in self.components)
        c2 = sum(zs[comp.name] * comp.c2 for comp in self.components)
        # The paper's Tr gate uses the WATER Tr of each worked case (all cases are
        # >Tc_water); per-component translation uses each component's own Tr.
        tr = sum(zs[comp.name] * trs[comp.name] for comp in self.components)
        return translated_volume_c(c0, c1, c2, tr)

    def density(self, zs: dict[str, float], temperature: float, pressure: float, mw: float) -> float:
        """Density [kg/m3] = MW / molar volume; ``mw`` in kg/mol (mixture)."""
        return mw / self.molar_volume(zs, temperature, pressure)

    # --- Properties outside the density-only scope: NotImplementedError -------

    def enthalpy(self, zs: dict[str, float], temperature: float, pressure: float) -> float:
        raise NotImplementedError(
            "SR-POLAR is density-only: Mangold 2019 regressed on density/caloric data "
            "but prints no enthalpy validation cases; not citable from this source yet"
        )

    def entropy(self, zs: dict[str, float], temperature: float, pressure: float) -> float:
        raise NotImplementedError("SR-POLAR is density-only (Mangold 2019, no VLE/caloric validation)")

    def cp(self, zs: dict[str, float], temperature: float, pressure: float) -> float:
        raise NotImplementedError("SR-POLAR is density-only (Mangold 2019, no VLE/caloric validation)")

    def flash(self, zs: dict[str, float], temperature: float, pressure: float) -> None:
        raise NotImplementedError("SR-POLAR is density-only: no vapour-pressure regression to flash against")

    def _solve_volume(self, a: float, b: float, c: float, temperature: float, pressure: float) -> float:
        """Physical real root of the translated RKS cubic, solved in u = v + c.

        p = RT/(u - b) - a/(u (u + b)) (Mangold 2019 eq. 14) cross-multiplied:
        p u^3 - RT u^2 - (p b^2 + RT b + a) u + a b = 0. All T3 cases are
        single-phase supercritical (one real-root region), so the largest real
        root above the co-volume is the phase volume.
        """
        rt = R * temperature
        roots = _cubic_real_roots(pressure, -rt, -(pressure * b * b + rt * b + a), -a * b)
        candidates = [r for r in roots if r > b]
        if not candidates:
            raise ValueError(f"no physical volume root at T={temperature} K, P={pressure} Pa")
        return max(candidates) - c


def _cbrt(x: float) -> float:
    """Real cube root, sign-preserving."""
    return math.copysign(abs(x) ** (1.0 / 3.0), x)


def _cubic_real_roots(a: float, b: float, c: float, d: float) -> list[float]:
    """Real roots of a x^3 + b x^2 + c x + d = 0 (Cardano, a != 0)."""
    # Depressed cubic t^3 + p t + q = 0 via x = t - b/(3a).
    p = (3.0 * a * c - b * b) / (3.0 * a * a)
    q = (2.0 * b**3 - 9.0 * a * b * c + 27.0 * a * a * d) / (27.0 * a**3)
    shift = -b / (3.0 * a)
    disc = (q / 2.0) ** 2 + (p / 3.0) ** 3
    if disc > 0.0:
        # One real root.
        sq = math.sqrt(disc)
        t = _cbrt(-q / 2.0 + sq) + _cbrt(-q / 2.0 - sq)
        return [t + shift]
    if disc < 0.0:
        # Three distinct real roots (trigonometric method).
        m = 2.0 * math.sqrt(-p / 3.0)
        arg = min(1.0, max(-1.0, -3.0 * q / (p * m)))
        theta = math.acos(arg) / 3.0
        return [m * math.cos(theta - 2.0 * k * math.pi / 3.0) + shift for k in range(3)]
    # disc == 0: repeated real roots.
    t1 = 2.0 * _cbrt(-q / 2.0)
    return [t1 + shift, -_cbrt(-q / 2.0) + shift]

