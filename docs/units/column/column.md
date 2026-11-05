# Rigorous distillation column (`column`)

Family: **column** · P&ID symbol: `T`

Rigour ladder: R2 provisional, R3 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `feed` | yes | main feed (further feeds via params) |
| outlet | `distillate` | yes | overhead product (total condenser) or vapour overhead (partial) |
| outlet | `bottoms` | yes | bottoms product |
| outlet | `side_draw` | yes | side draw (zero-flow state when no draw is configured) |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R2 | provisional | `ngdesign.units.column:Column` | MESH on the inside-out (Boston-Sullivan) solver with Naphtali-Sandholm fallback; configurations (absorber zero-tear, stripper/rectifier one-tear, two-tear distillation) select themselves from the condenser/reboiler kinds |
| R3 | provisional | `ngdesign.units.column.column_r3:ColumnR3` | one simultaneous Newton (the absorber/stripper R3 solver extended with a condenser end) over condenser, middle stages and kettle. rate_based - Krishna-Taylor packed segments (Onda 1968 coefficients), reduces to R2 as transfer_factor grows (measured 1.9e-6 max product mole-fraction deviation at 1e4, partial condenser); murphree - MESH trays with y_n = y_in + E (y*_n - y_in) (Murphree 1925), E = 1 reproduces R2 (measured 1.2e-9, partial condenser). Total condenser returns bubble-point reflux, as R2 does (measured 9.2e-5 product mole-fraction difference). Holland vaporisation efficiency not implemented (equation not verified from an accessible source) |

### R2 parameters

```yaml
properties:
  condenser:
    description: total | partial (total condenses above stage 1)
    type: string
  feed_stage:
    description: main feed stage
    type: integer
  feeds:
    description: additional feeds by stage
    type: object
  n_stages:
    description: equilibrium stages, numbered 1..N top to bottom
    type: integer
  pressure_profile:
    description: top pressure or per-stage profile, Pa
    type: number
  reboiler:
    description: kettle | none (none = absorber/rectifier configuration)
    type: string
  side_draws:
    description: additional draws by stage
    type: object
  specs:
    description: two specs for two tears (reflux_ratio, distillate_rate, boilup_ratio,
      boilup_rate, ...); one for one-tear; none for an absorber
    type: object
  stage_heaters:
    description: '[{stage, duty_W}] fixed heat added to an ordinary tray, W (< 0 cools)'
    type: array
required:
- n_stages
- condenser
- reboiler
- feed_stage
- specs
type: object
```

### R3 parameters

```yaml
additionalProperties: false
properties:
  column_diameter_m:
    description: 'rate_based: packed-bed diameter, m'
    exclusiveMinimum: 0
    type: number
  condenser:
    description: total (saturated bubble-point reflux and distillate) or partial (equilibrium
      stage, vapour distillate)
    enum:
    - total
    - partial
    type: string
  critical_surface_tension_N_m:
    description: 'rate_based: packing critical surface tension sigma_c, N/m'
    exclusiveMinimum: 0
    type: number
  feed_stage:
    description: feed stage, R2 numbering (feed vapour to the vapour side, liquid
      to the liquid side of a packed segment)
    minimum: 1
    type: integer
  murphree_efficiency:
    description: 'murphree: Murphree vapour efficiency in (0, 1], scalar or one per
      tray between condenser and kettle (top to bottom); default 1 (= R2)'
    oneOf:
    - exclusiveMinimum: 0
      maximum: 1
      type: number
    - items:
        exclusiveMinimum: 0
        maximum: 1
        type: number
      type: array
  n_stages:
    description: 'stages in R2 numbering: 1 = partial condenser or the stage under
      a total condenser, N = kettle'
    minimum: 3
    type: integer
  nominal_size_m:
    description: 'rate_based: nominal packing size D_p, m'
    exclusiveMinimum: 0
    type: number
  packed_height_m:
    description: 'rate_based: total packed height, m (split equally over the N-1 (total)
      or N-2 (partial) segments)'
    exclusiveMinimum: 0
    type: number
  pressure_profile:
    description: stage pressures, Pa abs (scalar = uniform; list = N values top to
      bottom; a total condenser sits at stage 1's pressure); default feed P
    oneOf:
    - exclusiveMinimum: 0
      type: number
    - items:
        exclusiveMinimum: 0
        type: number
      type: array
  reboiler:
    description: kettle (the only R3 reboiler; equilibrium stage)
    enum:
    - kettle
    type: string
  specific_area_m2_m3:
    description: 'rate_based: total packing area a_t, m2/m3'
    exclusiveMinimum: 0
    type: number
  specs:
    description: 'exactly two: one condenser-side (reflux_ratio, condenser_duty_W
      heat removed W, distillate_rate or bottoms_rate mol/s) and one reboiler-side
      (boilup_ratio, reboiler_duty_W W, distillate_rate or bottoms_rate)'
    type: object
  stage_model:
    description: rate_based (default) packed segments, or murphree equilibrium-stage
      trays
    enum:
    - rate_based
    - murphree
    type: string
  surface_tension_N_m:
    description: 'rate_based: liquid surface tension, N/m (the thermo contract carries
      none)'
    exclusiveMinimum: 0
    type: number
  transfer_factor:
    description: 'rate_based: multiplier on every film conductance and heat-transfer
      coefficient (default 1); large values reduce each segment to an equilibrium
      stage'
    exclusiveMinimum: 0
    type: number
required:
- n_stages
- condenser
- feed_stage
- specs
type: object
```

Mode map: `distillation` → `R2`, `absorber` → `R2`, `stripper` → `R2`, `rectifier` → `R2`, `reboiled_absorber` → `R2`

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V1-column-seader-10-9` | R2 | `outlet.distillate.T` | 301.856 | 301.861 | abs 0.003 | assessed miss |
| `V1-column-seader-10-9` | R2 | `outlet.bottoms.T` | 362.278 | 362.311 | abs 0.003 | assessed miss |
| `V1-column-seader-10-9` | R2 | `outlet.bottoms.composition.C3` | 0.0191 | 0.0191174 | abs 1e-05 | assessed miss |
| `V1-column-seader-10-9` | R2 | `outlet.bottoms.composition.nC4` | 0.247255 | 0.247198 | abs 1e-05 | assessed miss |
| `V1-column-seader-10-9` | R2 | `outlet.bottoms.composition.nC5` | 0.733625 | 0.733685 | abs 1e-05 | assessed miss |

- `V1-column-seader-10-9`: Seader, Henley & Roper, "Separation Process Principles", 3rd ed. (Wiley 2011), Example 10.9 "Inside-Out Method", p. 404, with the column of Figure 10.7, p. 384 (archive.org item separation-process-principles-chemical-a, PDF pages 412 and 432, read and retrieved 2026-11-04): total condenser (stage 1), three equilibrium stages, partial reboiler (stage 5), all at 100 psia; 100 lbmol/h saturated-liquid feed to stage 3 (C3 0.30, nC4 0.30, nC5 0.40); reflux ratio L1/U1 = 2.0; bottoms L5 = 50 lbmol/h; SRK equation of state (CHEMCAD TOWR). Converged (outer-loop iteration 3) results printed: T1 = 83.67 F, T5 = 192.43 F; bottoms C3 0.955, nC4 12.363, nC5 36.683 lbmol/h of L5 = 50.001 lbmol/h. The book reports the feed bubble point as 123.5 F.
  - assessed: Measured miss on srk-kij0 (just outside the printed rounding): distillate T 301.861 vs 301.856 K (+0.005 K = +0.009 F), bottoms T 362.311 vs 362.278 K (+0.033 K = +0.06 F); bottoms x_C3 0.019117 vs 0.019100 (0.9559 vs 0.955 lbmol/h), x_nC4 0.247198 vs 0.247255, x_nC5 0.733685 vs 0.733625. With the k_ij effect removed (the srk row missed by 0.5-1.7 K and x_C3 0.017153) the remaining gap is below the book's own convergence spread: between its outer-loop iterations 2 and 3 the printed T5 moved 0.10 F and bottoms C3 0.008 lbmol/h, so the printed iteration-3 values are not converged to their last digit. Smaller contributors: CHEMCAD's pure-component constants and ideal-gas Cp (energy balance) are not the ChemSep/thermo values, and the column meets its specs to the core's _SPEC_TOL (reflux ratio 2.000245, bottoms 0.0063007 mol/s = 50.006 lbmol/h; issue 248). Not a MESH defect; the level stays provisional because the printed-rounding tolerance is not met.

## References

- Boston & Sullivan 1974, Can. J. Chem. Eng. 52, 52-63
- Naphtali & Sandholm 1971, AIChE J. 17(1), 148-153
- Taylor, Kooijman & Hung 1994, Comput. Chem. Eng. 18, 205-217
- Murphree 1925, Ind. Eng. Chem. 17, 747-750
- docs/unit-catalogue-plan.md §2 U-E 2

> covers plan U-E 2 and the R2 of U-E 3 (feed-determined absorber, zero-tear) and U-E 4 (reboiled stripper, one-tear) as configurations. R3 (rate-based packed segments or Murphree trays, condenser + kettle) is the end state. Side draws exist (side_draw port) at R2 only; the graph-visible second feed and the extended composite are the column_extensions row. R3 V1 gap - provisional without a case (searched data/validation/ and data/validation_units/column/ for rate-based or Murphree distillation cases, none; the Taylor-Krishna and Seader-Henley rate-based distillation examples were not accessible with printed inputs and results); R3 is covered by the R2 reduction tests, closed-form condenser and Murphree-row tests.
