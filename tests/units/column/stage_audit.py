"""Stage-by-stage MESH audit of a solved column result (test helper, not a test).

Recomputes every stage's component and enthalpy balance from the REPORTED
profile in ``info`` (``stage_<j>_{T_K,P_Pa,L_mol_s,V_mol_s,x_<cid>,y_<cid>}``)
and fresh thermo calls, without any solver internals, and re-flashes each
stage's own contents to check phase equilibrium. A unit that claims MESH must
pass this: the solver's own residual gate is not the oracle.
"""

from __future__ import annotations

from dataclasses import dataclass

from ngdesign.contracts import StreamState
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.stream import PhaseKind


@dataclass
class Stage:
    T: float
    P: float
    L: float
    V: float
    x: dict[str, float]
    y: dict[str, float]


def read_stages(info: dict[str, float], comps: list[str]) -> list[Stage]:
    """The reported profile, top stage first."""
    n = int(info["n_stages"])
    return [
        Stage(
            T=info[f"stage_{j}_T_K"],
            P=info[f"stage_{j}_P_Pa"],
            L=info[f"stage_{j}_L_mol_s"],
            V=info[f"stage_{j}_V_mol_s"],
            x={c: info.get(f"stage_{j}_x_{c}", 0.0) for c in comps},
            y={c: info.get(f"stage_{j}_y_{c}", 0.0) for c in comps},
        )
        for j in range(n)
    ]


def _h(thermo: Thermo, comp: dict[str, float], t: float, p: float, kind: PhaseKind) -> float:
    z = {c: v for c, v in comp.items() if v > 0.0}
    total = sum(z.values())
    return thermo.phase_props({c: v / total for c, v in z.items()}, t, p, kind).enthalpy


def material_residuals(
    stages: list[Stage],
    comps: list[str],
    feeds: dict[int, list[StreamState]],
    draws: dict[int, list[tuple[bool, float]]] | None = None,
    reflux: float = 0.0,
    source: list[dict[str, float]] | None = None,
) -> list[float]:
    """Max |in - out| per stage over the components, relative to the stage throughput.

    ``feeds`` and ``draws`` are keyed by 0-based stage; a draw is (is_vapour,
    flow). ``reflux`` is the total-condenser return L_0, at the y_1 composition.
    ``source`` carries the per-stage generation of a reactive column, mol/s.
    """
    out: list[float] = []
    for j, st in enumerate(stages):
        worst = 0.0
        for c in comps:
            inflow = sum(f.molar_flow * f.composition.get(c, 0.0) for f in feeds.get(j, []))
            if j > 0:
                inflow += stages[j - 1].L * stages[j - 1].x[c]
            elif reflux:
                inflow += reflux * st.y[c]
            if j + 1 < len(stages):
                inflow += stages[j + 1].V * stages[j + 1].y[c]
            if source is not None:
                inflow += source[j].get(c, 0.0)
            outflow = st.L * st.x[c] + st.V * st.y[c]
            for is_vap, flow in (draws or {}).get(j, []):
                outflow += flow * (st.y[c] if is_vap else st.x[c])
            worst = max(worst, abs(inflow - outflow) / max(st.L + st.V, 1e-12))
        out.append(worst)
    return out


def energy_residuals(
    thermo: Thermo,
    stages: list[Stage],
    feeds: dict[int, list[StreamState]],
    duties: dict[int, float] | None = None,
    skip: frozenset[int] = frozenset(),
    draws: dict[int, list[tuple[bool, float]]] | None = None,
    reflux_enthalpy: float = 0.0,
) -> list[float]:
    """|H_in + Q - H_out| per stage, relative to the stage enthalpy throughput.

    ``skip``: stages whose balance defines a duty. ``duties``: heat added, W.
    Phase enthalpies are single-phase builds at the reported composition.
    """
    hv = [_h(thermo, s.y, s.T, s.P, PhaseKind.VAPOR) for s in stages]
    hl = [_h(thermo, s.x, s.T, s.P, PhaseKind.HC_LIQUID) for s in stages]
    out: list[float] = []
    for j, st in enumerate(stages):
        if j in skip:
            out.append(0.0)
            continue
        h_in = sum(f.molar_flow * f.enthalpy for f in feeds.get(j, [])) + (duties or {}).get(j, 0.0)
        if j > 0:
            h_in += stages[j - 1].L * hl[j - 1]
        else:
            h_in += reflux_enthalpy
        if j + 1 < len(stages):
            h_in += stages[j + 1].V * hv[j + 1]
        h_out = st.L * hl[j] + st.V * hv[j]
        for is_vap, flow in (draws or {}).get(j, []):
            h_out += flow * (hv[j] if is_vap else hl[j])
        scale = max(abs(st.L * hl[j]) + abs(st.V * hv[j]), 1.0)
        out.append(abs(h_in - h_out) / scale)
    return out


def equilibrium_residuals(thermo: Thermo, stages: list[Stage]) -> list[float]:
    """Max |y_flash - y_reported| per stage: flash the stage contents at (T, P).

    The stage's L + V contents are re-flashed at its reported T and P; if the
    profile is at equilibrium the flash hands back its own vapour. A stage
    carrying a negligible flow of either phase has nothing to compare and
    reports 0.
    """
    out: list[float] = []
    for st in stages:
        total = st.L + st.V
        if st.V < 1e-9 * total or st.L < 1e-9 * total:
            out.append(0.0)
            continue
        z = {c: (st.L * st.x[c] + st.V * st.y[c]) / total for c in st.x}
        z = {c: v for c, v in z.items() if v > 0.0}
        state = thermo.flash_pt(z, st.T, st.P, total)
        vap = next((p for p in state.phases if p.kind == PhaseKind.VAPOR), None)
        if vap is None:
            out.append(1.0)
            continue
        out.append(max(abs(vap.composition.get(c, 0.0) - st.y.get(c, 0.0)) for c in st.y))
    return out
