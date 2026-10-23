"""AGA 8 DC92 detail characterisation method — gas-phase equation of state.

Python port of NIST's public-domain reference implementation of the AGA
Report No. 8 (1992/1994) Part 1 DETAIL equation of state:

- Source: usnistgov/AGA8 @ ``3bdb9ab8ff317c618b0b59d1b704c2c86ddc5fce``,
  ``AGA8CODE/C/Detail.cpp`` (Lemmon; C++ translation Bell, April 2017).
  Public-domain US-government code, ported with citation per the repo licence
  rules.
- Check values: ``AGA8CODE/C/Detail_test_01.cpp`` in the same commit (the
  21-component example gas at 400 K / 50 000 kPa; the values NIST prints to 16
  digits), validated in ``tests/thermo/test_aga8.py``.

Units follow the reference exactly so the check values carry over 1:1:
T [K], P [kPa], molar density [mol/l], molar mass [g/mol], energies [J/mol],
entropies/heat capacities [J/(mol K)], speed of sound [m/s]. The gas constant
is the reference's ``8.31451`` — do NOT "correct" it; the check values were
generated with it.

The method is gas-phase only. :func:`aga8_dc92_properties` refuses states it
cannot prove are single-phase gas: the density iteration is re-run from a
liquid-side initial guess and if it converges to a different root than the
gas-side solution the state is two-phase/liquid and raises
:class:`Aga8Dc92Error`. The reference implementation's own warning applies:
"no checks are made to determine the phase boundary" — this port adds the
multi-root guard the reference leaves to the user. A deep liquid state whose
isotherm has no second root (T below a pure species' critical point and P well
above its vapour pressure) still yields a single dense root and is not
detected here; full phase-boundary detection is out of scope for the gas-phase
method. Components outside the 21 AGA8 species are refused with the component
named. The :class:`Aga8Dc92Package` adapter below exposes the gas surface on
the ``Thermo`` protocol; the ``aga8_dc92`` catalogue row (``provisional``,
T-16a) points at it.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

from ngdesign.contracts.stream import Phase, PhaseKind, StreamState
from ngdesign.contracts.thermo import PhaseProps, PropertyDerivatives, SaturationPoint

__all__ = [
    "Aga8Dc92Error",
    "Aga8Dc92Package",
    "Dc92Properties",
    "aga8_dc92_properties",
    "dc92_species",
]

_SOURCE_COMMIT = "3bdb9ab8ff317c618b0b59d1b704c2c86ddc5fce"
_R = 8.31451  # J/(mol K), NIST reference value (Detail.cpp SetupDetail)
_EPS = 1e-15
_NT = 58  # EOS terms
_NC = 21  # species


class Aga8Dc92Error(ValueError):
    """A DC92 call was out of scope: unsupported component or non-gas state."""


# ---------------------------------------------------------------------------
# Species tables (Detail.cpp SetupDetail; 1-based C indices flattened to 0-based)
# ---------------------------------------------------------------------------
#
# C index order: 1 methane, 2 nitrogen, 3 carbon dioxide, 4 ethane, 5 propane,
# 6 isobutane, 7 n-butane, 8 isopentane, 9 n-pentane, 10 n-hexane, 11 n-heptane,
# 12 n-octane, 13 n-nonane, 14 n-decane, 15 hydrogen, 16 oxygen,
# 17 carbon monoxide, 18 water, 19 hydrogen sulfide, 20 helium, 21 argon.

# Stomato component id -> 0-based species index.
_SPECIES_INDEX: dict[str, int] = {
    "C1": 0,
    "N2": 1,
    "CO2": 2,
    "C2": 3,
    "C3": 4,
    "IC4": 5,
    "NC4": 6,
    "IC5": 7,
    "NC5": 8,
    "NC6": 9,
    "NC7": 10,
    "NC8": 11,
    "NC9": 12,
    "NC10": 13,
    "H2": 14,
    "O2": 15,
    "CO": 16,
    "H2O": 17,
    "H2S": 18,
    "He": 19,
    "Ar": 20,
    # databank aliases that resolve to the same registry records
    "helium": 19,
    "argon": 20,
}


def dc92_species() -> tuple[str, ...]:
    """Canonical Stomato ids of the 21 AGA8 DC92 species."""
    return tuple(k for k in _SPECIES_INDEX if k not in ("helium", "argon"))


# The coefficient tables below are transcribed 1:1 from the NIST reference C
# sources (Detail.cpp setup tables); the fmt directives keep the compact
# reference layout so the transcription can be diffed against the original.
# fmt: off
_MOLAR_MASS = [  # g/mol
    16.043, 28.0135, 44.01, 30.07, 44.097, 58.123, 58.123, 72.15, 72.15,
    86.177, 100.204, 114.231, 128.258, 142.285, 2.0159, 31.9988, 28.01,
    18.0153, 34.082, 4.0026, 39.948,
]

_A = [  # EOS coefficients a[1..58] -> index 0..57
    0.1538326, 1.341953, -2.998583, -0.04831228, 0.3757965, -1.589575,
    -0.05358847, 0.88659463, -0.71023704, -1.471722, 1.32185035, -0.78665925,
    0.00000000229129, 0.1576724, -0.4363864, -0.04408159, -0.003433888,
    0.03205905, 0.02487355, 0.07332279, -0.001600573, 0.6424706, -0.4162601,
    -0.06689957, 0.2791795, -0.6966051, -0.002860589, -0.008098836, 3.150547,
    0.007224479, -0.7057529, 0.5349792, -0.07931491, -1.418465, -5.99905e-17,
    0.1058402, 0.03431729, -0.007022847, 0.02495587, 0.04296818, 0.7465453,
    -0.2919613, 7.294616, -9.936757, -0.005399808, -0.2432567, 0.04987016,
    0.003733797, 1.874951, 0.002168144, -0.6587164, 0.000205518, 0.009776195,
    -0.02048708, 0.01557322, 0.006862415, -0.001226752, 0.002850908,
]

_B = [  # density exponents b[1..58]
    1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2, 2,
    2, 2, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 4, 4, 4, 4, 4, 4, 4, 5, 5, 5, 5, 5, 6,
    6, 7, 7, 8, 8, 8, 9, 9,
]

_K_EXP = {  # exp(-D^k) exponents kn (default 0)
    13: 3, 14: 2, 15: 2, 16: 2, 17: 4, 18: 4, 21: 2, 22: 2, 23: 2, 24: 4,
    25: 4, 26: 4, 27: 4, 29: 1, 30: 1, 31: 2, 32: 2, 33: 3, 34: 3, 35: 4,
    36: 4, 37: 4, 40: 2, 41: 2, 42: 2, 43: 4, 44: 4, 46: 2, 47: 2, 48: 4,
    49: 4, 51: 2, 53: 2, 54: 1, 55: 2, 56: 2, 57: 2, 58: 2,
}
_K_EXP0 = [(_K_EXP.get(n + 1, 0)) for n in range(_NT)]

_U = [  # temperature exponents un[1..58]
    0.0, 0.5, 1.0, 3.5, -0.5, 4.5, 0.5, 7.5, 9.5, 6.0, 12.0, 12.5, -6.0, 2.0,
    3.0, 2.0, 2.0, 11.0, -0.5, 0.5, 0.0, 4.0, 6.0, 21.0, 23.0, 22.0, -1.0,
    -0.5, 7.0, -1.0, 6.0, 4.0, 1.0, 9.0, -13.0, 21.0, 8.0, -0.5, 0.0, 2.0,
    7.0, 9.0, 22.0, 23.0, 1.0, 9.0, 3.0, 8.0, 23.0, 1.5, 5.0, -0.5, 4.0, 7.0,
    3.0, 0.0, 1.0, 0.0,
]

_FN = frozenset(n - 1 for n in (13, 27, 30, 35))  # high-temperature flag
_GN = frozenset(n - 1 for n in (5, 6, 25, 29, 32, 33, 34, 51, 54, 56))
_QN = frozenset(n - 1 for n in (7, 16, 26, 28, 37, 42, 47, 49, 52, 58))
_SN = frozenset(n - 1 for n in (8, 9))  # dipole flag
_WN = frozenset(n - 1 for n in (10, 11, 12))  # association flag

_EI = [  # energy parameters
    151.3183, 99.73778, 241.9606, 244.1667, 298.1183, 324.0689, 337.6389,
    365.5999, 370.6823, 402.636293, 427.72263, 450.325022, 470.840891,
    489.558373, 26.95794, 122.7667, 105.5348, 514.0156, 296.355, 2.610111,
    119.6299,
]

_KI = [  # size parameters
    0.4619255, 0.4479153, 0.4557489, 0.5279209, 0.583749, 0.6406937,
    0.6341423, 0.6738577, 0.6798307, 0.7175118, 0.7525189, 0.784955,
    0.8152731, 0.8437826, 0.3514916, 0.4186954, 0.4533894, 0.3825868,
    0.4618263, 0.3589888, 0.4216551,
]

_GI = {1: 0.027815, 2: 0.189065, 3: 0.0793, 4: 0.141239, 5: 0.256692,
       6: 0.281835, 7: 0.332267, 8: 0.366911, 9: 0.289731, 10: 0.337542,
       11: 0.383381, 12: 0.427354, 13: 0.469659, 14: 0.034369, 15: 0.021,
       16: 0.038953, 17: 0.3325, 18: 0.0885}  # orientation (default 0)
_QI = {2: 0.69, 17: 1.06775, 18: 0.633276}  # quadrupole (default 0)
_FI = {14: 1.0}  # high-temperature parameter (hydrogen)
_SI = {17: 1.5822, 18: 0.39}  # dipole
_WI = {17: 1.0}  # association

# Binary interaction parameters, keys (i, j) 1-based upper-triangular (default 1.0).
_EIJ = {
    (1, 2): 0.97164, (1, 3): 0.960644, (1, 5): 0.994635, (1, 6): 1.01953,
    (1, 7): 0.989844, (1, 8): 1.00235, (1, 9): 0.999268, (1, 10): 1.107274,
    (1, 11): 0.88088, (1, 12): 0.880973, (1, 13): 0.881067, (1, 14): 0.881161,
    (1, 15): 1.17052, (1, 17): 0.990126, (1, 18): 0.708218, (1, 19): 0.931484,
    (2, 3): 1.02274, (2, 4): 0.97012, (2, 5): 0.945939, (2, 6): 0.946914,
    (2, 7): 0.973384, (2, 8): 0.95934, (2, 9): 0.94552, (2, 15): 1.08632,
    (2, 16): 1.021, (2, 17): 1.00571, (2, 18): 0.746954, (2, 19): 0.902271,
    (3, 4): 0.925053, (3, 5): 0.960237, (3, 6): 0.906849, (3, 7): 0.897362,
    (3, 8): 0.726255, (3, 9): 0.859764, (3, 10): 0.855134, (3, 11): 0.831229,
    (3, 12): 0.80831, (3, 13): 0.786323, (3, 14): 0.765171, (3, 15): 1.28179,
    (3, 17): 1.5, (3, 18): 0.849408, (3, 19): 0.955052, (4, 5): 1.02256,
    (4, 7): 1.01306, (4, 9): 1.00532, (4, 15): 1.16446, (4, 18): 0.693168,
    (4, 19): 0.946871, (5, 7): 1.0049, (5, 15): 1.034787, (6, 15): 1.3,
    (7, 15): 1.3, (10, 19): 1.008692, (11, 19): 1.010126, (12, 19): 1.011501,
    (13, 19): 1.012821, (14, 19): 1.014089, (15, 17): 1.1,
}
_UIJ = {
    (1, 2): 0.886106, (1, 3): 0.963827, (1, 5): 0.990877, (1, 7): 0.992291,
    (1, 9): 1.00367, (1, 10): 1.302576, (1, 11): 1.191904, (1, 12): 1.205769,
    (1, 13): 1.219634, (1, 14): 1.233498, (1, 15): 1.15639, (1, 19): 0.736833,
    (2, 3): 0.835058, (2, 4): 0.816431, (2, 5): 0.915502, (2, 7): 0.993556,
    (2, 15): 0.408838, (2, 19): 0.993476, (3, 4): 0.96987, (3, 10): 1.066638,
    (3, 11): 1.077634, (3, 12): 1.088178, (3, 13): 1.098291, (3, 14): 1.108021,
    (3, 17): 0.9, (3, 19): 1.04529, (4, 5): 1.065173, (4, 6): 1.25,
    (4, 7): 1.25, (4, 8): 1.25, (4, 9): 1.25, (4, 15): 1.61666,
    (4, 19): 0.971926, (10, 19): 1.028973, (11, 19): 1.033754,
    (12, 19): 1.038338, (13, 19): 1.042735, (14, 19): 1.046966,
}
_KIJ = {
    (1, 2): 1.00363, (1, 3): 0.995933, (1, 5): 1.007619, (1, 7): 0.997596,
    (1, 9): 1.002529, (1, 10): 0.982962, (1, 11): 0.983565, (1, 12): 0.982707,
    (1, 13): 0.981849, (1, 14): 0.980991, (1, 15): 1.02326, (1, 19): 1.00008,
    (2, 3): 0.982361, (2, 4): 1.00796, (2, 15): 1.03227, (2, 19): 0.942596,
    (3, 4): 1.00851, (3, 10): 0.910183, (3, 11): 0.895362, (3, 12): 0.881152,
    (3, 13): 0.86752, (3, 14): 0.854406, (3, 19): 1.00779, (4, 5): 0.986893,
    (4, 15): 1.02034, (4, 19): 0.999969, (10, 19): 0.96813, (11, 19): 0.96287,
    (12, 19): 0.957828, (13, 19): 0.952441, (14, 19): 0.948338,
}
_GIJ = {(1, 3): 0.807653, (1, 15): 1.95731, (2, 3): 0.982746,
        (3, 4): 0.370296, (3, 18): 1.67309}
# fmt: on

# Ideal-gas terms n0i[i][1..7] and th0i[i][4..7] (Detail.cpp, verbatim).
_N0I_RAW = [
    [29.83843397, -15999.69151, 4.00088, 0.76315, 0.0046, 8.74432, -4.46921],
    [17.56770785, -2801.729072, 3.50031, 0.13732, -0.1466, 0.90066, 0.0],
    [20.65844696, -4902.171516, 3.50002, 2.04452, -1.06044, 2.03366, 0.01393],
    [36.73005938, -23639.65301, 4.00263, 4.33939, 1.23722, 13.1974, -6.01989],
    [44.70909619, -31236.63551, 4.02939, 6.60569, 3.197, 19.1921, -8.37267],
    [34.30180349, -38525.50276, 4.06714, 8.97575, 5.25156, 25.1423, 16.1388],
    [36.53237783, -38957.80933, 4.33944, 9.44893, 6.89406, 24.4618, 14.7824],
    [43.17218626, -51198.30946, 4.0, 11.7618, 20.1101, 33.1688, 0.0],
    [42.67837089, -45215.83, 4.0, 8.95043, 21.836, 33.4032, 0.0],
    [46.99717188, -52746.83318, 4.0, 11.6977, 26.8142, 38.6164, 0.0],
    [52.07631631, -57104.81056, 4.0, 13.7266, 30.4707, 43.5561, 0.0],
    [57.25830934, -60546.76385, 4.0, 15.6865, 33.8029, 48.1731, 0.0],
    [62.09646901, -66600.12837, 4.0, 18.0241, 38.1235, 53.3415, 0.0],
    [65.93909154, -74131.45483, 4.0, 21.0069, 43.4931, 58.3657, 0.0],
    [13.07520288, -5836.943696, 2.47906, 0.95806, 0.45444, 1.56039, -1.3756],
    [16.8017173, -2318.32269, 3.50146, 1.07558, 1.01334, 0.0, 0.0],
    [17.45786899, -2635.244116, 3.50055, 1.02865, 0.00493, 0.0, 0.0],
    [21.57882705, -7766.733078, 4.00392, 0.01059, 0.98763, 3.06904, 0.0],
    [21.5830944, -6069.035869, 4.0, 3.11942, 1.00243, 0.0, 0.0],
    [10.04639507, -745.375, 2.5, 0.0, 0.0, 0.0, 0.0],
    [10.04639507, -745.375, 2.5, 0.0, 0.0, 0.0, 0.0],
]
_TH0I = [
    [820.659, 178.41, 1062.82, 1090.53],
    [662.738, 680.562, 1740.06, 0.0],
    [919.306, 865.07, 483.553, 341.109],
    [559.314, 223.284, 1031.38, 1071.29],
    [479.856, 200.893, 955.312, 1027.29],
    [438.27, 198.018, 1905.02, 893.765],
    [468.27, 183.636, 1914.1, 903.185],
    [292.503, 910.237, 1919.37, 0.0],
    [178.67, 840.538, 1774.25, 0.0],
    [182.326, 859.207, 1826.59, 0.0],
    [169.789, 836.195, 1760.46, 0.0],
    [158.922, 815.064, 1693.07, 0.0],
    [156.854, 814.882, 1693.79, 0.0],
    [164.947, 836.264, 1750.24, 0.0],
    [228.734, 326.843, 1651.71, 1671.69],
    [2235.71, 1116.69, 0.0, 0.0],
    [1550.45, 704.525, 0.0, 0.0],
    [268.795, 1141.41, 2507.37, 0.0],
    [1833.63, 847.181, 0.0, 0.0],
    [0.0, 0.0, 0.0, 0.0],
    [0.0, 0.0, 0.0, 0.0],
]

# --- SetupDetail() precalculations -----------------------------------------

_KI25 = [k**2.5 for k in _KI]
_EI25 = [e**2.5 for e in _EI]


def _b_row(i: int, j: int) -> list[float]:
    """Bsnij2[i][j][1..18]: second-virial pair coefficients (0-based n)."""
    gi = _GI.get(i, 0.0)
    gj = _GI.get(j, 0.0)
    qi = _QI.get(i, 0.0)
    qj = _QI.get(j, 0.0)
    fi = _FI.get(i, 0.0)
    fj = _FI.get(j, 0.0)
    si = _SI.get(i, 0.0)
    sj = _SI.get(j, 0.0)
    wi = _WI.get(i, 0.0)
    wj = _WI.get(j, 0.0)
    # 0-based i/j here; the binary tables are keyed 1-based
    eij = _EIJ.get((i + 1, j + 1), 1.0)
    gij = _GIJ.get((i + 1, j + 1), 1.0)
    row = [0.0] * 18
    for n in range(18):
        bs = 1.0
        if n in _GN:
            bs *= gij * (gi + gj) / 2.0
        if n in _QN:
            bs *= qi * qj
        if n in _FN:
            bs *= fi * fj
        if n in _SN:
            bs *= si * sj
        if n in _WN:
            bs *= wi * wj
        row[n] = _A[n] * (eij * math.sqrt(_EI[i] * _EI[j])) ** _U[n] * (_KI[i] * _KI[j]) ** 1.5 * bs
    return row


_BSNIJ2 = [[_b_row(i, j) for j in range(_NC)] for i in range(_NC)]

_KIJ5 = [[0.0] * _NC for _ in range(_NC)]
_UIJ5 = [[0.0] * _NC for _ in range(_NC)]
_GIJ5 = [[0.0] * _NC for _ in range(_NC)]
for _i in range(_NC):
    for _j in range(_NC):
        _kij = _KIJ.get((_i + 1, _j + 1), 1.0 if _j >= _i else 1.0)
        _uij = _UIJ.get((_i + 1, _j + 1), 1.0)
        _gij = _GIJ.get((_i + 1, _j + 1), 1.0)
        _KIJ5[_i][_j] = (_kij**5 - 1.0) * _KI25[_i] * _KI25[_j]
        _UIJ5[_i][_j] = (_uij**5 - 1.0) * _EI25[_i] * _EI25[_j]
        _GIJ5[_i][_j] = (_gij - 1.0) * (_GI.get(_i, 0.0) + _GI.get(_j, 0.0)) / 2.0

# Ideal-gas reference-state shift: n0[3] -= 1; n0[1] -= log(d0).
_D0 = 101.325 / _R / 298.15
_N0I = [[row[0] - math.log(_D0), row[1], row[2] - 1.0, row[3], row[4], row[5], row[6]] for row in _N0I_RAW]

del _i, _j, _kij, _uij, _gij


# ---------------------------------------------------------------------------
# Mixture composition terms (Detail.cpp xTermsDetail, uncached)
# ---------------------------------------------------------------------------


def _composition_terms(x: list[float]) -> tuple[list[float], list[float]]:
    """(Bs[1..18], Csn[1..58]) mixture terms; returns 0-based lists."""
    k3 = 0.0
    u = 0.0
    g = 0.0
    q = 0.0
    f = 0.0
    bs = [0.0] * 18
    for i in range(_NC):
        xi = x[i]
        if xi <= 0.0:
            continue
        xi2 = xi * xi
        k3 += xi * _KI25[i]
        u += xi * _EI25[i]
        g += xi * _GI.get(i, 0.0)
        q += xi * _QI.get(i, 0.0)
        f += xi2 * _FI.get(i, 0.0)
        row_i = _BSNIJ2[i][i]
        for n in range(18):
            bs[n] += xi2 * row_i[n]
    k3 *= k3
    u *= u
    for i in range(_NC - 1):
        xi = x[i]
        if xi <= 0.0:
            continue
        for j in range(i + 1, _NC):
            xj = x[j]
            if xj <= 0.0:
                continue
            xij = 2.0 * xi * xj
            k3 += xij * _KIJ5[i][j]
            u += xij * _UIJ5[i][j]
            g += xij * _GIJ5[i][j]
            row_ij = _BSNIJ2[i][j]
            for n in range(18):
                bs[n] += xij * row_ij[n]
    k3 = k3**0.6
    u = u**0.2
    q2 = q * q

    csn = [0.0] * _NT
    for n in range(12, _NT):  # C index 13..58
        c = _A[n] * u ** _U[n]
        if n in _GN:
            c *= g
        if n in _QN:
            c *= q2
        if n in _FN:
            c *= f
        csn[n] = c
    return bs, csn


# ---------------------------------------------------------------------------
# Helmholtz terms (Detail.cpp Alpha0Detail / AlpharDetail, uncached)
# ---------------------------------------------------------------------------


def _alpha0(T: float, d: float, x: list[float]) -> list[float]:
    """Ideal-gas Helmholtz energy and its T-derivatives [a0, da0/dT, T*d2a0/dT2]."""
    log_t = math.log(T)
    log_d = math.log(d) if d > _EPS else math.log(_EPS)
    a00 = 0.0
    a01 = 0.0
    a02 = 0.0
    for i in range(_NC):
        xi = x[i]
        if xi <= 0.0:
            continue
        log_xd = log_d + math.log(xi)
        hyp0 = 0.0
        hyp1 = 0.0
        hyp2 = 0.0
        # th0i rows store C indices 4..7 at python positions 0..3;
        # C j=4,6 use the sinh branch, C j=5,7 the cosh branch;
        # the matching n0i coefficient sits at python index jr+3 (C index jr+4).
        for jr in range(4):
            th = _TH0I[i][jr]
            if th <= 0.0:
                continue
            th_t = th / T
            ep = math.exp(th_t)
            em = 1.0 / ep
            hsn = (ep - em) / 2.0
            hcn = (ep + em) / 2.0
            nj = _N0I[i][jr + 3]
            if jr == 0 or jr == 2:  # C j==4 or j==6 -> sinh branch
                log_hyp = math.log(abs(hsn))
                hyp0 += nj * log_hyp
                hyp1 += nj * (log_hyp - th_t * hcn / hsn)
                hyp2 += nj * (th_t / hsn) ** 2
            else:  # cosh branch
                log_hyp = math.log(abs(hcn))
                hyp0 += -nj * log_hyp
                hyp1 += -nj * (log_hyp - th_t * hsn / hcn)
                hyp2 += +nj * (th_t / hcn) ** 2
        a00 += xi * (log_xd + _N0I[i][0] + _N0I[i][1] / T - _N0I[i][2] * log_t + hyp0)
        a01 += xi * (log_xd + _N0I[i][0] - _N0I[i][2] * (1.0 + log_t) + hyp1)
        a02 += -xi * (_N0I[i][2] + hyp2)
    return [a00 * _R * T, a01 * _R, a02 * _R]


def _alphar(T: float, d: float, x: list[float], itau: bool) -> list[list[float]]:
    """Residual Helmholtz derivatives ar[itau? 2:0][0..3] (Detail.cpp AlpharDetail).

    Returns the 4x4 ar array (only the entries the reference fills:
    ar[0][0..3], plus ar[1][0], ar[1][1], ar[2][0] when itau).
    """
    bs, csn = _composition_terms(x)
    tun = [T ** (-_U[n]) for n in range(_NT)]
    ar = [[0.0] * 4 for _ in range(4)]
    # Dred depends on composition via K3
    k3 = _k3_of(x)
    d_red = k3 * d
    dknn = [1.0]
    for _ in range(9):
        dknn.append(dknn[-1] * d_red)
    expn = [1.0] + [math.exp(-dknn[n]) for n in range(1, 5)]
    rt = _R * T
    for n in range(_NT):
        coef_t1 = _R * (_U[n] - 1.0)
        coef_t2 = coef_t1 * _U[n]
        sum_b = 0.0
        sum0 = 0.0
        coef_d1 = coef_d2 = coef_d3 = 0.0
        if n < 18:
            s = bs[n] * d
            if n >= 12:  # C n>=13
                s += -csn[n] * d_red
            sum_b = s * tun[n]
        if n >= 12:
            sum0 = csn[n] * dknn[_B[n]] * tun[n] * expn[_K_EXP0[n]]
            b = float(_B[n])
            k = float(_K_EXP0[n])
            bkd = b - k * dknn[int(k)]
            ckd = k * k * dknn[int(k)]
            coef_d1 = bkd
            coef_d2 = bkd * (bkd - 1.0) - ckd
            coef_d3 = (bkd - 2.0) * coef_d2 + ckd * (1.0 - k - 2.0 * bkd)
        s0 = sum0 + sum_b
        s1 = sum0 * coef_d1 + sum_b
        s2 = sum0 * coef_d2
        s3 = sum0 * coef_d3
        ar[0][0] += rt * s0
        ar[0][1] += rt * s1
        ar[0][2] += rt * s2
        ar[0][3] += rt * s3
        if itau:
            ar[1][0] -= coef_t1 * s0
            ar[1][1] -= coef_t1 * s1
            ar[2][0] += coef_t2 * s0
    return ar


def _k3_of(x: list[float]) -> float:
    """Mixture size sum K3 (Detail.cpp xTermsDetail K3)."""
    k3: float = 0.0
    for i in range(_NC):
        if x[i] > 0.0:
            k3 += x[i] * _KI25[i]
    k3 *= k3
    for i in range(_NC - 1):
        if x[i] <= 0.0:
            continue
        for j in range(i + 1, _NC):
            if x[j] > 0.0:
                k3 += 2.0 * x[i] * x[j] * _KIJ5[i][j]
    return float(k3**0.6)


# ---------------------------------------------------------------------------
# Pressure / density / properties (Detail.cpp PressureDetail / DensityDetail /
# PropertiesDetail)
# ---------------------------------------------------------------------------


def _pressure(T: float, d: float, x: list[float]) -> tuple[float, float, float]:
    """(P [kPa], Z, dP/dD [kPa/(mol/l)]) at T, D."""
    ar = _alphar(T, d, x, itau=False)
    z = 1.0 + ar[0][1] / _R / T
    p = d * _R * T * z
    dpdd = _R * T + 2.0 * ar[0][1] + ar[0][2]
    return p, z, dpdd


def _density(T: float, p: float, x: list[float], d_init: float | None = None) -> float:
    """Density [mol/l] at T, P (Detail.cpp DensityDetail Newton on log v)."""
    if abs(p) < _EPS:
        return 0.0
    tolr = 1e-7
    # d_init < 0 in the reference means "use as initial estimate"; here a
    # positive d_init always seeds the iteration, else ideal-gas start.
    d = abs(d_init) if d_init is not None else p / _R / T
    plog = math.log(p)
    vlog = -math.log(d)
    for _ in range(20):
        if vlog < -7.0 or vlog > 100.0:
            raise Aga8Dc92Error("DC92 density iteration failed to converge (ideal-gas fallback refused)")
        d = math.exp(-vlog)
        p2, _z, dpdd = _pressure(T, d, x)
        if dpdd < _EPS or p2 < _EPS:
            vlog += 0.1
            continue
        dpdlv = -d * dpdd
        vdiff = (math.log(p2) - plog) * p2 / dpdlv
        vlog -= vdiff
        if abs(vdiff) < tolr:
            return math.exp(-vlog)
    raise Aga8Dc92Error("DC92 density iteration failed to converge (ideal-gas fallback refused)")


@dataclass(frozen=True)
class Dc92Properties:
    """Gas-phase DC92 properties in the NIST reference units."""

    temperature: float  # K
    pressure: float  # kPa
    molar_density: float  # mol/l
    z_factor: float  # -
    molar_mass: float  # g/mol
    internal_energy: float  # J/mol
    enthalpy: float  # J/mol
    entropy: float  # J/(mol K)
    cp: float  # J/(mol K)
    cv: float  # J/(mol K)
    sound_speed: float  # m/s
    gibbs: float  # J/mol
    joule_thomson: float  # K/kPa
    isentropic_exponent: float  # -


def aga8_dc92_properties(composition: Mapping[str, float], T: float, P: float) -> Dc92Properties:
    """Gas-phase AGA8 DC92 properties at ``T`` [K] and ``P`` [kPa].

    ``composition`` maps Stomato component ids to mole fractions over the 21
    DC92 species (see :func:`dc92_species`). Raises :class:`Aga8Dc92Error` for
    components outside the species set and for states that are not provably
    single-phase gas (multi-root density probe, see module docstring).
    """
    if T <= 0.0:
        raise Aga8Dc92Error(f"temperature must be positive, got T={T}")
    x = [0.0] * _NC
    total = 0.0
    for cid, frac in composition.items():
        idx = _SPECIES_INDEX.get(cid)
        if idx is None:
            raise Aga8Dc92Error(
                f"component {cid!r} is outside the 21 AGA8 DC92 species; "
                f"supported: {', '.join(sorted(dc92_species()))}"
            )
        if frac < 0.0:
            raise Aga8Dc92Error(f"negative mole fraction for {cid!r}: {frac}")
        x[idx] = frac
        total += frac
    if total <= 0.0:
        raise Aga8Dc92Error("composition is empty")
    if abs(total - 1.0) > 1e-9:
        x = [xi / total for xi in x]

    # Gas root from the ideal-gas start (the reference's default path).
    d_gas = _density(T, P, x)
    # Multi-root probe: a converged liquid-side root means the state is not a
    # provable single-phase gas (the reference leaves this check to the user).
    d_ideal = P / _R / T
    d_probe = _density(T, P, x, d_init=min(10.0 * d_ideal, 100.0))
    if abs(d_probe - d_gas) > 1e-6 * d_gas:
        raise Aga8Dc92Error(
            f"state T={T} K, P={P} kPa is not provably gas: the DC92 pressure "
            f"function has multiple density roots ({d_gas:.6g} vs {d_probe:.6g} mol/l)"
        )

    mm = sum(x[i] * _MOLAR_MASS[i] for i in range(_NC))
    a0 = _alpha0(T, d_gas, x)
    ar = _alphar(T, d_gas, x, itau=True)
    p, z, dpdd = _pressure(T, d_gas, x)
    dpdt = d_gas * _R + d_gas * ar[1][1]
    internal = a0[0] + ar[0][0] + T * (-a0[1] - ar[1][0])
    entropy = -a0[1] - ar[1][0]
    cv = -(a0[2] + ar[2][0])
    if d_gas > _EPS:
        enthalpy = internal + p / d_gas
        gibbs = a0[0] + ar[0][0] + p / d_gas
        cp = cv + T * (dpdt / d_gas) ** 2 / dpdd
        jt = (T / d_gas * dpdt / dpdd - 1.0) / cp / d_gas
    else:
        enthalpy = internal + _R * T
        gibbs = a0[0] + ar[0][0] + _R * T
        cp = cv + _R
        jt = 1e20
    w2 = 1000.0 * cp / cv * dpdd / mm
    sound_speed = math.sqrt(w2) if w2 > 0.0 else 0.0
    kappa = sound_speed * sound_speed * mm / (_R * T * 1000.0 * z)
    return Dc92Properties(
        temperature=T,
        pressure=p,
        molar_density=d_gas,
        z_factor=z,
        molar_mass=mm,
        internal_energy=internal,
        enthalpy=enthalpy,
        entropy=entropy,
        cp=cp,
        cv=cv,
        sound_speed=sound_speed,
        gibbs=gibbs,
        joule_thomson=jt,
        isentropic_exponent=kappa,
    )


class Aga8Dc92Package:
    """AGA 8 DC92 gas-phase property package (kind ``thermo``).

    Vapour-only adapter over :func:`aga8_dc92_properties`: a single vapour phase
    at (T, P) from the PT flash, vapour :meth:`phase_props`, and typed refusals
    for everything the DC92 detail characterisation does not model — liquid-like
    phases, saturation and two-phase flashes, enthalpy/entropy-driven flashes,
    and fugacity derivatives. Pure-component saturation pressure and K-values
    are ``None`` (no saturation model), which the L0 gate reads as "not
    applicable" for a gas-only package.
    """

    def _props(self, z: dict[str, float], T: float, P: float) -> Dc92Properties:
        # Protocol pressures are Pa absolute; the DC92 kernel works in kPa.
        return aga8_dc92_properties(z, T, P / 1000.0)

    def _vapour_phase(self, z: dict[str, float], T: float, P: float) -> Phase:
        pr = self._props(z, T, P)
        # kernel molar_density is mol/L and molar_mass g/mol -> kg/m3.
        return Phase(
            kind=PhaseKind.VAPOR,
            mole_fraction=1.0,
            composition=dict(z),
            density=pr.molar_density * pr.molar_mass,
            molecular_weight=pr.molar_mass,
            z_factor=pr.z_factor,
            enthalpy=pr.enthalpy,
            entropy=pr.entropy,
            cp=pr.cp,
        )

    def flash_pt(self, z: dict[str, float], T: float, P: float, molar_flow: float) -> StreamState:
        ph = self._vapour_phase(z, T, P)
        return StreamState(
            T=T,
            P=P,
            molar_flow=molar_flow,
            composition=dict(z),
            vapor_fraction=1.0,
            enthalpy=ph.enthalpy,
            entropy=ph.entropy,
            phases=[ph],
        )

    def flash_ph(self, z: dict[str, float], P: float, H: float, molar_flow: float) -> StreamState:
        raise Aga8Dc92Error(
            "AGA8 DC92 is a gas-only characterisation: enthalpy-driven flashes need a "
            "saturation/two-phase inversion this package does not model"
        )

    def flash_ps(self, z: dict[str, float], P: float, S: float, molar_flow: float) -> StreamState:
        raise Aga8Dc92Error(
            "AGA8 DC92 is a gas-only characterisation: entropy-driven flashes need a "
            "saturation/two-phase inversion this package does not model"
        )

    def flash_tvf(self, z: dict[str, float], T: float, vf: float, molar_flow: float) -> StreamState:
        raise Aga8Dc92Error("AGA8 DC92 has no liquid phase: vapour-fraction flashes are unsupported")

    def flash_pvf(self, z: dict[str, float], P: float, vf: float, molar_flow: float) -> StreamState:
        raise Aga8Dc92Error("AGA8 DC92 has no liquid phase: vapour-fraction flashes are unsupported")

    def bubble_point(
        self, z: dict[str, float], *, T: float | None = None, P: float | None = None
    ) -> SaturationPoint:
        raise Aga8Dc92Error("AGA8 DC92 models gas only: no bubble point")

    def dew_point(
        self, z: dict[str, float], *, T: float | None = None, P: float | None = None
    ) -> SaturationPoint:
        raise Aga8Dc92Error("AGA8 DC92 models gas only: no dew point")

    def k_values(self, z: dict[str, float], T: float, P: float) -> dict[str, float] | None:
        return None

    def phase_props(self, composition: dict[str, float], T: float, P: float, kind: PhaseKind) -> PhaseProps:
        if kind is not PhaseKind.VAPOR:
            raise Aga8Dc92Error(f"AGA8 DC92 supports vapour phase properties only, got {kind}")
        pr = self._props(composition, T, P)
        return PhaseProps(
            kind=PhaseKind.VAPOR,
            mole_fraction=1.0,
            composition=dict(composition),
            molecular_weight=pr.molar_mass,
            density=pr.molar_density * pr.molar_mass,
            enthalpy=pr.enthalpy,
            entropy=pr.entropy,
            cp=pr.cp,
            gibbs=pr.gibbs,
            z_factor=pr.z_factor,
        )

    def derivatives(
        self, composition: dict[str, float], T: float, P: float, kind: PhaseKind
    ) -> PropertyDerivatives:
        raise Aga8Dc92Error("AGA8 DC92 exposes no fugacity model: ln phi derivatives are unsupported")

    def pure_psat(self, cid: str, T: float) -> float | None:
        return None
