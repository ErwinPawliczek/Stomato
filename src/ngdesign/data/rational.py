"""Exact linear algebra over the rationals, shared by stoichiometry and equilibrium."""

from __future__ import annotations

from fractions import Fraction


def rref(matrix: list[list[Fraction]], n_columns: int) -> tuple[list[list[Fraction]], list[int]]:
    """Reduced row echelon form over Q, with the pivot columns."""
    rows = [list(row) for row in matrix]
    pivots: list[int] = []
    row_index = 0
    for column in range(n_columns):
        pivot = next((r for r in range(row_index, len(rows)) if rows[r][column] != 0), None)
        if pivot is None:
            continue
        rows[row_index], rows[pivot] = rows[pivot], rows[row_index]
        head = rows[row_index][column]
        rows[row_index] = [value / head for value in rows[row_index]]
        for r in range(len(rows)):
            if r != row_index and rows[r][column] != 0:
                factor = rows[r][column]
                rows[r] = [a - factor * b for a, b in zip(rows[r], rows[row_index], strict=True)]
        pivots.append(column)
        row_index += 1
        if row_index == len(rows):
            break
    return rows, pivots
