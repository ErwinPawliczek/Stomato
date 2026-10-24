"""Lowering declarative logical nodes onto existing solver features (spec U-A step 4).

``adjust`` and ``recycle_block`` are canvas-side conveniences. Before the
solve they become the features the solver already has:

- ``adjust`` -> one P2-01 :class:`DesignSpec` (id ``DS-<tag>``), targeting
  ``target.{stream}.{variable}`` and manipulating
  ``manipulate.{unit}.params.{param}``;
- ``recycle_block`` -> the P2-03 flowsheet tear options: ``acceleration``
  (``none`` maps to ``direct``) and ``tolerance`` (-> ``rtol``).

Both nodes stay identity units in the graph (their adapters are pass-throughs),
so flowsheets without them take an unchanged fast path and byte-identical
solves. Declaring conflicting option values across blocks is refused, naming
both blocks. The registered solver entry (:meth:`SequentialModularWithSpecs.
solve`) calls :func:`lower_logical_nodes` once per solve; the function is
idempotent, so an already-lowered flowsheet passes through unharmed.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import Flowsheet
from ngdesign.contracts.flowsheet import SolverOptions
from ngdesign.contracts.specs import DesignSpec

__all__ = ["lower_logical_nodes"]

#: unit kind -> the lowering it carries
_LOGICAL_KINDS = ("adjust", "recycle_block")

#: acceleration vocabulary of the node; ``none`` is the user-facing name of the
#: solver's ``direct`` substitution
_ACCELERATION = {"none": "direct", "direct": "direct", "wegstein": "wegstein", "broyden": "broyden"}


def lower_logical_nodes(fs: Flowsheet) -> Flowsheet:
    """Return ``fs`` with adjust/recycle_block nodes expressed solver-natively."""
    if not any(u.kind in _LOGICAL_KINDS for u in fs.units):
        return fs

    specs = list(fs.design_specs)
    existing = {s.id for s in specs}
    options = fs.solver_options.model_copy()
    seen: dict[str, tuple[Any, str]] = {}
    for unit in fs.units:
        if unit.kind == "adjust":
            # idempotence: the registered entry lowers before the solve, and an
            # already-lowered flowsheet must not double-append its specs
            if f"DS-{unit.tag}" not in existing:
                specs.append(_design_spec(unit))
        elif unit.kind == "recycle_block":
            _apply_tear_options(unit, options, seen)
    return fs.model_copy(update={"design_specs": specs, "solver_options": options})


def _design_spec(unit: Any) -> DesignSpec:
    """One adjust node -> one DesignSpec (spec U-A step 4)."""
    params = unit.params or {}
    target = params.get("target") or {}
    manipulate = params.get("manipulate") or {}
    for name, keys in (
        ("target", ("stream", "variable", "value")),
        ("manipulate", ("unit", "param")),
    ):
        sub = target if name == "target" else manipulate
        missing = [k for k in keys if k not in sub]
        if missing:
            raise ValueError(
                f"adjust '{unit.tag}': {name} is missing {missing}; expected {list(keys)}"
            )
    bounds = params.get("bounds") or {}
    lower = float(bounds.get("lower", -1e30))
    upper = float(bounds.get("upper", 1e30))
    if lower >= upper:
        raise ValueError(f"adjust '{unit.tag}': bounds [{lower}, {upper}] are empty")
    return DesignSpec(
        id=f"DS-{unit.tag}",
        target=f"{target['stream']}.{target['variable']}",
        value=float(target["value"]),
        manipulated=f"{manipulate['unit']}.params.{manipulate['param']}",
        lower=lower,
        upper=upper,
    )


def _apply_tear_options(unit: Any, options: SolverOptions, seen: dict[str, tuple[Any, str]]) -> None:
    """Apply one recycle_block's tear options; refuse conflicts across blocks."""
    tag = unit.tag
    params = unit.params or {}
    declarations: dict[str, Any] = {}
    if "acceleration" in params:
        accel = str(params["acceleration"])
        if accel not in _ACCELERATION:
            raise ValueError(
                f"recycle_block '{tag}': acceleration must be one of "
                f"{sorted(set(_ACCELERATION))}, got {accel!r}"
            )
        declarations["tear_acceleration"] = _ACCELERATION[accel]
    if "tolerance" in params:
        tol = float(params["tolerance"])
        if tol <= 0.0:
            raise ValueError(f"recycle_block '{tag}': tolerance must be > 0, got {tol}")
        declarations["rtol"] = tol

    for option, value in declarations.items():
        if option in seen:
            other_value, other_tag = seen[option]
            if other_value != value:
                raise ValueError(
                    f"recycle_block '{tag}': {option}={value!r} conflicts with the "
                    f"options declared by recycle_block '{other_tag}'; per-block "
                    f"options are out of scope at R0"
                )
        else:
            seen[option] = (value, tag)
            setattr(options, option, value)
