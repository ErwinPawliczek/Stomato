"""Katz gas-gravity hydrate temperature for the hydrate check (spec U-R2, R1).

Level R1 of the ``hydrate_check`` row, on top of the R0 adapter
(:mod:`ngdesign.units.separation.hydrate_check`, imported read-only). The
R0 physics — the adiabatic PH mix, the Nielsen-Bucklin suppression and the
inhibitor-dose bisection — is unchanged; R1 adds a second
hydrate-temperature correlation and makes it selectable:

- ``hydrate_method="hammerschmidt"`` (default off): exactly R0.
- ``hydrate_method="towler_mokhatab"`` (default): the Katz (1945) gas-gravity
  method as fitted by **Towler & Mokhatab (2005)**, "Quickly estimate hydrate
  formation conditions in natural gases", Hydrocarbon Processing 84(4):61:

  .. math:: T[°F] = 13.47 ln P + 34.27 ln γ - 1.675 (ln P)(ln γ) - 20.35

  with ``P`` in psia (natural logarithms) and ``γ`` the gas specific gravity
  (MW_gas / MW_air). The correlation reproduces the Katz gravity chart for
  light, sweet natural gases. R1 still changes no stream: the outlet and duty
  are R0's; only the reported hydrate T (and, with ``T_operating_K``, the dose
  computed for it) differ.

The paper is not open access, so the four coefficients and the validity
ranges below are transcribed from reproductions that cite it (e.g. the Gas
Processing Journal evaluation of hydrate-formation regressions, Univ. of
Isfahan, and the AJER comparative analysis of Hammerschmidt vs Towler &
Mokhatab), all quoting the same equation.

The van der Waals-Platteeuw route in the row note is out of scope at R1: no
``ngdesign.thermo`` package exposes a hydrate model (checked by grep), so a
thermo contract addition would be needed.
"""

from __future__ import annotations

import math
from typing import Any

from ngdesign.contracts import PhaseKind, StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.separation._util import stream_molar_mass
from ngdesign.units.separation.hydrate_check import (
    MW_AIR_G_MOL,
    HydrateCheck,
    _inhibitor_in,
    _required_dose,
)

#: Towler & Mokhatab (2005) coefficients: T[°F] = a·lnP + b·lnγ - c·(lnP)(lnγ) - d.
_TOWLER_MOKHATAB_A = 13.47  # psia^-1 term
_TOWLER_MOKHATAB_B = 34.27
_TOWLER_MOKHATAB_C = 1.675
_TOWLER_MOKHATAB_D = 20.35

#: Stated validity of the correlation (reproductions citing the 2005 paper):
#: gas specific gravity 0.55 < γ < 1.0 and pressure 1200–40000 kPa.
_TOWLER_MOKHATAB_SG_RANGE = (0.55, 1.0)
_TOWLER_MOKHATAB_P_PA_RANGE = (1.2e6, 4.0e7)

#: NIST exact definition of the pound-force psi, and the exact °F → K offsets
#: (identical to the constants in ``ngdesign.sizing.hydrates``).
_PSIA_PER_PA = 1.0 / 6894.757293168
_F_TO_K_OFFSET_RANKINE = 459.67
_DEGF_PER_K = 1.8


class HydrateCheckR1SpecError(ValueError):
    """The hydrate-check R1 spec is bad; the message names the parameter."""


def towler_mokhatab_T_K(P_Pa: float, sg: float) -> float:
    """Katz gas-gravity hydrate-formation temperature, in kelvin.

    Towler & Mokhatab's (2005) fit of the Katz (Trans. AIME 160:140, 1945;
    GPSA Sect. 20 gravity chart) gas-gravity method:

        T[°F] = 13.47·ln P + 34.27·ln γ − 1.675·(ln P)(ln γ) − 20.35

    with ``P`` in psia, natural logarithms, and ``γ`` the gas specific
    gravity; converted with ``T_K = (T_F + 459.67)/1.8``.

    Args:
        P_Pa: Absolute pressure [Pa].
        sg: Gas specific gravity relative to air [dimensionless].

    Returns:
        The hydrate-formation temperature [K].

    Raises:
        HydrateCheckR1SpecError: on ``P`` or ``sg`` outside the correlation's
            stated validity range (never extrapolated silently).
    """
    if not _TOWLER_MOKHATAB_SG_RANGE[0] < sg < _TOWLER_MOKHATAB_SG_RANGE[1]:
        raise HydrateCheckR1SpecError(
            f"gas specific gravity {sg} outside the Towler-Mokhatab range "
            f"(0.55 < gamma < 1.0, per the 2005 paper as transcribed)"
        )
    if not _TOWLER_MOKHATAB_P_PA_RANGE[0] < P_Pa < _TOWLER_MOKHATAB_P_PA_RANGE[1]:
        raise HydrateCheckR1SpecError(
            f"P {P_Pa} Pa outside the Towler-Mokhatab range "
            f"(1200–40000 kPa, per the 2005 paper as transcribed)"
        )
    P_psia = P_Pa * _PSIA_PER_PA
    ln_p, ln_sg = math.log(P_psia), math.log(sg)
    T_F = (
        _TOWLER_MOKHATAB_A * ln_p
        + _TOWLER_MOKHATAB_B * ln_sg
        - _TOWLER_MOKHATAB_C * ln_p * ln_sg
        - _TOWLER_MOKHATAB_D
    )
    return (T_F + _F_TO_K_OFFSET_RANKINE) / _DEGF_PER_K


class HydrateCheckR1:
    """R1: selectable Katz gas-gravity (Towler-Mokhatab) hydrate temperature.

    The outlet, duty and power are R0's — R1 changes no stream. ``info``
    reports ``hydrate_T_K`` per the chosen method, the R0 (Hammerschmidt)
    value alongside as ``hydrate_T_hammerschmidt_K``, and
    ``hydrate_method_index`` (0.0 = Hammerschmidt, 1.0 = Towler-Mokhatab).
    """

    inlet_ports: tuple[str, ...] = ("inlet", "inhibitor_in")
    outlet_ports: tuple[str, ...] = ("outlet",)

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        method = params.get("hydrate_method", "towler_mokhatab")
        if method not in ("towler_mokhatab", "hammerschmidt"):
            raise HydrateCheckR1SpecError(
                f"hydrate_method {method!r} must be 'towler_mokhatab' or 'hammerschmidt'"
            )
        r0_params = {k: v for k, v in params.items() if k != "hydrate_method"}
        result = HydrateCheck().solve(inlets, r0_params, thermo)

        if method == "hammerschmidt":
            info = dict(result.info)
            info["hydrate_method_index"] = 0.0
            return UnitResult(
                outlets=result.outlets,
                duty_W=result.duty_W,
                power_W=result.power_W,
                info=info,
            )

        outlet = result.outlets["outlet"]
        sg = stream_molar_mass(inlets["inlet"].composition) / MW_AIR_G_MOL
        T_hyd = towler_mokhatab_T_K(outlet.P, sg)  # range-checked (K3)

        info = dict(result.info)
        info["hydrate_T_hammerschmidt_K"] = info["hydrate_T_K"]
        info["hydrate_T_K"] = T_hyd
        info["hydrate_method_index"] = 1.0

        T_operating = r0_params.get("T_operating_K")
        if T_operating is not None:
            # R0's dose bisection, driven by R1's hydrate T. suppression_K is
            # unchanged: Nielsen-Bucklin does not depend on the hydrate T.
            aqueous = next((p for p in outlet.phases if p.kind is PhaseKind.AQUEOUS), None)
            inhibitor_cid = _inhibitor_in(aqueous.composition) if aqueous else None
            info.update(_required_dose(outlet, aqueous, inhibitor_cid, T_hyd - float(T_operating)))
        return UnitResult(
            outlets=result.outlets,
            duty_W=result.duty_W,
            power_W=result.power_W,
            info=info,
        )


__all__ = [
    "HydrateCheckR1",
    "HydrateCheckR1SpecError",
    "towler_mokhatab_T_K",
]
