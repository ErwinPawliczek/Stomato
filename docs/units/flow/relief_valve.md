# Relief valve (`relief_valve`)

Family: **flow** · P&ID symbol: `PSV`

Rigour ladder: R0 provisional, R1 provisional, R2 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | relieved stream at set pressure |
| outlet | `outlet` | yes | discharge |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.flow.relief_valve:ReliefValve` | set pressure, orifice from API 520 (the psv_api520_gas correlation plugin exists) |
| R1 | provisional | `ngdesign.units.flow.relief_valve_r1:ReliefValveR1` | Leung omega two-phase and subcooled sizing (eqs. 1-5), gas delegated to R0; Kd by regime |
| R2 | provisional | `ngdesign.units.flow.relief_valve_r2:ReliefValveR2` | rated-capacity inlet-loss and built-up back-pressure checks with bellows Kb/Kw re-sizing |

### R1 parameters

```yaml
properties:
  Kb:
    description: back-pressure correction, default 1.0
    type: number
  Kc:
    description: combination (rupture disk) correction, default 1.0
    type: number
  Kd:
    description: discharge coefficient; default 0.975 gas / 0.85 two-phase / 0.65
      liquid, chosen by regime
    type: number
  Kv:
    description: viscosity correction (liquid), default 1.0
    type: number
  Kw:
    description: liquid back-pressure correction (balanced bellows), default 1.0
    type: number
  P_back:
    description: superimposed back pressure, Pa abs
    type: number
required:
- P_back
type: object
```

### R2 parameters

```yaml
properties:
  D_in_m:
    description: inlet line ID, m
    type: number
  D_out_m:
    description: discharge line ID, m
    type: number
  K_in:
    description: inlet line sum-K
    type: number
  K_out:
    description: discharge line sum-K
    type: number
  Kb:
    description: back-pressure correction, default 1.0
    type: number
  Kc:
    description: combination (rupture disk) correction, default 1.0
    type: number
  Kd:
    description: discharge coefficient; default 0.975 gas / 0.85 two-phase / 0.65
      liquid
    type: number
  Kv:
    description: viscosity correction (liquid), default 1.0
    type: number
  Kw:
    description: liquid back-pressure correction (balanced bellows), default 1.0
    type: number
  L_in_m:
    description: inlet line length, m
    type: number
  L_out_m:
    description: discharge line length, m
    type: number
  P_atm:
    description: atmospheric pressure, Pa, default 101325
    type: number
  P_back:
    description: superimposed back pressure, Pa abs
    type: number
  P_set:
    description: set pressure, Pa abs
    type: number
  overpressure:
    description: overpressure fraction, one of 0.10, 0.16, 0.21
    type: number
  roughness_in_m:
    description: inlet roughness, m, default 4.57e-5 commercial steel
    type: number
  roughness_out_m:
    description: discharge roughness, m, default 4.57e-5 commercial steel
    type: number
  valve_type:
    description: conventional, balanced_bellows or pilot
    type: string
required:
- P_back
- P_set
type: object
```

## V1 worked cases

| case | level | quantity | expected | measured | tolerance | result |
|---|---|---|---|---|---|---|
| `V1-relief-valve-diers-rr-case-ia` | R1 | `info.G_kg_m2s` | 6070 | 6098.73 | abs 90 | pass |
| `V1-relief-valve-diers-rr-case-ia` | R1 | `info.eta_c` | 0.866 | 0.864231 | abs 0.008 | pass |
| `V1-relief-valve-api520-d2-2-2-propane` | R1 | `info.G_kg_m2s` | 36911.2 | 36842.5 | abs 24.4 | assessed miss |
| `V1-relief-valve-api520-d2-2-2-propane` | R1 | `info.required_area_in2` | 0.208 | 0.208793 | abs 0.0005 | assessed miss |
| `V1-relief-valve-api520-d2-2-2-propane` | R1 | `info.selected_orifice_area_in2` | 0.307 | 0.307 | abs 0.0005 | pass |

- `V1-relief-valve-diers-rr-case-ia`: Leung, J.C., "Benchmark Flow Problems - A Round-Robin Exercise", DIERS Users Group Meeting, San Antonio TX, 20-22 Oct 2008 (https://www.iomosaic.com/diersweb/docs/DUG%2042-850-1.pdf, read 2026-11-04): critical (choked) homogeneous-equilibrium nozzle discharge, p. 2-3 case definitions, p. 10 table "100% c-C6, 10 bar, 182.3 C", Case Ia x_o = 0.0001 (bubble point): mean of the 12 participant results Gc = 6070 kg/m2s (std. dev. 90), eta_c = 0.866 (std. dev. 0.008); the omega_0.9 (JL) row prints 6160 / 0.863. Tolerance: the printed participant standard deviation (the benchmark's own stated spread), fixed before the run. The inlet is saturated cyclohexane at 10 bar on the package's own saturation line (PR bubble point 455.132 K = 181.98 C against the printed 182.3 C), fed 0.002 K below it so the PT flash returns the liquid; the back pressure (1 bar) is far below eta_c P0 so the flow is choked as in the benchmark.
- `V1-relief-valve-api520-d2-2-2-propane`: API RP 520 Part I, 7th ed. (January 2000), p. 73, Example D.2.2.2 (subcooled liquid at the PRV inlet), as transcribed in FluidFlow knowledge-base article "Relief valve sizing verification", section 5 (https://knowledge.fluidflowinfo.com/en/articles/13285154, read 2026-11-04; secondary transcription of the API example): propane 100 gal/min (pump blockage) at 60 F, set 260 psig, 10% accumulation, relieving pressure 300.7 psia, total back pressure 10 psig, Kd = 0.65, Kb = Kc = 1.0; printed mass flux G = 7560 lb/s ft2 (= 36,911 kg/m2s), required area 0.208 in2, orifice F (0.307 in2), inlet density 31.92 lb/ft3. Mass flow from the printed 100 gal/min at the printed 31.92 lb/ft3 = 7.1118 lb/s = 3.22587 kg/s = 73.156 mol/s. Tolerances: the printed 4-figure G (+/-5 lb/s ft2 = 24.4 kg/m2s) and 3-decimal area (+/-0.0005 in2), fixed before the run.
  - assessed: Orifice letter passes (F, 0.307 in2). G = 36,842.5 kg/m2s misses the printed 36,911 by -0.19% (tolerance 0.066%), and the required area 0.20879 in2 misses 0.208 by +0.38% (+0.19% on the API's unrounded 7.1118/(0.65 x 7560) = 0.20841 in2, the rest is the G gap). The unit takes the high-subcooling branch (regime 3, Psat = 742.7 kPa = 107.7 psia from the package at 60 F; eta_s = 0.358), where G = sqrt(2 rho (P0 - Ps)): the package's inlet density is 510.07 kg/m3 = 31.84 lb/ft3 (CoolProp 8.0.0 propane reference EOS) against the API's printed 31.92 lb/ft3 (FluidFlow reports 31.64), which alone gives -0.13% on G; the remainder is the API's vapour pressure. A property-data difference in the example's chart inputs, not a defect in the omega-method branch; kept as a measured miss, so R1 stays provisional despite the passing DIERS benchmark case.

## References

- docs/unit-catalogue-plan.md §2 U-B 7

> R0 gas PSV sizing per API 520 Part I with API 526 orifice selection. V1 gap (PR 217) - the sizing layer is pinned by a unit test to the API worked example's printed inputs and published area (API RP 520 Part I Example 3.6.2.2, p. 44 — W 53500 lb/h, M 65, Z 0.84, k 1.09, T 627 R, P1 97.2 psia, Kd 0.975, Kb = Kc = 1.0, C = 326 from Table 8; published area 3179 mm2 = 4.93 in2, read from FluidFlow's results-verified reproduction of that example), but no feed in the installed packages reproduces the printed M/Z/k as a single-phase vapour (C4/C5/C6 composition search at the relieving point - M ~ 65 states are liquid or two-phase; all-vapour tops out near M 61, Z 0.854, k 1.069), so the adapter-level V1 case is withdrawn, not tuned. R1/R2 (PR 313) implement Leung omega two-phase and subcooled sizing and the API 520 inlet-loss and built-up back-pressure checks with bellows re-sizing; V1 gap - the API 520 Part I 10th ed. liquid example (fluids' "Example 5", printed result 3066 mm2 on inputs 6814 L/min, SG 0.9, set 1724 kPag, 10 percent overpressure, Kw 0.97) cannot be confirmed against the standard from this workspace, and a case-level feed would additionally need thermo density 899.1 kg/m3 at relieving conditions, so the printed arithmetic is pinned by closed-form tests (G = 52821.2752591226, A = 3.06594883829264e-3 m2) and validation ids are empty. Pure-fluid subcooled feeds run the omega path directly since the thermo two-phase PS/PH flash fix (PR 312); regime tests use pure propane.
