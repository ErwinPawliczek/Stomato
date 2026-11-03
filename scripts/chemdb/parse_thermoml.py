"""Read ideal-gas Cp(T) of pure compounds from the NIST ThermoML archive.

Archive: ThermoML/Data Archive, NIST, doi:10.18434/mds2-2422 (ThermoML.v2020-09-30.tgz,
NIST open licence): data that NIST/TRC extracted from articles in J. Chem. Eng. Data,
J. Chem. Thermodyn., Fluid Phase Equilib., Thermochim. Acta and Int. J. Thermophys.
ThermoML is the IUPAC XML standard (Frenkel et al., Pure Appl. Chem. 78, 2006, 541-612).

Kept: a ``PureOrMixtureData`` block with one component whose property is "Molar heat
capacity at constant pressure, J/K/mol" in the phase "Ideal gas", one point per
temperature. Points whose stated method is a prediction are refused: the database
holds stated values only. The archive is read in place (no extraction).
"""

from __future__ import annotations

import tarfile
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path
from typing import Any

_NS = "{http://www.iupac.org/namespaces/ThermoML}"
_CP = "Molar heat capacity at constant pressure, J/K/mol"
_IDEAL_GAS = "Ideal gas"


def _text(element: ET.Element | None, path: str) -> str:
    found = element.find(path) if element is not None else None
    return found.text.strip() if found is not None and found.text else ""


def _first(element: ET.Element, tags: tuple[str, ...]) -> str:
    for node in element.iter():
        if node.tag in tags and node.text:
            return node.text.strip()
    return ""


def _citation(root: ET.Element) -> dict[str, str]:
    cit = root.find(_NS + "Citation")
    authors = [a.text.strip() for a in (cit.findall(_NS + "sAuthor") if cit is not None else []) if a.text]
    first = authors[0].split("[")[0].strip() if authors else ""
    return {
        "doi": _text(cit, _NS + "sDOI"),
        "year": _text(cit, _NS + "yrPubYr"),
        "first_author": first + (" et al." if len(authors) > 1 else ""),
    }


def parse_ideal_gas_cp(document: bytes) -> list[dict[str, Any]]:
    """Ideal-gas Cp points of one ThermoML document: InChIKey, T (K), Cp (J/(mol K))."""
    if _IDEAL_GAS.encode() not in document:
        return []
    root = ET.fromstring(document)
    citation = _citation(root)
    keys: dict[str, tuple[str, str]] = {}
    for compound in root.findall(_NS + "Compound"):
        number = _text(compound, f"{_NS}RegNum/{_NS}nOrgNum")
        keys[number] = (_text(compound, _NS + "sStandardInChIKey"), _text(compound, _NS + "sFormulaMolec"))
    points: list[dict[str, Any]] = []
    for block in root.findall(_NS + "PureOrMixtureData"):
        components = block.findall(_NS + "Component")
        if len(components) != 1:
            continue
        inchikey, formula = keys.get(_text(components[0], f"{_NS}RegNum/{_NS}nOrgNum"), ("", ""))
        wanted: dict[str, str] = {}
        for prop in block.findall(_NS + "Property"):
            name = _first(prop, (_NS + "ePropName",))
            phase = _text(prop, f"{_NS}PropPhaseID/{_NS}ePropPhase")
            method = _first(prop, (_NS + "eMethodName", _NS + "sMethodName"))
            if name == _CP and phase == _IDEAL_GAS and "predict" not in method.lower():
                wanted[_text(prop, _NS + "nPropNumber")] = method
        if not wanted or not inchikey:
            continue
        temperature_vars = {
            _text(var, _NS + "nVarNumber")
            for var in block.findall(_NS + "Variable")
            if _first(var, (_NS + "eTemperature",)).startswith("Temperature, K")
        }
        for values in block.findall(_NS + "NumValues"):
            T = next(
                (
                    float(_text(v, _NS + "nVarValue"))
                    for v in values.findall(_NS + "VariableValue")
                    if _text(v, _NS + "nVarNumber") in temperature_vars
                ),
                None,
            )
            if T is None:
                continue
            for value in values.findall(_NS + "PropertyValue"):
                number = _text(value, _NS + "nPropNumber")
                if number not in wanted:
                    continue
                uncertainty = _first(value, (_NS + "nCombExpandUncertValue", _NS + "nStdUncertValue"))
                points.append(
                    {
                        "inchikey": inchikey,
                        "formula": formula,
                        "T": T,
                        "Cp": float(_text(value, _NS + "nPropValue")),
                        "uncertainty": float(uncertainty) if uncertainty else None,
                        "method": wanted[number],
                        **citation,
                    }
                )
    return points


def iter_archive(archive: Path) -> Iterator[dict[str, Any]]:
    """Every kept point of every ThermoML (.xml) member of the archive, in member order."""
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar:
            if not (member.isfile() and member.name.endswith(".xml")):
                continue
            handle = tar.extractfile(member)
            if handle is not None:
                yield from parse_ideal_gas_cp(handle.read())
