"""Read-only access to the reference tables in /data. LOCKED.
Plugins read reference data only through these functions, never by hard-coding values.

The open component registry (spec P1-02) resolves any component id to its physical
constants through :func:`component_record`: curated ``data/components.yaml`` entries
first, then the ``chemicals`` databank by CAS or name, then registered
pseudo-components (Tb + sg via Lee-Kesler / Riazi-Daubert). This module sits at the
bottom of the import layering, so it returns plain dicts; the typed ``Component`` /
``ComponentSet`` records and the ``resolve``/``resolve_set`` adapters live in
``ngdesign.contracts.components``.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import yaml
from chemicals.acentric import LK_omega
from chemicals.identifiers import CAS_from_any
from thermo import ChemicalConstantsPackage

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


@cache
def _curated_table() -> dict[str, dict[str, Any]]:
    """The curated slate from data/components.yaml: id, name, CAS, provenance notes."""
    raw = yaml.safe_load((DATA_DIR / "components.yaml").read_text())
    table: dict[str, dict[str, Any]] = raw["components"]
    return table


def components() -> dict[str, dict[str, Any]]:
    """Resolved constants of the curated slate, keyed by curated id (SI).

    Legacy yaml shape (``name/cas/mw/tc_K/pc_Pa/omega``) kept for every existing
    caller; the values now come from the databank by CAS (spec P1-02 removed the
    dead Tc/Pc/omega columns from the yaml). Provenance per property is included.
    """
    out: dict[str, dict[str, Any]] = {}
    for cid in _curated_table():
        record = component_record(cid)
        out[cid] = {
            "name": record["name"],
            "cas": record["cas"],
            "mw": record["mw"],
            "tc_K": record["Tc"],
            "pc_Pa": record["Pc"],
            "omega": record["omega"],
            "tb_K": record["Tb"],
            "sg": record["sg"],
            "kind": record["kind"],
            "provenance": record["provenance"],
        }
    return out


@cache
def pipe_classes() -> dict[str, dict[str, Any]]:
    raw = yaml.safe_load((DATA_DIR / "pipe_classes.yaml").read_text())
    table: dict[str, dict[str, Any]] = raw["classes"]
    return table


@cache
def pipe_schedules() -> list[dict[str, Any]]:
    """Rows: nps_in, schedule, od_mm, wall_mm, id_mm (ASME B36.10M/B36.19M)."""
    with (DATA_DIR / "pipe_schedules_b3610.csv").open() as f:
        return [
            {
                "nps_in": float(r["nps_in"]),
                "schedule": r["schedule"],
                "od_mm": float(r["od_mm"]),
                "wall_mm": float(r["wall_mm"]),
                "id_mm": float(r["id_mm"]),
            }
            for r in csv.DictReader(f)
        ]


def pipe(nps_in: float, schedule: str) -> dict[str, Any]:
    for r in pipe_schedules():
        if r["nps_in"] == nps_in and r["schedule"] == schedule:
            return r
    raise KeyError(f"no pipe NPS {nps_in} SCH {schedule}")


@cache
def flange_ratings() -> list[dict[str, Any]]:
    """Rows: material_group, class, temp_F, max_pressure_psig (ASME B16.5)."""
    with (DATA_DIR / "flanges_b165.csv").open() as f:
        return [
            {
                "material_group": r["material_group"],
                "class": int(r["class"]),
                "temp_F": float(r["temp_F"]),
                "max_pressure_psig": float(r["max_pressure_psig"]),
            }
            for r in csv.DictReader(f)
        ]


def golden(name: str) -> list[dict[str, Any]]:
    """Golden test cases from data/golden/<name>.yaml."""
    raw = yaml.safe_load((DATA_DIR / "golden" / f"{name}.yaml").read_text())
    cases: list[dict[str, Any]] = raw["cases"]
    return cases


# ----------------------------------------------------------- open component registry (spec P1-02)

#: Kesler, M.G. & Lee, B.I., "Improve Prediction of Enthalpy of Fractions",
#: Hydrocarbon Processing 55(3), 153-158 (1976).
KESLER_LEE_1976 = "Kesler & Lee 1976, Hydrocarbon Processing 55(3), 153"

#: Lee, B.I. & Kesler, M.G., "A Generalized Thermodynamic Correlation Based on
#: Three-Parameter Corresponding States", AIChE J. 21(3), 510-527 (1975); the
#: acentric-factor form is implemented in chemicals.acentric.LK_omega.
LEE_KESLER_1975 = "Lee-Kesler 1975 acentric-factor correlation (chemicals.acentric.LK_omega)"

#: Riazi, M.R. & Daubert, T.E., "Simplified Property Correlations",
#: Hydrocarbon Processing 59(3), 115-117 (1980).
RIAZI_DAUBERT_1980 = "Riazi & Daubert 1980, Hydrocarbon Processing 59(3)"


def _lee_kesler_tc_pc(Tb: float, sg: float) -> tuple[float, float]:
    """Kesler & Lee (1976) pseudocomponent Tc (K) and Pc (Pa) from Tb (K) and sg.

    Published form uses Tb in Rankine and Pc in psia; converted here so callers
    stay SI. Verified against n-heptane (Tc 539.0 K vs 540.2 K databank) and
    n-pentane (Tc 468.7 K vs 469.7 K databank) in-session.
    """
    tb_r = Tb * 1.8
    tc_r = 341.7 + 811.1 * sg + (0.4244 + 0.1174 * sg) * tb_r + (0.4669 - 3.2623 * sg) * 1e5 / tb_r
    ln_pc_psia = (
        8.3634
        - 0.0566 / sg
        - (0.24244 + 2.2898 / sg + 0.11857 / sg**2) * 1e-3 * tb_r
        + (1.4685 + 3.648 / sg + 0.47227 / sg**2) * 1e-7 * tb_r**2
        - (0.42019 + 1.6977 / sg**2) * 1e-10 * tb_r**3
    )
    return tc_r / 1.8, math.exp(ln_pc_psia) * 6894.757  # psia -> Pa (1 psi = 6894.757 Pa)


def _riazi_daubert_mw(Tb: float, sg: float) -> float:
    """Riazi & Daubert (1980) pseudocomponent molecular weight from Tb (K) and sg.

    MW = 4.5673e-5 * Tb(R)^2.1962 * sg^-1.0164 (Tb in Rankine in the published
    form). g/mol.
    """
    return float(4.5673e-5 * (Tb * 1.8) ** 2.1962 * sg**-1.0164)


@dataclass(frozen=True)
class PseudoDefinition:
    """A user-registered pseudo-component: id plus the Tb + sg characterization pair."""

    id: str
    name: str
    Tb: float  # K
    sg: float  # specific gravity, water = 1


#: User-registered pseudo-components, by id. Registration is explicit user intent
#: (flowsheet authoring, tests, a future project store); the curated slate and the
#: databank always take precedence in the resolution order.
_PSEUDOS: dict[str, PseudoDefinition] = {}


def register_pseudo(id: str, name: str, Tb: float, sg: float) -> None:
    """Register a user pseudo-component defined by its normal boiling point and gravity.

    Re-registering the same definition is a no-op; a conflicting definition for a
    known id raises. The curated slate is reserved and cannot be shadowed (the
    resolution order resolves curated ids first anyway).
    """
    if Tb <= 0.0 or sg <= 0.0:
        raise ValueError(f"pseudo-component {id!r} needs positive Tb and sg")
    if id in _curated_table():
        raise ValueError(f"component id {id!r} is reserved by the curated slate")
    definition = PseudoDefinition(id=id, name=name, Tb=Tb, sg=sg)
    known = _PSEUDOS.get(id)
    if known is not None and known != definition:
        raise ValueError(f"pseudo-component {id!r} is already registered with a different definition")
    _PSEUDOS[id] = definition


@cache
def _databank_record(query: str) -> dict[str, Any] | None:
    """One ``chemicals`` databank record by CAS or name; None when the databank has no hit.

    ``CAS_from_any`` is the databank's universal resolver: dashed CAS numbers
    (the curated yaml's format), stripped CAS digits, and chemical names. The
    constants come from the same ``ChemicalConstantsPackage.from_IDs`` path the
    EOS uses, so a databank-resolved id and its flasher constants can never
    drift apart. It raises for absent matches - a normal outcome in a resolution
    chain, so that maps to None (the next source gets its turn).
    """
    try:
        cas = str(CAS_from_any(query))
    except Exception:
        return None
    constants, _ = ChemicalConstantsPackage.from_IDs([cas])
    provenance = {
        "name": "chemicals",
        "cas": "chemicals",
        "mw": "chemicals",
        "Tc": "chemicals",
        "Pc": "chemicals",
        "omega": "chemicals",
        "Tb": "chemicals",
    }
    return {
        "id": query,
        "name": str(constants.names[0]),
        "cas": cas,
        "formula": str(constants.formulas[0]) if constants.formulas[0] else None,
        "mw": float(constants.MWs[0]),
        "Tc": float(constants.Tcs[0]),
        "Pc": float(constants.Pcs[0]),
        "omega": float(constants.omegas[0]),
        "Tb": float(constants.Tbs[0]),
        "sg": None,
        "kind": "databank",
        "provenance": provenance,
    }


@cache
def _curated_record(cid: str) -> dict[str, Any]:
    """Resolved record for one curated id: yaml identity, databank properties by CAS."""
    entry = _curated_table()[cid]
    cas = str(entry["cas"])
    databank = _databank_record(cas)
    if databank is None:  # a curated entry whose CAS the databank does not know
        raise ValueError(f"curated component {cid!r}: CAS {cas} not found in the chemicals databank")
    provenance: dict[str, str] = {"name": "curated", "cas": "curated"}
    if "provenance" in entry:
        provenance.update({str(k): str(v) for k, v in entry["provenance"].items()})
    for prop in ("mw", "Tc", "Pc", "omega", "Tb"):
        provenance.setdefault(prop, "chemicals (by curated CAS)")
    return {
        "id": cid,
        "name": str(entry["name"]),
        "cas": cas,
        "formula": databank["formula"],
        "mw": databank["mw"],
        "Tc": databank["Tc"],
        "Pc": databank["Pc"],
        "omega": databank["omega"],
        "Tb": databank["Tb"],
        "sg": databank["sg"],
        "kind": "curated",
        "provenance": provenance,
    }


def _pseudo_record(definition: PseudoDefinition) -> dict[str, Any]:
    """Derived record for a registered pseudo: Lee-Kesler Tc/Pc/omega, Riazi-Daubert MW."""
    tc, pc = _lee_kesler_tc_pc(definition.Tb, definition.sg)
    omega = float(LK_omega(definition.Tb, tc, pc))
    mw = _riazi_daubert_mw(definition.Tb, definition.sg)
    return {
        "id": definition.id,
        "name": definition.name,
        "cas": None,
        "formula": None,
        "mw": mw,
        "Tc": tc,
        "Pc": pc,
        "omega": omega,
        "Tb": definition.Tb,
        "sg": definition.sg,
        "kind": "pseudo",
        "provenance": {
            "Tc": KESLER_LEE_1976,
            "Pc": KESLER_LEE_1976,
            "omega": LEE_KESLER_1975,
            "mw": RIAZI_DAUBERT_1980,
            "Tb": "user",
            "sg": "user",
        },
    }


def component_record(id_or_cas_or_name: str) -> dict[str, Any]:
    """Resolve one component key to its constant record, in the spec P1-02 order:

    1. curated ``data/components.yaml`` entry (by id; properties filled from the
       databank by CAS, with the yaml's deliberate overrides and notes kept),
    2. the ``chemicals`` databank (search_chemical handles CAS numbers and names),
    3. a registered pseudo-component (by id; Tc/Pc/omega/MW derived and
       provenance-graded).

    Raises ValueError naming the key when no source resolves it.
    """
    if id_or_cas_or_name in _curated_table():
        return _curated_record(id_or_cas_or_name)
    databank = _databank_record(id_or_cas_or_name)
    if databank is not None:
        return databank
    pseudo = _PSEUDOS.get(id_or_cas_or_name)
    if pseudo is not None:
        return _pseudo_record(pseudo)
    raise ValueError(
        f"unknown component {id_or_cas_or_name!r}: not a curated id, not in the "
        "chemicals databank, and not a registered pseudo-component"
    )
