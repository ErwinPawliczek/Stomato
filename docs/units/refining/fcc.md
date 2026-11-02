# Fluid catalytic cracker (`fcc`)

Family: **refining** · P&ID symbol: `FC`

Rigour ladder: R0 provisional, R1 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `feed_in` | yes | VGO feed |
| outlet | `dry_gas_out` | yes | dry gas |
| outlet | `lpg_out` | yes | LPG |
| outlet | `gasoline_out` | yes | gasoline |
| outlet | `lco_out` | yes | light cycle oil |
| outlet | `slurry_out` | yes | slurry/slops |
| outlet | `coke_out` | yes | coke on spent catalyst, to the regenerator |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.refining.fcc:FccR0` | mass yields linearly interpolated from a required user table against conversion, no extrapolation; mass-only lumps, duty sensible-only |
| R1 | provisional | `ngdesign.units.refining.fcc:FccR1` | Lee et al. four-lump form of the Weekman gas-oil lump over riser contact time with exp(-alpha t) decay and an adiabatic riser fed by regenerated catalyst; all constants are required user inputs. The regenerator is reported, not solved |

### R0 parameters

```yaml
properties:
  P_out:
    description: outlet pressure, Pa
    type: number
  T_out:
    description: outlet temperature, K
    type: number
  conversion_wt_pct:
    description: operating conversion, wt% on feed (100 - LCO - slurry)
    type: number
  yield_table:
    description: 'user table, no default: {conversion_wt_pct, dry_gas_wt_pct, lpg_wt_pct,
      gasoline_wt_pct, lco_wt_pct, slurry_wt_pct, coke_wt_pct}, equal-length arrays;
      each row sums to 100 and LCO + slurry = 100 - conversion'
    type: object
required:
- conversion_wt_pct
- yield_table
- T_out
- P_out
type: object
```

### R1 parameters

```yaml
properties:
  P_out:
    description: riser pressure, Pa
    type: number
  T_regen_K:
    description: regenerated catalyst temperature (an input
    the regenerator is not solved); heat balance: null
    type: number
  catalyst_to_oil:
    description: catalyst-to-oil mass ratio; heat balance
    type: number
  coke_heat_of_combustion_J_kg:
    description: for the reported regenerator residual
    type: number
  contact_time_s:
    description: riser contact time
    s: null
    type: number
  cp_cat_J_kgK:
    description: catalyst heat capacity; heat balance
    type: number
  deactivation_alpha_per_s:
    description: Weekman decay phi = exp(-alpha t), 1/s
    type: number
  dry_gas_fraction:
    description: dry-gas share of the gases lump
    type: number
  heat_of_cracking_J_kg:
    description: endothermic heat per kg converted; heat balance
    type: number
  isothermal_T_K:
    description: isothermal riser temperature, K; replaces the heat balance
    type: number
  kinetics:
    description: 'required, no default: {gasoil_to_gasoline, gasoil_to_gases, gasoil_to_coke,
      gasoline_to_gases, gasoline_to_coke}, each {k0_per_s, Ea_J_mol}; on the operating
      catalyst-to-oil basis'
    type: object
  lco_fraction:
    description: LCO share of the unconverted gas-oil lump
    type: number
required:
- kinetics
- contact_time_s
- deactivation_alpha_per_s
- dry_gas_fraction
- lco_fraction
- P_out
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-H 9

> Nothing above R1 is planned (plan §2 U-H preamble). R0 record of what was searched (U-H2 review, still true) - the published FCC yield correlations are chart/figure-based (Gary, Handwerk & Kaiser, Petroleum Refining, 5th ed. 2007, §6.12 Yield Estimation, pp. 143-144, points at Figures 6.17-6.28) and the U-R1 conventions forbid digitising figures; no equation-based R0 correlation was found in the open sources searched. R0 and R1 therefore ship with no numbers of their own - the table and the rate constants are required user inputs and absent ones refuse - so no figure is transcribed. The original Weekman & Nace (1970) and Lee et al. (1989) constants could not be read from an open copy (searched 2026-11-01; secondary quotations conflict in values and units), so none is a preset. The coke_out port was added at R0 so mass closes. V1 gap - provisional on the closed-form Weekman second-order solution, the first-order gasoline integral by quadrature, and refusals.
