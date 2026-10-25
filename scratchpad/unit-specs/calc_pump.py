"""Independent check of the pump R1 spec's closed-form chain (specs/backend/units/pump.md).

Recomputes the printed measured inlet values and the closed-form expectations
from the spec's equations, using pr for the inlet state only (the property
source the spec's measured values came from) and plain arithmetic for
everything else. Prints full precision so the test tolerances can be judged
against the spec's printed (truncated) digits.
"""

import math

from ngdesign import registry
from ngdesign.units.pump import G_STD, _liquid_density

FEED = {
    "T": 293.15,
    "P": 1.0e6,
    "molar_flow": 5.0,
    "composition": {
        "C3": 0.35,
        "iC4": 0.15,
        "nC4": 0.25,
        "iC5": 0.10,
        "nC5": 0.10,
        "C6+": 0.05,
    },
}

thermo = registry.create("thermo", "pr")
z = FEED["composition"]
inlet = thermo.flash_pt(z, FEED["T"], FEED["P"], FEED["molar_flow"])

rho = _liquid_density(inlet)
Q = inlet.mass_flow / rho

print(f"rho_L      = {rho!r}")
print(f"mass_flow  = {inlet.mass_flow!r}")
print(f"Q          = {Q!r}")

# Closed-form 1: speed 1, linear curve H = 80 - 40000*Q, eta = 0.40 + 500*Q.
H1 = 80.0 - 40000.0 * Q
eta1 = 0.40 + 500.0 * Q
dP1 = rho * G_STD * H1
P_out1 = inlet.P + dP1
shaft1 = Q * dP1 / eta1
print(f"CF1: H = {H1!r}  eta = {eta1!r}")
print(f"CF1: dP = {dP1!r}  P_out = {P_out1!r}  shaft = {shaft1!r}")

# Closed-form 2: speed ratio 1.1: Q_eq = Q/s, H = s^2 (80 - 40000 Q_eq).
s = 1.1
Q_eq2 = Q / s
H2 = s**2 * (80.0 - 40000.0 * Q_eq2)
eta2 = 0.40 + 500.0 * Q_eq2
dP2 = rho * G_STD * H2
P_out2 = inlet.P + dP2
shaft2 = Q * dP2 / eta2
print(f"CF2: Q_eq = {Q_eq2!r}  H = {H2!r}  eta = {eta2!r}")
print(f"CF2: dP = {dP2!r}  P_out = {P_out2!r}  shaft = {shaft2!r}")

# NPSHa: P_v = bubble point at T_in; NPSHa = (P_in - P_v)/(rho g) + z_s - h_f.
P_v = thermo.bubble_point(z, T=FEED["T"]).P
npsha_0 = (inlet.P - P_v) / (rho * G_STD)
npsha_3 = npsha_0 + 3.0 - 0.5
print(f"P_v        = {P_v!r}")
print(f"NPSHa(z=0, hf=0)    = {npsha_0!r}")
print(f"NPSHa(z=3, hf=0.5)  = {npsha_3!r}")

# NPSHr: linear 2 + 2500*Q_eq at speed 1; margin.
npshr1 = 2.0 + 2500.0 * Q
print(f"NPSHr      = {npshr1!r}")
print(f"margin     = {npsha_0 - npshr1!r}")

# Cavitation case: static_head = -110 -> NPSHa; report margin.
npsha_cav = (inlet.P - P_v) / (rho * G_STD) - 110.0
print(f"NPSHa(z=-110) = {npsha_cav!r}")
print(f"margin(z=-110) = {npsha_cav - npshr1!r}")

# Sanity: printed spec values vs these, relative differences.
spec = {
    "rho": 598.62109,
    "mdot": 0.287104355,
    "Q": 4.79609489e-4,
    "H1": 60.8156204,
    "eta1": 0.639804745,
    "dP1": 357016.124,
    "P_out1": 1357016.12,
    "shaft1": 267.6259,
    "Q_eq2": 4.36008627e-4,
    "H2": 75.6971825,
    "eta2": 0.618004313,
    "dP2": 444377.85,
    "P_out2": 1444377.85,
    "shaft2": 344.864638,
    "P_v": 391351.429,
    "NPSHa0": 103.679744,
    "NPSHa3": 106.179744,
    "NPSHr": 3.19902372,
    "margin": 100.48072,
}
mine = {
    "rho": rho,
    "mdot": inlet.mass_flow,
    "Q": Q,
    "H1": H1,
    "eta1": eta1,
    "dP1": dP1,
    "P_out1": P_out1,
    "shaft1": shaft1,
    "Q_eq2": Q_eq2,
    "H2": H2,
    "eta2": eta2,
    "dP2": dP2,
    "P_out2": P_out2,
    "shaft2": shaft2,
    "P_v": P_v,
    "NPSHa0": npsha_0,
    "NPSHa3": npsha_3,
    "NPSHr": npshr1,
    "margin": npsha_0 - npshr1,
}
print("\nkey      spec            mine                  rel.diff")
for k in spec:
    rel = abs(mine[k] - spec[k]) / abs(spec[k])
    print(f"{k:8s} {spec[k]!r:15s} {mine[k]!r:20s} {rel:.3e}")
assert math.isfinite(P_out1)
