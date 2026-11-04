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

The split is taken at the condensate's saturated state - the decanter
drum with zero subcooling (``saturated_decant``). A total condenser returns
its liquid at the bubble point (Seader, Henley & Roper, Separation Process
Principles 3rd ed., §10.3); for a condensate that separates into a
hydrocarbon liquid and free water that is the HETEROGENEOUS bubble point, the
temperature at which both liquids coexist with incipient vapour (Seader,
Henley & Roper ch. 4, three-phase vapour-liquid-liquid equilibrium of
hydrocarbon-water systems; the reflux drum of a steam-stripped column is
such a three-phase separator, Kister, Distillation Design, McGraw-Hill 1992).
At it the water-saturated hydrocarbon liquid is itself at its bubble point,
because its water fugacity equals the free water's, so

    T* = T_bub(x_hc(T*), P),

solved by secant from the single-liquid bubble point T_bub(y_1). The
stage-1 temperature (the vapour's dew point) is not a state the condensate
can hold as liquid: above its bubble point it would partly boil. A subcooled
drum (a specified drum temperature, the usual refinery overhead practice;
Watkins, Petroleum Refinery Distillation 2nd ed. (1979) ch. 2) is not
modelled. When the condensate holds no free water at T_bub(y_1) it is one
liquid there and the state is the plain total condenser's exactly. The
free-water refusal of a column without the decant
(``strippers._check_free_water``) tests the condensate at that same
single-liquid bubble point, so the two agree on when free water exists.
"""

from __future__ import annotations

import math
from collections.abc import Callable

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


#: Secant tolerance on the heterogeneous bubble temperature (K): two decades
#: above the package bubble point's own resolution (1e-8 relative on T).
_T_STAR_TOL = 1e-6
_T_STAR_MAX = 30


def saturated_decant(
    tb: _ThermoBox,
    y0: dict[str, float],
    t_fallback: float,
    p: float,
    bubble: Callable[[dict[str, float]], float | None],
) -> tuple[dict[str, float], float, float]:
    """(hydrocarbon-liquid composition, free-water fraction phi of V_1, T) of a
    decanting total condenser at its saturated (heterogeneous bubble) state.

    T solves T = T_bub(x_hc(T), P) (module docstring), where x_hc(T) is the
    hydrocarbon liquid of ``decant_split`` at T and T_bub the column's bubble
    temperature of a liquid at P (``bubble``: the plain condenser's own,
    ``inside_out._saturated_liquid_temperature``). No free water at the
    single-liquid bubble point T_bub(y_1) returns (y_1, 0, T_bub(y_1)) - the
    plain total condenser. ``t_fallback`` stands in for a bubble point the
    package cannot evaluate (super-critical overhead).
    """
    t0 = bubble(y0)
    if t0 is None:
        t0 = t_fallback
    x0, phi0 = decant_split(tb, y0, t0, p)
    if phi0 <= 0.0:
        return y0, 0.0, t0

    def g(t: float) -> tuple[float, dict[str, float], float] | None:
        x, phi = decant_split(tb, y0, t, p)
        t_bub = bubble(x)
        if t_bub is None:
            return None
        return t_bub - t, x, phi

    first = g(t0)
    if first is None:
        return x0, phi0, t0
    ta, (ga, xa, phia) = t0, first
    tb_ = ta + ga  # fixed-point step: T_1 = T_bub(x_hc(T_0))
    for _ in range(_T_STAR_MAX):
        nxt = g(tb_)
        if nxt is None:
            break
        gb, xb, phib = nxt
        if abs(gb) <= _T_STAR_TOL:
            return xb, phib, tb_
        slope = (gb - ga) / (tb_ - ta) if tb_ != ta else -1.0
        step = -gb / slope if slope < 0.0 else gb  # secant; fixed point if non-contracting
        ta, ga = tb_, gb
        tb_ = tb_ + step
        xa, phia = xb, phib
    return xa, phia, ta
