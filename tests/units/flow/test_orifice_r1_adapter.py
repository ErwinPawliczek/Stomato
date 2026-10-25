"""Adapter tests for the orifice R1 unit: sizing (S1), R0 identity, refusals."""

from __future__ import annotations

from typing import Any

import pytest
from fluids.flow_meter import C_Reader_Harris_Gallagher

from ngdesign.contracts import PhaseKind, StreamState
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.stream import Phase
from ngdesign.contracts.thermo import PhaseProps, PropertyDerivatives, SaturationPoint
from ngdesign.units.flow import orifice, orifice_r1_adapter
from ngdesign.units.flow.orifice_r1 import OrificeR1Error
from tests.conftest import flash_feed

_LIQ = {"H2O": 1.0}
_LIQ_MW = 18.0  # g/mol: StreamState.molecular_weight is g/mol, mass_flow divides by 1000


class StaticThermo:
    """Minimal Thermo: one phase-property set, flash_ph echoes at the target P."""

    def __init__(self, density: float, viscosity: float | None, mw: float = _LIQ_MW):
        self._density = density
        self._viscosity = viscosity
        self._mw = mw

    def phase_props(self, composition: dict[str, float], T: float, P: float, kind: PhaseKind) -> PhaseProps:
        return PhaseProps(
            kind=kind,
            mole_fraction=1.0,
            composition=dict(composition),
            molecular_weight=self._mw,
            density=self._density,
            enthalpy=0.0,
            entropy=0.0,
            cp=75.0,
            gibbs=0.0,
            z_factor=0.99,
            viscosity=self._viscosity,
        )

    def flash_ph(self, z: dict[str, float], P: float, H: float, molar_flow: float) -> StreamState:
        return StreamState(
            T=293.15,
            P=P,
            molar_flow=molar_flow,
            composition=dict(z),
            vapor_fraction=0.0,
            enthalpy=H,
            entropy=0.0,
            phases=[
                Phase(
                    kind=PhaseKind.HC_LIQUID,
                    mole_fraction=1.0,
                    composition=dict(z),
                    density=self._density,
                    molecular_weight=self._mw,
                )
            ],
        )

    def flash_pt(self, z: dict[str, float], T: float, P: float, molar_flow: float) -> StreamState:
        raise NotImplementedError("not needed by the orifice adapter tests")

    def flash_ps(self, z: dict[str, float], P: float, S: float, molar_flow: float) -> StreamState:
        raise NotImplementedError("not needed by the orifice adapter tests")

    def flash_tvf(self, z: dict[str, float], T: float, vf: float, molar_flow: float) -> StreamState:
        raise NotImplementedError("not needed by the orifice adapter tests")

    def flash_pvf(self, z: dict[str, float], P: float, vf: float, molar_flow: float) -> StreamState:
        raise NotImplementedError("not needed by the orifice adapter tests")

    def bubble_point(
        self, z: dict[str, float], *, T: float | None = None, P: float | None = None
    ) -> SaturationPoint:
        raise NotImplementedError("not needed by the orifice adapter tests")

    def dew_point(
        self, z: dict[str, float], *, T: float | None = None, P: float | None = None
    ) -> SaturationPoint:
        raise NotImplementedError("not needed by the orifice adapter tests")

    def k_values(self, z: dict[str, float], T: float, P: float) -> dict[str, float] | None:
        raise NotImplementedError("not needed by the orifice adapter tests")

    def derivatives(
        self, composition: dict[str, float], T: float, P: float, kind: PhaseKind
    ) -> PropertyDerivatives:
        raise NotImplementedError("not needed by the orifice adapter tests")

    def pure_psat(self, cid: str, T: float) -> float | None:
        raise NotImplementedError("not needed by the orifice adapter tests")


def _o1_inlet() -> StreamState:
    """O1's liquid basis as a StreamState: qm = 10 kg/s, rho = 998, mu = 1e-3."""
    return StreamState(
        T=293.15,
        P=5.0e5,
        molar_flow=10.0 / (_LIQ_MW / 1000.0),  # kg/s -> mol/s: MW is g/mol
        composition=dict(_LIQ),
        vapor_fraction=0.0,
        enthalpy=0.0,
        entropy=0.0,
        phases=[
            Phase(
                kind=PhaseKind.HC_LIQUID,
                mole_fraction=1.0,
                composition=dict(_LIQ),
                density=998.0,
                molecular_weight=_LIQ_MW,
            )
        ],
    )


def test_s1_sizes_the_o1_basis_to_25000_pa() -> None:
    """Spec S1: D = 0.10226 m, liquid O1 basis, target dP = 25000 Pa, flange taps."""
    thermo = StaticThermo(density=998.0, viscosity=1e-3)
    result = orifice_r1_adapter.OrificeR1().solve(
        {"inlet": _o1_inlet()},
        {"D_m": 0.10226, "dP_design_Pa": 25000.0, "taps": "flange"},
        thermo,
    )
    info = result.info
    assert info["sizing"] == 1.0
    assert info["bore_m"] == pytest.approx(0.0534567804546456, rel=1e-10)
    assert info["beta"] == pytest.approx(0.522753573779049, rel=1e-10)
    assert info["Re_D"] == pytest.approx(124510.027844237, rel=1e-10)
    assert info["Re_D"] > 5000.0  # validity at the sized point
    assert info["dP_Pa"] == pytest.approx(25000.0, rel=1e-10)


def test_r0_identity_liquid(thermo: Thermo) -> None:
    """R1 with C pinned to Cd equals R0 exactly on the R0 example (1e-12)."""
    cls = orifice.Orifice
    feeds, params = cls.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    r0 = cls().solve(inlets, params, thermo)
    r1 = orifice_r1_adapter.OrificeR1().solve(
        inlets,
        {"D_m": 0.1, "bore_m": 0.05, "C_specified": 0.61, "mu_Pa_s": 1e-3},
        thermo,
    )
    assert r1.info["dP_Pa"] == pytest.approx(r0.info["dP_Pa"], rel=1e-12)
    assert r1.info["permanent_loss_Pa"] == pytest.approx(r0.info["permanent_loss_Pa"], rel=1e-12)
    assert r1.outlets["outlet"].P == pytest.approx(r0.outlets["outlet"].P, rel=1e-12)
    assert r1.outlets["outlet"].enthalpy == pytest.approx(r0.outlets["outlet"].enthalpy, rel=1e-12)


def test_r0_identity_gas(thermo: Thermo) -> None:
    """R1 with C pinned equals R0 for a vapour inlet too (1e-9: R0's fixed point)."""
    gas_feed = {
        "T": 348.15,
        "P": 670170.408,
        "molar_flow": 20.0,
        "composition": {"C3": 0.45, "nC4": 0.55},
    }
    inlet = flash_feed(thermo, gas_feed)
    assert inlet.vapor_fraction > 0.999
    r0 = orifice.Orifice().solve({"inlet": inlet}, {"bore_m": 0.05, "beta": 0.5, "Cd": 0.61}, thermo)
    r1 = orifice_r1_adapter.OrificeR1().solve(
        {"inlet": inlet},
        {"D_m": 0.1, "bore_m": 0.05, "C_specified": 0.61, "mu_Pa_s": 1.2e-5},
        thermo,
    )
    assert r1.info["dP_Pa"] == pytest.approx(r0.info["dP_Pa"], rel=1e-9)
    assert r1.info["permanent_loss_Pa"] == pytest.approx(r0.info["permanent_loss_Pa"], rel=1e-9)
    assert r1.outlets["outlet"].P == pytest.approx(r0.outlets["outlet"].P, rel=1e-12)


def test_reports_rhg_C_and_closes_eq1(thermo: Thermo) -> None:
    """On a liquid inlet, reported C is fluids' RHG value and dP closes eq. (1)."""
    feeds, _ = orifice.Orifice.example_case()
    inlet = flash_feed(thermo, feeds["inlet"])
    params: dict[str, Any] = {"D_m": 0.1, "bore_m": 0.05, "taps": "flange"}
    result = orifice_r1_adapter.OrificeR1().solve({"inlet": inlet}, params, thermo)

    dense = max(
        (p for p in inlet.phases if p.kind is not PhaseKind.VAPOR),
        key=lambda p: p.mole_fraction,
    )
    props = thermo.phase_props(dense.composition, inlet.T, inlet.P, dense.kind)
    mu = props.viscosity
    assert mu is not None
    qm = inlet.mass_flow
    d, D = params["bore_m"], params["D_m"]
    beta = d / D
    E = 1.0 / (1.0 - beta**4) ** 0.5
    A = 3.141592653589793 / 4.0 * d**2
    C_expected = C_Reader_Harris_Gallagher(D, d, dense.density, mu, qm, taps="flange")
    assert result.info["C"] == pytest.approx(C_expected, rel=1e-12)
    dP_expected = (qm / (C_expected * E * A * 1.0)) ** 2 / (2.0 * dense.density)
    assert result.info["dP_Pa"] == pytest.approx(dP_expected, rel=1e-12)
    assert result.info["sizing"] == 0.0


def test_example_case_solves(thermo: Thermo) -> None:
    """The R1 example solves on the real package without a viscosity override."""
    feeds, params = orifice_r1_adapter.OrificeR1.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    result = orifice_r1_adapter.OrificeR1().solve(inlets, params, thermo)
    outlet = result.outlets["outlet"]
    assert outlet.T > 0.0 and outlet.P > 0.0 and outlet.molar_flow > 0.0
    assert result.info["C"] > 0.5 and result.info["C"] < 0.7
    assert result.info["Re_D"] >= 5000.0


def test_refuses_missing_D_m() -> None:
    with pytest.raises(OrificeR1Error, match="D_m"):
        orifice_r1_adapter.OrificeR1().solve(
            {"inlet": _o1_inlet()}, {"bore_m": 0.05}, StaticThermo(998.0, 1e-3)
        )


def test_refuses_nonpositive_D_m() -> None:
    with pytest.raises(OrificeR1Error, match="D_m"):
        orifice_r1_adapter.OrificeR1().solve(
            {"inlet": _o1_inlet()}, {"D_m": 0.0, "bore_m": 0.05}, StaticThermo(998.0, 1e-3)
        )


def test_refuses_bore_and_target_together() -> None:
    with pytest.raises(OrificeR1Error, match="exactly one of bore_m / dP_design_Pa"):
        orifice_r1_adapter.OrificeR1().solve(
            {"inlet": _o1_inlet()},
            {"D_m": 0.10226, "bore_m": 0.05, "dP_design_Pa": 25000.0},
            StaticThermo(998.0, 1e-3),
        )


def test_refuses_neither_bore_nor_target() -> None:
    with pytest.raises(OrificeR1Error, match="exactly one of bore_m / dP_design_Pa"):
        orifice_r1_adapter.OrificeR1().solve(
            {"inlet": _o1_inlet()}, {"D_m": 0.10226}, StaticThermo(998.0, 1e-3)
        )


def test_refuses_unknown_taps() -> None:
    with pytest.raises(OrificeR1Error, match="taps"):
        orifice_r1_adapter.OrificeR1().solve(
            {"inlet": _o1_inlet()},
            {"D_m": 0.10226, "bore_m": 0.05, "taps": "venacontracta"},
            StaticThermo(998.0, 1e-3),
        )


def test_refuses_two_phase_inlet(thermo: Thermo) -> None:
    """0.001 < vapor_fraction < 0.999 is refused: ISO 5167 is single-phase."""
    feeds, _ = orifice.Orifice.example_case()
    inlet = flash_feed(thermo, feeds["inlet"])
    mislabelled = inlet.model_copy(update={"vapor_fraction": 0.5})
    with pytest.raises(OrificeR1Error, match="single-phase"):
        orifice_r1_adapter.OrificeR1().solve({"inlet": mislabelled}, {"D_m": 0.1, "bore_m": 0.05}, thermo)


def test_refuses_without_any_viscosity() -> None:
    """No phase viscosity from the package and no mu_Pa_s: refused, named."""
    with pytest.raises(OrificeR1Error, match="mu_Pa_s"):
        orifice_r1_adapter.OrificeR1().solve(
            {"inlet": _o1_inlet()},
            {"D_m": 0.10226, "bore_m": 0.05},
            StaticThermo(density=998.0, viscosity=None),
        )


def test_refuses_unreachable_sizing_target() -> None:
    """A target below dP(d_hi) refuses with the achievable range, not a silent bore."""
    with pytest.raises(OrificeR1Error, match="no bore"):
        orifice_r1_adapter.OrificeR1().solve(
            {"inlet": _o1_inlet()},
            {"D_m": 0.10226, "dP_design_Pa": 1e-6},
            StaticThermo(998.0, 1e-3),
        )


def test_refuses_sizing_non_convergence(monkeypatch: pytest.MonkeyPatch) -> None:
    """A brentq failure becomes a typed refusal, not a bare RuntimeError."""

    def boom(*args: Any, **kwargs: Any) -> float:
        raise RuntimeError("boom")

    monkeypatch.setattr(orifice_r1_adapter, "brentq", boom)
    with pytest.raises(OrificeR1Error, match="sizing did not converge"):
        orifice_r1_adapter.OrificeR1().solve(
            {"inlet": _o1_inlet()},
            {"D_m": 0.10226, "dP_design_Pa": 25000.0, "taps": "flange"},
            StaticThermo(998.0, 1e-3),
        )


def test_refuses_fixed_point_non_convergence(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-convergent expansibility hits the iteration cap and refuses."""
    import ngdesign.units.flow.orifice_r1 as pure

    calls = {"n": 0}

    def oscillating(D: float, d: float, P1: float, P2: float, kappa: float) -> float:
        calls["n"] += 1
        return 0.99 if calls["n"] % 2 else 0.999

    monkeypatch.setattr(pure, "orifice_expansibility", oscillating)
    gas_inlet = StreamState(
        T=300.0,
        P=5.0e6,
        molar_flow=100.0,
        composition={"H2O": 1.0},
        vapor_fraction=1.0,
        enthalpy=0.0,
        entropy=0.0,
        phases=[
            Phase(
                kind=PhaseKind.VAPOR,
                mole_fraction=1.0,
                composition={"H2O": 1.0},
                density=40.0,
                molecular_weight=18.0,
            )
        ],
    )
    with pytest.raises(OrificeR1Error, match="did not converge"):
        orifice_r1_adapter.OrificeR1().solve(
            {"inlet": gas_inlet},
            {"D_m": 0.1, "bore_m": 0.06, "mu_Pa_s": 1.2e-5, "taps": "corner"},
            StaticThermo(density=40.0, viscosity=1.2e-5, mw=18.0),
        )
