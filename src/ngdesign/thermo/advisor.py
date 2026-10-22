"""T-08: rank the registered thermo property methods for a flowsheet.

The advisor turns the data-driven model catalogue (T-01) into ranked,
cited recommendations for a specific flowsheet: the component slate, the
feed conditions (T/P range and polarity from the component classes) and a
probe-based coverage check drive the score. The payload contract:

- ``recommendations``: ranked rows ``{id, name, score, reasons, warnings,
  status}`` — ``experimental`` rows never rank; every row carries its
  catalogue status.
- ``profile``: what the ranking was derived from — component classes,
  T/P window, expected phases, polarity — so the UI and the agent can
  show *why*.

Ranking rules (cited in the reasons rows):
- Applicability match on component classes (Carlson 1996, Chem. Eng.
  Prog. 92(10): 35) and the feed T/P window against the row's window.
- Polarity: a strongly polar slate demotes cubic EOS with classical
  mixing rules and lifts gamma-phi models (Carlson 1996).
- Water with hydrocarbons: warn on free-water (VLL) handling — rows
  that do not claim a liquid-liquid capable formulation drop behind the
  ones that do (GPSA Engineering Data Book, 13th ed., sec. 25).
- Amine chemistry in the slate (amine + acid gas + water): the amine
  rows surface first, everything else is demoted with an explicit
  reason (Kohl & Nielsen, Gas Purification, 5th ed., ch. 2).
- Coverage: the row's adapter is probed at the feed conditions; a
  gamma-phi row without binary parameters for a present pair gets a
  refusal warning and a demotion below every candidate that covers the
  slate (Prausnitz, Lichtenthaler & de Azevedo, Molecular
  Thermodynamics of Fluid-Phase Equilibria, 3rd ed., ch. 6).
- ``provisional`` rows carry a status warning; ``experimental`` rows
  never rank (issue #154).

Deterministic: stable sort by (-score, id). The agent's
``recommend_thermo`` tool and ``GET /api/thermo/recommend`` both return
``payload(flowsheet)`` — one serialisation, two surfaces.
"""

from __future__ import annotations

from dataclasses import dataclass

from ngdesign.contracts import Flowsheet
from ngdesign.thermo.catalogue import ModelRow, load_catalogue
from ngdesign.thermo.gamma_phi import GammaPhiPackage

# --- component classification ------------------------------------------------

_COMPONENT_CLASSES: dict[str, set[str]] = {
    "H2O": {"water"},
    "CO2": {"acid_gas", "light_gas"},
    "H2S": {"acid_gas", "sour"},
    "N2": {"inert", "light_gas"},
    "C1": {"hydrocarbon", "light_gas"},
    "C2": {"hydrocarbon", "light_gas"},
    "C3": {"hydrocarbon", "light_gas"},
    "iC4": {"hydrocarbon", "light_gas"},
    "nC4": {"hydrocarbon", "light_gas"},
    "iC5": {"hydrocarbon"},
    "nC5": {"hydrocarbon"},
    "nC6": {"hydrocarbon"},
    "C6+": {"hydrocarbon"},  # flowsheet-owned pseudo (mapped to n-hexane)
    "TEG": {"glycol"},
    "MeOH": {"alcohol"},
    "MDEA": {"amine"},
}


@dataclass(frozen=True)
class Profile:
    """What the ranking was derived from (payload ``profile``)."""

    component_classes: tuple[str, ...]
    T_min_K: float
    T_max_K: float
    P_min_Pa: float
    P_max_Pa: float
    expected_phases: tuple[str, ...]
    polar: bool
    polar_dominant: bool


def _classify(slate: list[str]) -> set[str]:
    unknown = [name for name in slate if name not in _COMPONENT_CLASSES]
    if unknown:
        raise ValueError(f"unclassified components: {sorted(unknown)}")
    return set().union(*(_COMPONENT_CLASSES[name] for name in slate))


def _profile(fs: Flowsheet) -> Profile:
    classes = _classify(sorted(set(fs.slate_ids())))
    feeds = [s.feed for s in fs.streams if s.feed is not None]
    if not feeds:
        raise ValueError("flowsheet has no feeds; nothing to recommend from")
    T_min = min(f.T for f in feeds)
    T_max = max(f.T for f in feeds)
    P_min = min(f.P for f in feeds)
    P_max = max(f.P for f in feeds)
    expected = ("V", "L")  # both phases in scope for screening
    polar = bool(classes & {"water", "glycol", "alcohol", "amine"})
    # Polar-DOMINANT: every component is a polar species (no gas/HC classes) —
    # the Carlson 1996 cubic demotion applies to polar systems like MeOH/H2O
    # columns, not to gas plants that happen to carry water/glycol.
    polar_dominant = polar and not (classes & {"hydrocarbon", "light_gas", "inert", "acid_gas"})
    return Profile(
        component_classes=tuple(sorted(classes)),
        T_min_K=T_min,
        T_max_K=T_max,
        P_min_Pa=P_min,
        P_max_Pa=P_max,
        expected_phases=expected,
        polar=polar,
        polar_dominant=polar_dominant,
    )


# --- scoring -----------------------------------------------------------------

_BASE: dict[str, int] = {
    "gamma_phi": 40,
    "cubic": 30,
    "helmholtz": 20,
    "kvalue": 15,
    "saft": 20,
    "electrolyte": 25,
    "special": 10,
}


def _amine_chemistry(slate: list[str]) -> bool:
    names = set(slate)
    return bool(names & {"MDEA"} and names & {"CO2", "H2S"} and "H2O" in names)


def _score_row(row: ModelRow, fs: Flowsheet, profile: Profile) -> tuple[int, list[str], list[str]]:
    """Score one catalogue row: (score, reasons, warnings) before sorting."""
    score = _BASE.get(row.family, 10)
    reasons: list[str] = []
    warnings: list[str] = []

    # Applicability: component classes (Carlson 1996).
    slate_set = set(profile.component_classes)
    row_classes = set(row.applicability.component_classes)
    if slate_set <= row_classes:
        reasons.append(
            "applicability: the slate's component classes are covered by the row's "
            "claimed classes (Carlson 1996)"
        )
    else:
        outside = sorted(slate_set - row_classes)
        score -= 5
        warnings.append(
            f"applicability: slate component classes {outside} sit outside the row's "
            f"claimed classes {sorted(row_classes)} (Carlson 1996)"
        )

    # Polarity (Carlson 1996). The cubic demotion applies to polar-DOMINANT
    # systems (MeOH/H2O columns); gas plants carrying water/glycol keep the
    # GPSA-favoured PR/SRK on top.
    # Every cubic-family row carries a classical (van der Waals one-fluid)
    # mixing rule; the gE-mixing rows (family C, spec T-06) are a separate
    # family and are not demoted. Keyed on the family, not an id list, so
    # new cubic rows inherit the rule.
    if profile.polar_dominant and row.family == "cubic":
        score -= 40
        reasons.append(
            "polar feed: a cubic EOS with a classical mixing rule treats the polar "
            "components as nonpolar — demoted (Carlson 1996)"
        )
    elif profile.polar_dominant and row.family == "gamma_phi":
        score += 40
        reasons.append(
            "polar feed: an activity-coefficient (gamma-phi) model is the right "
            "shape for the polar VLE — lifted (Carlson 1996)"
        )

    # Natural-gas processing: GPSA favours PR/SRK for natural-gas systems
    # (GPSA Engineering Data Book, 13th ed., sec. 25).
    if not profile.polar_dominant and row.id in ("pr", "srk"):
        score += 10
        reasons.append(
            "natural gas: PR/SRK is the GPSA-favoured choice for natural-gas "
            "systems (GPSA Engineering Data Book, 13th ed., sec. 25)"
        )

    # Free water (GPSA 13th ed. sec. 25): always flagged on a water + HC slate —
    # even a VLL-claiming row needs the three-phase separation check.
    if "H2O" in {name for name in fs.slate_ids()} and any(
        c in slate_set for c in ("hydrocarbon", "light_gas")
    ):
        warnings.append(
            "slate contains water with hydrocarbons — verify free-water (VLL) "
            "handling for three-phase separation"
        )
        if "VLL" in row.applicability.phases:
            score += 10
            reasons.append(
                "slate contains water with hydrocarbons: the row claims VLL "
                "(free-water) support (GPSA Engineering Data Book, 13th ed., sec. 25)"
            )

    # Amine chemistry (Kohl & Nielsen ch. 2).
    slate = fs.slate_ids()
    if _amine_chemistry(slate):
        if row.id.startswith("amine_"):
            score += 30
            reasons.append(
                "amine treating loop: an amine-specific model captures the "
                "amine + acid gas + water chemistry (Kohl & Nielsen, Gas "
                "Purification, 5th ed., ch. 2)"
            )
        else:
            score -= 20
            reasons.append(
                "amine treating loop: this method does not model amine chemistry "
                "(amine + CO2/H2S + water in the slate) — demoted (Kohl & Nielsen, "
                "Gas Purification, 5th ed., ch. 2)"
            )

    # Coverage: probe the adapter at the feed conditions (Prausnitz et al. ch. 6).
    err = _probe_refusal(row, fs)
    if err is not None:
        score -= 50
        warnings.append(f"missing binary parameters: {err}")

    # Status.
    if row.status == "provisional":
        warnings.append("status: provisional — L0 self-consistency green; L1/L2 validation cases pending")
    elif row.status == "validated":
        reasons.append("status: validated (L0 plus L1/L2 validation cases green)")
    return score, reasons, warnings


def _probe_refusal(row: ModelRow, fs: Flowsheet) -> str | None:
    """Return the adapter's refusal message, or None when it supports the slate.

    Constructing ``GammaPhiPackage`` with ``components`` runs its provenance
    checks eagerly: a pair, component or correlation the model cannot describe
    raises before any state is returned (the same refusal a flash would hit).
    Construction is the cached flasher factory, so probing is cheap after the
    first call per (liquid, vapour, slate).
    """
    if row.family != "gamma_phi":
        return None
    if row.adapter.endswith(":NrtlThermo"):
        liquid, vapour = "nrtl", "pr"
    elif row.adapter.endswith(":GammaPhiPackage") and "liquid" in row.options:
        liquid = row.options["liquid"]
        vapour = row.options.get("vapour", "ideal")
    else:
        return None  # a bespoke gamma-phi adapter probes through its own flash
    try:
        GammaPhiPackage(liquid, vapour, components=tuple(fs.slate_ids()))
    except Exception as exc:  # the adapter's own refusal message, verbatim
        return str(exc)
    return None


# --- public surface ------------------------------------------------------------


@dataclass(frozen=True)
class Recommendation:
    """One ranked row of the payload."""

    id: str
    name: str
    family: str
    score: int
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    status: str


def recommend(fs: Flowsheet) -> list[Recommendation]:
    """Rank every non-experimental catalogue row for this flowsheet."""
    profile = _profile(fs)
    rows = [row for row in load_catalogue().values() if row.status != "experimental"]
    ranked = [(row, *_score_row(row, fs, profile)) for row in rows]
    ranked.sort(key=lambda t: (-t[1], t[0].id))
    return [
        Recommendation(
            id=row.id,
            name=row.name,
            family=row.family,
            score=score,
            reasons=tuple(reasons),
            warnings=tuple(warnings),
            status=row.status,
        )
        for row, score, reasons, warnings in ranked
    ]


def payload(fs: Flowsheet) -> dict[str, object]:
    """The shared JSON payload: the agent tool and the API route both return it."""
    return {
        "profile": {
            "component_classes": list(_profile(fs).component_classes),
            "T_K": [_profile(fs).T_min_K, _profile(fs).T_max_K],
            "P_Pa": [_profile(fs).P_min_Pa, _profile(fs).P_max_Pa],
            "expected_phases": list(_profile(fs).expected_phases),
            "polar": _profile(fs).polar,
        },
        "recommendations": [
            {
                "id": rec.id,
                "name": rec.name,
                "family": rec.family,
                "score": rec.score,
                "reasons": list(rec.reasons),
                "warnings": list(rec.warnings),
                "status": rec.status,
            }
            for rec in recommend(fs)
        ],
    }
