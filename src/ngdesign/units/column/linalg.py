"""Linear algebra for the column solvers (spec P1-03).

Moved unchanged from the former ``units/column.py`` god-file: the Thomas
algorithm for the tridiagonal M-equation systems and Gaussian elimination with
partial pivoting for the Newton systems.
"""

from __future__ import annotations

from .spec import ColumnConvergenceError


def _thomas(sub: list[float], diag: list[float], up: list[float], rhs: list[float]) -> list[float]:
    """Thomas algorithm for the tridiagonal system sub*x + diag*x + up*x = rhs.

    The M-equation matrix is diagonally dominant here (|diag| = L + V*K dominates
    its neighbours), so no pivoting is needed; a vanishing pivot is a convergence
    failure, not a case for a silent fix.
    """
    n = len(diag)
    if abs(diag[0]) < 1e-300:
        raise ColumnConvergenceError("singular tridiagonal system in stage balances")
    if n == 1:
        return [rhs[0] / diag[0]]
    cp = [0.0] * n
    dp = [0.0] * n
    cp[0] = up[0] / diag[0]
    dp[0] = rhs[0] / diag[0]
    for j in range(1, n):
        m = diag[j] - sub[j] * cp[j - 1]
        if abs(m) < 1e-300:
            raise ColumnConvergenceError("singular tridiagonal system in stage balances")
        cp[j] = up[j] / m if j < n - 1 else 0.0
        dp[j] = (rhs[j] - sub[j] * dp[j - 1]) / m
    out = [0.0] * n
    out[n - 1] = dp[n - 1]
    for j in range(n - 2, -1, -1):
        out[j] = dp[j] - cp[j] * out[j + 1]
    return out


def _gauss(matrix: list[list[float]], rhs: list[float]) -> list[float]:
    """Solve a dense square linear system by Gaussian elimination with partial pivoting."""
    n = len(rhs)
    a = [row[:] + [rhs[i]] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot_row = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[pivot_row][col]) < 1e-300:
            raise ColumnConvergenceError("singular Newton system in column solver")
        a[col], a[pivot_row] = a[pivot_row], a[col]
        pivot = a[col][col]
        for r in range(col + 1, n):
            factor = a[r][col] / pivot
            if factor == 0.0:
                continue
            for c in range(col, n + 1):
                a[r][c] -= factor * a[col][c]
    out = [0.0] * n
    for r in range(n - 1, -1, -1):
        acc = a[r][n] - sum(a[r][c] * out[c] for c in range(r + 1, n))
        out[r] = acc / a[r][r]
    return out
