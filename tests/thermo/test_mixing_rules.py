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
    MHV1,
    MHV2,
    PRMIX_HV,
    PRMIX_MHV1,
    PRMIX_MHV2,
    SRKMIX_MHV2,
    GEProvider,
    HuronVidal,
    LinearVDW,
    RuleState,
    _nrtl_provider,
    pure_alpha_from,
)

R_GAS = 8.31446261815324
_T, _P = 350.0, 101325.0


def _meoh_h2o_rule() -> tuple[ChemicalConstantsPackage, HuronVidal]:
    """Huron-Vidal rule over the ChemSep NRTL databank, MeOH/H2O support."""
    consts, _ = ChemicalConstantsPackage.from_IDs(["methanol", "water"])
    provider = _nrtl_provider([c for c in consts.CASs], ("methanol", "water"))
    return consts, HuronVidal(provider)


def _helmholtz_lnphi(
    rule: HuronVidal | MHV1 | MHV2, eos: Any, xs: Sequence[float], root_z: float, kind: str = "pr"
) -> list[float]:
    """Finite-difference ln phi via n*A_res/(R T) mole-number derivatives.

    Cubic form written directly from the residual Helmholtz departure,
    A_res/(R T) = -ln((v - b)/v) - a(x)/(R T s) ln((2v + delta - s)/(2v + delta + s)),
    with (u, w) = (2, -1) for PR (delta = 2b, s = 2 sqrt(2) b) and the SRK
    limit (u, w) = (1, 0) collapsing the log to (a/(b R T)) ln((v+b)/v) --
    independent of the analytic fugacity path (which goes through the rule's
    projected derivatives).
    """
    # Total volume for the 1-mol reference state:
    V_tot = root_z * R_GAS * _T / _P

    def F(nn: Sequence[float]) -> float:
        ntot = sum(nn)
        v = V_tot / ntot
        xxs = [x / ntot for x in nn]
        st = rule.state(_T, tuple(xxs), eos._pure_alpha(), tuple(eos.bs))
        b = sum(x * bi for x, bi in zip(xxs, eos.bs, strict=True))
        if kind == "pr":
            s = 2.0 * math.sqrt(2.0) * b
            delta = 2.0 * b  # eps = -b^2 only enters the cubic, not A_res
            log_term = math.log((2 * v + delta - s) / (2 * v + delta + s))
            return float(ntot * (-math.log((v - b) / v) + st.a / (R_GAS * _T * s) * log_term))
        log_term = math.log((v + b) / v)
        return float(ntot * (-math.log((v - b) / v) - st.a / (R_GAS * _T * b) * log_term))

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


class TestMHVTDerivatives:
    """Temperature derivatives of the rule state against central FD in T.

    The Helmholtz ln-phi test runs at fixed T and never exercises
    ``da_dT``/``d2a_dT2``/``a_xT``; these feed the enthalpy/Cp of the hosted
    phases, so they get their own finite-difference gate.
    """

    @pytest.mark.parametrize("xs", ((0.3, 0.7), (0.5, 0.5)))
    @pytest.mark.parametrize("rule_kind", ("mhv1", "mhv2"))
    def test_temperature_derivatives_match_fd(self, rule_kind: str, xs: tuple[float, ...]) -> None:
        consts, _ = ChemicalConstantsPackage.from_IDs(["methanol", "water"])
        provider = _nrtl_provider([c for c in consts.CASs], ("methanol", "water"))
        if rule_kind == "mhv1":
            rule: MHV1 | MHV2 = MHV1(provider, q1=-0.53)
        else:
            rule = MHV2(provider, q1=-0.4347, q2=-0.003654)

        def state_at(T: float) -> RuleState:
            eos = PRMIX_MHV1(
                Tcs=consts.Tcs,
                Pcs=consts.Pcs,
                omegas=consts.omegas,
                zs=list(xs),
                T=T,
                P=_P,
                rule=rule,
            )
            a_alphas, da_alphas, d2a_alphas = eos.a_alpha_and_derivatives_vectorized(T)
            pa = pure_alpha_from(eos.ais, a_alphas, da_alphas, d2a_alphas)
            return rule.state(T, xs, pa, tuple(eos.bs))

        h = 1e-2
        st = state_at(_T)
        st_up, st_dn = state_at(_T + h), state_at(_T - h)
        # d a/dT and d2 a/dT2
        assert st.da_dT == pytest.approx((st_up.a - st_dn.a) / (2.0 * h), rel=1e-6)
        assert st.d2a_dT2 == pytest.approx((st_up.da_dT - st_dn.da_dT) / (2.0 * h), rel=1e-4)
        # mixed derivative: d/dT of the projected composition partials
        for k in range(len(xs)):
            want = (st_up.a_x[k] - st_dn.a_x[k]) / (2.0 * h)
            got = st.a_xT[k]
            assert got == pytest.approx(want, rel=1e-4), (rule_kind, xs, k, got, want)


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
# MHV1 / MHV2 (T-06 step 3, branch t-06b/mhv): zero-pressure gE reference
# ----------------------------------------------------------------------------


class TestMHVConstants:
    """The q constants are literature values, cited per EOS."""

    def test_mhv1_cited_constants(self) -> None:
        # Michelsen, Fluid Phase Equilib. 60, 213-219, 1990 (table for the
        # zero-pressure reference); sign convention: negative q1 with
        # alpha = sum + (gE/RT + sum x ln(b/b_i))/q1.
        assert PRMIX_MHV1.q1 == -0.53

    def test_mhv2_cited_constants(self) -> None:
        # Dahl & Michelsen, AIChE J. 36, 1829-1836, 1990.
        assert (PRMIX_MHV2.q1, PRMIX_MHV2.q2) == (-0.4347, -0.003654)
        assert (SRKMIX_MHV2.q1, SRKMIX_MHV2.q2) == (-0.4783, -0.0047)


class TestMHVPureCollapse:
    """At gE = 0 the zero-pressure reference reduces to the pure EOS."""

    @pytest.mark.parametrize(
        "eos_cls,base_cls,rule",
        (
            (PRMIX_MHV1, PRMIX_HV, "mhv1"),
            (PRMIX_MHV2, PRMIX_HV, "mhv2"),
            (SRKMIX_MHV2, SRKMIX_MHV2, "mhv2"),
        ),
    )
    def test_pure_feed_collapses_to_base_cubic(self, eos_cls: Any, base_cls: Any, rule: str) -> None:
        from thermo import PRMIX, SRKMIX

        consts, _ = ChemicalConstantsPackage.from_IDs(["methanol", "water"])
        provider = _nrtl_provider([c for c in consts.CASs], ("methanol", "water"))
        zs = [1.0, 0.0]
        base_type = PRMIX if eos_cls is not SRKMIX_MHV2 else SRKMIX
        del base_cls
        base = base_type(Tcs=consts.Tcs, Pcs=consts.Pcs, omegas=consts.omegas, zs=zs, T=_T, P=_P)
        if rule == "mhv1":
            r: MHV1 | MHV2 = MHV1(provider, q1=eos_cls.q1)
        else:
            r = MHV2(provider, q1=eos_cls.q1, q2=eos_cls.q2)
        hosted = eos_cls(Tcs=consts.Tcs, Pcs=consts.Pcs, omegas=consts.omegas, zs=zs, T=_T, P=_P, rule=r)
        assert hosted.a_alpha == pytest.approx(base.a_alpha, rel=1e-12)
        assert hosted.Z_g == base.Z_g
        assert hosted.Z_l == base.Z_l
        assert hosted.lnphis_g[0] == pytest.approx(base.lnphis_g[0], rel=1e-10)
        assert hosted.lnphis_l[0] == pytest.approx(base.lnphis_l[0], rel=1e-10)

    def test_srkmix_mhv2_pure_collapses_to_srkmix(self) -> None:
        from thermo import SRKMIX

        consts, _ = ChemicalConstantsPackage.from_IDs(["methanol", "water"])
        provider = _nrtl_provider([c for c in consts.CASs], ("methanol", "water"))
        zs = [1.0, 0.0]
        base = SRKMIX(Tcs=consts.Tcs, Pcs=consts.Pcs, omegas=consts.omegas, zs=zs, T=_T, P=_P)
        hosted = SRKMIX_MHV2(
            Tcs=consts.Tcs,
            Pcs=consts.Pcs,
            omegas=consts.omegas,
            zs=zs,
            T=_T,
            P=_P,
            rule=MHV2(provider, q1=SRKMIX_MHV2.q1, q2=SRKMIX_MHV2.q2),
        )
        assert hosted.a_alpha == pytest.approx(base.a_alpha, rel=1e-12)
        assert hosted.Z_g == base.Z_g
        assert hosted.Z_l == base.Z_l
        assert hosted.lnphis_g[0] == pytest.approx(base.lnphis_g[0], rel=1e-10)
        assert hosted.lnphis_l[0] == pytest.approx(base.lnphis_l[0], rel=1e-10)


class TestMHVAnalyticLnphi:
    """FD-vs-analytic ln phi to 1e-6 per rule (T-06 step-3 acceptance)."""

    @pytest.mark.parametrize("zs", ([0.3, 0.7], [0.5, 0.5]))
    @pytest.mark.parametrize(
        "eos_cls,q,kind",
        (
            (PRMIX_MHV1, (-0.53,), "pr"),
            (PRMIX_MHV2, (-0.4347, -0.003654), "pr"),
            (SRKMIX_MHV2, (-0.4783, -0.0047), "srk"),
        ),
    )
    def test_mhv_lnphi_matches_helmholtz_fd_both_roots(
        self, eos_cls: Any, q: tuple[float, ...], kind: str, zs: Sequence[float]
    ) -> None:
        consts, _ = ChemicalConstantsPackage.from_IDs(["methanol", "water"])
        provider = _nrtl_provider([c for c in consts.CASs], ("methanol", "water"))
        if len(q) == 1:
            rule: MHV1 | MHV2 = MHV1(provider, q1=q[0])
        else:
            rule = MHV2(provider, q1=q[0], q2=q[1])
        eos = eos_cls(
            Tcs=consts.Tcs, Pcs=consts.Pcs, omegas=consts.omegas, zs=list(zs), T=_T, P=_P, rule=rule
        )
        for root_z, analytic in ((eos.Z_g, eos.lnphis_g), (eos.Z_l, eos.lnphis_l)):
            reference = _helmholtz_lnphi(rule, eos, zs, root_z, kind=kind)
            for got, want in zip(analytic, reference, strict=True):
                rel = abs(got - want) / max(abs(want), 1e-10)
                assert rel < 1e-6, (eos_cls.__name__, zs, analytic, reference)


class TestMHVRuleAlgebra:
    @pytest.mark.parametrize("rule_cls,q", ((MHV1, (-0.53,)), (MHV2, (-0.4347, -0.003654))))
    @pytest.mark.parametrize("xs", ((0.2, 0.3, 0.5), (0.9, 0.05, 0.05)))
    def test_ternary_mole_number_fd(
        self, rule_cls: type[GEProvider] | Any, q: tuple[float, ...], xs: tuple[float, ...]
    ) -> None:
        rule = (
            rule_cls(_ToyProvider(), q1=q[0]) if len(q) == 1 else rule_cls(_ToyProvider(), q1=q[0], q2=q[1])
        )
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
        assert sum(x * ax for x, ax in zip(xs, st.a_x, strict=True)) == pytest.approx(0.0, abs=1e-12)
        assert sum(x * axt for x, axt in zip(xs, st.a_xT, strict=True)) == pytest.approx(0.0, abs=1e-12)

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
