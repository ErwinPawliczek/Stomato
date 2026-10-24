"""Assay slates and refinery stream properties shared by the refining units (spec U-H1).

``assay_slate`` loads a stored crude assay from ``data/assays/<id>.yaml``, runs it
through the A-01 assay cutter (:func:`ngdesign.data.assay.cut`) and hands the unit
adapters the pseudo-component definitions plus the slate's mole fractions. Results
are cached per ``(assay_id, scheme)`` so repeated unit solves do not re-cut the
assay.

Refinery ``info`` quantities use two conventions, both documented per adapter:

- Reference (standard) liquid volume, from component data bank ``sg`` -- the basis
  for cut-point volumes, BS&W and blend indices.  ``sg`` is specific gravity
  60 degF/60 degF, so the mass-to-volume constant is the density of water at
  15.6 degC, 999.0 kg/m3 (standard tables; it cancels in every asserted ratio,
  which is why the exact third digit is immaterial here).
- API gravity, ``141.5/sg - 131.5`` (standard definition).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from ngdesign.contracts.assay import Assay
from ngdesign.contracts.stream import StreamState
from ngdesign.data import PseudoDefinition, component_record, register_pseudo
from ngdesign.data.assay import CutScheme, CutSlate, cut

#: Directory holding the stored crude assays (one ``<id>.yaml`` per assay).
ASSAYS_DIR = Path(__file__).resolve().parents[4] / "data" / "assays"

#: Water density at 15.6 degC (60 degF), kg/m3 -- the reference for ``sg``.
WATER_60F_KG_M3 = 999.0

_cache: dict[tuple[str, CutScheme | None], CutSlate] = {}


def load_assay(assay_id: str) -> Assay:
    """Load and validate ``data/assays/<assay_id>.yaml`` as an ``Assay``."""
    path = ASSAYS_DIR / f"{assay_id}.yaml"
    if not path.is_file():
        raise ValueError(f"assay {assay_id!r}: no assay file at {path}")
    with open(path, encoding="utf-8") as stream:
        data = yaml.safe_load(stream)
    if not isinstance(data, dict):
        raise ValueError(f"assay {assay_id!r}: {path} is not a mapping")
    return Assay.model_validate(data)


def cut_assay(assay_id: str, scheme: CutScheme | None = None) -> CutSlate:
    """Cut the stored assay through A-01 (cached per assay id and scheme)."""
    key = (assay_id, scheme)
    if key not in _cache:
        _cache[key] = cut(load_assay(assay_id), scheme)
    return _cache[key]


def assay_slate(
    assay_id: str, scheme: CutScheme | None = None
) -> tuple[tuple[PseudoDefinition, ...], dict[str, float]]:
    """The A-01 pseudo definitions and mole fractions of the assay's cut slate."""
    slate = cut_assay(assay_id, scheme)
    return slate.pseudos, dict(slate.mole)


def register_slate(assay_id: str, scheme: CutScheme | None = None) -> None:
    """Register the slate's pseudos through the module-level ``register_pseudo``.

    Idempotent: re-registering the same definition is a no-op in
    ``register_pseudo``, so ``example_case`` may call this on every solve.
    """
    for pseudo in cut_assay(assay_id, scheme).pseudos:
        register_pseudo(pseudo.id, pseudo.name, pseudo.Tb, pseudo.sg)


def api_gravity(sg: float) -> float:
    """API gravity from specific gravity 60/60 (standard definition)."""
    return 141.5 / sg - 131.5


def reference_volume(state: StreamState) -> float:
    """Reference liquid volume of ``state`` in m3/s (component ``sg`` basis, additive)."""
    volume = 0.0
    for cid, x in state.composition.items():
        record = component_record(cid)
        mass_kg_s = x * state.molar_flow * float(record["mw"]) / 1000.0
        volume += mass_kg_s / (float(record["sg"]) * WATER_60F_KG_M3)
    return volume


def component_volume(state: StreamState, cid: str) -> float:
    """Reference volume of one component in ``state`` (m3/s)."""
    record = component_record(cid)
    mass_kg_s = state.composition.get(cid, 0.0) * state.molar_flow * float(record["mw"]) / 1000.0
    return mass_kg_s / (float(record["sg"]) * WATER_60F_KG_M3)
