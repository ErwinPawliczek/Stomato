# Ejector (`ejector`)

Family: **flow** · P&ID symbol: `EJ`

Rigour ladder: R0 provisional, R1 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `motive_in` | yes | motive stream |
| inlet | `suction_in` | yes | suction stream |
| outlet | `outlet` | yes | combined discharge |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.flow.ejector:Ejector` | entrainment ratio spec |
| R1 | provisional | `ngdesign.units.flow.ejector_r1:EjectorR1` | Keenan constant-pressure mixing with Huang efficiencies: achievable discharge pressure |

### R1 parameters

```yaml
properties:
  P_out_required:
    description: optional required discharge pressure, Pa
    type: number
  eta_diffuser:
    description: diffuser isentropic efficiency, default 0.85
    type: number
  eta_nozzle:
    description: motive nozzle isentropic efficiency, default 0.95
    type: number
  phi_mix:
    description: mixing momentum coefficient, default 0.85
    type: number
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-B 10

> R0 momentum balance at a specified entrainment ratio. V1 gap (PR #217): the previous Graham 3:1 case was circular (both expectations restated the inputs) and is withdrawn; no open published ejector example with a printed outlet state was found (searched Graham Manufacturing ejector performance literature and Perry sect. 10 — operating points are entrainment ratios and curves, not outlet states). R0 mixing remains covered by closed-form unit tests. 1-D momentum design mode remains roadmap. R1 V1 gap: no open-source source prints inputs and results for a full steam-ejector rating that the thermo can reproduce exactly. Candidates assessed: Huang et al. 1999 Table 2/3 (R141b test data; R141b is not in the component set), Power, Steam Jet Ejectors for the Process Industries (McGraw-Hill, 1994) worked examples, and Perry's 9th ed. sect. 10 examples — none reproducible exactly. R1 rests on the ideal-gas closed-form tests, the R0-reduction identity and the refusal tests.
