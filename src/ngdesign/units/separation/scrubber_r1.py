"""Scrubber R1: Souders-Brown sizing and droplet carry-over at a given diameter.

Spec ``specs/backend/units/scrubber.md``; conventions in
``specs/backend/U-R2-level-wave-conventions.md`` (U-R1 still binds).

The R0 adapter (:class:`ngdesign.units.separator.Scrubber`) PT-flashes the feed
at (T_in, P_in - dP) and maps the flash phases to the ports. R1 adds, on top of
that result:

- **S1 Souders-Brown sizing** (GPSA Engineering Data Book, Sect. 7; Svrcek &
  Monnery, Chem. Eng. Prog. 89(10):53, 1993), computed by
  :func:`ngdesign.sizing.souders_brown.souders_brown` — never re-derived here.
- **S2 York demister K** (Svrcek & Monnery 1993 fit of the Otto H. York curve),
  computed by ``fluids.separator.K_separator_demister_York`` after the module
  range-checks the pressure: fluids silently clamps P outside 1-5500 psia, so
  this unit refuses outside that range before calling it.
- **S3** gas velocity at a given diameter, ``v_G = 4 Q_G / (pi D^2)``.
- **S4 cut diameter**: a droplet settles when its terminal velocity exceeds
  ``v_G``; ``d_cut`` solves ``g(d) = 4 g d (rho_L - rho_G) / (3 C_D(Re) rho_G
  v_G^2) - 1 = 0`` with ``Re = rho_G v_G d / mu_G``, g = 9.80665 m/s2 (GPSA
  Sect. 7 gravity settling; Arnold & Stewart, Surface Production Operations,
  Vol. 1, Ch. 4). C_D is Morrison (2013), called through
  ``fluids.drag.drag_sphere(..., Method="Morrison")``.
- **S5** Rosin-Rammler droplet distribution by mass, ``F(d) = 1 -
  exp(-(d/d_RR)^n_RR)`` finer than d (Rosin & Rammler 1933; Bothamley,
  "Gas/liquid separators: quantifying separation performance", Oil & Gas
  Facilities, 2013).
- **S6 carry-over**: ``mdot_co = E mdot_L F(d_cut)`` with E the
  ``inlet_entrained_fraction`` and mdot_L the R0 liquid-outlet mass flow.

Outlets: the liquid outlet is R0's scaled with ``model_copy`` (never re-flashed
- S-24b); the gas outlet is re-flashed only where the carried droplets make it
genuinely two-phase. With ``f == 0`` (no diameter, or E = 0) the level reduces
exactly to R0. No ``@register``: dispatch comes from the catalogue YAML row.
"""

from __future__ import annotations

import math
from typing import Any

from fluids.drag import drag_sphere
from fluids.separator import K_separator_demister_York

from ngdesign.contracts import PhaseKind, StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.sizing.souders_brown import souders_brown
from ngdesign.units.separator import Scrubber

__all__ = [
    "ScrubberR1",
    "ScrubberR1SpecError",
    "carryover_mass_flow",
    "cut_diameter_m",
    "liquid_density_kg_m3",
    "rosin_rammler_fines",
    "size_gas_section",
    "york_K_m_s",
]

#: psia per Pa (exact conversion, 1 psi = 6894.757293168 Pa).
_PSIA_PER_PA = 1.0 / 6894.757293168

#: Standard gravity for the terminal-velocity balance [m/s2] (spec S4).
_G = 9.80665

#: Bisection window on the droplet diameter [m] (spec step 7).
_D_LO = 1e-8
_D_HI = 1e-1

#: Relative bisection stop (``hi/lo - 1``) and iteration cap (spec step 7).
_BRACKET_RTOL = 1e-12
_MAX_ITER = 200


class ScrubberR1SpecError(ValueError):
    """A refused scrubber R1 specification (typed ValueError, spec U-R1)."""


def york_K_m_s(P_Pa: float) -> float:
    """S2 York demister K at the drum pressure.

    Svrcek & Monnery (1993) fit of the Otto H. York curve, with P in psia and
    K in ft/s converted at 0.3048 m/ft::

        1  <= P < 15 : K = 0.1821 + 0.0029 P + 0.0460 ln P
        15 <= P <= 40: K = 0.35
        40 <  P <= 5500: K = 0.430 - 0.023 ln P

    The fluids helper returns m/s but silently clamps P outside 1-5500 psia,
    so the range is refused here before the call.

    Args:
        P_Pa: absolute pressure [Pa].

    Returns:
        K [m/s].

    Raises:
        ScrubberR1SpecError: when P is outside 1-5500 psia.
    """
    P_psia = P_Pa * _PSIA_PER_PA
    if not 1.0 <= P_psia <= 5500.0:
        raise ScrubberR1SpecError(
            f"York demister K requires 1-5500 psia, got {P_psia} psia ({P_Pa} Pa); "
            "pass K_m_s explicitly for this pressure"
        )
    return K_separator_demister_York(P_Pa, horizontal=False)


def size_gas_section(
    K_m_s: float,
    rho_liquid: float,
    rho_gas: float,
    gas_flow_m3_s: float,
) -> dict[str, float]:
    """S1 Souders-Brown sizing through the single owner of the equation.

    ``v_max = K sqrt((rho_L - rho_G)/rho_G)`` and
    ``D_min = sqrt(4 Q_G / (pi v_max))`` (GPSA Sect. 7; Svrcek & Monnery 1993),
    computed by :func:`ngdesign.sizing.souders_brown.souders_brown`.

    Args:
        K_m_s: Souders-Brown constant [m/s].
        rho_liquid: liquid density [kg/m3].
        rho_gas: gas density [kg/m3].
        gas_flow_m3_s: actual volumetric gas flow [m3/s].

    Returns:
        dict with ``v_max_m_s`` and ``min_diameter_m``.
    """
    return souders_brown(K_m_s, rho_liquid, rho_gas, gas_flow_m3_s)


def cut_diameter_m(
    v_gas_m_s: float,
    rho_liquid: float,
    rho_gas: float,
    mu_gas_Pa_s: float,
) -> dict[str, float]:
    """S4 cut diameter by bisection on log d over [1e-8, 1e-1] m.

    ``g(d) = 4 g d (rho_L - rho_G) / (3 C_D(Re) rho_G v_G^2) - 1`` with
    ``Re = rho_G v_G d / mu_G`` and g = 9.80665 m/s2; C_D is Morrison (2013)
    through ``fluids.drag.drag_sphere(Re, Method="Morrison")``. g(d) increases
    monotonically in d, so the bisection brackets the root. When even a 10 cm
    drop is carried over (``g(1e-1) < 0``) the cut diameter is ``math.inf``;
    below the window (``g(1e-8) > 0``) the smallest searched droplet already
    settles and the window edge is reported (its fines fraction is ~0 anyway).

    Args:
        v_gas_m_s: actual gas velocity [m/s].
        rho_liquid: liquid density [kg/m3].
        rho_gas: gas density [kg/m3].
        mu_gas_Pa_s: gas viscosity [Pa s].

    Returns:
        dict with ``d_cut_m`` and the droplet Reynolds number ``Re`` at the cut.

    Raises:
        ScrubberR1SpecError: when the bisection hits its 200-iteration cap.
    """

    def g(d: float) -> float:
        Re = rho_gas * v_gas_m_s * d / mu_gas_Pa_s
        C_D = drag_sphere(Re, Method="Morrison")
        return 4.0 * _G * d * (rho_liquid - rho_gas) / (3.0 * C_D * rho_gas * v_gas_m_s**2) - 1.0

    lo, hi = _D_LO, _D_HI
    if g(hi) < 0.0:
        return {"d_cut_m": math.inf, "Re": math.inf}
    if g(lo) > 0.0:
        Re = rho_gas * v_gas_m_s * lo / mu_gas_Pa_s
        return {"d_cut_m": lo, "Re": Re}
    for _ in range(_MAX_ITER):
        mid = 0.5 * (lo + hi)
        if g(mid) < 0.0:
            lo = mid
        else:
            hi = mid
        if hi / lo - 1.0 < _BRACKET_RTOL:
            break
    else:
        raise ScrubberR1SpecError("cut diameter did not converge")
    d_cut = 0.5 * (lo + hi)
    Re = rho_gas * v_gas_m_s * d_cut / mu_gas_Pa_s
    return {"d_cut_m": d_cut, "Re": Re}


def rosin_rammler_fines(d_m: float, droplet_d_rr_m: float, droplet_n_rr: float) -> float:
    """S5 Rosin-Rammler mass fraction finer than d: ``F = 1 - exp(-(d/d_RR)^n_RR)``.

    Rosin & Rammler (1933), as used for separator droplets by Bothamley,
    Oil & Gas Facilities (2013).

    Args:
        d_m: droplet diameter [m].
        droplet_d_rr_m: Rosin-Rammler characteristic size [m].
        droplet_n_rr: Rosin-Rammler spread parameter [-].

    Returns:
        Mass fraction of droplets finer than ``d_m`` [-].
    """
    return 1.0 - math.exp(-((d_m / droplet_d_rr_m) ** droplet_n_rr))


def carryover_mass_flow(
    liquid_mass_flow_kg_s: float,
    inlet_entrained_fraction: float,
    fines_fraction: float,
) -> float:
    """S6 carry-over: ``mdot_co = E mdot_L F(d_cut)`` [kg/s].

    Args:
        liquid_mass_flow_kg_s: R0 liquid-outlet mass flow [kg/s].
        inlet_entrained_fraction: fraction of that liquid reaching the gravity
            section as droplets [-].
        fines_fraction: Rosin-Rammler fraction finer than the cut diameter [-].
    """
    return inlet_entrained_fraction * liquid_mass_flow_kg_s * fines_fraction


def _mass_flow(stream: StreamState) -> float:
    """Stream mass flow [kg/s] from its phases: sum n x mole_fraction x MW/1000."""
    return stream.molar_flow * sum(p.mole_fraction * p.molecular_weight for p in stream.phases) / 1000.0


def liquid_density_kg_m3(*streams: StreamState) -> float:
    """Mass-weighted volumetric mean liquid density [kg/m3] (spec step 3).

    Accepts one or more liquid streams: the weighting runs over every liquid
    phase of every stream, so callers with several liquid outlets (flash_drum
    R1) get the combined mean from this single owner instead of copying it.
    """
    mass = 0.0
    volume = 0.0
    for stream in streams:
        for p in stream.phases:
            if p.kind is PhaseKind.VAPOR:
                continue
            m_phase = p.mole_fraction * stream.molar_flow * p.molecular_weight / 1000.0
            mass += m_phase
            volume += m_phase / p.density
    return mass / volume


def _vapour_phase(stream: StreamState) -> Any:
    """The stream's vapour phase (the R0 gas outlet carries exactly one)."""
    for p in stream.phases:
        if p.kind is PhaseKind.VAPOR:
            return p
    raise ScrubberR1SpecError("gas outlet carries no vapour phase")


class ScrubberR1:
    """Scrubber R1: Souders-Brown sizing and carry-over at a given diameter."""

    inlet_ports: tuple[str, ...] = ("inlet",)
    outlet_ports: tuple[str, ...] = ("gas_out", "liquid_out")

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """The R0 example feed (50 MMSCFD rich wet sweet gas at 20 degC, 500 psia)."""
        return Scrubber.example_case()

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        """Solve the R1 level on top of the R0 flash (spec algorithm, steps 1-10)."""
        diameter = params.get("diameter_m")
        E = params.get("inlet_entrained_fraction")
        d_rr = params.get("droplet_d_rr_m")
        n_rr = params.get("droplet_n_rr")
        K_param = params.get("K_m_s")
        if diameter is not None and diameter <= 0:
            raise ScrubberR1SpecError(f"diameter_m must be positive, got {diameter}")
        if K_param is not None and K_param <= 0:
            raise ScrubberR1SpecError(f"K_m_s must be positive, got {K_param}")
        if E is not None and not 0.0 <= E <= 1.0:
            raise ScrubberR1SpecError(f"inlet_entrained_fraction must be within [0, 1], got {E}")
        # A diameter carry-over calculation requires the entrainment and
        # droplet-distribution params (refusal table); bind them narrowed.
        entrainment = 0.0
        droplet_d_m = 0.0
        droplet_n = 0.0
        if diameter is not None:
            if E is None or d_rr is None or n_rr is None:
                raise ScrubberR1SpecError(
                    "a diameter_m carry-over calculation requires inlet_entrained_fraction, "
                    "droplet_d_rr_m and droplet_n_rr"
                )
            entrainment = float(E)
            droplet_d_m = float(d_rr)
            droplet_n = float(n_rr)
        if d_rr is not None and d_rr <= 0:
            raise ScrubberR1SpecError(f"droplet_d_rr_m must be positive, got {d_rr}")
        if n_rr is not None and n_rr <= 0:
            raise ScrubberR1SpecError(f"droplet_n_rr must be positive, got {n_rr}")

        # Step 1: the R0 flash owns the phase split; dP passes through unchanged.
        r0 = Scrubber().solve(inlets, {"dP": params.get("dP", 0.0)}, thermo)
        gas0 = r0.outlets["gas_out"]
        liq0 = r0.outlets["liquid_out"]
        if gas0.molar_flow <= 0.0 or liq0.molar_flow <= 0.0:
            raise ScrubberR1SpecError("sizing needs both a gas and a liquid outlet with non-zero flow")

        # Step 2: gas properties from the vapour phase of the R0 gas outlet.
        vap = _vapour_phase(gas0)
        rho_G = vap.density
        mu_G = vap.viscosity
        if mu_G is None:
            override = params.get("gas_viscosity_Pa_s")
            if override is None:
                raise ScrubberR1SpecError("the package gives no gas viscosity; pass gas_viscosity_Pa_s")
            mu_G = float(override)
        Q_G = _mass_flow(gas0) / rho_G

        # Step 3: mass-weighted volumetric mean liquid density.
        rho_L = liquid_density_kg_m3(liq0)

        # Step 4: K from the param or the York fit at the drum pressure.
        K = float(K_param) if K_param is not None else york_K_m_s(gas0.P)

        # Step 5: Souders-Brown sizing (always reported).
        size = size_gas_section(K, rho_L, rho_G, Q_G)
        v_max = size["v_max_m_s"]
        info: dict[str, float] = {
            "K_m_s": K,
            "v_max_m_s": v_max,
            "D_min_m": size["min_diameter_m"],
            "rho_gas_kg_m3": rho_G,
            "rho_liquid_kg_m3": rho_L,
            "Q_gas_m3_s": Q_G,
        }

        outlets = dict(r0.outlets)
        if diameter is not None:
            # Steps 6-8: velocity ratio, cut diameter, fines, carry-over.
            v_G = 4.0 * Q_G / (math.pi * float(diameter) ** 2)
            cut = cut_diameter_m(v_G, rho_L, rho_G, mu_G)
            d_cut = cut["d_cut_m"]
            F = 1.0 if math.isinf(d_cut) else rosin_rammler_fines(d_cut, droplet_d_m, droplet_n)
            mdot_L = _mass_flow(liq0)
            mdot_co = carryover_mass_flow(mdot_L, entrainment, F)
            f = mdot_co / mdot_L
            info.update(
                {
                    "v_gas_m_s": v_G,
                    "v_ratio": v_G / v_max,
                    "d_cut_m": d_cut,
                    "fines_fraction": F,
                    "carryover_kg_s": mdot_co,
                    "carryover_mol_fraction": f,
                }
            )
            if f > 0.0:
                # Step 9: the liquid outlet is R0's scaled, never re-flashed (S-24b);
                # the gas outlet is a genuine two-phase mix, so a flash is valid.
                n_G = gas0.molar_flow
                n_L = liq0.molar_flow
                n_total = n_G + f * n_L
                z_mix = {
                    cid: (n_G * gas0.composition.get(cid, 0.0) + f * n_L * liq0.composition.get(cid, 0.0))
                    / n_total
                    for cid in {**gas0.composition, **liq0.composition}
                }
                outlets["liquid_out"] = liq0.model_copy(update={"molar_flow": (1.0 - f) * n_L})
                outlets["gas_out"] = thermo.flash_pt(z_mix, gas0.T, gas0.P, n_total)

        # Step 10: the balance duty, summed exactly as R0 sums it.
        h_in_W = inlets["inlet"].enthalpy * inlets["inlet"].molar_flow
        h_out_W = sum(s.enthalpy * s.molar_flow for s in outlets.values())
        return UnitResult(
            outlets=outlets,
            duty_W=h_out_W - h_in_W,
            power_W=0.0,
            info=info,
        )
