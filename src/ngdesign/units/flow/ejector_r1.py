"""Ejector, R1: 1-D constant-pressure mixing model giving the achievable discharge pressure.

Spec ``specs/backend/units/ejector.md`` (level-wave U-R2). Method: the
constant-pressure mixing ejector of Keenan, Neumann & Lustwerk, "An
investigation of ejector design by analysis and experiment", J. Appl. Mech.
17:299-309 (1950), in the component-efficiency form of Huang, Chang, Wang &
Petrenko, "A 1-D analysis of ejector performance", Int. J. Refrig.
22(5):354-364 (1999). ESDU 86030 is cited for context only; no ESDU data or
equations are used.

Assumptions (stated in the spec):
- steady, adiabatic, 1-D;
- the motive expands to the suction pressure Ps, and mixing happens at
  constant Ps;
- the suction stream enters the mixing section at negligible velocity;
- the outlet velocity is negligible (stagnation state at discharge);
- the efficiencies are constants supplied by the user.

Equations (symbols: m in kg/s, n in mol/s, h in J/mol, MW in kg/mol):
1. Motive nozzle: ``h_is = h(Ps, s_p)`` (isentropic flash),
   ``dh_n = eta_n * (h_p - h_is)``, ``u_p = sqrt(2 * dh_n / MW_p)``.
2. Mixing momentum: ``(m_p + m_s) * u_m = phi_m * m_p * u_p``.
3. Mixing energy: the stagnation enthalpy is conserved,
   ``h_0 = (n_p*h_p + n_s*h_s) / (n_p + n_s)`` (exactly R0's ``h_mix``);
   the static enthalpy after mixing is ``h_m = h_0 - MW_mix * u_m**2 / 2``,
   with ``MW_mix = (m_p + m_s) / (n_p + n_s)``.
4. Mixed static state: ``s_m = s(Ps, h_m)`` (PH flash of z_mix).
5. Diffuser: ``h(P_out, s_m) = h_m + eta_d * MW_mix * u_m**2 / 2``, solved
   for ``P_out`` by Brent's method on ``[Ps, P_hi]``.
6. Outlet at stagnation: a PH flash at ``(z_mix, P_out, h_0)``.

The pure core :func:`ejector_core` takes its property evaluations as injected
callables: the :class:`EjectorR1` adapter passes thermo-backed flashes, the
closed-form test passes calorically perfect ideal-gas relations. Nothing here
imports a property package.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from math import sqrt

from scipy.optimize import brentq

from ngdesign.units.flow.ejector import EjectorSpecError

#: ``h = h(P, s)`` for a composition: an isentropic (PS) flash enthalpy.
EnthalpyAtPS = Callable[[float, float], float]

#: ``s = s(P, h)`` for a composition: a PH flash entropy.
EntropyAtPH = Callable[[float, float], float]


class EjectorR1Error(EjectorSpecError):
    """Typed refusal for a bad ejector R1 rating spec (naming the parameter)."""


def ejector_core(
    np: float,
    ns: float,
    MWp: float,
    MWs: float,
    hp: float,
    sp: float,
    hs: float,
    Pp: float,
    Ps: float,
    eta_n: float,
    phi_m: float,
    eta_d: float,
    h_at_PS_motive: EnthalpyAtPS,
    h_at_PS_mix: EnthalpyAtPS,
    s_at_PH_mix: EntropyAtPH,
    P_hi: float,
) -> dict[str, float]:
    """Pure constant-pressure mixing ejector (Keenan 1950 / Huang 1999).

    ``np``/``ns`` are the motive/suction molar flows (mol/s), ``MWp``/``MWs``
    the motive/suction molar masses (kg/mol), ``hp``/``sp`` the motive inlet
    enthalpy/entropy (J/mol, J/mol/K), ``hs`` the suction enthalpy (J/mol),
    and ``Pp``/``Ps`` the inlet pressures (Pa). ``P_hi`` is the upper bracket
    for the discharge-pressure root (the adapter passes ``Pp``). Returns
    ``P_out_Pa``, ``u_motive_m_s``, ``u_mix_m_s``, ``h_static_mix_J_mol``,
    ``h_stag_mix_J_mol``, ``s_static_mix_J_molK`` and ``MW_mix_kg_mol``.
    """
    if np <= 0.0 or ns <= 0.0:
        raise EjectorR1Error(f"molar_flow must be > 0 on both inlets (np={np}, ns={ns})")
    if Pp <= Ps:
        raise EjectorR1Error(f"motive pressure {Pp} Pa must exceed suction pressure {Ps} Pa")
    for name, value in (("eta_nozzle", eta_n), ("phi_mix", phi_m), ("eta_diffuser", eta_d)):
        if not 0.0 < value <= 1.0:
            raise EjectorR1Error(f"{name} {value} must be in (0, 1]")

    m_p, m_s = np * MWp, ns * MWs
    MW_mix = (m_p + m_s) / (np + ns)

    # Eq. 1: motive nozzle, isentropic drop scaled by eta_nozzle.
    h_is = h_at_PS_motive(Ps, sp)
    dh_n = eta_n * (hp - h_is)
    if dh_n <= 0.0:
        raise EjectorR1Error(f"no nozzle enthalpy drop: dh_n={dh_n} J/mol (eta_nozzle={eta_n})")
    u_p = sqrt(2.0 * dh_n / MWp)

    # Eq. 2: mixing-section momentum balance.
    u_m = phi_m * m_p * u_p / (m_p + m_s)

    # Eq. 3: stagnation enthalpy conserved; static enthalpy after mixing.
    h_0 = (np * hp + ns * hs) / (np + ns)
    h_m = h_0 - MW_mix * u_m**2 / 2.0

    # Eq. 4: mixed static state at Ps.
    s_m = s_at_PH_mix(Ps, h_m)

    # Eq. 5: diffuser, solved for the discharge pressure.
    kinetic = eta_d * MW_mix * u_m**2 / 2.0
    target = h_m + kinetic

    def g(P: float) -> float:
        return h_at_PS_mix(P, s_m) - target

    if g(P_hi) < 0.0:
        raise EjectorR1Error(
            f"computed discharge exceeds the motive pressure {P_hi} Pa; check efficiencies"
        )
    try:
        P_out = brentq(g, Ps, P_hi, xtol=1e-9 * Ps, rtol=4 * sys.float_info.epsilon, maxiter=100)
    except (ValueError, RuntimeError) as exc:
        raise EjectorR1Error(f"diffuser discharge pressure did not converge: {exc}") from exc

    return {
        "P_out_Pa": P_out,
        "u_motive_m_s": u_p,
        "u_mix_m_s": u_m,
        "h_static_mix_J_mol": h_m,
        "h_stag_mix_J_mol": h_0,
        "s_static_mix_J_molK": s_m,
        "MW_mix_kg_mol": MW_mix,
    }
