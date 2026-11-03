"""Report Thermo-protocol calls to the active recorder (docs/provenance.md section 5).

A property package opts in by inheriting :class:`TracedThermo`: every protocol
method a class defines is wrapped once, at class creation. The wrapper is a
pass-through when tracing is off (one ``ContextVar.get``) and when the call is
nested inside another traced thermo call (only the outermost call is a node:
a PH flash's inner PT flashes are its own business).
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from typing import Any

from ngdesign.provenance.recorder import _ACTIVE

PROTOCOL_METHODS: tuple[str, ...] = (
    "flash_pt",
    "flash_ph",
    "flash_ps",
    "flash_tvf",
    "flash_pvf",
    "bubble_point",
    "dew_point",
    "k_values",
    "phase_props",
    "derivatives",
    "pure_psat",
)

_get = _ACTIVE.get


def traced(name: str, fn: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap one protocol method so the active recorder sees its outermost calls."""
    if getattr(fn, "__provenance_traced__", False):
        return fn
    names = [p for p in inspect.signature(fn).parameters][1:]

    @functools.wraps(fn)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        rec = _get()
        if rec is None or rec.in_thermo:
            return fn(self, *args, **kwargs)
        rec.in_thermo = True
        try:
            result = fn(self, *args, **kwargs)
        finally:
            rec.in_thermo = False
        bound = dict(zip(names, args, strict=False))
        bound.update(kwargs)
        rec.thermo_call(self, name, bound, result)
        return result

    wrapper.__provenance_traced__ = True  # type: ignore[attr-defined]
    return wrapper


def wrap_class(cls: type) -> None:
    """Wrap the protocol methods ``cls`` itself defines."""
    for name in PROTOCOL_METHODS:
        fn = cls.__dict__.get(name)
        if fn is not None and callable(fn):
            setattr(cls, name, traced(name, fn))


def note_convergence(info: Any) -> None:
    """Called by flash kernels with the converged flash's iteration record."""
    rec = _get()
    if rec is not None and isinstance(info, dict):
        rec.note_convergence(info)


class TracedThermo:
    """Base class: subclasses' protocol methods report to the active recorder."""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        wrap_class(cls)

    def trace_model(self) -> str | None:
        """Method-catalogue key of this package's model (None = unknown)."""
        return None
