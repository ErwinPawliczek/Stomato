"""``ngdesign chem ...``: the chemistry engine from a shell.

Quantities on the command line carry their units (``--T "650 degC"``, ``--P 30bar``)
and are checked at this edge; results print in the chosen ``--units`` set.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from typing import Any

from ngdesign.chem import equilibrium, phase, stoichiometry, thermochem
from ngdesign.data import DATA_DIR, chemdb
from ngdesign.uom.quantity import coerce, convert
from ngdesign.uom.sets import UNIT_SETS, display


def _pairs(items: Sequence[str]) -> dict[str, float]:
    """``CH4=1 O2=2`` into a mapping of species to amount."""
    out: dict[str, float] = {}
    for item in items:
        key, separator, value = item.partition("=")
        if not separator:
            raise argparse.ArgumentTypeError(f"expected SPECIES=AMOUNT, got {item!r}")
        out[key] = float(value)
    return out


def _lookup(args: argparse.Namespace) -> str:
    if args.search:
        hits = chemdb.search(args.species, args.limit)
        return "\n".join(f"{s.cas:>12}  {s.formula:<14} {s.name}" for s in hits) or "no match"
    species = chemdb.find(args.species)
    lines = [
        f"{species.name}  CAS {species.cas}  {species.formula}  MW {species.mw}",
        f"InChIKey {species.inchikey}  SMILES {species.smiles}  PubChem CID {species.pubchem_cid}",
        f"identity from {species.identity_source}",
    ]
    for prop, row in sorted(chemdb.properties_of(species.cas).items()):
        spread = len(chemdb.values(species.cas, prop))
        at = f" at {row.T_K} K" if row.T_K is not None else ""
        reference = f" ({row.reference})" if row.reference else ""
        lines.append(
            f"  {prop:<12} {row.value:>14.6g} {row.unit:<10}{at}  [{row.grade}] {row.source}{reference}"
            f"  1 of {spread}"
        )
    return "\n".join(lines)


def _balance(args: argparse.Namespace) -> str:
    return str(stoichiometry.balance(args.equation))


def _react(args: argparse.Namespace) -> str:
    T = coerce(args.T, "temperature")
    result = thermochem.reaction_thermo(args.equation, T)
    table = args.units
    lines = [
        result.equation,
        f"T = {display(T, 'temperature', table):.2f}",
        f"dH = {display(result.dH, 'molar_energy', table):.3f}",
        f"dS = {display(result.dS, 'molar_entropy', table):.3f}",
        f"dG = {display(result.dG, 'molar_energy', table):.3f}",
        f"ln K = {result.lnK:.4f}  K = {result.K:.4g}",
    ]
    for key, thermo in result.species.items():
        lines.append(f"  {key}: {thermo.phase}, {thermo.model}, H from {thermo.provenance['hf298']}")
    return "\n".join(lines)


def _equilibrium(args: argparse.Namespace) -> str:
    T = coerce(args.T, "temperature")
    P = coerce(args.P, "pressure")
    result = equilibrium.gibbs_equilibrium(_pairs(args.feed), args.species, T, P)
    lines = [f"T = {display(T, 'temperature', args.units):.2f}, P = {display(P, 'pressure', args.units):.3f}"]
    for key, y in sorted(result.mole_fractions.items(), key=lambda pair: -pair[1]):
        lines.append(f"  {key:<14} y = {y:.6g}  n = {result.gas[key]:.6g} mol")
    for key, n in result.condensed.items():
        lines.append(f"  {key:<14} condensed  n = {n:.6g} mol")
    return "\n".join(lines)


def _saturation(args: argparse.Namespace) -> str:
    if args.T is not None:
        fit = phase.psat(args.species, coerce(args.T, "temperature"))
        return f"Psat = {display(fit.P, 'pressure', args.units):.5g}  ({fit.form}, {fit.source})"
    boiling = phase.tsat(args.species, coerce(args.P, "pressure"))
    return f"Tsat = {display(boiling, 'temperature', args.units):.3f}"


def _convert(args: argparse.Namespace) -> str:
    return repr(convert(args.value, args.source, args.target, mw=args.mw, rho=args.rho))


def _info(_args: argparse.Namespace) -> str:
    return json.dumps(json.loads((DATA_DIR / "chemdb" / "MANIFEST.json").read_text()), indent=2)


def add_parser(sub: Any) -> None:
    """Register the ``chem`` command and its subcommands on the main parser."""
    chem = sub.add_parser(
        "chem", help="chemistry engine: lookup, balance, react, equilibrium, saturation, convert"
    )
    verbs = chem.add_subparsers(dest="verb", required=True)
    for name, function, help_text in (
        ("lookup", _lookup, "species identity and cited properties"),
        ("balance", _balance, "balance a chemical equation"),
        ("react", _react, "reaction enthalpy, entropy, Gibbs energy and K at T"),
        ("equilibrium", _equilibrium, "multiphase Gibbs equilibrium at T and P"),
        ("saturation", _saturation, "saturation pressure or temperature"),
        ("convert", _convert, "convert a value between units"),
        ("info", _info, "database manifest: counts and provenance"),
    ):
        verb = verbs.add_parser(name, help=help_text)
        verb.set_defaults(chem_handler=function)
        if name in ("react", "equilibrium", "saturation"):
            verb.add_argument("--units", default="METRIC", choices=sorted(UNIT_SETS))
        if name == "lookup":
            verb.add_argument("species")
            verb.add_argument(
                "--search", action="store_true", help="substring search instead of exact lookup"
            )
            verb.add_argument("--limit", type=int, default=20)
        elif name == "balance":
            verb.add_argument("equation")
        elif name == "react":
            verb.add_argument("equation")
            verb.add_argument("--T", default="25 degC")
        elif name == "equilibrium":
            verb.add_argument("--feed", nargs="+", required=True, metavar="SPECIES=MOL")
            verb.add_argument("--species", nargs="+", required=True, help="candidates: CO2 CO 'C(s)' ...")
            verb.add_argument("--T", required=True)
            verb.add_argument("--P", default="1 atm")
        elif name == "saturation":
            verb.add_argument("species")
            verb.add_argument("--T")
            verb.add_argument("--P", default="1 atm")
        elif name == "convert":
            verb.add_argument("value", type=float)
            verb.add_argument("source")
            verb.add_argument("target")
            verb.add_argument("--mw", type=float, help="molar mass, g/mol")
            verb.add_argument("--rho", type=float, help="density, kg/m3")


def run(args: argparse.Namespace) -> int:
    print(args.chem_handler(args))
    return 0
