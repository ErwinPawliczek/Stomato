# mypy: disable-error-code="no-untyped-call"
"""Steam-table properties for the free-water phase of a cubic package.

A cubic EOS gets water wrong in the two places a hydrocarbon/water flash cares about:
its vapour pressure, which sets the water content of the gas over a free-water phase,
and its liquid density and enthalpy. The free-water method keeps the EOS for the
hydrocarbon phases and takes pure water from the steam tables.

Here the correction is Lewis-Randall on the water-rich liquid (x_w > 0.5, the state
layer's aqueous test): the EOS composition dependence stays and water's pure-liquid
reference moves from the EOS to IAPWS-95,

    ln phi_w = ln phi_w,EOS(x) + [ln phi0_w,IAPWS(T, P) - ln phi0_w,EOS(T, P)],

with H, S and V moved by x_w times the same pure-water difference. The offset does
not depend on composition, so Gibbs-Duhem at fixed T, P still holds on the phase.
Solutes keep their EOS fugacities: the aqueous phase is not forced to pure water, it
is whatever the flash finds, which for hydrocarbons is close to it.

Residual properties from the reduced Helmholtz energy (Wagner & Pruss, J. Phys. Chem.
Ref. Data 31 (2002) 387, Table 6.3): ln phi = phi_r + d phi_r_d - ln(1 + d phi_r_d),
h_r / RT = t phi_r_t + d phi_r_d, s_r / R = t phi_r_t - phi_r.

Below Psat a water-rich liquid is metastable and IAPWS-95 has no liquid root in
``iapws95_rho``, so such a state is evaluated at Psat with the ideal-gas pressure term
added. Outside the triple-point to near-critical window the phase keeps the EOS.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, ClassVar

from chemicals.iapws import (
    iapws95_Ar,
    iapws95_dAr_ddelta,
    iapws95_dAr_dtau,
    iapws95_Psat,
    iapws95_R,
    iapws95_rho,
    iapws95_rhoc,
    iapws95_rhol_sat,
    iapws95_Tc,
    iapws95_Tt,
)
from thermo.eos import PR, SRK

from ngdesign.thermo._state import AQUEOUS_WATER_FRACTION
from ngdesign.thermo.liquid_density import holds_liquid_root

#: The window the correction applies in (K): IAPWS-95's triple point, and short of
#: the critical point, where a "free water" liquid stops meaning anything.
_T_MAX = 640.0

#: Half step (K) of the numeric Cp offset.
_CP_D_T = 0.05

#: IAPWS-95 molar mass, kg/mol.
_MW_WATER_KG = 0.018015268

_PURE_EOS: dict[str, Any] = {"PR": PR, "SRK": SRK}


@dataclass(frozen=True)
class PureWaterOffset:
    """Steam table minus EOS for pure liquid water at one (T, P); all per mole of water."""

    ln_phi: float
    enthalpy: float  # J/mol
    entropy: float  # J/(mol K)
    volume: float  # m3/mol


def steam_table_residuals(T: float, P: float) -> tuple[float, float, float, float]:
    """(ln phi, h_res J/mol, s_res J/(mol K), V m3/mol) of IAPWS-95 liquid at (T, P)."""
    psat = iapws95_Psat(T)
    p_eval = max(P, psat)
    rho = iapws95_rho(T, p_eval)
    if rho < iapws95_rhol_sat(T):  # at Psat the solver may pick the vapour root
        rho = iapws95_rhol_sat(T)
    tau = iapws95_Tc / T
    delta = rho / iapws95_rhoc
    ar = iapws95_Ar(tau, delta)
    d_ar = delta * iapws95_dAr_ddelta(tau, delta)
    t_ar = tau * iapws95_dAr_dtau(tau, delta)
    r_molar = iapws95_R * _MW_WATER_KG  # the module's R is per kilogram
    rt = r_molar * T
    ln_phi = ar + d_ar - math.log(1.0 + d_ar) + math.log(p_eval / P)
    return (
        ln_phi,
        rt * (t_ar + d_ar),
        r_molar * (t_ar - ar) - r_molar * math.log(p_eval / P),
        _MW_WATER_KG / rho,
    )


@lru_cache(maxsize=4096)
def pure_water_offset(
    eos_name: str, tc: float, pc: float, omega: float, T: float, P: float
) -> PureWaterOffset | None:
    """IAPWS-95 minus EOS for pure liquid water; None without an EOS liquid root."""
    eos = _PURE_EOS[eos_name](Tc=tc, Pc=pc, omega=omega, T=T, P=P)
    if not hasattr(eos, "V_l"):
        return None
    ln_phi, h_res, s_res, volume = steam_table_residuals(T, P)
    return PureWaterOffset(
        ln_phi - float(eos.lnphi_l),
        h_res - float(eos.H_dep_l),
        s_res - float(eos.S_dep_l),
        volume - float(eos.V_l),
    )


class FreeWaterPhase:
    """Mixin for CEOS phase classes: a water-rich liquid takes water from the steam tables.

    Class attributes hold the slate data; see liquid_density.CorrelatedDensityPhase.
    """

    free_water_index: ClassVar[int] = -1
    free_water_eos: ClassVar[str] = "PR"

    # Provided by the CEOS phase this mixes into.
    eos_mix: Any
    zs: list[float]
    T: float
    P: float

    def _offset_at(self, T: float) -> PureWaterOffset | None:
        i = self.free_water_index
        if i < 0 or self.zs[i] <= AQUEOUS_WATER_FRACTION or not iapws95_Tt <= T <= _T_MAX:
            return None
        if not holds_liquid_root(self):
            return None
        eos = self.eos_mix
        return pure_water_offset(self.free_water_eos, eos.Tcs[i], eos.Pcs[i], eos.omegas[i], T, self.P)

    def lnphis(self) -> Any:
        base = super().lnphis()  # type: ignore[misc]
        offset = self._offset_at(self.T)
        if offset is None:
            return base
        out = list(base)
        out[self.free_water_index] += offset.ln_phi
        return out

    def H(self) -> float:
        base = float(super().H())  # type: ignore[misc]
        offset = self._offset_at(self.T)
        return base if offset is None else base + self.zs[self.free_water_index] * offset.enthalpy

    def S(self) -> float:
        base = float(super().S())  # type: ignore[misc]
        offset = self._offset_at(self.T)
        return base if offset is None else base + self.zs[self.free_water_index] * offset.entropy

    def V(self) -> float:
        base = float(super().V())  # type: ignore[misc]
        offset = self._offset_at(self.T)
        return base if offset is None else base + self.zs[self.free_water_index] * offset.volume

    def Cp(self) -> float:
        """Base Cp plus x_w d(offset H)/dT, the offset differenced over +/- 0.05 K."""
        base = float(super().Cp())  # type: ignore[misc]
        hi, lo = self._offset_at(self.T + _CP_D_T), self._offset_at(self.T - _CP_D_T)
        if hi is None or lo is None:
            return base
        slope = (hi.enthalpy - lo.enthalpy) / (2.0 * _CP_D_T)
        return base + self.zs[self.free_water_index] * slope
