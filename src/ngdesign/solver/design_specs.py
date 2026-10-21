"""Flowsheet-level design specs: an outer loop around the solver (spec P2-01).

The registered ``sequential_modular`` solver: when the flowsheet carries no
design specs it delegates to the bare sequential-modular solve unchanged; with
specs it wraps the inner solve in an outer loop that manipulates writable
addresses until the targets are met.

Method (Biegler, Grossmann & Westerberg, *Systematic Methods of Chemical Process
Design*, ch. 8 - design specifications):

- one spec: a bounded secant on the manipulated variable, bracketed from the
  spec's own ``lower``/``upper``; once the bracket straddles the root, Brent's
  method (Brent, *Algorithms for Minimization without Derivatives*, 1973;
  the ``zbrent`` form in Numerical Recipes) takes over;
- several specs: a bounded Broyden on the vector of manipulated variables
  (Broyden, "A class of methods for solving nonlinear simultaneous equations",
  Mathematics of Computation 19, 1965), the Jacobian seeded by one-sided finite
  differences with a step of 1 % of each variable's range.

Every outer iteration runs one inner solve, warm-started from the previous
solve's tear vectors (``SequentialModular.solve(..., warm_start=...)``): warm
starts are the point, since without them each outer iteration re-converges every
recycle from the global mean. A failed inner solve (``status="failed"``, spec
P2-02) aborts the loop with the partial result and ``converged=False`` on every
spec. A target the bounds cannot reach ends ``converged=False`` with the closest
value any iteration achieved and both bracket ends in the result history.
"""

from __future__ import annotations

import numpy as np

from ngdesign.contracts import Flowsheet, SolvedFlowsheet
from ngdesign.contracts.components import resolve_set
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.specs import DesignSpec, DesignSpecResult
from ngdesign.registry import register
from ngdesign.solver.sequential_modular import SequentialModular, _tear_vector
from ngdesign.variables import assign, resolve

__all__ = ["SequentialModularWithSpecs", "solve_with_specs"]


def solve_with_specs(fs: Flowsheet, thermo: Thermo, inner: SequentialModular) -> SolvedFlowsheet:
    """Solve ``fs`` driving every entry of ``fs.design_specs`` to its target.

    ``inner`` is the bare sequential-modular solver; it runs once per outer
    iteration, warm-started from the previous solve's tear vectors. Returns the
    last inner solve with ``design_spec_results`` filled (one per spec, in
    order). Raises nothing for a non-converging spec: the result reports it.
    """
    return _Outer(fs, thermo, inner).solve()


class _Outer:
    """The design-spec outer loop state: warm start, histories, last result."""

    def __init__(self, fs: Flowsheet, thermo: Thermo, inner: SequentialModular) -> None:
        self.fs = fs
        self.thermo = thermo
        self.inner = inner
        self.specs = list(fs.design_specs)
        self.components = tuple(resolve_set(fs.components).ids)
        self.warm: dict[str, list[float]] | None = None
        self.last: SolvedFlowsheet | None = None
        #: one (manipulated, achieved) pair per successful inner solve, per spec
        self.histories: list[list[tuple[float, float]]] = [[] for _ in self.specs]

    # ------------------------------------------------------------------ plumbing

    def evaluate(self, u: list[float]) -> list[float] | None:
        """One inner solve at manipulated values ``u``; achieved target values.

        ``None`` when the inner solve failed (spec P2-02 ``status="failed"``) -
        the partial result is still recorded, the loop aborts on it. Each
        successful solve is recorded in every spec's history and seeds the next
        warm start.
        """
        fs_i = self.fs
        for spec, val in zip(self.specs, u, strict=True):
            fs_i = assign(fs_i, spec.manipulated, val)
        solved = self.inner.solve(fs_i, self.thermo, warm_start=self.warm)
        self.warm = {sid: _tear_vector(state, self.components) for sid, state in solved.streams.items()}
        self.last = solved
        if solved.status == "failed":
            return None
        achieved: list[float] = []
        for spec in self.specs:
            try:
                achieved.append(resolve(spec.target, solved))
            except ValueError:
                achieved.append(float("nan"))
        for i, val in enumerate(u):
            self.histories[i].append((val, achieved[i]))
        return achieved

    def _met(self, spec: DesignSpec, achieved: float) -> bool:
        """Convergence: ``tolerance`` is relative on the target value."""
        return abs(achieved - spec.value) <= spec.tolerance * abs(spec.value)

    def _assemble(self, flags: list[bool]) -> SolvedFlowsheet:
        results: list[DesignSpecResult] = []
        for i, spec in enumerate(self.specs):
            hist = self.histories[i]
            if not hist:
                results.append(
                    DesignSpecResult(
                        id=spec.id,
                        achieved=float("nan"),
                        manipulated_value=float("nan"),
                        iterations=0,
                        converged=False,
                        history=[],
                    )
                )
                continue
            u_best, a_best = hist[-1] if flags[i] else min(hist, key=lambda p: abs(p[1] - spec.value))
            results.append(
                DesignSpecResult(
                    id=spec.id,
                    achieved=a_best,
                    manipulated_value=u_best,
                    iterations=len(hist),
                    converged=flags[i],
                    history=list(hist),
                )
            )
        solved = self.last
        if solved is None:  # unreachable: every path runs at least one inner solve
            raise RuntimeError("design-spec loop produced no inner solve")
        return solved.model_copy(update={"design_spec_results": results})

    def solve(self) -> SolvedFlowsheet:
        flags = [False] * len(self.specs)
        if len(self.specs) == 1:
            self._single(self.specs[0], flags)
        else:
            self._multi(flags)
        return self._assemble(flags)

    # ------------------------------------------------------------- one spec

    def _single(self, spec: DesignSpec, flags: list[bool]) -> None:
        """Bounded secant with a bisection safeguard; Brent once bracketed."""
        lo, hi = spec.lower, spec.upper
        a_lo = self.evaluate([lo])
        if a_lo is None:
            return
        a_hi = self.evaluate([hi])
        if a_hi is None:
            return
        if self._met(spec, a_lo[0]) or self._met(spec, a_hi[0]):
            flags[0] = True
            return
        g_lo, g_hi = a_lo[0] - spec.value, a_hi[0] - spec.value
        budget = spec.max_iterations - len(self.histories[0])
        if g_lo * g_hi < 0.0:
            self._brent(spec, lo, hi, g_lo, g_hi, budget, flags)
        else:
            self._secant(spec, lo, hi, lo, g_lo, hi, g_hi, budget, flags)

    def _brent(
        self,
        spec: DesignSpec,
        xa: float,
        xb: float,
        fa: float,
        fb: float,
        budget: int,
        flags: list[bool],
    ) -> None:
        """Brent's method on a straddling bracket (Numerical Recipes ``zbrent``)."""
        eps = 1e-12
        a, b, f_a, f_b = xa, xb, fa, fb
        c, f_c = a, f_a
        d = e = b - a
        for _ in range(max(budget, 0)):
            if self._met(spec, f_b + spec.value):
                flags[0] = True
                return
            if (f_b > 0.0) == (f_c > 0.0):
                c, f_c = a, f_a
                d = e = b - a
            if abs(f_c) < abs(f_b):
                a, b, c = b, c, b
                f_a, f_b, f_c = f_b, f_c, f_b
            tol_u = 2.0 * eps * abs(b) + 0.5 * eps
            xm = 0.5 * (c - b)
            if abs(xm) <= tol_u:
                return  # u converged but the target not met to tolerance
            if abs(e) >= tol_u and abs(f_a) > abs(f_b):
                s = f_b / f_a
                if a == c:
                    p, q = 2.0 * s * xm, 1.0 - s
                else:
                    q, r = f_a / f_c, f_b / f_c
                    p = s * (2.0 * xm * q * (q - r) - (b - a) * (r - 1.0))
                    q = (q - 1.0) * (r - 1.0) * (s - 1.0)
                if p > 0.0:
                    q = -q
                p = abs(p)
                if 2.0 * p < min(3.0 * xm * q - abs(tol_u * q), abs(e * q)):
                    e = d
                    d = p / q
                else:
                    d = e = xm
            else:
                d = e = xm
            a, f_a = b, f_b
            b = b + d if abs(d) > tol_u else b + (tol_u if xm > 0.0 else -tol_u)
            g = self.evaluate([b])
            if g is None:
                return
            f_b = g[0] - spec.value

    def _secant(
        self,
        spec: DesignSpec,
        lo: float,
        hi: float,
        u1: float,
        g1: float,
        u2: float,
        g2: float,
        budget: int,
        flags: list[bool],
    ) -> None:
        """Bounded secant with a bisection safeguard for an unbracketed target."""
        for _ in range(max(budget, 0)):
            denom = g2 - g1
            u_new = 0.5 * (u1 + u2) if denom == 0.0 else u2 - g2 * (u2 - u1) / denom
            if not lo <= u_new <= hi:
                u_new = min(max(u_new, lo), hi)
            if abs(u_new - u2) <= 1e-9 * max(abs(u2), 1.0) or u_new in (u1, u2):
                u_new = 0.5 * (u1 + u2)
                if abs(u_new - u2) <= 1e-9 * max(abs(u2), 1.0):
                    return  # interval collapsed: the target is not inside the bounds
            g = self.evaluate([u_new])
            if g is None:
                return
            g_new = g[0] - spec.value
            if self._met(spec, g_new + spec.value):
                flags[0] = True
                return
            u1, g1, u2, g2 = u2, g2, u_new, g_new

    # ----------------------------------------------------------- several specs

    def _multi(self, flags: list[bool]) -> None:
        """Bounded Broyden on the manipulated vector; Jacobian from one-sided FD."""
        m = len(self.specs)
        lowers = [s.lower for s in self.specs]
        uppers = [s.upper for s in self.specs]
        targets = [s.value for s in self.specs]
        x = [_initial_value(self.fs, spec) for spec in self.specs]
        f = self.evaluate(x)
        if f is None:
            return
        jac = np.zeros((m, m), dtype=np.float64)
        for i in range(m):
            h = 0.01 * (uppers[i] - lowers[i])
            probe = list(x)
            probe[i] = min(probe[i] + h, uppers[i])
            if probe[i] == x[i]:
                probe[i] = max(probe[i] - h, lowers[i])
            step = probe[i] - x[i]
            f_probe = self.evaluate(probe)
            if f_probe is None or step == 0.0:
                return
            jac[:, i] = (np.asarray(f_probe) - np.asarray(f)) / step
        for _ in range(self.specs[0].max_iterations - len(self.histories[0])):
            if all(self._met(s, f[i]) for i, s in enumerate(self.specs)):
                for i in range(m):
                    flags[i] = True
                return
            try:
                du = -np.linalg.solve(jac, np.asarray(f) - np.asarray(targets))
            except np.linalg.LinAlgError:
                return  # singular Jacobian: cannot continue deterministically
            u_new = [min(max(x[j] + float(du[j]), lowers[j]), uppers[j]) for j in range(m)]
            if all(abs(u_new[j] - x[j]) <= 1e-12 * max(abs(x[j]), 1.0) for j in range(m)):
                return  # step collapsed inside the bounds: not reachable
            f_new = self.evaluate(u_new)
            if f_new is None:
                return
            du_eff = np.asarray(u_new) - np.asarray(x)
            denom = float(du_eff @ du_eff)
            if denom > 0.0:
                resid = np.asarray(f_new) - np.asarray(f) - jac @ du_eff
                jac = jac + np.outer(resid, du_eff) / denom
            x, f = u_new, f_new


def _initial_value(fs: Flowsheet, spec: DesignSpec) -> float:
    """The manipulated variable's value as built, clamped into the bounds.

    Falls back to the range midpoint when the address does not name a value the
    unsolved flowsheet carries (a params key the unit does not set yet).
    """
    head, *rest = spec.manipulated.split(".")
    mid = 0.5 * (spec.lower + spec.upper)
    value: float | None = None
    for unit in fs.units:
        if unit.tag == head and len(rest) == 2 and rest[0] == "params":
            raw = unit.params.get(rest[1])
            value = float(raw) if isinstance(raw, (int, float)) else None
    if head in {s.id for s in fs.streams}:
        feed = next((s.feed for s in fs.streams if s.id == head), None)
        if feed is not None and len(rest) >= 2 and rest[0] == "feed":
            if rest[1] == "composition" and len(rest) == 3:
                value = feed.composition.get(rest[2])
            elif rest[1] != "composition":
                value = float(getattr(feed, rest[1]))
    if value is None:
        return mid
    return min(max(value, spec.lower), spec.upper)


@register("solver", "sequential_modular")
class SequentialModularWithSpecs:
    """Solver plugin: the sequential-modular solve wrapped in design-spec loops.

    One ``sequential_modular`` name (spec P2-01): with ``fs.design_specs`` empty
    this is exactly the bare :class:`SequentialModular` solve (byte-identical);
    with specs it is the outer loop of :func:`solve_with_specs`. The inner class
    stays importable for a plain solve or a warm-started re-solve.
    """

    def solve(
        self, fs: Flowsheet, thermo: Thermo, warm_start: dict[str, list[float]] | None = None
    ) -> SolvedFlowsheet:
        inner = SequentialModular()
        if not fs.design_specs:
            return inner.solve(fs, thermo, warm_start)
        return solve_with_specs(fs, thermo, inner)
