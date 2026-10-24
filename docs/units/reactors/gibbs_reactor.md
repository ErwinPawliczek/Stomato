# Gibbs reactor (`gibbs_reactor`)

Family: **reactors** · P&ID symbol: `R`

Rigour ladder: R0 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | feed |
| outlet | `outlet` | yes | Gibbs-minimum effluent |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.reactors.gibbs_reactor:GibbsReactor` | Gibbs minimisation at the stationarity conditions (element-potential method) |

### R0 parameters

```yaml
properties:
  inerts:
    description: fixed-amount spectators excluded from the minimisation
    type: array
  species:
    description: components allowed to react (element-potential Gibbs minimum)
    type: array
  thermal:
    description: '''isothermal'' | ''adiabatic'' | {duty_W: W} | {T_out: K} (default
      isothermal)'
type: object
```

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V1-WGS-GIBBS` | R0 | `outlet.outlet.composition.CO` | 0.250577 | 0.250465 | abs 0.001 | pass |
| `V1-WGS-GIBBS` | R0 | `outlet.outlet.composition.CO2` | 0.249423 | 0.249535 | abs 0.001 | pass |
| `V1-WGS-GIBBS` | R0 | `outlet.outlet.composition.H2` | 0.249423 | 0.249535 | abs 0.001 | pass |

- `V1-WGS-GIBBS`: JANAF Thermochemical Tables (Chase 1998), printed log Kf at 1100 K: CO2 18.805, CO 9.928, H2O 8.881 (janaf.nist.gov C-095/C-093/H-064) -> log K(WGS) = -0.004; X = sqrt(K)/(1+sqrt(K)) = 0.498846

## References

- docs/unit-catalogue-plan.md §2 U-F 4

> R0 implemented (U-F). Every feed component must be listed in species or inerts; restricted equilibria stay an R1+ concern. The SVA steam-methane-reforming worked example (mole fractions to 3 decimals) could not be verified in any open source (searched 2026-10-24 — the FOSSEE ch13 transcription, whose Ex 13.5 is the WGS example at 1100 K, plus solution-manual and course-note searches); the Gibbs oracle anchors to the JANAF-printed WGS case (V1-WGS-GIBBS) until a copy of the 7th-edition example page is available.
