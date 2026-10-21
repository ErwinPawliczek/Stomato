"""P1-11 step-1 smoothness test: the amine K-value surface on a real profile.

Spec: specs/backend/P1-11-reactive-mesh-closure.md.  Central finite-difference
derivatives of the K-values and flash enthalpies w.r.t. T and the liquid CO2
mole fraction, at every stage state of the converged 20-stage MDEA absorber
(fixture of tests/units/test_column_amine.py: T 281.6-314.3 K, loadings
0.005-0.502 mol/mol).  A smooth surface's derivatives converge as the step
shrinks until round-off; a noisy one's diverge.  The step at which a derivative
stops converging is the noise floor the Naphtali-Sandholm finite-difference
Jacobian sees.

Measured floors on this branch (documented per the spec):

- amine_ke: every derivative converges monotonically down to h = 1e-6 with the
  final two steps (1e-5, 1e-6) agreeing to < 1e-4 relative wherever the
  derivative itself exceeds the round-off floor eps * f / (2 h T); for the
  trace hydrocarbons (K rides a T-constant Henry correlation) the derivative
  sits AT the round-off floor and the gate falls back to it.  No divergence at
  any step: the loading fixed point is a smooth function of the state.
- amine_enrtl: same behaviour on the H2S-free analogue states (the package
  refuses H2S service with a typed scope error -- no citable parameter set
  covers CO2+H2S amine chemistry, module docstring "Honest parameter-status" --
  so each stage liquid is evaluated with H2S stripped and renormalised, and the
  absorber's cold-end stages below enrtl's 290 K model window are skipped:
  the package's typed window rejection there is its documented behaviour).

Two evaluations at the same state are bit-identical (asserted directly).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from ngdesign.contracts import StreamState
from ngdesign.registry import get
from ngdesign.units.column import Column
from ngdesign.units.mdea_absorber import MdeaAbsorber

#: Relative FD steps, largest to smallest (spec: converge down to 1e-6).
_STEPS = (1e-2, 1e-3, 1e-4, 1e-5, 1e-6)

#: The spec's convergence gate: the final two steps agree within 1e-4 relative.
_FINAL_AGREEMENT = 1e-4

_EPS = 2.220446049250313e-16

_STAGES = 20

_ALL_CIDS = ("C1", "C2", "C3", "N2", "CO2", "H2S", "MDEA", "H2O")

#: amine_enrtl's declared model window (enrtl.py _T_MIN_K/_T_MAX_K).
_T_WINDOW = (290.0, 400.0)

#: The enrtl speciation root solve makes each evaluation ~0.1 s; a full
#: per-package derivative walk is thousands of evaluations.  The repo-wide
#: 120 s cap is a flake here, not a guard (the run is deterministic, so a slow
#: pass is still a pass); 900 s leaves an order of magnitude of headroom.
_TIMEOUT_S = 900


def _profile_states() -> list[dict[str, Any]]:
    """Solve the absorber once and return its per-stage (T, P, liquid x) states."""
    feeds, _params = MdeaAbsorber.example_case()
    gas, lean = feeds["gas_in"], feeds["lean_amine_in"]
    port = StreamState(
        T=gas["T"],
        P=gas["P"],
        molar_flow=gas["molar_flow"],
        composition=dict(gas["composition"]),
        vapor_fraction=1.0,
        enthalpy=0.0,
        entropy=0.0,
        phases=[],
    )
    params: dict[str, Any] = {
        "n_stages": _STAGES,
        "condenser": "none",
        "reboiler": "none",
        "pressure_profile": 6.5e6,
        "feed_stage": _STAGES,
        "feeds": [
            {
                "T": lean["T"],
                "P": lean["P"],
                "molar_flow": lean["molar_flow"],
                "composition": lean["composition"],
                "stage": 1,
            }
        ],
    }
    res = Column().solve({"feed": port}, params, get("thermo", "amine_ke")())
    states: list[dict[str, Any]] = []
    for j in range(_STAGES):
        states.append(
            {
                "T": res.info[f"stage_{j}_T_K"],
                "P": res.info[f"stage_{j}_P_Pa"],
                "x": {cid: res.info[f"stage_{j}_x_{cid}"] for cid in _ALL_CIDS},
            }
        )
    return states


@pytest.fixture(name="profile", scope="module")
def _profile() -> Iterator[list[dict[str, Any]]]:
    yield _profile_states()


def _derivs(
    pkg: Any, state: dict[str, Any], which: str, cid: str | None = None
) -> tuple[list[float], float] | None:
    """Central-difference derivatives of the requested function at h = 1e-2 ...
    1e-6, plus the evaluation scale (max |f|) for the round-off floor.  The K
    branches read component ``cid``; the enthalpy branch is scalar.  None if
    any evaluation is single-phase: the K surface is only defined in the
    two-phase window."""
    T, P, x0 = state["T"], state["P"], state["x"]
    if which == "K_xco2" and x0["CO2"] == 0.0:
        return None
    out: list[float] = []
    f_scale = 0.0
    for h in _STEPS:
        if which == "K_T":
            f_lo = pkg.k_values(x0, T * (1.0 - h), P)
            f_hi = pkg.k_values(x0, T * (1.0 + h), P)
        elif which == "K_xco2":
            xs = dict(x0)
            xs["CO2"] = x0["CO2"] * (1.0 + h)
            sx = sum(xs.values())
            xs = {c: v / sx for c, v in xs.items()}
            f_lo = pkg.k_values(x0, T, P)
            f_hi = pkg.k_values(xs, T, P)
        else:  # "H_T": flash enthalpy vs T (scalar function, once per stage)
            f_lo = pkg.flash_pt(x0, T * (1.0 - h), P, 1.0).enthalpy
            f_hi = pkg.flash_pt(x0, T * (1.0 + h), P, 1.0).enthalpy
        if f_lo is None or f_hi is None:
            return None
        if which == "H_T":
            v_lo, v_hi, den_c = float(f_lo), float(f_hi), T
        else:
            assert cid is not None
            v_lo, v_hi = float(f_lo[cid]), float(f_hi[cid])
            den_c = T if which == "K_T" else x0["CO2"]
        f_scale = max(f_scale, abs(v_lo), abs(v_hi))
        out.append((v_hi - v_lo) / (2.0 * h * den_c))
    floor = 8.0 * _EPS * f_scale / (2.0 * _STEPS[-1] * (T if which != "K_xco2" else x0["CO2"]))
    return out, floor


def _analogue(state: dict[str, Any], pkg_name: str) -> dict[str, Any] | None:
    """The state as the given package sees it, or None when the state sits
    outside that package's declared applicability.

    amine_enrtl refuses H2S service by design (no citable parameter set covers
    CO2+H2S amine chemistry, module docstring "Honest parameter-status"), so
    its states are the H2S-free analogue, renormalised.  Its model window is
    290-400 K (enrtl.py _T_MIN_K/_T_MAX_K); the absorber's cold-end stages
    (down to 281.6 K) are outside it and the package raises its typed
    AmineChemistryError there -- that rejection is the documented behaviour,
    so those stages are skipped for enrtl rather than exercised.
    """
    if pkg_name != "amine_enrtl":
        return state
    if not (_T_WINDOW[0] <= state["T"] <= _T_WINDOW[1]):
        return None
    s = {c: v for c, v in state["x"].items() if c != "H2S"}
    sx = sum(s.values())
    return {**state, "x": {c: v / sx for c, v in s.items()}}


def _check_walk(pkg_name: str, which: str, label: str, d: list[float], floor: float) -> None:
    """The spec's convergence gates on one derivative walk.

    1. The final two estimates agree within 1e-4 relative, or both sit at the
       evaluation's round-off floor eps * f / (2 h_min T) (where T-constant
       Henry K's derivatives live).
    2. The estimate at the smallest step is no larger than at the largest
       step: a divergent (noisy) surface makes the derivative estimate GROW as
       h shrinks by orders of magnitude; a convergent one stabilises.
    """
    diffs = [abs(d[i + 1] - d[i]) for i in range(len(d) - 1)]
    scale = max(_FINAL_AGREEMENT * max(abs(d[-1]), abs(d[-2])), floor)
    assert diffs[-1] <= scale, f"{pkg_name} {which} {label}: final two steps disagree: {d}"
    assert abs(d[-1]) <= max(2.0 * abs(d[0]), 4.0 * floor), (
        f"{pkg_name} {which} {label}: derivative estimate diverges as h shrinks: {d}"
    )


@pytest.mark.timeout(_TIMEOUT_S)
@pytest.mark.parametrize("pkg_name", ["amine_ke", "amine_enrtl"])
@pytest.mark.parametrize("which", ["K_T", "K_xco2", "H_T"])
def test_surface_derivatives_converge(profile: list[dict[str, Any]], pkg_name: str, which: str) -> None:
    """FD derivatives converge down to h = 1e-6; final two steps agree < 1e-4.

    K derivatives are checked per component; the flash enthalpy is a scalar
    function of the state, so its derivative is checked once per stage.
    """
    pkg = get("thermo", pkg_name)()
    cids = _ALL_CIDS if pkg_name == "amine_ke" else ("C1", "C2", "C3", "N2", "CO2", "MDEA", "H2O")
    for stage in profile:
        state = _analogue(stage, pkg_name)
        if state is None:
            continue  # outside the package's declared applicability window
        if which == "H_T":
            got = _derivs(pkg, state, which)
            if got is not None:
                d, floor = got
                _check_walk(pkg_name, which, f"T={state['T']:.2f}", d, floor)
            continue
        for c in cids:
            got = _derivs(pkg, state, which, cid=c)
            if got is None:
                continue  # single-phase edge: K surface intentionally undefined
            d, floor = got
            _check_walk(pkg_name, which, c, d, floor)


@pytest.mark.parametrize("pkg_name", ["amine_ke", "amine_enrtl"])
def test_same_state_bit_identical(profile: list[dict[str, Any]], pkg_name: str) -> None:
    """Two evaluations at the same state return bit-identical values (spec)."""
    pkg = get("thermo", pkg_name)()
    for stage in profile:
        state = _analogue(stage, pkg_name)
        if state is None:
            continue
        x = state["x"]
        k1 = pkg.k_values(x, stage["T"], stage["P"])
        k2 = pkg.k_values(x, stage["T"], stage["P"])
        if k1 is None:
            continue  # single-phase: nothing to compare
        assert k1 == k2
        f1 = pkg.flash_pt(x, stage["T"], stage["P"], 1.0)
        f2 = pkg.flash_pt(x, stage["T"], stage["P"], 1.0)
        assert f1.enthalpy == f2.enthalpy
        assert f1.vapor_fraction == f2.vapor_fraction
