"""Liquid-liquid extractor, R2 (plan U-E 9, unit ``liquid_liquid_extractor``).

Plugin kind "unit", name "liquid_liquid_extractor", level R2. Ports ``feed`` +
``solvent_in`` -> ``extract`` + ``raffinate``, as R0. Equilibrium LLE stages
1..N, feed on stage 1, solvent on stage N: raffinate R_j runs 1 -> N, extract
E_j runs N -> 1.

Method: the isothermal sum-rates algorithm (Tsuboka & Katayama, J. Chem. Eng.
Japan 9 (1976) 40; Seader, Henley & Roper 3rd ed., Sect. 10.5). With K_ij =
x^E_ij / x^R_ij frozen, the component balances

    R_{j-1} x_{j-1} + E_{j+1} K_{j+1} x_{j+1} + f_j - (R_j + E_j K_j) x_j = 0

are tridiagonal (the column package's ``_thomas``). The raffinate flows then
follow from the sum rates R_j = sum_i (R_j x_ij), the extract flows from the
total balances, and the K-values from a liquid-liquid flash of each stage's
contents on the package's own surface. This cannot use the inside-out column:
its temperature comes from a bubble equation, and an LLE stage has no vapour to
give one. K is a tie line, so T does not enter the loop at all.

The column temperature is uniform, ``T`` (default: the flow-weighted inlet
temperature), so the level is isothermal: heat of mixing is carried by
``duty_W``, the boundary enthalpy difference needed to hold T. The loop ends when
the tie lines stop moving; the stage flash is then the equilibrium of record.

Refusals (:class:`ExtractorR2Error`): a stage whose contents do not split into
two liquids (no second phase, or a vapour), non-convergence within ``_MAX_ITER``,
bad parameters.

All SI: K, Pa abs, mol/s, J/mol, W. Pure functions; no I/O; no global state.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.stream import Phase, PhaseKind
from ngdesign.units.column.linalg import _thomas

_ALLOWED_KEYS = frozenset({"n_stages", "T", "P"})
_MAX_ITER = 200
#: Convergence: largest relative move of any K and of any flow between sweeps.
_TOL = 1e-8
#: Geometric damping of K and arithmetic damping of the flows between sweeps.
_DAMP = 0.7
#: Floor on a tie-line K for a component absent from one liquid.
_K_FLOOR = 1e-14


class ExtractorR2Error(ValueError):
    """Refusal: the extractor spec is invalid or a stage does not split."""


def _phases(
    z: dict[str, float], t: float, p: float, key: str, thermo: Thermo, stage: int
) -> tuple[Phase, Phase]:
    """(extract, raffinate) of one stage: the liquid richer in the solvent key is the extract."""
    state = thermo.flash_pt({c: v for c, v in z.items() if v > 0.0}, t, p, 1.0)
    if any(ph.kind == PhaseKind.VAPOR for ph in state.phases):
        raise ExtractorR2Error(f"stage {stage} forms a vapour at {t:.2f} K, {p:.4g} Pa")
    if len(state.phases) != 2:
        raise ExtractorR2Error(
            f"stage {stage} holds {len(state.phases)} liquid phase(s) at {t:.2f} K: "
            "an extractor stage needs exactly two"
        )
    a, b = state.phases
    return (a, b) if a.composition.get(key, 0.0) >= b.composition.get(key, 0.0) else (b, a)


class ExtractorR2:
    """Counter-current LLE stages by the isothermal sum-rates method."""

    inlet_ports = ("feed", "solvent_in")
    outlet_ports = ("extract", "raffinate")

    def solve(self, inlets: dict[str, StreamState], params: dict[str, Any], thermo: Thermo) -> UnitResult:
        feed = inlets.get("feed")
        solvent = inlets.get("solvent_in")
        if feed is None or solvent is None:
            raise ExtractorR2Error("liquid_liquid_extractor R2 requires the feed and solvent_in streams")
        if feed.molar_flow <= 0.0 or solvent.molar_flow <= 0.0:
            raise ExtractorR2Error("liquid_liquid_extractor R2 refuses a zero-flow inlet")
        for key in params:
            if key not in _ALLOWED_KEYS:
                raise ExtractorR2Error(f"liquid_liquid_extractor R2 refuses unknown parameter {key!r}")
        n = params.get("n_stages")
        if not isinstance(n, int) or isinstance(n, bool) or n < 1:
            raise ExtractorR2Error(f"n_stages must be an integer >= 1, got {n!r}")
        f_tot, s_tot = feed.molar_flow, solvent.molar_flow
        t = float(params.get("T", (feed.T * f_tot + solvent.T * s_tot) / (f_tot + s_tot)))
        p = float(params.get("P", min(feed.P, solvent.P)))
        comps = sorted(set(feed.composition) | set(solvent.composition))
        key = max(solvent.composition, key=lambda c: solvent.composition[c])
        f_in = [[0.0] * n for _ in comps]
        for i, c in enumerate(comps):
            f_in[i][0] += feed.composition.get(c, 0.0) * f_tot
            f_in[i][n - 1] += solvent.composition.get(c, 0.0) * s_tot

        below = [sum(f_in[i][m] for i in range(len(comps)) for m in range(j, n)) for j in range(n)]
        mix = {c: sum(f_in[i]) for i, c in enumerate(comps)}
        total = f_tot + s_tot
        extract, raffinate = _phases({c: v / total for c, v in mix.items()}, t, p, key, thermo, 1)
        k_mix = {
            c: max(extract.composition.get(c, 0.0), _K_FLOOR)
            / max(raffinate.composition.get(c, 0.0), _K_FLOOR)
            for c in comps
        }
        ks = [dict(k_mix) for _ in range(n)]
        r = [f_tot] * n
        e = [s_tot] * n
        x: list[dict[str, float]] = [dict(raffinate.composition) for _ in range(n)]
        iterations = 0
        moved = float("inf")
        converged = False
        for iterations in range(1, _MAX_ITER + 1):  # noqa: B007 - reported in info
            solved: list[list[float]] = []
            for i, c in enumerate(comps):
                sub = [r[j - 1] if j else 0.0 for j in range(n)]
                diag = [-(r[j] + e[j] * ks[j][c]) for j in range(n)]
                up = [e[j + 1] * ks[j + 1][c] if j + 1 < n else 0.0 for j in range(n)]
                rhs = [-f_in[i][j] for j in range(n)]
                solved.append([max(v, 0.0) for v in _thomas(sub, diag, up, rhs)])
            moved = 0.0
            r_new = [r[j] * sum(col[j] for col in solved) for j in range(n)]
            # Envelope over stages j..N: R_{j-1} + sum_{m>=j} F_m = E_j + R_N.
            e_new = [(r_new[j - 1] if j else 0.0) + below[j] - r_new[n - 1] for j in range(n)]
            for j in range(n):
                if r_new[j] <= 0.0 or e_new[j] <= 0.0:
                    raise ExtractorR2Error(
                        f"stage {j + 1} lost a liquid phase: R={r_new[j]:.4g}, E={e_new[j]:.4g}"
                    )
                moved = max(moved, abs(r_new[j] / r[j] - 1.0), abs(e_new[j] / e[j] - 1.0))
                r[j] += _DAMP * (r_new[j] - r[j])
                e[j] += _DAMP * (e_new[j] - e[j])
            for j in range(n):
                total_x = sum(col[j] for col in solved)
                x[j] = {c: solved[i][j] / total_x for i, c in enumerate(comps)}
                y_j = {c: ks[j][c] * x[j][c] for c in comps}
                y_sum = sum(y_j.values())
                z = {c: (r[j] * x[j][c] + e[j] * y_j[c] / y_sum) / (r[j] + e[j]) for c in comps}
                extract, raffinate = _phases(z, t, p, key, thermo, j + 1)
                for c in comps:
                    k_new = max(extract.composition.get(c, 0.0), _K_FLOOR) / max(
                        raffinate.composition.get(c, 0.0), _K_FLOOR
                    )
                    moved = max(moved, abs(k_new / ks[j][c] - 1.0))
                    ks[j][c] = ks[j][c] ** (1.0 - _DAMP) * k_new**_DAMP
            if moved < _TOL:
                converged = True
                break
        if not converged:
            raise ExtractorR2Error(
                f"sum-rates loop did not converge in {_MAX_ITER} sweeps (move {moved:.3g})"
            )

        y1 = {c: ks[0][c] * x[0][c] for c in comps}
        norm = sum(y1.values())
        z_extract = {c: v / norm for c, v in y1.items() if v > 0.0}
        z_raffinate = {c: v for c, v in x[n - 1].items() if v > 0.0}
        extract_out = thermo.flash_pt(z_extract, t, p, e[0])
        raffinate_out = thermo.flash_pt(z_raffinate, t, p, r[n - 1])
        h_in = feed.enthalpy * f_tot + solvent.enthalpy * s_tot
        h_out = extract_out.enthalpy * e[0] + raffinate_out.enthalpy * r[n - 1]

        info: dict[str, float] = {
            "n_stages": float(n),
            "T_K": t,
            "P_Pa": p,
            "sum_rates_sweeps": float(iterations),
        }
        for j in range(n):
            info[f"stage_{j}_R_mol_s"] = r[j]
            info[f"stage_{j}_E_mol_s"] = e[j]
            y_sum = sum(ks[j][c] * x[j][c] for c in comps)
            for c in comps:
                info[f"stage_{j}_xR_{c}"] = x[j][c]
                info[f"stage_{j}_xE_{c}"] = ks[j][c] * x[j][c] / y_sum
                info[f"stage_{j}_K_{c}"] = ks[j][c]
        return UnitResult(
            outlets={"extract": extract_out, "raffinate": raffinate_out},
            duty_W=h_out - h_in,
            power_W=0.0,
            info=info,
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Illustrative: water washes methanol out of n-hexane, 300 K, 1 MPa."""
        feeds = {
            "feed": {"T": 300.0, "P": 1.0e6, "molar_flow": 100.0, "composition": {"nC6": 0.8, "MeOH": 0.2}},
            "solvent_in": {"T": 300.0, "P": 1.0e6, "molar_flow": 40.0, "composition": {"H2O": 1.0}},
        }
        return feeds, {"n_stages": 4}
