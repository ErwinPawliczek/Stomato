"""Plugin registry with auto-discovery. LOCKED.

A plugin is any module under one of PLUGIN_PACKAGES that decorates a class:

    from ngdesign.registry import register

    @register("unit", "compressor")
    class Compressor: ...

Nothing else needs editing: discover() imports every module in those packages.
This is what keeps parallel agents from colliding on a shared list.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable
from typing import Any, TypeVar

KINDS = (
    "thermo",
    "unit",
    "sizer",
    "solver",
    "pid_builder",
    "pid_rule",
    "router",
    "iso_renderer",
    "diagram",
    "correlation",
)
PLUGIN_PACKAGES = (
    "ngdesign.thermo",
    "ngdesign.amine",  # reactive amine property packages (P1-04)
    "ngdesign.units",
    "ngdesign.sizing",
    "ngdesign.solver",
    "ngdesign.pid_rules",
    "ngdesign.piping",
    "ngdesign.render",
)

_REGISTRY: dict[str, dict[str, type]] = {k: {} for k in KINDS}
_discovered = False

T = TypeVar("T", bound=type)


def register(kind: str, name: str) -> Callable[[T], T]:
    if kind not in KINDS:
        raise ValueError(f"unknown plugin kind {kind!r}; allowed: {KINDS}")

    def deco(cls: T) -> T:
        existing = _REGISTRY[kind].get(name)
        if existing is not None and existing is not cls:
            raise ValueError(f"duplicate {kind} plugin {name!r}: {existing} vs {cls}")
        _REGISTRY[kind][name] = cls
        return cls

    return deco


def discover() -> None:
    """Import every module under PLUGIN_PACKAGES (idempotent), then the catalogue.

    Spec T-01: thermo property methods are data — after the decorator-based
    plugins import, ``ngdesign.thermo.catalogue.register_all`` registers one
    factory per row in ``data/thermo_models/*.yaml``. The import is dynamic on
    purpose: ``ngdesign.registry`` sits BELOW ``ngdesign.thermo`` in the layer
    contract (.importlinter), so a static import would be a lint failure and
    ignore_imports lines are not allowed. The hook is the one registry-side
    seam the T-01 spec grants.
    """
    global _discovered
    if _discovered:
        return
    for pkg_name in PLUGIN_PACKAGES:
        pkg = importlib.import_module(pkg_name)
        for mod in pkgutil.walk_packages(pkg.__path__, prefix=pkg_name + "."):
            importlib.import_module(mod.name)
    # The flag goes up before the catalogue hooks: the unit catalogue validates
    # its rows' sizer names against the registry while loading, which calls
    # available("sizer") -> discover(); a second full pass here would
    # re-register the thermo catalogue factories and fail on the duplicates.
    _discovered = True
    try:
        importlib.import_module("ngdesign.thermo.catalogue").register_all(_REGISTRY["thermo"])
        importlib.import_module("ngdesign.units.catalogue").register_all(_REGISTRY["unit"])
    except BaseException:
        _discovered = False
        raise


def get(kind: str, name: str) -> type:
    discover()
    try:
        return _REGISTRY[kind][name]
    except KeyError:
        raise KeyError(f"no {kind} plugin named {name!r}; have {sorted(_REGISTRY[kind])}") from None


def create(kind: str, name: str, *args: Any, **kwargs: Any) -> Any:
    return get(kind, name)(*args, **kwargs)


def available(kind: str) -> list[str]:
    discover()
    return sorted(_REGISTRY[kind])


def replace(kind: str, name: str, cls: type) -> None:
    """Point an existing registration at another class (spec U-00 dispatch hook).

    ``register`` stays duplicate-strict; ``replace`` is the one sanctioned
    overwrite. The unit catalogue's review-round-2 contract requires it:
    ``discover()`` imports the decorator-based plugins first, then replaces
    every implemented unit id with its per-row ``LevelDispatch`` — the same
    id, one entry, solve-time level resolution in front of the adapter.
    """
    if kind not in KINDS:
        raise ValueError(f"unknown plugin kind {kind!r}; allowed: {KINDS}")
    _REGISTRY[kind][name] = cls
