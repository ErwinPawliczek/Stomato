"""Kremser absorber, R0 (spec U-E).

Plugin kind "unit", name "absorber". Ports gas_in + solvent_in -> gas_out +
rich_out. Method (spec): the Kremser group method per component at R0 —
``A_i = L/(K_i*V)`` on the two inlet flows at the average of the inlet
temperatures and the inlet pressure (documented); the fraction absorbed is
``kremser_fraction(A_i, N)`` with ``N`` given in params. The generalized
two-feed split (eqs. 5-48/5-50/5-54/5-55) lets the lean solvent carry a
component that strips into the gas, as the absorbent oil does in the book's
hydrocarbon/oil example. Isothermal R0: gas_out flashes at the gas-in state,
rich_out at the solvent-in state, and the duty reports the enthalpy change.

K-values come from ``thermo.k_values`` at the average condition; params
``k_overrides`` (``{cid: K}``) replaces them per component, for reference
cases whose basis is the book's estimated ideal K-values (or dilute systems
the package K-values do not describe). Raises typed ValueErrors on a bad
``N``, non-positive overrides, a missing K, or an empty phase flow.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units._physics.shortcut import kremser_fraction
from ngdesign.units.column_shortcut._kremser import two_feed_split

#: Components of the Seader-Henley Example 5.3 basis (pp. 186-188), used as
#: the adapter's example case: 800 lbmol/h rich gas at 105 F / 400 psia,
#: 165 lbmol/h absorbent oil at 90 F, 6 ideal stages. The oil is the C6+
#: stand-in; the K-values are the book's estimates at 97.5 F.
_EXAMPLE_GAS_LBMOL_H = {"C1": 160.0, "C2": 370.0, "C3": 240.0, "nC4": 25.0, "nC5": 5.0}
_EXAMPLE_GAS_T = 313.7056  # 105 F, K
_EXAMPLE_SOLVENT_T = 305.3722  # 90 F, K
_EXAMPLE_P = 2757902.8  # 400 psia, Pa
_EXAMPLE_OIL_LBMOL_H = 165.0
_EXAMPLE_N = 6.0
_EXAMPLE_K = {"C1": 6.65, "C2": 1.64, "C3": 0.584, "nC4": 0.195, "nC5": 0.0713, "C6+": 0.0001}

#: lbmol/h -> mol/s (0.45359237 kmol per lbmol, 3600 s per h).
_LBMOL_H_TO_MOL_S = 0.45359237 / 3.6


class Absorber:
    """Kremser absorber (feed-determined), R0: balances plus a stage spec."""

    inlet_ports = ("gas_in", "solvent_in")
    outlet_ports = ("gas_out", "rich_out")

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        gas = inlets.get("gas_in")
        solvent = inlets.get("solvent_in")
        if gas is None or solvent is None:
            raise ValueError("absorber needs gas_in and solvent_in inlet streams")
        if gas.molar_flow <= 0.0 or solvent.molar_flow <= 0.0:
            raise ValueError("absorber inlet flows must both be positive")
        if "N" not in params:
            raise ValueError("absorber requires the 'N' parameter (ideal stages)")
        stages = float(params["N"])
        if stages <= 0.0:
            raise ValueError(f"absorber N must be positive, got {stages}")
        overrides = params.get("k_overrides") or {}
        if not isinstance(overrides, dict):
            raise ValueError("absorber k_overrides must be a {cid: K} mapping")

        t_avg = 0.5 * (gas.T + solvent.T)
        p_avg = 0.5 * (gas.P + solvent.P)
        k_map: dict[str, float]
        if overrides:
            k_map = {str(cid): float(k) for cid, k in overrides.items()}
            for cid, k in k_map.items():
                if k <= 0.0:
                    raise ValueError(f"absorber k_overrides[{cid}] must be positive, got {k}")
        else:
            package_ks = thermo.k_values(gas.composition, t_avg, p_avg)
            if package_ks is None:
                raise ValueError(
                    "absorber: thermo gives no K-values at the average inlet condition "
                    f"({t_avg:.2f} K, {p_avg:.0f} Pa); pass k_overrides"
                )
            k_map = package_ks

        gas_flows = {cid: y * gas.molar_flow for cid, y in gas.composition.items()}
        liquid_flows = {cid: y * solvent.molar_flow for cid, y in solvent.composition.items()}
        out_gas, out_rich = two_feed_split(
            gas_flows, liquid_flows, k_map, solvent.molar_flow, gas.molar_flow, stages
        )

        total_gas_out = sum(out_gas.values())
        total_rich_out = sum(out_rich.values())
        z_gas = {cid: n / total_gas_out for cid, n in out_gas.items()}
        z_rich = {cid: n / total_rich_out for cid, n in out_rich.items()}
        gas_out = thermo.flash_pt(z_gas, gas.T, gas.P, total_gas_out)
        rich_out = thermo.flash_pt(z_rich, solvent.T, solvent.P, total_rich_out)

        info: dict[str, float] = {}
        for cid in sorted(set(gas_flows) | set(liquid_flows)):
            info[f"out_gas_{cid}"] = out_gas[cid]
            info[f"rich_{cid}"] = out_rich[cid]
            a_i = solvent.molar_flow / (k_map[cid] * gas.molar_flow)
            s_i = k_map[cid] * gas.molar_flow / solvent.molar_flow
            info[f"f_not_absorbed_{cid}"] = 1.0 - kremser_fraction(a_i, stages)
            info[f"f_not_stripped_{cid}"] = 1.0 - kremser_fraction(s_i, stages)
        duty_w = _enthalpy_flow(gas_out, rich_out) - _enthalpy_flow(gas, solvent)
        return UnitResult(
            outlets={"gas_out": gas_out, "rich_out": rich_out},
            duty_W=duty_w,
            power_W=0.0,
            info=info,
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Seader-Henley-Roper Example 5.3 basis (pp. 186-188): hydrocarbon gas
        absorbed by oil at 400 psia, N = 6, on the book's K-values at 97.5 F.
        The oil is the ``C6+`` stand-in."""
        gas_total = sum(_EXAMPLE_GAS_LBMOL_H.values())
        gas_flow = gas_total * _LBMOL_H_TO_MOL_S
        oil_flow = _EXAMPLE_OIL_LBMOL_H * _LBMOL_H_TO_MOL_S
        feeds = {
            "gas_in": {
                "T": _EXAMPLE_GAS_T,
                "P": _EXAMPLE_P,
                "molar_flow": gas_flow,
                "composition": {cid: n / gas_total for cid, n in _EXAMPLE_GAS_LBMOL_H.items()},
            },
            "solvent_in": {
                "T": _EXAMPLE_SOLVENT_T,
                "P": _EXAMPLE_P,
                "molar_flow": oil_flow,
                "composition": {"C6+": 1.0},
            },
        }
        params = {"N": _EXAMPLE_N, "k_overrides": dict(_EXAMPLE_K)}
        return feeds, params


def _enthalpy_flow(*states: StreamState) -> float:
    """Sum of stream enthalpy flows, W (molar enthalpy J/mol x molar flow)."""
    return sum(s.molar_flow * s.enthalpy for s in states)
