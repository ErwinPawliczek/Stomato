"""The eos_cg row: the 2016 model over its six components, refusing everything else."""

from __future__ import annotations

from itertools import combinations

import pytest

from ngdesign import registry
from ngdesign.thermo.helmholtz import ComponentNotSupported

cp = pytest.importorskip("CoolProp.CoolProp")

CAS = {
    "CO2": "124-38-9",
    "H2O": "7732-18-5",
    "N2": "7727-37-9",
    "O2": "7782-44-7",
    "Ar": "7440-37-1",
    "CO": "630-08-0",
}


@pytest.mark.parametrize(("a", "b"), list(combinations(CAS, 2)))
def test_every_pair_of_the_slate_is_the_gernert_model(a: str, b: str) -> None:
    """The row's claim to be EOS-CG rests on this: CoolProp's pair source for all 15."""
    try:
        source = cp.get_mixture_binary_pair_data(CAS[a], CAS[b], "BibTeX")
    except ValueError:  # CoolProp keys each pair in one order
        source = cp.get_mixture_binary_pair_data(CAS[b], CAS[a], "BibTeX")
    assert "Gernert" in source


def test_mixture_with_oxygen_argon_and_co_flashes() -> None:
    z = {"CO2": 0.9, "O2": 0.04, "Ar": 0.03, "CO": 0.01, "N2": 0.02}
    state = registry.create("thermo", "eos_cg").flash_pt(z, 350.0, 5e6, 1.0)
    assert state.vapor_fraction == 1.0
    ideal = (
        5e6
        / (8.31446261815324 * 350.0)
        * sum(z[c] * {"CO2": 44.01, "O2": 32.0, "Ar": 39.95, "CO": 28.01, "N2": 28.01}[c] / 1000.0 for c in z)
    )
    assert state.phases[0].density > ideal  # attractive gas near 80 bar-reduced pressure


def test_humid_co2_density_matches_teqp_on_the_same_departure() -> None:
    """teqp's multifluid over the same files: an independent implementation of the sum."""
    z = {"CO2": 0.95, "H2O": 0.05}
    state = registry.create("thermo", "eos_cg").flash_pt(z, 500.0, 5e6, 1.0)
    teqp = pytest.importorskip("teqp")
    root = teqp.get_datapath()
    model = teqp.build_multifluid_model(["CarbonDioxide", "Water"], root)
    rho = state.phases[0].density / (0.95 * 0.04401 + 0.05 * 0.018015)
    import numpy as np

    pressure = rho * 8.31446261815324 * 500.0 * (1.0 + model.get_Ar01(500.0, rho, np.array([0.95, 0.05])))
    assert pressure == pytest.approx(5e6, rel=0.005)


def test_a_hydrocarbon_refuses_by_name() -> None:
    with pytest.raises(ComponentNotSupported, match="C1"):
        registry.create("thermo", "eos_cg").flash_pt({"C1": 0.5, "CO2": 0.5}, 300.0, 1e6, 1.0)
