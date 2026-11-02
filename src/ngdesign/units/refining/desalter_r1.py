"""Desalter R1: Stokes settling with a two-population drop model (``specs/backend/units/desalter.md``).

No open source with printed numbers gives a desalting-efficiency correlation in wash
rate and temperature, so R1 computes R0's two split parameters from a physical model.

- Upward oil velocity in the settling zone: U = Q_oil/A.
- Stokes terminal velocity of a water drop (Stokes 1851; Perry's, gravity decanters),
  v(d) = g*d**2*(rho_w - rho_o)/(18*mu_o); a drop falls against the rising oil only if
  v(d) > U, so the cut diameter is d_c = sqrt(18*mu_o*U/(g*(rho_w - rho_o))).
- Rosin & Rammler (1933) drop sizes by volume, F(d) = 1 - exp(-(d/dbar)**n), with
  dbar = d50/(ln 2)**(1/n) so that F(d50) = 0.5.
- A fraction eps of the brine B has coalesced with all the wash water W, median d50_mixed;
  the rest stays as fine emulsion, median d50_fine.  With c_m, c_f the fractions finer than
  d_c: water to crude = c_m*(eps*B + W) + c_f*(1 - eps)*B, and salt to crude is
  S*(eps*c_m + (1 - eps)*c_f).

R0 owns the split, the flashes and the duty, called at the computed fractions.

Oil and water densities and the oil viscosity are required params (the spec's option B),
because no package gives honest values for a pseudo crude: every one returns no viscosity
and densities well off real ones, and the Peneloux packages invert the density difference.
The temperature effect therefore comes only through the properties the user supplies at T.
"""

from __future__ import annotations

import math
from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.data import component_record
from ngdesign.units.pump import G_STD
from ngdesign.units.refining._cuts import RefiningSpecError, optional_float, require_float
from ngdesign.units.refining.desalter import SALT_ID, WATER_ID, Desalter
from ngdesign.units.separation.scrubber_r1 import rosin_rammler_fines


def _splits(
    Q_oil: float,
    A: float,
    rho_o: float,
    rho_w: float,
    mu_o: float,
    d50_mixed: float,
    d50_fine: float,
    n: float,
    eps: float,
    B: float,
    W: float,
) -> tuple[float, float, float, float, float, float]:
    """(U, d_c, c_m, c_f, water_carryover_frac, salt_removal); SI, drop sizes in m."""
    u = Q_oil / A
    d_c = math.sqrt(18.0 * mu_o * u / (G_STD * (rho_w - rho_o)))
    dbar = math.log(2.0) ** (-1.0 / n)
    c_m = rosin_rammler_fines(d_c, d50_mixed * dbar, n)
    c_f = rosin_rammler_fines(d_c, d50_fine * dbar, n)
    carried = c_m * (eps * B + W) + c_f * (1.0 - eps) * B
    return u, d_c, c_m, c_f, carried / (B + W), 1.0 - (eps * c_m + (1.0 - eps) * c_f)


def _positive(params: dict[str, Any], key: str) -> float:
    value = require_float(params, key)
    if value <= 0.0:
        raise RefiningSpecError(f"{key}: must be > 0")
    return value


class DesalterR1:
    """Desalter whose water and salt splits come from Stokes settling, level R1."""

    inlet_ports: tuple[str, ...] = ("crude_in", "wash_in")
    outlet_ports: tuple[str, ...] = ("crude_out", "water_out")

    def solve(self, inlets: dict[str, StreamState], params: dict[str, Any], thermo: Thermo) -> UnitResult:
        for key in ("water_carryover_frac", "salt_removal"):
            if key in params:
                raise RefiningSpecError(f"{key}: computed at R1, use level R0 to specify it")
        temperature = require_float(params, "T")
        area = _positive(params, "settling_area_m2")
        d50_mixed = _positive(params, "d50_mixed_um") * 1.0e-6
        d50_fine = _positive(params, "d50_fine_um") * 1.0e-6
        n = _positive(params, "rosin_rammler_n")
        eps = require_float(params, "mixing_efficiency")
        if not 0.0 <= eps <= 1.0:
            raise RefiningSpecError("mixing_efficiency: must be in [0, 1]")
        rho_o = _positive(params, "rho_oil_kg_m3")
        rho_w = _positive(params, "rho_water_kg_m3")
        mu_o = _positive(params, "mu_oil_Pa_s")
        if rho_w <= rho_o:
            raise RefiningSpecError(
                f"rho_water_kg_m3 {rho_w} is not above rho_oil_kg_m3 {rho_o}: density, no settling"
            )

        crude, wash = inlets["crude_in"], inlets["wash_in"]
        flows = crude.component_flows()
        brine = flows.get(WATER_ID, 0.0)
        water = wash.component_flows().get(WATER_ID, 0.0)
        if brine + water <= 0.0:
            raise RefiningSpecError("neither crude_in nor wash_in carries water")
        mass_oil = math.fsum(
            n_i * float(component_record(cid)["mw"]) / 1000.0
            for cid, n_i in flows.items()
            if cid not in (WATER_ID, SALT_ID)
        )
        u, d_c, c_m, c_f, carryover, salt_removal = _splits(
            mass_oil / rho_o, area, rho_o, rho_w, mu_o, d50_mixed, d50_fine, n, eps, brine, water
        )
        r0 = Desalter().solve(
            inlets,
            {
                "T": temperature,
                "dP": optional_float(params, "dP", 0.0),
                "water_carryover_frac": carryover,
                "salt_removal": salt_removal,
            },
            thermo,
        )
        info = {
            **r0.info,
            "oil_velocity_m_s": u,
            "cut_diameter_um": d_c * 1.0e6,
            "carryover_mixed": c_m,
            "carryover_fine": c_f,
            "water_carryover_frac": carryover,
            "salt_removal": salt_removal,
            "rho_oil_kg_m3": rho_o,
            "rho_water_kg_m3": rho_w,
            "mu_oil_Pa_s": mu_o,
        }
        return UnitResult(outlets=r0.outlets, duty_W=r0.duty_W, power_W=0.0, info=info)

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """The R0 feeds with the spec's arithmetic-check inputs.  Test values, not defaults."""
        feeds, params = Desalter.example_case()
        return feeds, {
            "T": params["T"],
            "dP": params["dP"],
            "settling_area_m2": 200.0,
            "d50_mixed_um": 300.0,
            "d50_fine_um": 20.0,
            "rosin_rammler_n": 2.5,
            "mixing_efficiency": 0.9,
            "rho_oil_kg_m3": 850.0,
            "rho_water_kg_m3": 935.0,
            "mu_oil_Pa_s": 2.0e-3,
        }
