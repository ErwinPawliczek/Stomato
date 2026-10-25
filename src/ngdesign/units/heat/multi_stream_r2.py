"""Multi-stream R2: plate-fin geometry and correlations (spec step 3 pure functions).

Spec ``specs/backend/units/multi_stream.md`` (R2). Each active stream gets an
offset-strip-fin layer geometry instead of a given ``hA``; this module holds
the per-layer geometry and the correlations as pure functions, with no state
and no thermodynamics:

- **Per-layer geometry** (Manglik & Bergles 1995, Exp. Therm. Fluid Sci.
  10:171): hydraulic diameter, the dimensionless fin parameters
  (alpha = s/h_f, delta = t/l, gamma = t/s), the free-flow area per layer and
  the heat-transfer area per layer (fin plus parting sheet; Shah & Sekulic,
  *Fundamentals of Heat Exchanger Design*, 2003, section 8.2).
- **Single-phase surface performance**: the Manglik & Bergles (1995) Colburn
  ``j`` and Fanning ``f`` correlations (their equation 34 pair), valid over
  the fitted range 120 < Re < 10^4 without extrapolation checks here (the
  adapter owns refusal policy). ``h = j*G*cp*Pr^(-2/3)``.
- **Fin efficiency**: ``eta_f = tanh(m L_f)/(m L_f)`` with
  ``m = sqrt(2 h/(k_fin t))`` and ``L_f = h_f/2`` for a fin between two
  parting sheets of the same stream; surface efficiency
  ``eta_o = 1 - (A_fin/A_ht)(1 - eta_f)`` with ``A_fin/A_ht = h_f/(s + h_f)``
  (Shah & Sekulic section 4.3).

The R2 adapter (:class:`MultiStreamR2`, spec step 4) applies the tube-side
condensation (``ht.Shah``) and boiling (``ht.Liu_Winterton``) correlations to
plate-fin channels through the hydraulic diameter - a stated approximation
(Shah 1979; Liu & Winterton 1991) documented there.

U-R2: private helpers live in the owning unit module and are consolidated by
the orchestrator later.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ngdesign.units.heat.multi_stream_r1 import MultiStreamRatingError

#: Aluminium alloy fin thermal conductivity default, W/(m K) (spec params).
K_FIN_DEFAULT_W_MK = 180.0

#: Default zone count for the R2 zone loop (spec algorithm step 5).
N_ZONES_DEFAULT = 20

#: Zone-loop outer iteration cap (spec algorithm step 5e).
ZONE_MAX_ITERATIONS = 30

#: Zone-loop outlet-temperature convergence, K (spec algorithm step 5e).
ZONE_TOL_K = 1e-6


@dataclass(frozen=True)
class FinGeometry:
    """One stream's offset-strip-fin layer geometry (pure; spec R2 params)."""

    fin_height_m: float
    fin_spacing_m: float
    fin_thickness_m: float
    strip_length_m: float

    @property
    def alpha(self) -> float:
        """``s/h_f`` (Manglik & Bergles 1995; spec R2 equation 1)."""
        return self.fin_spacing_m / self.fin_height_m

    @property
    def delta(self) -> float:
        """``t/l`` (Manglik & Bergles 1995; spec R2 equation 1)."""
        return self.fin_thickness_m / self.strip_length_m

    @property
    def gamma(self) -> float:
        """``t/s`` (Manglik & Bergles 1995; spec R2 equation 1)."""
        return self.fin_thickness_m / self.fin_spacing_m


def osf_hydraulic_diameter_m(geom: FinGeometry) -> float:
    """Offset-strip-fin hydraulic diameter, m (Manglik & Bergles 1995).

    ``D_h = 4 s h_f l / [2 (s l + h_f l + t h_f) + t s]`` - the spec R2
    equation 1; the test geometry reproduces 0.00232730508 m.
    """
    s, h_f, t, strip_length = (
        geom.fin_spacing_m,
        geom.fin_height_m,
        geom.fin_thickness_m,
        geom.strip_length_m,
    )
    return 4.0 * s * h_f * strip_length / (2.0 * (s * strip_length + h_f * strip_length + t * h_f) + t * s)


def osf_channels_per_layer(fin_spacing_m: float, fin_thickness_m: float, layer_width_m: float) -> float:
    """Number of fin channels in one layer, ``layer_width/(s + t)`` (spec R2)."""
    return layer_width_m / (fin_spacing_m + fin_thickness_m)


def osf_free_flow_area_m2(geom: FinGeometry, layer_width_m: float) -> float:
    """Free-flow area of one layer, ``A_ff = s h_f n_channels`` (spec R2)."""
    n = osf_channels_per_layer(geom.fin_spacing_m, geom.fin_thickness_m, layer_width_m)
    return geom.fin_spacing_m * geom.fin_height_m * n


def osf_heat_transfer_area_m2(geom: FinGeometry, length_m: float, layer_width_m: float) -> float:
    """Heat-transfer area of one layer, ``A_ht = 2 (s + h_f) L n_channels``.

    Fin plus parting-sheet area (Shah & Sekulic 2003, section 8.2; spec R2
    equation 1).
    """
    n = osf_channels_per_layer(geom.fin_spacing_m, geom.fin_thickness_m, layer_width_m)
    return 2.0 * (geom.fin_spacing_m + geom.fin_height_m) * length_m * n


def manglik_bergles_j(Re: float, alpha: float, delta: float, gamma: float) -> float:
    """Colburn ``j`` factor of an offset-strip-fin surface.

    Manglik & Bergles 1995, Exp. Therm. Fluid Sci. 10:171 (equation 34 pair):

        j = 0.6522 Re^-0.5403 alpha^-0.1541 delta^0.1499 gamma^-0.0678
            [1 + 5.269e-5 Re^1.340 alpha^0.504 delta^0.456 gamma^-1.055]^0.1
    """
    return float(
        0.6522
        * Re**-0.5403
        * alpha**-0.1541
        * delta**0.1499
        * gamma**-0.0678
        * (1.0 + 5.269e-5 * Re**1.340 * alpha**0.504 * delta**0.456 * gamma**-1.055) ** 0.1
    )


def manglik_bergles_f(Re: float, alpha: float, delta: float, gamma: float) -> float:
    """Fanning friction factor of an offset-strip-fin surface.

    Manglik & Bergles 1995, Exp. Therm. Fluid Sci. 10:171 (the friction
    member of the equation 34 pair):

        f = 9.6243 Re^-0.7422 alpha^-0.1856 delta^0.3053 gamma^-0.2659
            [1 + 7.669e-8 Re^4.429 alpha^0.920 delta^3.767 gamma^0.236]^0.1
    """
    return float(
        9.6243
        * Re**-0.7422
        * alpha**-0.1856
        * delta**0.3053
        * gamma**-0.2659
        * (1.0 + 7.669e-8 * Re**4.429 * alpha**0.920 * delta**3.767 * gamma**0.236) ** 0.1
    )


def fin_conductance_parameter_1_m(h_W_m2K: float, k_fin_W_mK: float, fin_thickness_m: float) -> float:
    """Fin parameter ``m = sqrt(2 h/(k_fin t))``, 1/m (spec R2 equation 3)."""
    if fin_thickness_m <= 0.0 or k_fin_W_mK <= 0.0:
        raise MultiStreamRatingError(
            f"param fin geometry must be positive: k_fin {k_fin_W_mK}, t {fin_thickness_m}"
        )
    return math.sqrt(2.0 * h_W_m2K / (k_fin_W_mK * fin_thickness_m))


def fin_efficiency(h_W_m2K: float, k_fin_W_mK: float, geom: FinGeometry) -> tuple[float, float]:
    """Fin efficiency ``eta_f = tanh(m L_f)/(m L_f)`` with ``L_f = h_f/2``.

    A strip fin between two parting sheets of the same stream (spec R2
    equation 3). Returns ``(m, eta_f)``.
    """
    m = fin_conductance_parameter_1_m(h_W_m2K, k_fin_W_mK, geom.fin_thickness_m)
    m_L_f = m * geom.fin_height_m / 2.0
    return m, math.tanh(m_L_f) / m_L_f


def surface_efficiency(h_W_m2K: float, k_fin_W_mK: float, geom: FinGeometry) -> float:
    """Overall surface efficiency ``eta_o = 1 - (A_fin/A_ht)(1 - eta_f)``.

    With ``A_fin/A_ht = h_f/(s + h_f)`` (Shah & Sekulic 2003, section 4.3;
    spec R2 equation 3).
    """
    _, eta_f = fin_efficiency(h_W_m2K, k_fin_W_mK, geom)
    A_fin_over_A_ht = geom.fin_height_m / (geom.fin_spacing_m + geom.fin_height_m)
    return 1.0 - A_fin_over_A_ht * (1.0 - eta_f)
