# Hydrocracker (`hcu`)

Family: **refining** · P&ID symbol: `HC`

Rigour ladder: R0 provisional, R1 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `vgo_in` | yes | VGO feed |
| inlet | `hydrogen_in` | yes | hydrogen feed |
| outlet | `naphtha_out` | yes | hydrocracked naphtha |
| outlet | `diesel_out` | yes | diesel |
| outlet | `unconverted_out` | yes | unconverted oil recycle |
| outlet | `gas_out` | yes | light gases and unreacted hydrogen |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.refining.hcu:HcuR0` | yield table vs conversion on representative real paraffins (nC20, nC12, nC6, C3); gas by element balance; H2 consumption counts scissions only, a lower bound |
| R1 | provisional | `ngdesign.units.refining.hcu:HcuR1` | discrete four-lump six-path first-order kinetics (Sadighi et al. 2010 network form) on representative paraffins, isothermal bed, hydrogen in excess; continuous lumping as such is not implemented |

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
    description: operating conversion, wt% on VGO
    type: number
  yield_table:
    description: 'user table, no default: {conversion_wt_pct, diesel_wt_pct, naphtha_wt_pct};
      gas and H2 follow from the element balance'
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
    description: outlet pressure, Pa
    type: number
  T_bed_K:
    description: isothermal bed temperature, K
    type: number
  T_out:
    description: outlet temperature, K
    type: number
  kinetics:
    description: 'required, no default: {vgo_to_diesel, vgo_to_naphtha, vgo_to_gas,
      diesel_to_naphtha, diesel_to_gas, naphtha_to_gas}, each {k0_per_s, Ea_J_mol}'
    type: object
  lhsv_per_h:
    description: liquid hourly space velocity, 1/h; contact time 1/LHSV
    type: number
required:
- kinetics
- T_bed_K
- lhsv_per_h
- T_out
- P_out
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-H 10

> R0 record of what was searched (U-H2 review) - published hydrocracker yield correlations are chart/figure-based (Gary, Handwerk & Kaiser, Petroleum Refining, 5th ed. 2007, §7.6 Hydrocracking Yields, pp. 170-172, reads Figure 7.4 / Figure 7.6 curves; its Table 7.3 is fixed-feed vol% tables, not a correlation) and the U-R1 conventions forbid digitising figures. R0 and R1 therefore ship with no numbers of their own - the table and the rate constants are required user inputs and absent ones refuse. The gas_out port was added at R0 so excess H2 and light gases close the mass balance. Pseudo VGO is refused (issue 222); real H2 consumed into formula-free lumps cannot close the element ledger. V1 gap - Faraji et al., ACS Omega 2020 Table 2 prints k1-k6 at 663.15 K, but the open text does not map each constant to a path, so it is not used; provisional on the series-reaction closed form and the reduction of R1 to R0.
