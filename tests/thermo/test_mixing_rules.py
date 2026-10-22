"""T-06 tests: gE mixing rules hosted on thermo's GCEOSMIX (spec T-06).

Evidence ladder:
- vdw1 identity: LinearVDW through the hosting layer must reproduce thermo's
  own PRMIX bit-for-bit (same arithmetic helper, same rows, same solver).
- analytic ln phi_i: matches an independent Helmholtz finite-difference
  reference, ln phi_i = d(n A_res/RT)/dn_i |_{T,V} - ln Z, on both roots.
- rule algebra: projected composition derivatives satisfy the Euler identity
  and match mole-number finite differences, binary and ternary.
- pure feeds: the gE rule collapses exactly to the base cubic (gE = 0).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import pytest
from thermo import ChemicalConstantsPackage

from ngdesign.thermo.mixing_rules import (
    C_WS_PR,
    PRMIX_HV,
    PRMIX_WS,
    SRKMIX_WS,
    GEProvider,
    HuronVidal,
    LinearVDW,
    WongSandler,
    _nrtl_provider,
)

R_GAS = 8.31446261815324
_T, _P = 350.0, 101325.0


def _meoh_h2o_rule() -> tuple[ChemicalConstantsPackage, HuronVidal]:
    """Huron-Vidal rule over the ChemSep NRTL databank, MeOH/H2O support."""
    consts, _ = ChemicalConstantsPackage.from_IDs(["methanol", "water"])
    provider = _nrtl_provider([c for c in consts.CASs], ("methanol", "water"))
    return consts, HuronVidal(provider)


def _helmholtz_lnphi(rule: HuronVidal, eos: PRMIX_HV, xs: Sequence[float], root_z: float) -> list[float]:
    """Finite-difference ln phi via n*A_res/(R T) mole-number derivatives.

    PR form written directly from the residual Helmholtz departure,
    A_res/(R T) = -ln((v - b)/v) + a(x)/(R T s) ln((2v + delta - s)/(2v + delta + s)),
    delta = 2 b, eps = -b^2, s = 2 sqrt(2) b -- independent of the analytic
    fugacity path (which goes through the rule's projected derivatives).
    """
    # Total volume for the 1-mol reference state:
    V_tot = root_z * R_GAS * _T / _P

    def F(nn: Sequence[float]) -> float:
        ntot = sum(nn)
        v = V_tot / ntot
        xxs = [x / ntot for x in nn]
        st = rule.state(_T, tuple(xxs), eos._pure_alpha(), tuple(eos.bs))
        b = sum(x * bi for x, bi in zip(xxs, eos.bs, strict=True))
        s = 2.0 * math.sqrt(2.0) * b
        delta = 2.0 * b  # eps = -b^2 only enters the cubic, not A_res
        return float(
            ntot
            * (
                -math.log((v - b) / v)
                + st.a / (R_GAS * _T * s) * math.log((2 * v + delta - s) / (2 * v + delta + s))
            )
        )

    n0 = [x for x in xs]
    out = []
    # Richardson extrapolation from h and h/2 kills the O(h^2) truncation
    # term; h = 1e-5 keeps the roundoff floor well under 1e-9 relative.
    h = 1e-5
    for i in range(len(n0)):
        n_up, n_dn = list(n0), list(n0)
        n_up[i] += h
        n_dn[i] -= h
        f_h = (F(n_up) - F(n_dn)) / (2.0 * h) - math.log(root_z)
        n_up, n_dn = list(n0), list(n0)
        n_up[i] += h / 2.0
        n_dn[i] -= h / 2.0
        f_h2 = (F(n_up) - F(n_dn)) / h - math.log(root_z)
        out.append((4.0 * f_h2 - f_h) / 3.0)
    return out


class _ToyProvider(GEProvider):
    """g = sum_i sum_j x_i x_j B_ij / T-unity with asymmetric B_ij.

    Analytic derivatives make the ternary projection test exact; B_ij != B_ji
    exercises the general (non-symmetric-sum) provider contract.
    """

    B = (
        (0.0, 1.3, -0.7),
        (0.9, 0.0, 2.1),
        (-0.4, 1.7, 0.0),
    )

    def state(
        self, T: float, xs: Sequence[float]
    ) -> tuple[float, tuple[float, ...], float, float, tuple[float, ...]]:
        n = len(xs)
        g = sum(xs[i] * xs[j] * self.B[i][j] for i in range(n) for j in range(n))
        g_x = tuple(
            sum(xs[j] * self.B[i][j] for j in range(n)) + sum(xs[j] * self.B[j][i] for j in range(n))
            for i in range(n)
        )
        # T-dependence: g -> g * T0 / T gives the trivial smooth family; the
        # projection identities under test are in the composition algebra, so
        # a constant-in-T model suffices and keeps the FD references clean.
        g_xT = tuple(0.0 for _ in range(n))
        return g, g_x, 0.0, 0.0, g_xT


class TestVdw1Identity:
    def test_pr_bit_identical_to_prmix(self) -> None:
        from thermo import PRMIX

        consts, _ = ChemicalConstantsPackage.from_IDs(["methanol", "water"])
        zs = [0.3, 0.7]
        base = PRMIX(Tcs=consts.Tcs, Pcs=consts.Pcs, omegas=consts.omegas, zs=zs, T=_T, P=_P)
        hosted = PRMIX_HV(
            Tcs=consts.Tcs,
            Pcs=consts.Pcs,
            omegas=consts.omegas,
            zs=zs,
            T=_T,
            P=_P,
            rule=LinearVDW(),
        )
        assert hosted.a_alpha == base.a_alpha
        assert hosted.a_alpha_j_rows == base.a_alpha_j_rows
        assert hosted.da_alpha_dT == base.da_alpha_dT
        assert hosted.da_alpha_dT_j_rows == base.da_alpha_dT_j_rows
        assert hosted.Z_g == base.Z_g
        assert hosted.Z_l == base.Z_l
        assert hosted.lnphis_g == base.lnphis_g
        assert hosted.lnphis_l == base.lnphis_l

    def test_pure_feed_collapses_to_prmix(self) -> None:
        from thermo import PRMIX

        consts, _ = ChemicalConstantsPackage.from_IDs(["methanol", "water"])
        zs = [1.0, 0.0]
        base = PRMIX(Tcs=consts.Tcs, Pcs=consts.Pcs, omegas=consts.omegas, zs=zs, T=_T, P=_P)
        hosted = PRMIX_HV(
            Tcs=consts.Tcs,
            Pcs=consts.Pcs,
            omegas=consts.omegas,
            zs=zs,
            T=_T,
            P=_P,
            rule=HuronVidal(_nrtl_provider([c for c in consts.CASs], ("methanol", "water"))),
        )
        # gE = 0 on a pure feed: the mixture scalars and the PRESENT
        # component's ln phi collapse to the base cubic bit-for-bit. The
        # ABSENT component's ln phi does NOT collapse: its residual chemical
        # potential at infinite dilution is rule-dependent (HV carries the
        # gE model's infinite-dilution derivative; VDW1 does not).
        assert hosted.a_alpha == base.a_alpha
        assert hosted.Z_g == base.Z_g
        assert hosted.Z_l == base.Z_l
        assert hosted.lnphis_g[0] == base.lnphis_g[0]
        assert hosted.lnphis_l[0] == base.lnphis_l[0]
        assert hosted.lnphis_g[1] != base.lnphis_g[1]


class TestAnalyticLnphi:
    @pytest.mark.parametrize("zs", ([0.3, 0.7], [0.5, 0.5]))
    def test_hv_lnphi_matches_helmholtz_fd_both_roots(self, zs: Sequence[float]) -> None:
        consts, rule = _meoh_h2o_rule()
        eos = PRMIX_HV(
            Tcs=consts.Tcs,
            Pcs=consts.Pcs,
            omegas=consts.omegas,
            zs=zs,
            T=_T,
            P=_P,
            rule=rule,
        )
        for root_z, analytic in ((eos.Z_g, eos.lnphis_g), (eos.Z_l, eos.lnphis_l)):
            reference = _helmholtz_lnphi(rule, eos, zs, root_z)
            for got, want in zip(analytic, reference, strict=True):
                rel = abs(got - want) / max(abs(want), 1e-10)
                assert rel < 1e-8, (zs, analytic, reference)


class TestRuleAlgebra:
    def test_binary_euler_identity(self) -> None:
        consts, rule = _meoh_h2o_rule()
        eos = PRMIX_HV(
            Tcs=consts.Tcs,
            Pcs=consts.Pcs,
            omegas=consts.omegas,
            zs=[0.3, 0.7],
            T=_T,
            P=_P,
            rule=rule,
        )
        xs = (0.3, 0.7)
        st = rule.state(_T, xs, eos._pure_alpha(), tuple(eos.bs))
        assert sum(x * ax for x, ax in zip(xs, st.a_x, strict=True)) == pytest.approx(0.0, abs=1e-12)
        assert sum(x * axt for x, axt in zip(xs, st.a_xT, strict=True)) == pytest.approx(0.0, abs=1e-12)

    @pytest.mark.parametrize("xs", ((0.2, 0.3, 0.5), (0.9, 0.05, 0.05)))
    def test_ternary_mole_number_fd(self, xs: tuple[float, ...]) -> None:
        rule = HuronVidal(_ToyProvider())
        consts, _ = ChemicalConstantsPackage.from_IDs(["methanol", "water"])
        # Dummy third component: the rule layer is provider-agnostic; only
        # lengths matter here because we FD the rule itself.
        eos = PRMIX_HV(
            Tcs=[512.6, 647.1, 400.0],
            Pcs=[8.09e6, 2.206e7, 3.0e6],
            omegas=[0.563, 0.345, 0.1],
            zs=list(xs),
            T=_T,
            P=_P,
            rule=rule,
        )
        pa = eos._pure_alpha()
        st = rule.state(_T, xs, pa, tuple(eos.bs))

        h = 1e-6
        n0 = list(xs)
        for i in range(3):
            n_up, n_dn = list(n0), list(n0)
            n_up[i] += h
            n_dn[i] -= h

            def a_total(nn: Sequence[float]) -> float:
                ntot = sum(nn)
                st_t = rule.state(_T, tuple(x / ntot for x in nn), pa, tuple(eos.bs))
                return ntot * st_t.a

            expected = (a_total(n_up) - a_total(n_dn)) / (2.0 * h)
            assert st.a + st.a_x[i] == pytest.approx(expected, rel=1e-6)


class TestProviderContract:
    def test_thermo_provider_derivative_temperature_shape(self) -> None:
        """d(g)/dT of gE/(RT) matches a central difference in T."""
        consts, _ = ChemicalConstantsPackage.from_IDs(["methanol", "water"])
        provider = _nrtl_provider([c for c in consts.CASs], ("methanol", "water"))
        xs = (0.3, 0.7)
        g, g_x, g_t, g_tt, g_xt = provider.state(_T, xs)
        h = 1e-2
        g_up = provider.state(_T + h, xs)[0]
        g_dn = provider.state(_T - h, xs)[0]
        assert g_t == pytest.approx((g_up - g_dn) / (2.0 * h), rel=1e-6)

    def test_gE_vanishes_at_pure_endpoints(self) -> None:
        """NRTL gE must be zero (and smooth) at both pure-endpoint feeds."""
        consts, _ = ChemicalConstantsPackage.from_IDs(["methanol", "water"])
        provider = _nrtl_provider([c for c in consts.CASs], ("methanol", "water"))
        assert provider.state(_T, (1.0, 0.0))[0] == pytest.approx(0.0, abs=1e-12)
        assert provider.state(_T, (0.0, 1.0))[0] == pytest.approx(0.0, abs=1e-12)


# ----------------------------------------------------------------------------
# Wong-Sandler (1992) — T-06a step 2
# ----------------------------------------------------------------------------


class _ZeroGEProvider(GEProvider):
    """gE = 0: isolates the WS second-virial machinery (ideal-solution limit)."""

    def state(
        self, T: float, xs: Sequence[float]
    ) -> tuple[float, tuple[float, ...], float, float, tuple[float, ...]]:
        n = len(xs)
        return 0.0, tuple(0.0 for _ in range(n)), 0.0, 0.0, tuple(0.0 for _ in range(n))


class TestWongSandler:
    @staticmethod
    def _ws_rule(eos_cls: type) -> WongSandler:
        consts, _ = ChemicalConstantsPackage.from_IDs(["methanol", "water"])
        return WongSandler(_nrtl_provider([c for c in consts.CASs], ("methanol", "water")), eos_cls.ws_c)

    @staticmethod
    def _ws_eos(eos_cls: type, zs: Sequence[float], rule: WongSandler | None = None) -> Any:
        consts, _ = ChemicalConstantsPackage.from_IDs(["methanol", "water"])
        return eos_cls(
            Tcs=consts.Tcs,
            Pcs=consts.Pcs,
            omegas=consts.omegas,
            zs=list(zs),
            T=_T,
            P=_P,
            rule=rule if rule is not None else TestWongSandler._ws_rule(eos_cls),
        )

    @pytest.mark.parametrize("eos_cls,base_cls", ((PRMIX_WS, "PRMIX"), (SRKMIX_WS, "SRKMIX")))
    def test_pure_feed_collapses(self, eos_cls: type, base_cls: str) -> None:
        import thermo  # noqa: PLC0415

        base_ctor = getattr(thermo, base_cls)
        consts, _ = ChemicalConstantsPackage.from_IDs(["methanol", "water"])
        base = base_ctor(Tcs=consts.Tcs, Pcs=consts.Pcs, omegas=consts.omegas, zs=[1.0, 0.0], T=_T, P=_P)
        hosted = self._ws_eos(eos_cls, [1.0, 0.0])
        # Quotient arithmetic (b_m = Q/(1-D)) reorders the float ops, so the
        # collapse is to double precision, not bit-for-bit.
        assert hosted.a_alpha == pytest.approx(base.a_alpha, rel=1e-12)
        assert hosted.Z_g == base.Z_g
        assert hosted.Z_l == base.Z_l
        assert hosted.lnphis_g[0] == pytest.approx(base.lnphis_g[0], rel=1e-12)
        assert hosted.lnphis_l[0] == pytest.approx(base.lnphis_l[0], rel=1e-12)
        # The absent component's infinite-dilution ln phi is rule-dependent
        # (WS carries a non-linear covolume derivative; the base rule does not).
        assert hosted.lnphis_g[1] != base.lnphis_g[1]

    @pytest.mark.parametrize("zs", ([0.3, 0.7], [0.5, 0.5]))
    @pytest.mark.parametrize("eos_cls,delta_factor", ((PRMIX_WS, 2.0), (SRKMIX_WS, 1.0)))
    def test_ws_lnphi_matches_helmholtz_fd_both_roots(
        self, eos_cls: type, delta_factor: float, zs: Sequence[float]
    ) -> None:
        """Analytic WS fugacity vs independent Helmholtz finite difference.

        The reference writes the PR/SRK residual Helmholtz departure directly
        with the rule's b_m(x) and a_m(x) (non-linear covolume), then takes
        mole-number derivatives -- independent of the analytic path, whose
        dQ/dn and dD/dn chain through the projected db/dn and da/dn rows.
        """
        eos = self._ws_eos(eos_cls, zs)
        rule, pa = eos.rule, eos._pure_alpha()
        for root_z, analytic in ((eos.Z_g, eos.lnphis_g), (eos.Z_l, eos.lnphis_l)):
            V_tot = root_z * R_GAS * _T / _P

            def F(nn: Sequence[float], _v_tot: float = V_tot) -> float:
                ntot = sum(nn)
                v = _v_tot / ntot
                st = rule.state(_T, tuple(x / ntot for x in nn), pa, tuple(eos.bs))
                b = st.b
                s = 2.0 * math.sqrt(2.0) * b if delta_factor == 2.0 else b
                delta = delta_factor * b
                return float(
                    ntot
                    * (
                        -math.log((v - b) / v)
                        + st.a / (R_GAS * _T * s) * math.log((2 * v + delta - s) / (2 * v + delta + s))
                    )
                )

            h = 1e-5
            for i, got in enumerate(analytic):
                n_up, n_dn = list(zs), list(zs)
                n_up[i] += h
                n_dn[i] -= h
                f_h = (F(n_up) - F(n_dn)) / (2.0 * h) - math.log(root_z)
                n_up, n_dn = list(zs), list(zs)
                n_up[i] += h / 2.0
                n_dn[i] -= h / 2.0
                f_h2 = (F(n_up) - F(n_dn)) / h - math.log(root_z)
                want = (4.0 * f_h2 - f_h) / 3.0
                rel = abs(got - want) / max(abs(want), 1e-10)
                assert rel < 1e-6, (eos_cls.__name__, zs, i, got, want)

    @pytest.mark.parametrize("eos_cls", (PRMIX_WS, SRKMIX_WS))
    def test_rule_scalars_match_paper_formulas(self, eos_cls: type) -> None:
        """a_m and b_m match an independent scalar re-implementation of the
        Wong-Sandler equations (Q, D, b_m = Q/(1-D), a_m = R T b_m D)."""
        eos = self._ws_eos(eos_cls, [0.3, 0.7])
        pa = eos._pure_alpha()
        bs, st = eos.bs, eos._rule_state
        n = 2
        xs = (0.3, 0.7)
        q = 0.0
        for i in range(n):
            for j in range(n):
                gi = bs[i] - pa.a_alphas[i] / (R_GAS * _T)
                gj = bs[j] - pa.a_alphas[j] / (R_GAS * _T)
                q += xs[i] * xs[j] * (gi + gj) / 2.0
        d = (
            sum(xs[k] * pa.a_alphas[k] / (bs[k] * R_GAS * _T) for k in range(n))
            + eos.rule.provider.state(_T, xs)[0] / eos_cls.ws_c
        )
        assert st.b == pytest.approx(q / (1.0 - d), rel=1e-12)
        assert st.a == pytest.approx(R_GAS * _T * (q / (1.0 - d)) * d, rel=1e-12)

    def test_ideal_limit_second_virial_matches_quadratic_rule(self) -> None:
        """WS with A^E = 0 and the exact-k_ij fit reproduces the quadratic
        rule's mixture second virial (the Wong-Sandler 1992 vdW1f reduction
        is a second-virial statement: the separate a_m and b_m do NOT equal
        the quadratic rule's on general feeds, only their b - a/RT sum does).
        """
        consts, _ = ChemicalConstantsPackage.from_IDs(["methanol", "water"])
        rule = WongSandler(_ZeroGEProvider(), C_WS_PR)
        probe = PRMIX_WS(
            Tcs=consts.Tcs, Pcs=consts.Pcs, omegas=consts.omegas, zs=[0.4, 0.6], T=_T, P=_P, rule=rule
        )
        pa = probe._pure_alpha()
        rt = R_GAS * _T
        # Exact k_ij: per-pair (b - a/RT)_ij = (1 - k_ij)(g_i + g_j)/2 must
        # equal the quadratic rule's cross second virial
        # (b_i + b_j)/2 - sqrt(a_i a_j)(1 - k_ij)/RT  (Wong-Sandler 1992).
        k01 = 1.0 - (probe.bs[0] + probe.bs[1]) / (
            (probe.bs[0] - pa.a_alphas[0] / rt)
            + (probe.bs[1] - pa.a_alphas[1] / rt)
            + 2.0 * math.sqrt(pa.a_alphas[0] * pa.a_alphas[1]) / rt
        )
        rule = WongSandler(_ZeroGEProvider(), C_WS_PR, [[0.0, k01], [k01, 0.0]])
        eos = self._ws_eos(PRMIX_WS, [0.4, 0.6], rule)
        st = eos._rule_state
        ws_virial = st.b - st.a / rt
        xs = (0.4, 0.6)
        quad_virial = 0.0
        for i in range(2):
            for j in range(2):
                k = 0.0 if i == j else k01
                a_ij = math.sqrt(pa.a_alphas[i] * pa.a_alphas[j]) * (1.0 - k)
                quad_virial += xs[i] * xs[j] * ((eos.bs[i] + eos.bs[j]) / 2.0 - a_ij / rt)
        assert ws_virial == pytest.approx(quad_virial, rel=1e-9)
