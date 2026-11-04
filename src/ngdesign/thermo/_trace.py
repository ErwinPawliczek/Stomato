"""Model-parameter provenance for flasher-based property packages (docs/provenance.md 3.3).

``describe_flasher_parameters`` reads the constants and correlations from the
flasher a package actually flashes with, so every traced number is the number
the EOS saw, and cites each one (``ngdesign.provenance.citations``). Only
called while a trace is recorded; never on the solve path otherwise.
"""

from __future__ import annotations

from typing import Any

from thermo.eos import R as THERMO_R
from thermo.interaction_parameters import IPDB

from ngdesign.contracts.components import resolve
from ngdesign.data import DATABANK_LOCK
from ngdesign.provenance import catalogue, citations
from ngdesign.provenance.model import Citation
from ngdesign.thermo._state import KIJ_TABLE_NONE

#: EOS mixture class name -> method catalogue key.
EOS_METHOD_KEYS: dict[str, str] = {
    "PRMIX": "peng_robinson_1976",
    "PR78MIX": "peng_robinson_1978",
    "SRKMIX": "soave_redlich_kwong_1972",
}


def _leaf(
    key: tuple[Any, ...],
    label: str,
    value: Any,
    unit: str,
    citation: Citation | None,
    quality: str,
    *,
    kind: str = "constant",
    role: str = "",
    prop: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "value": value,
        "unit": unit,
        "citation": citation,
        "quality": quality if citation is not None or quality in ("estimated", "user") else "uncited",
        "kind": kind,
        "role": role,
        "prop": prop,
        "note": note,
    }


def untraced_leaf(package: str) -> dict[str, Any]:
    """An explicit uncited leaf for model parameters a package does not report yet."""
    return _leaf(
        ("untraced", package),
        f"{package} model-specific parameters (not traced)",
        "binary/model parameters",
        "",
        None,
        "uncited",
        kind="parameter",
        role="model parameters",
        note="The package's own parameters (activity, SAFT, K-value ...) are not reported yet.",
    )


def _pseudo_citation(record: Any, prop: str) -> tuple[Citation | None, str]:
    """A pseudo-component constant: its record's provenance note (correlation or user)."""
    note = record.provenance.get(prop)
    if note is None:
        return None, "uncited"
    if note == "user" or note.startswith("user"):
        return Citation(source="user", citation=f"User input: pseudo-component {record.id} {prop}"), "user"
    return Citation(source="correlation", citation=str(note)), "estimated"


def _pair_pages(kij_table: str, cas: list[str | None]) -> dict[str, str]:
    """'A|B' -> page reference for the pairs the IPDB table carries."""
    pages: dict[str, str] = {}
    try:
        table = IPDB.tables[kij_table]
    except (AttributeError, KeyError):
        return pages
    data = getattr(table, "get", None)
    if data is None:
        return pages
    for i, a in enumerate(cas):
        for b in cas[i + 1 :]:
            if a is None or b is None:
                continue
            rec = table.get(f"{a} {b}") or table.get(f"{b} {a}")
            if isinstance(rec, dict) and rec.get("page"):
                pages[f"{a}|{b}"] = ",".join(str(p) for p in rec["page"])
    return pages


def describe_flasher_parameters(
    flasher: Any, ids: tuple[str, ...], model_key: str | None, kij_table: str | None, pseudos: Any = None
) -> dict[str, Any]:
    """The parameter-set description the recorder turns into cited leaves."""
    with DATABANK_LOCK:
        records = [resolve(cid, pseudos={d.id: d for d in pseudos} if pseudos else None) for cid in ids]
    constants = flasher.constants
    correlations = flasher.correlations
    entry = catalogue.method(model_key) if model_key else None
    model_name = entry.name if entry else (model_key or type(flasher).__name__)
    leaves: list[dict[str, Any]] = []
    for i, (cid, record) in enumerate(zip(ids, records, strict=True)):
        cas = record.cas
        for prop, vec, unit in (
            ("Tc", constants.Tcs, "K"),
            ("Pc", constants.Pcs, "Pa"),
            ("omega", constants.omegas, "1"),
        ):
            value = float(vec[i])
            if cas is None:
                cit, quality = _pseudo_citation(record, prop)
                method = None
            else:
                cit, quality, method = citations.cite_constant(str(cas), prop, value)
            leaves.append(
                _leaf(
                    ("const", cid, cas, prop),
                    f"{cid} {prop}",
                    value,
                    unit,
                    cit,
                    quality,
                    role=f"{prop}[{cid}]",
                    prop=prop,
                    note=f"chemicals method {method}" if method else None,
                )
            )
        mw = float(constants.MWs[i])
        mw_cit, mw_q = (citations.cite_mw(), "cited") if cas is not None else _pseudo_citation(record, "mw")
        leaves.append(
            _leaf(
                ("const", cid, cas, "MW"),
                f"{cid} MW",
                mw,
                "g/mol",
                mw_cit,
                mw_q,
                role=f"MW[{cid}]",
                prop="MW",
            )
        )
        cp = correlations.HeatCapacityGases[i] if correlations is not None else None
        cp_method = getattr(cp, "method", None)
        if cas is None:
            # pseudo-components: thermo builds Lastovka-Shaw Cp (thermo/_state.py)
            cp_cit: Citation | None = catalogue.source_citation("lastovka_shaw")
            cp_q = "estimated"
        else:
            cp_cit, cp_q = citations.cite_correlation("heat_capacity_gas", cp_method)
        leaves.append(
            _leaf(
                ("cp_ig", cid, cas, str(cp_method)),
                f"{cid} Cp_ig(T) [{cp_method}]",
                f"HeatCapacityGas method {cp_method}",
                "J/(mol K)",
                cp_cit,
                cp_q,
                kind="parameter",
                role=f"Cp_ig[{cid}]",
                prop="Cp_ig",
            )
        )
    if kij_table == KIJ_TABLE_NONE and len(ids) > 1:
        leaves.append(
            _leaf(
                ("kij", kij_table, ids),
                "k_ij = 0 (none)",
                [[0.0] * len(ids) for _ in ids],
                "1",
                Citation(
                    source="model_definition",
                    citation="Plain cubic EOS: every binary interaction parameter k_ij = 0 "
                    "(catalogue kij_table: none)",
                ),
                "cited",
                kind="parameter",
                role="k_ij",
                prop="kij",
                note="order: " + ", ".join(ids),
            )
        )
    elif kij_table is not None and len(ids) > 1:
        try:
            kijs = flasher.gas.eos_kwargs.get("kijs")
        except AttributeError:
            kijs = None
        if kijs is not None:
            cas_list = [r.cas for r in records]
            pages = _pair_pages(kij_table, cas_list)
            leaves.append(
                _leaf(
                    ("kij", kij_table, ids),
                    f"k_ij ({kij_table})",
                    [[float(x) for x in row] for row in kijs],
                    "1",
                    catalogue.source_citation(
                        "chemsep_pr_kij",
                        table=kij_table,
                        reference="; ".join(f"{k}: p. {v}" for k, v in pages.items()) or None,
                    ),
                    "cited",
                    kind="parameter",
                    role="k_ij",
                    prop="kij",
                    note="order: " + ", ".join(ids),
                )
            )
    leaves.append(
        _leaf(
            ("R",),
            "R (gas constant)",
            float(THERMO_R),
            "J/(mol K)",
            catalogue.source_citation("codata2018"),
            "cited",
            role="R",
            prop="R",
        )
    )
    leaves.append(
        _leaf(
            ("ref_state",),
            "enthalpy reference state",
            "ideal gas, 298.15 K, 101325 Pa, H = S = 0",
            "",
            catalogue.source_citation("thermo_reference_state"),
            "cited",
            kind="parameter",
            role="reference state",
            prop="reference_state",
        )
    )
    return {"model": model_name, "leaves": leaves}
