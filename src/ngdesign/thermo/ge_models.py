"""In-house van Laar and Margules gE models for the gamma-phi adapter (spec T-03).

``thermo`` 0.6.1 ships no van Laar or Margules modules, so the two classic
two-parameter models live here on the same :class:`GibbsExcess` interface the
thermo-library models use. Both are written in the energy form (parameters in
J/mol, temperature-independent):

- van Laar:  G^E = A12 A21 x1 x2 / (A12 x1 + A21 x2)
- Margules:  G^E = A12 x1 x2^2 + A21 x1^2 x2
- Wohl three-suffix (Scatchard-Hamer):
  G^E = x1 x2 (A12 q2^2 x2 + A21 q1^2 x1) / (q1 x1 + q2 x2)^2

giving ln gamma_1^inf = A12/(RT) and ln gamma_2^inf = A21/(RT). All GE
derivatives are analytic; the unit tests cross-check every one of them against
the base class's numerical differentiation (``gammas_numerical``,
``dGE_dxs_numerical``, ``d2GE_dxixjs_numerical``).

Both models are binary by construction: a pure component degenerates to
G^E = 0 and a support with more than two components raises, naming the model -
no silent extension to an unverified multicomponent form.
"""

from __future__ import annotations

from typing import Any

from thermo.activity import GibbsExcess


class BinaryOnlyModelError(ValueError):
    """A binary-only gE model was asked to evaluate a larger support."""


def _check_xs(model: str, xs: list[float]) -> None:
    if len(xs) > 2:
        raise BinaryOnlyModelError(
            f"{model} is a binary-only gE model (no verified multicomponent form); "
            f"got {len(xs)} components - use a local-composition model (NRTL, "
            "UNIQUAC, Wilson) or a UNIFAC variant for larger supports"
        )


class VanLaar(GibbsExcess):  # type: ignore[misc]  # thermo ships no stubs for GibbsExcess
    # thermo's GibbsExcessLiquid stamps itself 20000 + model_id; 5xx/6xx are
    # unclaimed in thermo 0.6.1 (NRTL=100, Wilson=200, UNIQUAC=300, RS=400).
    model_id = 500
    """van Laar gE model, energy form (A12, A21 in J/mol)."""

    __slots__ = ("A12", "A21", "T", "xs", "N", "vectorized")

    def __init__(self, *, xs: list[float], T: float = 298.15, A12: float, A21: float) -> None:
        _check_xs("van Laar", list(xs))
        self.A12 = float(A12)
        self.A21 = float(A21)
        self.T = T
        self.xs = list(xs)
        self.N = len(xs)
        self.vectorized = False

    def to_T_xs(self, T: float, xs: list[float]) -> VanLaar:
        return VanLaar(xs=list(xs), T=T, A12=self.A12, A21=self.A21)

    def GE(self) -> float:
        if self.N < 2:
            return 0.0
        x1, x2 = self.xs
        u = self.A12 * x1 + self.A21 * x2
        return self.A12 * self.A21 * x1 * x2 / u

    def dGE_dxs(self) -> list[float]:
        if self.N < 2:
            return [0.0] * self.N
        x1, x2 = self.xs
        a12, a21 = self.A12, self.A21
        u = a12 * x1 + a21 * x2
        return [a12 * a21**2 * x2**2 / u**2, a12**2 * a21 * x1**2 / u**2]

    def d2GE_dxixjs(self) -> list[list[float]]:
        if self.N < 2:
            return [[0.0] * self.N for _ in range(self.N)]
        x1, x2 = self.xs
        a12, a21 = self.A12, self.A21
        f = 2.0 * a12**2 * a21**2 / (a12 * x1 + a21 * x2) ** 3
        return [[-f * x2**2, f * x1 * x2], [f * x1 * x2, -f * x1**2]]

    def d3GE_dxixjxks(self) -> list[list[list[float]]]:
        if self.N < 2:
            return [[[0.0] * self.N for _ in range(self.N)] for _ in range(self.N)]
        x1, x2 = self.xs
        a12, a21 = self.A12, self.A21
        u = a12 * x1 + a21 * x2
        u4 = u**4
        g111 = 6.0 * a12**3 * a21**2 * x2**2 / u4
        g222 = 6.0 * a12**2 * a21**3 * x1**2 / u4
        g112 = (-4.0 * a12**2 * a21**2 * x2 * u + 6.0 * a12**2 * a21**3 * x2**2) / u4
        g122 = 2.0 * a12**2 * a21**2 * x1 * (a12 * x1 - 2.0 * a21 * x2) / u4
        return [[[g111, g112], [g112, g122]], [[g112, g122], [g122, g222]]]

    # energy-form parameters: G^E is T-independent, the entropic derivatives vanish
    def dGE_dT(self) -> float:
        return 0.0

    def d2GE_dT2(self) -> float:
        return 0.0

    def d3GE_dT3(self) -> float:
        return 0.0

    def d2GE_dTdxs(self) -> list[float]:
        return [0.0] * self.N

    def __repr__(self) -> str:
        return f"VanLaar(T={self.T!r}, xs={self.xs!r}, A12={self.A12!r}, A21={self.A21!r})"


class Margules(GibbsExcess):  # type: ignore[misc]  # thermo ships no stubs for GibbsExcess
    # See VanLaar.model_id.
    model_id = 600
    """Three-suffix (two-parameter) Margules gE model, energy form (A12, A21 in J/mol)."""

    __slots__ = ("A12", "A21", "T", "xs", "N", "vectorized")

    def __init__(self, *, xs: list[float], T: float = 298.15, A12: float, A21: float) -> None:
        _check_xs("Margules", list(xs))
        self.A12 = float(A12)
        self.A21 = float(A21)
        self.T = T
        self.xs = list(xs)
        self.N = len(xs)
        self.vectorized = False

    def to_T_xs(self, T: float, xs: list[float]) -> Margules:
        return Margules(xs=list(xs), T=T, A12=self.A12, A21=self.A21)

    def GE(self) -> float:
        if self.N < 2:
            return 0.0
        x1, x2 = self.xs
        return self.A12 * x1 * x2**2 + self.A21 * x1**2 * x2

    def dGE_dxs(self) -> list[float]:
        if self.N < 2:
            return [0.0] * self.N
        x1, x2 = self.xs
        a12, a21 = self.A12, self.A21
        return [a12 * x2**2 + 2.0 * a21 * x1 * x2, 2.0 * a12 * x1 * x2 + a21 * x1**2]

    def d2GE_dxixjs(self) -> list[list[float]]:
        if self.N < 2:
            return [[0.0] * self.N for _ in range(self.N)]
        x1, x2 = self.xs
        a12, a21 = self.A12, self.A21
        return [
            [2.0 * a21 * x2, 2.0 * a12 * x2 + 2.0 * a21 * x1],
            [2.0 * a12 * x2 + 2.0 * a21 * x1, 2.0 * a12 * x1],
        ]

    def d3GE_dxixjxks(self) -> list[list[list[float]]]:
        if self.N < 2:
            return [[[0.0] * self.N for _ in range(self.N)] for _ in range(self.N)]
        a12, a21 = self.A12, self.A21
        # constants: two 1-indices -> 2*A21, two 2-indices -> 2*A12
        return [
            [[0.0, 2.0 * a21], [2.0 * a21, 2.0 * a12]],
            [[2.0 * a21, 2.0 * a12], [2.0 * a12, 0.0]],
        ]

    def dGE_dT(self) -> float:
        return 0.0

    def d2GE_dT2(self) -> float:
        return 0.0

    def d3GE_dT3(self) -> float:
        return 0.0

    def d2GE_dTdxs(self) -> list[float]:
        return [0.0] * self.N

    def __repr__(self) -> str:
        return f"Margules(T={self.T!r}, xs={self.xs!r}, A12={self.A12!r}, A21={self.A21!r})"


class WohlThreeSuffix(GibbsExcess):  # type: ignore[misc]  # thermo ships no stubs for GibbsExcess
    # See VanLaar.model_id.
    model_id = 700
    """Wohl (1946) three-suffix binary gE model, energy form (A12, A21 in J/mol).

    The general form both classic two-parameter models truncate, with the effective
    volume fractions z_i = q_i x_i / (q1 x1 + q2 x2):

        G^E = (q1 x1 + q2 x2) z1 z2 (A12 z2 / q1 + A21 z1 / q2)

    ln gamma_1 = z2^2 [A + 2 z1 (B q1/q2 - A)] with A = A12/(RT), B = A21/(RT), and
    the same with the indices exchanged (Wohl, Trans. AIChE 42 (1946) 215; Prausnitz,
    Lichtenthaler & de Azevedo, Molecular Thermodynamics, 3rd ed., sec. 6.10).
    q1 = q2 is the three-suffix Margules equation, q1/q2 = A12/A21 is van Laar's; the
    catalogue row takes q_i = V_i, the Scatchard-Hamer (1935) choice, so the volume
    ratio carries the information neither special case has and the infinite-dilution
    limits stay exactly A12/(RT) and A21/(RT).
    """

    __slots__ = ("A12", "A21", "q1", "q2", "T", "xs", "N", "vectorized")

    def __init__(
        self, *, xs: list[float], T: float = 298.15, A12: float, A21: float, q1: float, q2: float
    ) -> None:
        _check_xs("Wohl three-suffix", list(xs))
        self.A12 = float(A12)
        self.A21 = float(A21)
        self.q1 = float(q1)
        self.q2 = float(q2)
        self.T = T
        self.xs = list(xs)
        self.N = len(xs)
        self.vectorized = False

    def to_T_xs(self, T: float, xs: list[float]) -> WohlThreeSuffix:
        return WohlThreeSuffix(xs=list(xs), T=T, A12=self.A12, A21=self.A21, q1=self.q1, q2=self.q2)

    def _terms(self) -> tuple[float, float, float]:
        """(a, b, s) of G^E = x1 x2 (a x2 + b x1) / s^2."""
        x1, x2 = self.xs
        return self.A12 * self.q2**2, self.A21 * self.q1**2, self.q1 * x1 + self.q2 * x2

    def GE(self) -> float:
        if self.N < 2:
            return 0.0
        x1, x2 = self.xs
        a, b, s = self._terms()
        return x1 * x2 * (a * x2 + b * x1) / s**2

    def dGE_dxs(self) -> list[float]:
        if self.N < 2:
            return [0.0] * self.N
        x1, x2 = self.xs
        a, b, s = self._terms()
        n = x1 * x2 * (a * x2 + b * x1)
        n_i = (a * x2**2 + 2.0 * b * x1 * x2, 2.0 * a * x1 * x2 + b * x1**2)
        q = (self.q1, self.q2)
        return [n_i[i] / s**2 - 2.0 * n * q[i] / s**3 for i in range(2)]

    def d2GE_dxixjs(self) -> list[list[float]]:
        if self.N < 2:
            return [[0.0] * self.N for _ in range(self.N)]
        x1, x2 = self.xs
        a, b, s = self._terms()
        n = x1 * x2 * (a * x2 + b * x1)
        n_i = (a * x2**2 + 2.0 * b * x1 * x2, 2.0 * a * x1 * x2 + b * x1**2)
        n_12 = 2.0 * a * x2 + 2.0 * b * x1
        n_ij = ((2.0 * b * x2, n_12), (n_12, 2.0 * a * x1))
        q = (self.q1, self.q2)
        return [
            [
                n_ij[i][j] / s**2
                - 2.0 * (n_i[i] * q[j] + n_i[j] * q[i]) / s**3
                + 6.0 * n * q[i] * q[j] / s**4
                for j in range(2)
            ]
            for i in range(2)
        ]

    def d3GE_dxixjxks(self) -> list[list[list[float]]]:
        if self.N < 2:
            return [[[0.0] * self.N for _ in range(self.N)] for _ in range(self.N)]
        x1, x2 = self.xs
        a, b, s = self._terms()
        n = x1 * x2 * (a * x2 + b * x1)
        n_i = (a * x2**2 + 2.0 * b * x1 * x2, 2.0 * a * x1 * x2 + b * x1**2)
        n_12 = 2.0 * a * x2 + 2.0 * b * x1
        n_ij = ((2.0 * b * x2, n_12), (n_12, 2.0 * a * x1))

        def n_ijk(i: int, j: int, k: int) -> float:
            ones = (i, j, k).count(0)
            return 2.0 * b if ones == 2 else 2.0 * a if ones == 1 else 0.0

        q = (self.q1, self.q2)
        return [
            [
                [
                    n_ijk(i, j, k) / s**2
                    - 2.0 * (n_ij[i][j] * q[k] + n_ij[i][k] * q[j] + n_ij[j][k] * q[i]) / s**3
                    + 6.0 * (n_i[i] * q[j] * q[k] + n_i[j] * q[i] * q[k] + n_i[k] * q[i] * q[j]) / s**4
                    - 24.0 * n * q[i] * q[j] * q[k] / s**5
                    for k in range(2)
                ]
                for j in range(2)
            ]
            for i in range(2)
        ]

    def dGE_dT(self) -> float:
        return 0.0

    def d2GE_dT2(self) -> float:
        return 0.0

    def d3GE_dT3(self) -> float:
        return 0.0

    def d2GE_dTdxs(self) -> list[float]:
        return [0.0] * self.N

    def __repr__(self) -> str:
        return (
            f"WohlThreeSuffix(T={self.T!r}, xs={self.xs!r}, A12={self.A12!r}, A21={self.A21!r}, "
            f"q1={self.q1!r}, q2={self.q2!r})"
        )


def gammas_from_ge(model: Any) -> list[float]:
    """Activity coefficients via the base class's exact GE-derivative identity.

    Test helper: pins the in-house models' analytic derivatives against the
    numerically differentiated route the base class uses for verification.
    """
    return list(GibbsExcess.gammas(model))
