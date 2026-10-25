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
from typing import Any

from scipy.optimize import brentq

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
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


class EjectorR1:
    """Rating-mode ejector: the achievable discharge pressure (R1).

    Reads ``motive_in`` and ``suction_in`` and computes the discharge pressure
    the streams can actually reach (eqs. 1-5), with the outlet a stagnation
    (PH) flash at that pressure (eq. 6). R0 is recovered exactly by rating a
    solve and re-running :class:`~ngdesign.units.flow.ejector.Ejector` at the
    computed ``P_out`` (the identity test). Params: ``eta_nozzle`` (0.95),
    ``phi_mix`` (0.85), ``eta_diffuser`` (0.85), and the optional
    ``P_out_required`` (Pa) which only switches on the discharge check.
    """

    inlet_ports = ("motive_in", "suction_in")
    outlet_ports = ("outlet",)

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        motive = inlets["motive_in"]
        suction = inlets["suction_in"]
        eta_n = float(params.get("eta_nozzle", 0.95))
        phi_m = float(params.get("phi_mix", 0.85))
        eta_d = float(params.get("eta_diffuser", 0.85))
        P_out_required = params.get("P_out_required")
        if P_out_required is not None:
            P_out_required = float(P_out_required)
            if P_out_required <= 0.0:
                raise EjectorR1Error(f"P_out_required {P_out_required} Pa must be > 0")

        n_p, n_s = motive.molar_flow, suction.molar_flow
        if n_p <= 0.0 or n_s <= 0.0:
            # Validate before any division (MWs needs n_s) or flash call.
            raise EjectorR1Error(f"molar_flow must be > 0 on both inlets (np={n_p}, ns={n_s})")
        z_mix: dict[str, float] = {
            cid: (n_p * motive.composition.get(cid, 0.0) + n_s * suction.composition.get(cid, 0.0))
            / (n_p + n_s)
            for cid in set(motive.composition) | set(suction.composition)
        }

        def h_at_PS_motive(P: float, s: float) -> float:
            return thermo.flash_ps(motive.composition, P, s, n_p).enthalpy

        def h_at_PS_mix(P: float, s: float) -> float:
            return thermo.flash_ps(z_mix, P, s, n_p + n_s).enthalpy

        def s_at_PH_mix(P: float, h: float) -> float:
            return thermo.flash_ph(z_mix, P, h, n_p + n_s).entropy

        info = ejector_core(
            np=n_p,
            ns=n_s,
            MWp=motive.mass_flow / n_p,
            MWs=suction.mass_flow / n_s,
            hp=motive.enthalpy,
            sp=motive.entropy,
            hs=suction.enthalpy,
            Pp=motive.P,
            Ps=suction.P,
            eta_n=eta_n,
            phi_m=phi_m,
            eta_d=eta_d,
            h_at_PS_motive=h_at_PS_motive,
            h_at_PS_mix=h_at_PS_mix,
            s_at_PH_mix=s_at_PH_mix,
            P_hi=motive.P,
        )
        P_out = info["P_out_Pa"]
        # Eq. 6: the outlet is the stagnation state (h_0, exactly R0's h_mix).
        outlet = thermo.flash_ph(z_mix, P_out, info["h_stag_mix_J_mol"], n_p + n_s)

        result_info: dict[str, float] = {
            "P_out_Pa": P_out,
            "compression_ratio": P_out / suction.P,
            "u_motive_m_s": info["u_motive_m_s"],
            "u_mix_m_s": info["u_mix_m_s"],
            "entrainment_kg_kg": suction.mass_flow / motive.mass_flow,
            "h_static_mix_J_mol": info["h_static_mix_J_mol"],
        }
        if P_out_required is not None:
            # R1 is a rating model: the outlet stays at the computed P_out.
            result_info["meets_discharge"] = 1.0 if P_out >= P_out_required else 0.0
            result_info["discharge_margin_Pa"] = P_out - P_out_required
        return UnitResult(
            outlets={"outlet": outlet},
            duty_W=0.0,
            power_W=0.0,
            info=result_info,
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """R0's Graham-style basis without ``P_out``/``entrainment``: R1 rates it."""
        motive = {"T": 500.0, "P": 1.0e6, "molar_flow": 146.873, "composition": {"H2O": 1.0}}
        suction = {"T": 300.0, "P": 2000.0, "molar_flow": 48.958, "composition": {"H2O": 1.0}}
        params: dict[str, Any] = {
            "eta_nozzle": 0.95,
            "phi_mix": 0.85,
            "eta_diffuser": 0.85,
        }
        return {"motive_in": motive, "suction_in": suction}, params
