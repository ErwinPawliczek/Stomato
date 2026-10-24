# U-B: Pressure-change and flow units, R0

- **Phase:** Unit catalogue round 1. Read `specs/backend/U-R1-round1-conventions.md` first.
- **Depends on:** U-00, U-01
- **Packages you may edit:**
  - `src/ngdesign/units/flow/` (new);
  - `src/ngdesign/units/_physics/efficiency.py` (new; you own it);
  - `data/unit_models/flow.yaml`, `data/validation_units/flow/`;
  - `tests/units/flow/`, generated `docs/units*`.
- **GitHub issue:** #207
- **Contract change:** no
- **Benchmark delta expected:** none. `pump`, `compressor`, `expander`, `jt_valve` and
  `compression_train` stay untouched.

## Shared physics first
Create `units/_physics/efficiency.py`:

    isentropic_step(state, P_out, eta, thermo, mode="compress"|"expand") -> (outlet, power_W)

- It does a PS flash for the isentropic outlet, then a PH flash at the efficiency-corrected enthalpy.
- Pin it with a closed-form test: ideal-gas air, k = 1.4, compared with `T2s = T1·(P2/P1)^((k−1)/k)`
  within the ideal-gas deviation.
- The existing compressor/expander keep their own code in this round. Do not migrate them; migrating is a
  later byte-identical refactor.

## Units (all R0, `units/flow/`)
| id | R0 method | V1 oracle candidates |
|---|---|---|
| reciprocating_compressor | per-stage pressure ratio `r = (P_out/P_in)^(1/n_stages)`; stage outlet from `isentropic_step` with `eta_isentropic`; optional intercooling to `T_intercool` with the duty reported; volumetric efficiency `E_v = 1 − L − c·(r^(1/k) − 1)` (k from Cp/Cv at suction, c = clearance fraction, L = loss allowance) reported in info, together with the displacement needed for the actual flow | GPSA EDB Sect. 13 worked example; Perry 9th ed. Sect. 10 |
| control_valve | isenthalpic PH flash to `outlet_P` or `dP`; info `Cv` from `sizing.cv_liquid_isa` when the inlet is all liquid, and `choked: bool` from the ISA liquid criterion; vapour or two-phase Cv is reported as not-applicable at R0, never invented | ISA-75.01 / IEC 60534-2-1 liquid example; Emerson Control Valve Handbook |
| relief_valve | isenthalpic expansion to the backpressure `P_back`; required area from `sizing.psv_api520_gas` (gas service), then the next API 526 letter orifice (D…T effective areas, typed from API 526 and checked digit by digit); refuse liquid or two-phase relief at R0 | API 520 Part I worked gas example |
| pipe_segment | fixed `dP` (or `outlet_P`); isenthalpic PH flash; optional `elevation_m` hydrostatic term reported in info only at R0 | Crane TP-410 fixed-ΔP is definitional; closed-form only |
| orifice | ISO 5167 incompressible form: `ΔP = (ṁ / (Cd·E·A·Y))² / (2ρ)`, with `E = 1/√(1−β⁴)` and Y = 1 for liquids, or the ISO 5167-2 expansibility for gas; params `beta`, `bore_m`, `Cd` (given); outlet by isenthalpic flash | ISO 5167-2 annex example; Crane TP-410 |
| ejector | motive and suction inlets, one outlet at `P_out`; adiabatic mixing `H_out = H_m + H_s` with a PH flash; the entrainment ratio `ṁ_s/ṁ_m` is an input spec, and the required motive-to-suction ratio is reported in info | Perry Sect. 10 ejector example (entrainment) |
| fan | `isentropic_step` with `eta`, low ratio; power reported | Perry fan example; AMCA |

Hydraulic turbine (plan U-B 12) has no row in the catalogue; leave it, and note it in the PR body.

## Out of scope
R1 curves and maps; two-phase relief; Beggs-Brill; any compressor refactor.
