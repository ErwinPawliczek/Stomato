"""Total-condenser free-water decant (S0-1c step 4, issue #235).

With ``condenser_water_decant`` on, the overhead vapour V_1 (composition y_1)
is totally condensed and any free water is drawn off as the internal product
``water_decant``; the reflux and the distillate carry the hydrocarbon liquid
only. The split lives INSIDE the condenser-stage balance: the reflux entering
stage 1 carries the hydrocarbon-liquid composition and enthalpy, so the
graph residual (and its exact gate) see the decant at every iterate.

Method: the free-water phase is pure liquid water, and the water held by the
hydrocarbon liquid is fixed by equality of water fugacity with that phase
(the standard free-water treatment of hydrocarbon/water systems; API
Technical Data Book ch. 9 basis; Aspen Plus "free-water calculations"):

    x_w phi_w^L(x, T, P) = phi_w^0,L(T, P),

with the hydrocarbon part of x in the proportions of y_1. The saturation
x_w* is the first root of g(x_w) = ln x_w + ln phi_w^L(x) - ln phi_w^0,L
from dilute water (Michelsen's pure-water tangent-plane distance, see
``strippers``). When y_1 holds no more water than x_w* the condensate is one
liquid and the decant is exactly zero - the reflux is then y_1 itself, the
plain total condenser bit for bit. Otherwise the free-water fraction of the
condensate is phi = (y_w - x_w*) / (1 - x_w*), from the water and
hydrocarbon balances of the split.

The split is taken at the stage-1 temperature: the plain total condenser
returns its reflux at that state (``inside_out``), so the decanted reflux is
read on the same convention and decant on with no free water there reduces
to decant off exactly (the reflux is y_1 itself). A subcooled drum, which
would decant more water, is not modelled; the free-water refusal of a column
without the decant (``strippers._check_free_water``) tests the condensate at
the same temperature, so the two agree on when free water exists. Measured:
splitting at the condensate's bubble temperature instead cost one
``bubble_point`` (0.26 s) per Jacobian column touching stage 1 - 22 of the
26 s of a 14-stage decanting mesh.
"""

from __future__ import annotations

import math

import scipy.optimize

from ngdesign.contracts import PhaseKind

from .spec import STEAM_COMPONENT
from .thermo_adapter import _ThermoBox

#: Dilute end of the saturation scan (mole fraction of water).
_XW_LO = 1e-10
#: Scan points (log-spaced in x_w) bracketing the first root of g; Brent's
#: method then refines ln x_w* to an absolute 1e-13 (relative 1e-13 in x_w*)
#: within a bounded iteration count.
_XW_SCAN = 24
_XW_LN_TOL = 1e-13
_XW_BRENT_MAX = 100
_EPS = 2.220446049250313e-16
#: Upper end of the scan: past it the liquid is water-rich, and a root there
#: is the pure-water end (g(1) = 0 by construction), not a hydrocarbon-liquid
#: saturation.
_XW_HI = 0.9


def _g(tb: _ThermoBox, hc: dict[str, float], xw: float, t: float, p: float, ln_phi0: float) -> float | None:
    """ln x_w + ln phi_w^L(x) - ln phi_w^0,L at x = (1 - x_w) hc + x_w water."""
    x = {cid: (1.0 - xw) * v for cid, v in hc.items()}
    x[STEAM_COMPONENT] = xw
    try:
        ln_phi = tb._thermo.phase_props(x, t, p, PhaseKind.HC_LIQUID).ln_phi
    except ValueError:
        return None
    if not ln_phi or STEAM_COMPONENT not in ln_phi:
        return None
    return math.log(xw) + ln_phi[STEAM_COMPONENT] - ln_phi0


def water_saturation(tb: _ThermoBox, hc: dict[str, float], t: float, p: float) -> float | None:
    """x_w* of a hydrocarbon liquid of (water-free) composition ``hc`` at (T, P).

    None when no free-water phase can form below ``_XW_HI`` (the package
    holds water and this liquid miscible) or the package has no ln phi.
    """
    try:
        pure = tb._thermo.phase_props({STEAM_COMPONENT: 1.0}, t, p, PhaseKind.AQUEOUS).ln_phi
    except ValueError:
        return None
    if not pure or STEAM_COMPONENT not in pure:
        return None
    ln_phi0 = pure[STEAM_COMPONENT]
    lo = math.log(_XW_LO)
    g_lo = _g(tb, hc, _XW_LO, t, p, ln_phi0)
    if g_lo is None:
        return None
    if g_lo >= 0.0:
        return _XW_LO
    start = lo
    step = (math.log(_XW_HI) - start) / _XW_SCAN
    hi: float | None = None
    for k in range(1, _XW_SCAN + 1):
        point = start + k * step
        g_pt = _g(tb, hc, math.exp(point), t, p, ln_phi0)
        if g_pt is None:
            return None
        if g_pt >= 0.0:
            hi = point
            break
        lo = point
    if hi is None:
        return None

    def g_ln(ln_xw: float) -> float:
        val = _g(tb, hc, math.exp(ln_xw), t, p, ln_phi0)
        if val is None:
            raise ValueError("water fugacity not evaluable inside the saturation bracket")
        return val

    try:
        root = scipy.optimize.brentq(g_ln, lo, hi, xtol=_XW_LN_TOL, rtol=4.0 * _EPS, maxiter=_XW_BRENT_MAX)
    except (ValueError, RuntimeError):
        return None
    return math.exp(float(root))


def decant_split(tb: _ThermoBox, y0: dict[str, float], t: float, p: float) -> tuple[dict[str, float], float]:
    """(reflux/distillate liquid composition, free-water fraction phi of V_1).

    ``phi`` = W / V_1, the share of the condensate drawn off as free water.
    phi = 0 returns ``y0`` itself (the same dict), so a condensate without
    free water is the plain total condenser exactly.
    """
    yw = y0.get(STEAM_COMPONENT, 0.0)
    if yw <= 0.0:
        return y0, 0.0
    hc_total = 1.0 - yw
    if hc_total <= 0.0:
        return y0, 0.0
    hc = {cid: v / hc_total for cid, v in y0.items() if cid != STEAM_COMPONENT and v > 0.0}
    if not hc:
        return y0, 0.0
    xw = water_saturation(tb, hc, t, p)
    if xw is None or yw <= xw:
        return y0, 0.0
    phi = (yw - xw) / (1.0 - xw)
    x = {cid: (1.0 - xw) * hc.get(cid, 0.0) for cid in y0}
    x[STEAM_COMPONENT] = xw
    return x, phi
