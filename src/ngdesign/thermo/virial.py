"""Virial vapour models for the gamma-phi adapter (spec T-03).

The spec calls for Hayden–O'Connell (1975) and Nothnagel (1973) second-virial
coefficients with the published parameter tables (dipole moments, radii of
gyration, association parameters). Neither equation set could be verified from
a complete, citable open source this session — DWSIM's implementation is GPLv3
and must not be copied — so the two virial vapour rows register as
``experimental`` catalogue rows whose builders refuse rather than invent
physics. Landing them needs a verifiable parameter table source (spec
deviation, decision with the maintainer).
"""

from __future__ import annotations

HOC_MODEL = "Hayden-O'Connell (1975)"
NOTHNAGEL_MODEL = "Nothnagel (1973)"

#: vapour option value -> model name, for refusal messages naming the model.
NOT_IMPLEMENTED_VAPOURS: dict[str, str] = {
    "hoc": HOC_MODEL,
    "nothnagel": NOTHNAGEL_MODEL,
}


def refuse_not_implemented(vapour: str) -> None:
    """Raise naming the virial model; the experimental rows' builders call this."""
    model = NOT_IMPLEMENTED_VAPOURS.get(vapour)
    if model is None:
        return
    raise NotImplementedError(
        f"the {model} second-virial vapour model is not implemented (spec T-03 deviation: "
        "no complete, citable open equation set or association-parameter table was "
        "verifiable, so the row registers as experimental and refuses to build rather "
        "than invent physics) - select vapour 'ideal' or a cubic vapour ('rk', 'pr')"
    )
