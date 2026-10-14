"""TEG water-activity correlation for the contactor equilibrium (S-29 delta).

Replaces the v1 ideal-solution linearization (``y* = x_w * Psat_H2O/P``, which
ignores the water-activity depression of real TEG solutions) with the
GPSA-recommended Parrish-Won-Baltatu correlation for the activity coefficient
of water in aqueous triethylene glycol.

Model (Parrish, W.R., Won, K.W. and Baltatu, M.E., 1986, "Phase behavior of the
triethylene glycol-water system and dehydration/regeneration design for
extremely low dew point requirements", *Proceedings of the 65th GPA
Convention*, San Antonio, TX; parameterization as documented in Filep, A.-D.,
Todinca, T. and Dumitrel, G.-A., 2022, "Triethylene glycol dehydration of
natural gas", Chem. Biochem. Eng. Q. 36(1) 25-38, eqs. 12-17, doi
10.15255/CABEQ.2021.1998):

    tau = A * x_w / (B * x_TEG)
    ln gamma_w = B * (tanh(tau) - 1) - C * x_TEG**2

    A = exp(-12.792 + 0.03293 T)      # T in K
    B = exp(0.77377 - 0.00695 T)
    C = 0.88874 - 0.001915 T

The water activity follows as ``a_w = gamma_w * x_w``, and the equilibrium
water mole fraction over the TEG phase as

    y* = a_w * Psat_H2O(T) / P      [Poynting and vapor-nonideality terms
                                     neglected; both are small at absorber
                                     conditions, ~5-10 MPa, 280-340 K]

Validity: the correlation was fitted to TEG-water VLE data -- the isopiestic
activity measurements of Herskowitz & Gottlieb (1984, J. Chem. Eng. Data 29,
173; x_w = 0.2-0.95 at 297.6 and 332.6 K) and the GLPC infinite-dilution data
of Parrish et al. (1986; 300-380 K) -- and is the model GPSA recommends for
glycol dehydration design (GPSA Engineering Data Book, 10th ed., 1994).
Accuracy on its own underlying data sets is ~3% AAD on the infinite-dilution
coefficient (Gironi, Maschietti & Piemonte, 2007, ICHEAP-8, Table 2); it is
used here over the natural-gas absorption window (roughly 280-340 K, lean TEG
90-99.9 wt%) and degrades outside the fitted range. Because gamma_w < 1 over
the whole TEG-water frame, the model depresses the equilibrium water content
below the ideal v1 value -- by the largest margin at high TEG purity, which is
what makes tight outlet specs (e.g. 7 lb/MMscf at 98.7 wt% lean TEG) reachable.

Validation against the published numbers above lives in
``tests/units/test_teg_activity_validation.py``.
"""

from __future__ import annotations

import math

from chemicals.vapor_pressure import Psat_IAPWS

__all__ = [
    "water_activity_coefficient",
    "water_activity",
    "activity_equilibrium_slope",
]


def water_activity_coefficient(T: float, x_water: float) -> float:
    """Activity coefficient of water in an aqueous TEG solution (Parrish et al.).

    Args:
        T: Temperature [K].
        x_water: Water mole fraction in the TEG phase [dimensionless].

    Returns:
        ``gamma_w`` [dimensionless]; 1.0 outside the mixture range (pure water
        or pure TEG limit), where the correlation degenerates.

    Raises:
        ValueError: if ``x_water`` is not in [0, 1].
    """
    if not 0.0 <= x_water <= 1.0:
        raise ValueError(f"x_water must be in [0, 1], got {x_water}")

    x_teg = 1.0 - x_water
    if x_teg <= 0.0 or x_water <= 0.0:
        return 1.0

    a_par = math.exp(-12.792 + 0.03293 * T)
    b_par = math.exp(0.77377 - 0.00695 * T)
    c_par = 0.88874 - 0.001915 * T

    tau = a_par * x_water / (b_par * x_teg)
    return math.exp(b_par * (math.tanh(tau) - 1.0) - c_par * x_teg**2)


def water_activity(T: float, x_water: float) -> float:
    """Water activity ``a_w = gamma_w * x_w`` of an aqueous TEG solution [dimensionless]."""
    return water_activity_coefficient(T, x_water) * x_water


def activity_equilibrium_slope(T: float, P: float, x_water: float) -> float:
    """Equilibrium-line slope ``y* = m * x_w`` including TEG activity depression.

    ``m = gamma_w(T, x_w) * Psat_H2O(T) / P`` -- the v1 GPSA-style ideal
    slope divided by the (positive) TEG activity-coefficient depression, so
    the Kremser (S-05) linear form is preserved. Source and validity: see the
    module docstring.

    Args:
        T: Gas/contactor temperature [K].
        P: Gas pressure [Pa abs].
        x_water: Water mole fraction in the (lean) TEG phase [dimensionless].

    Returns:
        Equilibrium slope ``m`` [dimensionless].
    """
    if P <= 0.0:
        raise ValueError(f"pressure must be positive, got {P}")
    return water_activity_coefficient(T, x_water) * Psat_IAPWS(T) / P
