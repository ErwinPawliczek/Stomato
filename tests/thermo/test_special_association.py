"""Chemical-theory association vapour in the hoc_dimer / hf_hexamer flash surface.

Since 2026-11-04 the association kernels are the flashers' vapour phase
(``special.AssociatingGas``; Marek & Standart, Collect. Czech. Chem. Commun.
19, 1074 (1954); Prausnitz, Lichtenthaler & de Azevedo, Molecular
Thermodynamics of Fluid-Phase Equilibria, 3rd ed., sec. 5.8-5.9). Three kinds
of check:

* the closed-form state against an independent true-species reconstruction;
* thermodynamic consistency by finite differences (Gibbs-Helmholtz for H and
  V, Cp = dH/dT, ln phi derivatives, Gibbs-Duhem, phi_sat derivatives,
  Clapeyron at saturation) and the catalogue row's L0 suite;
* published data through the flash surface: the Mehling & Kleiber (2020)
  acetic-acid vapour compressibility, the CRC Handbook (95th ed.) latent
  heats of acetic acid (the table chemicals ships, ``Hvap_data_CRC``), the
  Jarry & Davis (1953) HF association factors, and the VDI Heat Atlas
  (2nd ed. 2010) HF latent heat (with the Perry 8E HF vapour pressure since
  2026-11-04, data/thermo_params/psat_methods.yaml).
"""

from __future__ import annotations

import importlib.util
import math
import sys
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from ngdesign.contracts.stream import PhaseKind
from ngdesign.thermo import catalogue
from ngdesign.thermo.special import (
    AssociatingGas,
    AssociationLaw,
    HaydenOConnellDimerPackage,
    HFHexamerPackage,
    association_state,
)

R = 8.31446261815324
REPO_ROOT = Path(__file__).resolve().parents[2]

# Ritter & Simons (1945) acetic-acid dimerization (association.yaml).
ACOH_LAW = AssociationLaw.dimer(-60574.0, 2.39647e-5, 399.35)


@cache
def _dimer_pkg() -> HaydenOConnellDimerPackage:
    return HaydenOConnellDimerPackage()


@cache
def _hexamer_pkg() -> HFHexamerPackage:
    return HFHexamerPackage()


def _gas(pkg: Any, ids: tuple[str, ...], zs: list[float], T: float, P: float) -> AssociatingGas:
    gas = pkg._build_flasher(ids).gas
    assert isinstance(gas, AssociatingGas)
    return gas.to(zs, T=T, P=P)


def _saturated(pkg: Any, cid: str, T: float, P: float | None = None) -> tuple[Any, Any]:
    """(liquid, vapour) PhaseProps of the pure component at (T, P or its Psat)."""
    p = pkg.pure_psat(cid, T) if P is None else P
    z = {cid: 1.0}
    return pkg.phase_props(z, T, p, PhaseKind.HC_LIQUID), pkg.phase_props(z, T, p, PhaseKind.VAPOR)


# --------------------------------------------------------------------------
# Closed-form state
# --------------------------------------------------------------------------


class TestAssociationState:
    @pytest.mark.parametrize("n", [2, 6])
    @pytest.mark.parametrize("y_a", [1.0, 0.3])
    @pytest.mark.parametrize("ln_kappa", [-4.0, 0.0, 3.0])
    def test_true_species_reconstruction(self, n: int, y_a: float, ln_kappa: float) -> None:
        """Rebuild the true-species mixture from (ln w, xi) and check every relation.

        Per apparent mole: xi n-mers, y_a - n xi monomers, 1 - y_a inert;
        n_true = 1 - (n-1) xi. Equilibrium z_n = kappa z_M^n (Kp P^(n-1) on
        true mole fractions), phi_a = z_M / y_a, phi_I = z_I / y_I = 1/Z.
        """
        st = association_state(y_a, ln_kappa, n)
        n_true = 1.0 - (n - 1) * st.xi
        z_m = (y_a - n * st.xi) / n_true
        z_n = st.xi / n_true
        assert z_n == pytest.approx(math.exp(ln_kappa) * z_m**n, rel=1e-12)
        assert math.exp(st.ln_w) == pytest.approx(z_m / y_a, rel=1e-12)
        assert 1.0 / st.e == pytest.approx(n_true, rel=1e-12)

    @pytest.mark.parametrize("n,y_a", [(2, 1.0), (2, 0.4), (6, 1.0), (6, 0.7)])
    def test_derivatives_match_finite_differences(self, n: int, y_a: float) -> None:
        u, h = 0.7, 1e-6
        st = association_state(y_a, u, n)
        hi, lo = association_state(y_a, u + h, n), association_state(y_a, u - h, n)
        assert st.dlnw == pytest.approx((hi.ln_w - lo.ln_w) / (2 * h), rel=1e-7)
        assert st.dlne == pytest.approx((math.log(hi.e) - math.log(lo.e)) / (2 * h), rel=1e-7)
        assert st.dxi == pytest.approx((hi.xi - lo.xi) / (2 * h), rel=1e-7)

    def test_limits_and_no_overflow(self) -> None:
        """y_a = 0 and kappa -> 0 are the ideal gas; kappa -> inf saturates at Z = 1/n."""
        for st in (association_state(0.0, 5.0, 2), association_state(1.0, -60.0, 6)):
            assert st.e == pytest.approx(1.0, abs=1e-12)
            assert st.xi == pytest.approx(0.0, abs=1e-12)
        # ln kappa this large overflows exp(): the log-space solve must not
        st = association_state(1.0, 4000.0, 6)
        assert 1.0 / st.e == pytest.approx(1.0 / 6.0, rel=1e-9)
        assert st.ln_w == pytest.approx(-4000.0 / 6.0, rel=1e-6)


# --------------------------------------------------------------------------
# Thermodynamic consistency of the vapour phase
# --------------------------------------------------------------------------


class TestAssociatingGasConsistency:
    CASES = [
        (("AcOH", "H2O"), [0.4, 0.6], 420.0, 1.0e5, "dimer"),
        (("AcOH",), [1.0], 400.0, 5.0e4, "dimer"),
        (("HF", "N2"), [0.7, 0.3], 300.0, 5.0e4, "hexamer"),
    ]

    @staticmethod
    def _pkg(kind: str) -> Any:
        return _dimer_pkg() if kind == "dimer" else _hexamer_pkg()

    @pytest.mark.parametrize("ids,zs,T,P,kind", CASES)
    def test_departures_follow_gibbs_helmholtz(
        self, ids: tuple[str, ...], zs: list[float], T: float, P: float, kind: str
    ) -> None:
        """H_dep = -R T^2 d(G_dep/RT)/dT and V_dep = R T d(G_dep/RT)/dP at fixed y."""
        pkg = self._pkg(kind)

        def g_rt(t: float, p: float) -> float:
            return float(_gas(pkg, ids, zs, t, p).G_dep()) / (R * t)

        gas = _gas(pkg, ids, zs, T, P)
        h_t, h_p = 1e-3, P * 1e-6
        h_dep = -R * T * T * (g_rt(T + h_t, P) - g_rt(T - h_t, P)) / (2 * h_t)
        v_dep = R * T * (g_rt(T, P + h_p) - g_rt(T, P - h_p)) / (2 * h_p)
        assert gas.H_dep() == pytest.approx(h_dep, rel=1e-6)
        assert gas.V() - R * T / P == pytest.approx(v_dep, rel=1e-6)

    @pytest.mark.parametrize("ids,zs,T,P,kind", CASES)
    def test_analytic_derivatives(
        self, ids: tuple[str, ...], zs: list[float], T: float, P: float, kind: str
    ) -> None:
        pkg = self._pkg(kind)
        gas = _gas(pkg, ids, zs, T, P)
        h_t, h_p = 1e-3, P * 1e-6
        up_t, dn_t = _gas(pkg, ids, zs, T + h_t, P), _gas(pkg, ids, zs, T - h_t, P)
        up_p, dn_p = _gas(pkg, ids, zs, T, P + h_p), _gas(pkg, ids, zs, T, P - h_p)
        assert gas.Cp() == pytest.approx((up_t.H() - dn_t.H()) / (2 * h_t), rel=1e-6)
        assert gas.dV_dT() == pytest.approx((up_t.V() - dn_t.V()) / (2 * h_t), rel=1e-6)
        assert gas.dV_dP() == pytest.approx((up_p.V() - dn_p.V()) / (2 * h_p), rel=1e-6)
        assert gas.dH_dP() == pytest.approx((up_p.H() - dn_p.H()) / (2 * h_p), rel=1e-5)
        assert gas.dS_dP() == pytest.approx((up_p.S() - dn_p.S()) / (2 * h_p), rel=1e-5)
        for i in range(len(ids)):
            fd_t = (up_t.lnphis()[i] - dn_t.lnphis()[i]) / (2 * h_t)
            fd_p = (up_p.lnphis()[i] - dn_p.lnphis()[i]) / (2 * h_p)
            assert gas.dlnphis_dT()[i] == pytest.approx(fd_t, rel=1e-6)
            assert gas.dlnphis_dP()[i] == pytest.approx(fd_p, rel=1e-6)

    @pytest.mark.parametrize("ids,zs,T,P,kind", CASES[::2])
    def test_gibbs_duhem(self, ids: tuple[str, ...], zs: list[float], T: float, P: float, kind: str) -> None:
        """sum_i y_i d ln phi_i / d n_j = 0 at fixed T, P."""
        dlnphis = _gas(self._pkg(kind), ids, zs, T, P).dlnphis_dns()
        for j in range(len(ids)):
            assert abs(sum(zs[i] * dlnphis[i][j] for i in range(len(ids)))) < 1e-8

    def test_saturation_phi_derivatives(self) -> None:
        """phi_sat (the liquid's PhiSat input) and its T derivatives against differences."""
        for pkg, cid, T in ((_dimer_pkg(), "AcOH", 380.0), (_hexamer_pkg(), "HF", 300.0)):
            sat = pkg._build_flasher((cid,)).liquid.eos_pure_instances[0]
            h = 1e-3
            assert sat.dphi_sat_dT(T) == pytest.approx(
                (sat.phi_sat(T + h) - sat.phi_sat(T - h)) / (2 * h), rel=1e-6
            )
            assert sat.d2phi_sat_dT2(T) == pytest.approx(
                (sat.dphi_sat_dT(T + h) - sat.dphi_sat_dT(T - h)) / (2 * h), rel=1e-5
            )

    def test_ideal_closed_forms_are_refused_not_inherited(self) -> None:
        gas = _gas(_dimer_pkg(), ("AcOH",), [1.0], 400.0, 5.0e4)
        with pytest.raises(NotImplementedError, match="d2P_dT2"):
            gas.d2P_dT2()
        with pytest.raises(ValueError, match="volume specification"):
            gas.to([1.0], T=400.0, V=0.05)


# --------------------------------------------------------------------------
# hoc_dimer flash surface against published data
# --------------------------------------------------------------------------


@cache
def _harness() -> Any:
    spec = importlib.util.spec_from_file_location(
        "validate_properties_association", REPO_ROOT / "scripts" / "validate_properties.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TestHocDimerFlash:
    def test_vapour_is_associated_mehling_kleiber(self) -> None:
        """Vapour Z at 399.35 K / 1 bar (true pressure) through phase_props.

        Before 2026-11-04 the row's vapour was IdealGas (Z = 1). The Ritter &
        Simons constant predicts Z = 0.6537 (the kernel value pinned in
        test_special.py); Mehling & Kleiber (2020) measured 0.6299: +3.8 %,
        assessed (dimer-only vs their dimer+tetramer treatment).
        """
        vap = _dimer_pkg().phase_props({"AcOH": 1.0}, 399.35, 1.0e5, PhaseKind.VAPOR)
        assert vap.z_factor == pytest.approx(0.6537, rel=1e-3)
        assert vap.z_factor == pytest.approx(0.6299, rel=0.05)

    @pytest.mark.parametrize("T", [330.0, 380.0])
    def test_pure_acid_boils_at_psat(self, T: float) -> None:
        """PhiSat liquid: the pure acid's liquid and vapour fugacities meet at Psat."""
        pkg = _dimer_pkg()
        psat = pkg.pure_psat("AcOH", T)
        assert psat is not None
        liq, vap = _saturated(pkg, "AcOH", T)
        assert liq.gibbs == pytest.approx(vap.gibbs, rel=1e-12, abs=1e-6)
        state = pkg.flash_pt({"AcOH": 1.0}, T, psat * 1.001, 1.0)
        assert state.vapor_fraction == 0.0
        state = pkg.flash_pt({"AcOH": 1.0}, T, psat * 0.999, 1.0)
        assert state.vapor_fraction == 1.0

    @pytest.mark.parametrize("T", [298.15, 391.05])
    def test_clapeyron_with_associated_vapour(self, T: float) -> None:
        """Latent heat = Z_v R T^2 d ln Psat/dT exactly (Clapeyron, V_L neglected as the
        PhiSat route without Poynting does): the association enters only through Z_v."""
        pkg = _dimer_pkg()
        vp = pkg._build_flasher(("AcOH",)).correlations.VaporPressures[0]
        dlnp = float(vp.T_dependent_property_derivative(T)) / float(vp.T_dependent_property(T))
        liq, vap = _saturated(pkg, "AcOH", T)
        assert vap.enthalpy - liq.enthalpy == pytest.approx(vap.z_factor * R * T * T * dlnp, rel=1e-9)

    def test_latent_heat_vs_crc_handbook(self) -> None:
        """Acetic-acid latent heat vs the CRC Handbook (95th ed.) table.

        Haynes, Bruno & Lide, CRC Handbook of Chemistry and Physics, 95th ed.
        (2014), "Enthalpy of vaporization": 23.36 kJ/mol at 298.15 K and
        23.70 kJ/mol at the normal boiling point 391.05 K (as shipped in
        chemicals' Hvap_data_CRC). Measured misses -0.8 % and +3.5 %; an
        ideal-gas vapour (Z_v = 1) would give R T^2 d ln Psat/dT = 39.1 kJ/mol
        at the boiling point (+65 %).
        """
        from chemicals.phase_change import Hvap_data_CRC

        row = Hvap_data_CRC.loc["64-19-7"]
        assert float(row["Hvap298"]) == 23360.0 and float(row["HvapTb"]) == 23700.0
        pkg = _dimer_pkg()
        for T, ref in ((298.15, 23360.0), (391.05, 23700.0)):
            liq, vap = _saturated(pkg, "AcOH", T)
            assert vap.enthalpy - liq.enthalpy == pytest.approx(ref, rel=0.05)

    def test_inert_component_fugacity_coefficient(self) -> None:
        """A non-associating component's apparent phi is 1/Z > 1 (z_I / y_I)."""
        vap = _dimer_pkg().phase_props({"AcOH": 0.5, "H2O": 0.5}, 400.0, 5.0e4, PhaseKind.VAPOR)
        assert vap.z_factor is not None
        assert vap.ln_phi["H2O"] == pytest.approx(-math.log(vap.z_factor), rel=1e-12)
        assert vap.ln_phi["H2O"] > 0.0 > vap.ln_phi["AcOH"]

    def test_refusals(self) -> None:
        with pytest.raises(ValueError, match="HCl"):
            HaydenOConnellDimerPackage(components=("HCl",))

    def test_row_l0_suite_passes(self) -> None:
        vp = _harness()
        row = catalogue.load_catalogue()["hoc_dimer"]
        assert row.status == "provisional"
        results = vp.run_l0_row(row)
        assert {r.check for r in results} == set(vp.L0_CHECKS)
        failed = [(r.check, r.detail) for r in results if not r.passed]
        assert not failed, failed


# --------------------------------------------------------------------------
# hf_hexamer flash surface
# --------------------------------------------------------------------------


def _jarry_davis_psat_pa(t_c: float) -> float:
    """Jarry & Davis (1953) eq. 1 saturation pressure, mmHg basis converted to Pa."""
    return float(10.0 ** (8.38036 - 1952.55 / (335.52 + t_c))) * 101325.0 / 760.0


class TestHFHexamerFlash:
    @pytest.mark.parametrize("T,factor", [(298.16, 3.580), (303.16, 3.438)])
    def test_association_factor_through_flash(self, T: float, factor: float) -> None:
        """Saturated-vapour n_nominal/n_true = 1/Z vs Jarry & Davis Table I, via phase_props.

        Same 5 % band as the kernel tests in test_special.py; at their own
        Antoine pressure the flash gives 3.486 (-2.6 %) and 3.395 (-1.2 %).
        """
        p = _jarry_davis_psat_pa(T - 273.15)
        vap = _hexamer_pkg().phase_props({"HF": 1.0}, T, p, PhaseKind.VAPOR)
        assert vap.z_factor is not None
        assert 1.0 / vap.z_factor == pytest.approx(factor, rel=0.05)

    def test_latent_heat_vs_vdi_heat_atlas(self) -> None:
        """Latent heat vs the VDI Heat Atlas, 2nd ed. (2010), D3.1 HF saturation table.

        The table as shipped in chemicals (lookup_VDI_tabular_data). Since
        2026-11-04 HF runs on the Perry 8E vapour pressure
        (data/thermo_params/psat_methods.yaml); measured misses +7.1 % at the
        292.69 K boiling point, +2.7 % at 305 K, -0.9 % at 325 K, +1.3 % at
        345 K, +5.4 % at 365 K. With thermo's default "Fit 2023" correlation
        they were -14.4 / -7.6 / -1.0 / +3.8 / +6.0 %.
        """
        from chemicals.miscdata import lookup_VDI_tabular_data

        ts, hs = lookup_VDI_tabular_data("7664-39-3", "Hvap")
        table = dict(zip(ts, hs, strict=True))
        pkg = _hexamer_pkg()
        expected = {292.69: 0.071, 305.0: 0.027, 325.0: -0.009, 345.0: 0.013, 365.0: 0.054}
        for T, miss in expected.items():
            liq, vap = _saturated(pkg, "HF", T)
            assert (vap.enthalpy - liq.enthalpy) / table[T] - 1.0 == pytest.approx(miss, abs=0.005), T

    @pytest.mark.parametrize("T", [295.0, 300.0, 305.0, 310.0])
    def test_saturated_liquid_cp_is_physical(self, T: float) -> None:
        """Regression: the old databank Psat ("Fit 2023") had a nearly flat d ln Psat/dT at
        300-310 K, so the PhiSat liquid Cp collapsed to 0.1-1.7 J/(mol K). With the Perry 8E
        correlation it is 37-38 J/(mol K) - still below the VDI table's 61-62 (the gamma-phi
        vapour-route limitation with no residual liquid Cp, as on hoc_dimer), but positive
        and smooth.
        """
        liq, _ = _saturated(_hexamer_pkg(), "HF", T)
        assert 30.0 < liq.cp < 45.0

    def test_row_l0_suite_passes(self) -> None:
        """hf_hexamer is provisional since 2026-11-04: every L0 check runs and passes."""
        vp = _harness()
        row = catalogue.load_catalogue()["hf_hexamer"]
        assert row.status == "provisional"
        results = vp.run_l0_row(row)
        assert {r.check for r in results} == set(vp.L0_CHECKS)
        failed = [(r.check, r.detail) for r in results if not r.passed]
        assert not failed, failed

    def test_psat_override_touches_only_listed_cas(self) -> None:
        """The override file changes HF only; water keeps thermo's default ranking."""
        from thermo import VaporPressure

        from ngdesign.thermo import _state

        constants, correlations = _state._constants_package(_state._records(("H2O", "HF"), ()))
        by_cas = dict(zip(constants.CASs, correlations.VaporPressures, strict=True))
        assert by_cas["7664-39-3"].method == "DIPPR_PERRY_8E"
        assert by_cas["7732-18-5"].method == VaporPressure(CASRN="7732-18-5").method

    def test_hf_vapour_pressure_hits_the_normal_boiling_point(self) -> None:
        """Root fix: HF's Psat at its databank normal boiling point 292.69 K is 1 atm
        within 0.5 % (the default "Fit 2023" gave 109.34 kPa, +7.9 %), in pure_psat and in
        the flasher's PhiSat liquid alike."""
        pkg = _hexamer_pkg()
        assert pkg.pure_psat("HF", 292.69) == pytest.approx(101325.0, rel=0.005)
        flasher = pkg._build_flasher(("HF",))
        vp = flasher.liquid.VaporPressures[0]
        assert vp.method == "DIPPR_PERRY_8E"
        assert vp(292.69) == pytest.approx(101325.0, rel=0.005)
