"""Closed-form, wiring and refusal tests for the column_internals R1 unit.

Hand computation of the tray closed-form case (spec
``specs/backend/units/column_internals.md``; Seader-Henley-Roper 3rd ed. §6.6):

    G = 50 mol/s * 40 g/mol = 2.0 kg/s;  L = 60 mol/s * 80 g/mol = 4.8 kg/s
    F_LV = (L/G)*sqrt(rhoV/rhoL) = 2.4*sqrt(20/600) = 0.438178046
    C_SB = 0.0105 + 8.127e-4 * 609.6**0.755 * exp(-1.463 * F_LV**0.842)
         = 0.0600980456 m/s          (TS = 0.6096 m = 609.6 mm)
    F_ST = (0.015/0.020)**0.2 = 0.944087511
    C    = F_ST*F_F*F_HA*C_SB = 0.944087511*1*1*0.0600980456 = 0.0567378143 m/s
    U_f  = C*sqrt((rhoL-rhoV)/rhoV) = 0.0567378143*sqrt(580/20) = 0.305542481 m/s
    A_t  = pi*1.5**2/4 = 1.76714587 m2;  A_n = A_t*(1-0.12) = 1.55508836 m2
    U_n  = (G/rhoV)/A_n = 0.1/1.55508836 = 0.0643050275 m/s
    flood_fraction = U_n/U_f = 0.210461823
    A_a  = A_t*(1-2*0.12) = 1.34303086 m2;  A_h = 0.10*A_a = 0.134303086 m2
    u_o  = 0.1/0.134303086 = 0.744584529 m/s
    h_d  = (rhoV/rhoL)*u_o**2/(2*9.80665*0.73**2) = 0.00176811444 m
    q_L  = L/rhoL = 0.008 m3/s;  h_ow = (0.008/(1.84*1.1))**(2/3) = 0.0249988282 m
    h_l  = 0.6*(0.05 + 0.0249988282) = 0.0449992969 m
    dP   = 600*9.80665*(h_d + h_l) = 275.178981 Pa
    design at f = 0.80: D = sqrt(4*G/(f*U_f*pi*(1-Ad/At)*rhoV)) = 0.769365893 m

Tolerance note: the spec's expected table prints 9 significant figures, whose
rounding alone is up to ~5e-10 relative (e.g. A_t reads 1.33e-9 off the exact
``pi*1.5**2/4`` double). 1e-8 relative is the tightest tolerance the printed
values support; exact-arithmetic agreement is 1e-9 (verified before coding).

Packing hand computation (Stichlmair dry, spec's case): eps = 0.68, a =
260 m2/m3, C1/C2/C3 = 32/7/1, rhoG = 5 kg/m3, muG = 5e-5 Pa s, Vg = 1.0 m/s,
H = 1 m.  d_p = 6(1-eps)/a = 0.00738461538 m; Re = 738.461538;
f0 = 32/Re + 7/sqrt(Re) + 1 = 1.30092636;
dP_dry = 0.75*f0*(1-eps)/eps**4.65*rhoG*Vg**2/d_p*H = 1270.397511660357 Pa,
matching ``fluids.Stichlmair_dry`` to 1e-12.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.stream import Phase, PhaseKind, StreamState
from ngdesign.units.column_shortcut.column_internals_r1 import (
    ColumnInternalsError,
    ColumnInternalsR1,
)

_VF = 50.0 / 110.0

_TRAY_PARAMS: dict[str, Any] = {
    "internals": "sieve_tray",
    "surface_tension_N_m": 0.015,
    "tray_spacing_m": 0.6096,
    "diameter_m": 1.5,
    "downcomer_area_frac": 0.12,
    "hole_area_frac": 0.10,
    "weir_height_m": 0.05,
    "weir_length_m": 1.1,
    "orifice_coefficient": 0.73,
    "aeration_factor": 0.6,
}


def _tray_inlet() -> StreamState:
    """The spec's closed-form tray inlet, built literally (no thermo)."""
    return StreamState(
        T=350.0,
        P=1.0e6,
        molar_flow=110.0,
        composition={"C1": _VF, "nC4": 1.0 - _VF},
        vapor_fraction=_VF,
        enthalpy=0.0,
        entropy=0.0,
        phases=[
            Phase(
                kind=PhaseKind.VAPOR,
                mole_fraction=_VF,
                composition={"C1": 1.0},
                density=20.0,
                viscosity=1e-5,
                molecular_weight=40.0,
            ),
            Phase(
                kind=PhaseKind.HC_LIQUID,
                mole_fraction=1.0 - _VF,
                composition={"nC4": 1.0},
                density=600.0,
                viscosity=2e-4,
                molecular_weight=80.0,
            ),
        ],
    )


def _packing_inlet(diameter: float, g_kg_s: float, l_kg_s: float, mu_l: float | None = 2e-3) -> StreamState:
    """An inlet whose traffic gives the wanted mass flows through ``diameter``."""
    v_mol = g_kg_s * 1000.0 / 40.0
    l_mol = l_kg_s * 1000.0 / 80.0
    total = v_mol + l_mol
    vf = v_mol / total
    return StreamState(
        T=300.0,
        P=1.0e6,
        molar_flow=total,
        composition={"C1": vf, "nC4": 1.0 - vf},
        vapor_fraction=vf,
        enthalpy=0.0,
        entropy=0.0,
        phases=[
            Phase(
                kind=PhaseKind.VAPOR,
                mole_fraction=vf,
                composition={"C1": 1.0},
                density=5.0,
                viscosity=5e-5,
                molecular_weight=40.0,
            ),
            Phase(
                kind=PhaseKind.HC_LIQUID,
                mole_fraction=1.0 - vf,
                composition={"nC4": 1.0},
                density=800.0,
                viscosity=mu_l,
                molecular_weight=80.0,
            ),
        ],
    )


def _packing_params(diameter: float, **extra: Any) -> dict[str, Any]:
    params: dict[str, Any] = {
        "internals": "packing",
        "column_diameter_m": diameter,
        "packed_height_m": 1.0,
        "voidage": 0.68,
        "specific_area_m2_m3": 260.0,
        "stichlmair_C1": 32.0,
        "stichlmair_C2": 7.0,
        "stichlmair_C3": 1.0,
    }
    params.update(extra)
    return params


class TestTrayClosedForm:
    """The spec's closed-form tray table (rel 1e-8; see the module docstring)."""

    EXPECTED: dict[str, float] = {
        "F_LV": 0.438178046,
        "C_SB_m_s": 0.0600980456,
        "C_m_s": 0.0567378143,
        "U_flood_m_s": 0.305542481,
        "U_net_m_s": 0.0643050275,
        "flood_fraction": 0.210461823,
        "A_total_m2": 1.76714587,
        "A_net_m2": 1.55508836,
        "A_active_m2": 1.34303086,
        "A_hole_m2": 0.134303086,
        "u_hole_m_s": 0.744584529,
        "h_dry_m": 0.00176811444,
        "h_ow_m": 0.0249988282,
        "h_liquid_m": 0.0449992969,
        "dP_tray_Pa": 275.178981,
    }

    def test_closed_form(self, thermo: Thermo) -> None:
        res = ColumnInternalsR1().solve({"inlet": _tray_inlet()}, _TRAY_PARAMS, thermo=thermo)
        worst = 0.0
        for key, want in self.EXPECTED.items():
            got = res.info[key]
            rel = abs(got - want) / abs(want)
            worst = max(worst, rel)
            assert rel <= 1e-8, f"{key}: got {got!r}, want {want!r} (rel {rel:.2e})"
        assert res.info["diameter_m"] == 1.5
        assert res.info["flooded"] == 0.0
        assert worst <= 1e-8

    def test_design_mode(self, thermo: Thermo) -> None:
        params = {k: v for k, v in _TRAY_PARAMS.items() if k != "diameter_m"}
        params["design_flood_fraction"] = 0.80
        res = ColumnInternalsR1().solve({"inlet": _tray_inlet()}, params, thermo=thermo)
        assert abs(res.info["diameter_m"] - 0.769365893) / 0.769365893 <= 1e-8


class TestPacking:
    """Stichlmair dry closed form, then the wet/flood/Robbins wiring."""

    def test_dry_closed_form(self, thermo: Thermo) -> None:
        # G = 2 kg/s through rhoV = 5 gives Vg = 1.0 m/s at A_t = 0.4 m2.
        diameter = math.sqrt(4.0 * 0.4 / math.pi)
        inlet = _packing_inlet(diameter, g_kg_s=2.0, l_kg_s=4.0)
        res = ColumnInternalsR1().solve({"inlet": inlet}, _packing_params(diameter), thermo=thermo)
        assert res.info["Vg_m_s"] == pytest.approx(1.0, rel=1e-9)
        # Hand: d_p = 6(1-eps)/a, Re = rhoG*Vg*d_p/muG, f0 = C1/Re + C2/sqrt(Re) + C3,
        # dP = 0.75*f0*(1-eps)/eps^4.65*rhoG*Vg^2/d_p*H = 1270.397511660357 Pa.
        assert res.info["dP_dry_Pa"] == pytest.approx(1270.397511660357, rel=1e-9)

    def test_wet_flood_and_robbins_wiring(self, thermo: Thermo) -> None:
        # Below flood (Vg_flood = 0.2823 m/s at Vl = 0.0125 m/s): D = 1 m,
        # G = 0.2*rhoV*A_t and L = 0.0125*rhoL*A_t give Vg = 0.2, Vl = 0.0125.
        diameter = 1.0
        a_total = math.pi * diameter**2 / 4.0
        inlet = _packing_inlet(diameter, g_kg_s=0.2 * 5.0 * a_total, l_kg_s=0.0125 * 800.0 * a_total)
        params = _packing_params(diameter, Fpd_per_ft=24.0, hetp_m=0.6, n_stages=5)
        res = ColumnInternalsR1().solve({"inlet": inlet}, params, thermo=thermo)
        # The unit conversion is the thing under test: the info values must equal
        # the library calls made with the hand-derived superficial velocities.
        from fluids.packed_tower import Robbins, Stichlmair_flood, Stichlmair_wet

        assert res.info["Vg_m_s"] == pytest.approx(0.2, rel=1e-9)
        assert res.info["Vl_m_s"] == pytest.approx(0.0125, rel=1e-9)
        assert res.info["Vg_flood_m_s"] == pytest.approx(
            Stichlmair_flood(0.0125, 5.0, 800.0, 5e-5, 0.68, 260.0, 32.0, 7.0, 1.0, 1.0), rel=1e-12
        )
        assert res.info["dP_wet_Pa"] == pytest.approx(
            Stichlmair_wet(0.2, 0.0125, 5.0, 800.0, 5e-5, 0.68, 260.0, 32.0, 7.0, 1.0, 1.0),
            rel=1e-12,
        )
        assert res.info["flood_fraction"] == pytest.approx(
            res.info["Vg_m_s"] / res.info["Vg_flood_m_s"], rel=1e-12
        )
        assert res.info["dP_robbins_Pa"] == pytest.approx(
            Robbins(0.0125 * 800.0, 0.2 * 5.0, 800.0, 5.0, 2e-3, 1.0, 24.0), rel=1e-12
        )
        assert res.info["packed_height_from_hetp_m"] == pytest.approx(3.0, rel=1e-12)


class TestPackingFlooded:
    """The flooded flag, both sides (orchestrator ruling on PR #288).

    Hand check at Vg = 0.25 m/s, Vl = 0.0125 m/s (eps = 0.68, a = 260 m2/m3,
    C1/C2/C3 = 32/7/1, rhoG = 5 kg/m3, rhoL = 800 kg/m3, muG = 5e-5 Pa s,
    H = 1 m): ``fluids.Stichlmair_flood`` gives Vg_flood = 0.28232805949431117
    m/s, so flood_fraction = 0.25/0.282328 = 0.8855 < 1 (not flooded) and the
    irrigated correlation is defined: ``Stichlmair_wet(0.25, 0.0125, ...)`` =
    544.8235414348013 Pa (the orchestrator's quoted regression value 544.82).
    The spec's own state (Vg = 1.0 m/s at the same Vl) sits ~3.5x above the
    flood point: flooded, with ``dP_wet_Pa`` omitted.

    Encoding: the contract's ``info`` is ``dict[str, float]``, which coerces a
    bool, so the ruling's ``True``/``False`` is carried as 1.0/0.0.
    """

    def test_above_flood(self, thermo: Thermo) -> None:
        # The spec's dry closed-form state: Vg = 1.0 m/s, Vl = 0.0125 m/s.
        diameter = math.sqrt(4.0 * 0.4 / math.pi)
        inlet = _packing_inlet(diameter, g_kg_s=2.0, l_kg_s=4.0)
        res = ColumnInternalsR1().solve({"inlet": inlet}, _packing_params(diameter), thermo=thermo)
        assert res.info["flooded"] == 1.0
        assert res.info["flood_fraction"] > 1.0
        assert "dP_wet_Pa" not in res.info
        assert res.info["dP_dry_Pa"] == pytest.approx(1270.397511660357, rel=1e-9)

    def test_below_flood(self, thermo: Thermo) -> None:
        # Vg = 0.25 m/s, Vl = 0.0125 m/s at A_t = 0.4 m2.
        diameter = math.sqrt(4.0 * 0.4 / math.pi)
        inlet = _packing_inlet(diameter, g_kg_s=0.25 * 5.0 * 0.4, l_kg_s=0.0125 * 800.0 * 0.4)
        res = ColumnInternalsR1().solve({"inlet": inlet}, _packing_params(diameter), thermo=thermo)
        from fluids.packed_tower import Stichlmair_wet

        assert res.info["flooded"] == 0.0
        assert res.info["flood_fraction"] == pytest.approx(0.25 / 0.28232805949431117, rel=1e-9)
        # Regression value (the orchestrator's quoted measurement), and the
        # wiring check against the direct library call at rel 1e-12.
        assert res.info["dP_wet_Pa"] == pytest.approx(544.8235414348013, rel=1e-9)
        assert res.info["dP_wet_Pa"] == pytest.approx(
            Stichlmair_wet(0.25, 0.0125, 5.0, 800.0, 5e-5, 0.68, 260.0, 32.0, 7.0, 1.0, 1.0),
            rel=1e-12,
        )


class TestPassThrough:
    """The outlet is the inlet state itself; duty and power are exactly zero."""

    def test_passthrough(self, thermo: Thermo) -> None:
        inlet = _tray_inlet()
        res = ColumnInternalsR1().solve({"inlet": inlet}, _TRAY_PARAMS, thermo=thermo)
        assert res.duty_W == 0.0
        assert res.power_W == 0.0
        assert res.outlets["outlet"] == inlet
        assert res.outlets["outlet"].model_dump() == inlet.model_dump()

    def test_v0_closes(self, thermo: Thermo) -> None:
        # Pass-through: total moles and enthalpy flow are carried unchanged.
        inlet = _tray_inlet()
        res = ColumnInternalsR1().solve({"inlet": inlet}, _TRAY_PARAMS, thermo=thermo)
        out = res.outlets["outlet"]
        assert out.molar_flow == inlet.molar_flow
        assert out.enthalpy * out.molar_flow == inlet.enthalpy * inlet.molar_flow


class TestRefusals:
    """One test per row of the spec's refusal table."""

    def test_bad_internals(self, thermo: Thermo) -> None:
        params = {**_TRAY_PARAMS, "internals": "random"}
        with pytest.raises(ColumnInternalsError, match="internals"):
            ColumnInternalsR1().solve({"inlet": _tray_inlet()}, params, thermo=thermo)

    @staticmethod
    def _liquid_only() -> StreamState:
        inlet = _tray_inlet()
        return inlet.model_copy(update={"vapor_fraction": 0.0, "phases": [inlet.phases[1]]})

    @staticmethod
    def _vapor_only() -> StreamState:
        inlet = _tray_inlet()
        return inlet.model_copy(update={"vapor_fraction": 1.0, "phases": [inlet.phases[0]]})

    def test_no_vapor_phase(self, thermo: Thermo) -> None:
        with pytest.raises(ColumnInternalsError, match="two-phase"):
            ColumnInternalsR1().solve({"inlet": self._liquid_only()}, _TRAY_PARAMS, thermo=thermo)

    def test_no_liquid_phase(self, thermo: Thermo) -> None:
        with pytest.raises(ColumnInternalsError, match="two-phase"):
            ColumnInternalsR1().solve({"inlet": self._vapor_only()}, _TRAY_PARAMS, thermo=thermo)

    def test_packing_missing_vapor_viscosity(self, thermo: Thermo) -> None:
        inlet = _tray_inlet()
        vapor = inlet.phases[0].model_copy(update={"viscosity": None})
        two_phase = inlet.model_copy(update={"phases": [vapor, inlet.phases[1]]})
        with pytest.raises(ColumnInternalsError, match="viscosity"):
            ColumnInternalsR1().solve({"inlet": two_phase}, _packing_params(1.0), thermo=thermo)

    def test_packing_robbins_missing_liquid_viscosity(self, thermo: Thermo) -> None:
        # Stichlmair needs only muV; Robbins also needs muL. Build an inlet whose
        # Vg sits below flood at D = 1 m so the Stichlmair calls succeed first.
        diameter = 1.0
        a_total = math.pi * diameter**2 / 4.0
        inlet = _packing_inlet(
            diameter, g_kg_s=0.2 * 5.0 * a_total, l_kg_s=0.0125 * 800.0 * a_total, mu_l=None
        )
        with pytest.raises(ColumnInternalsError, match="viscosity"):
            ColumnInternalsR1().solve(
                {"inlet": inlet}, _packing_params(diameter, Fpd_per_ft=24.0), thermo=thermo,
            )

    def test_tray_neither_diameter_nor_fraction(self, thermo: Thermo) -> None:
        params = {k: v for k, v in _TRAY_PARAMS.items() if k != "diameter_m"}
        with pytest.raises(ColumnInternalsError, match="diameter_m"):
            ColumnInternalsR1().solve({"inlet": _tray_inlet()}, params, thermo=thermo)

    def test_tray_both_diameter_and_fraction(self, thermo: Thermo) -> None:
        params = {**_TRAY_PARAMS, "design_flood_fraction": 0.8}
        with pytest.raises(ColumnInternalsError, match="diameter_m"):
            ColumnInternalsR1().solve({"inlet": _tray_inlet()}, params, thermo=thermo)

    def test_hole_area_frac_low(self, thermo: Thermo) -> None:
        params = {**_TRAY_PARAMS, "hole_area_frac": 0.05}
        with pytest.raises(ColumnInternalsError, match="hole_area_frac"):
            ColumnInternalsR1().solve({"inlet": _tray_inlet()}, params, thermo=thermo)

    def test_downcomer_area_frac_out_of_range(self, thermo: Thermo) -> None:
        params = {**_TRAY_PARAMS, "downcomer_area_frac": 0.6}
        with pytest.raises(ColumnInternalsError, match="downcomer_area_frac"):
            ColumnInternalsR1().solve({"inlet": _tray_inlet()}, params, thermo=thermo)

    def test_negative_weir_height(self, thermo: Thermo) -> None:
        params = {**_TRAY_PARAMS, "weir_height_m": -0.05}
        with pytest.raises(ColumnInternalsError, match="weir_height_m"):
            ColumnInternalsR1().solve({"inlet": _tray_inlet()}, params, thermo=thermo)

    def test_nonpositive_surface_tension(self, thermo: Thermo) -> None:
        params = {**_TRAY_PARAMS, "surface_tension_N_m": 0.0}
        with pytest.raises(ColumnInternalsError, match="surface_tension_N_m"):
            ColumnInternalsR1().solve({"inlet": _tray_inlet()}, params, thermo=thermo)

    def test_aeration_factor_above_one(self, thermo: Thermo) -> None:
        params = {**_TRAY_PARAMS, "aeration_factor": 1.5}
        with pytest.raises(ColumnInternalsError, match="aeration_factor"):
            ColumnInternalsR1().solve({"inlet": _tray_inlet()}, params, thermo=thermo)

    def test_voidage_out_of_range(self, thermo: Thermo) -> None:
        params = _packing_params(1.0, voidage=1.5)
        with pytest.raises(ColumnInternalsError, match="voidage"):
            ColumnInternalsR1().solve({"inlet": _tray_inlet()}, params, thermo=thermo)

    def test_stichlmair_failure_is_refused(self, monkeypatch: pytest.MonkeyPatch, thermo: Thermo) -> None:
        """Any library exception in the Stichlmair solve becomes the typed refusal."""
        import ngdesign.units.column_shortcut.column_internals_r1 as mod

        def _boom(*_args: Any, **_kwargs: Any) -> float:
            raise RuntimeError("no convergence")

        monkeypatch.setattr(mod, "Stichlmair_flood", _boom)
        with pytest.raises(ColumnInternalsError, match="Stichlmair"):
            ColumnInternalsR1().solve({"inlet": _tray_inlet()}, _packing_params(1.0), thermo=thermo)
