# Thermo roadmap: from 6 packages to the Aspen/HYSYS catalogue

Written 2026-10-21 after Phase 2/3 closed. Question: commercial simulators list ~170 property
methods; how does Stomato get there without 170 hand-written packages?

## The shape of the answer

The 170 are not 170 implementations. They are a handful of **families** × a set of **options**
(alpha function, mixing rule, interaction-parameter databank, vapour-phase model) × **parameter
sets**. Stomato already has the seam that makes this cheap: every package is a `Thermo` plugin
built on `ThermoSurfaceMixin` + `thermo/_state.build_flasher(ids, eos, kij_table)`, and the
`thermo` library (0.6.1) underneath ships most of the physics:

| What `thermo` 0.6.1 ships today | Count |
|---|---|
| Cubic mixture EOS classes (PR, PR78, SRK, PRSV, PRSV2, TWU-PR, TWU-SRK, API-SRK, RK, VdW, ideal gas) | 11 |
| Liquid activity models (NRTL, UNIQUAC, Wilson, Regular Solution, UNIFAC: original, Dortmund, PSRK, NIST, LLE, Lyngby) | 10 |
| Vapour models for gamma-phi (ideal gas, virial, any cubic) | 3+ |
| Reference equations (IAPWS-95 water; CoolProp Helmholtz fluids incl. GERG-2008 natural-gas mixtures) | ~120 fluids |
| Flash drivers (VL, VLN three-phase, pure VLS) | 3 |

Stomato today exposes 6 packages: `pr`, `pr78`, `srk`, `nrtl` (NRTL/PR), `amine_ke`,
`amine_enrtl`. The 1,073-line reactive amine package is the only one with real in-house physics;
the rest are configuration over the library. That ratio is the plan.

## Families and the adapter each needs

| Family | Models it yields | Adapter | Cost |
|---|---|---|---|
| **A. Cubic EOS** | PR, PR78, SRK, PRSV, PRSV2, Twu-PR, Twu-SRK, API-SRK, RK, VdW, each × k_ij databank (ChemSep, user, none) | exists (`cubic.py`); add alpha-function and volume-translation options | registration + validation only |
| **B. Gamma-phi (activity)** | NRTL, UNIQUAC, Wilson, Regular Solution, UNIFAC ×5 variants, each × vapour model (ideal, virial, PR/SRK) ≈ 30 packages | generalise `nrtl.py` into `GammaPhiPackage(liquid, vapour, params)` over `GibbsExcessLiquid`; parameters from the ChemSep databank or user tables; UNIFAC needs the group-assignment data per component | one adapter spec |
| **C. Predictive EOS/gE** | PSRK, VTPR (UNIFAC-based mixing rules), MHV2, Wong–Sandler | mixing-rule layer on the cubic adapter; `thermo` has the PSRK groups, not the mixing rule — in-house code (~300 lines, literature-exact) | one spec, medium |
| **D. Reference / Helmholtz** | IAPWS-95 steam, CoolProp pure fluids (~120), GERG-2008 and EOS-CG natural-gas mixtures | `CoolPropPhase` adapter; CoolProp as an optional dependency | one spec, small; validation is the work |
| **E. K-value correlations (classic refinery)** | Chao–Seader, Grayson–Streed, Braun K10, Lee–Kesler–Plöcker, Kabadi–Danner, Zudkevitch–Joffe | in-house; each is a published correlation of ≤100 lines; shared K-value package base that reuses the ideal-gas / Lee-Kesler departure enthalpies | one spec for the family |
| **F. SAFT / CPA** | PC-SAFT, SAFT-VR Mie, CPA, plus multi-fluid Helmholtz | bridge to `teqp` (C++ with Python bindings, maintained by NIST) — do not write SAFT by hand | one bridge spec; parameters per component are the cost |
| **G. Electrolytes** | general eNRTL, Pitzer, extended UNIQUAC; amines already done | in-house, hardest; after A–F | later |

Sum: A ≈ 25 named packages, B ≈ 30, C 4, D ≈ 120 fluids under 2 packages, E 6, F ≈ 10, G 3.
That is the commercial catalogue; what distinguishes a serious simulator is not the count but
whether each entry is validated and whether the user is steered to the right one.

## The two rules that keep this honest

1. **A model is data, not code.** `data/thermo_models.yaml` lists every package: family, adapter,
   parameter source, applicability (polar / non-polar, electrolyte, T and P window, phases), and a
   `status` of `validated` or `provisional`. The registry builds packages from this table; a new
   cubic variant or UNIFAC flavour is a YAML entry plus parameters.
2. **No validation, no `validated` status.** The P1-05 harness (`data/validation/cases.yaml`,
   `scripts/validate_properties.py`) gates every entry: pure-component Psat and density, at least
   two binary VLE sets against literature (DECHEMA / NIST TDE references), and the model's own
   canonical case (steam tables for IAPWS, GERG natural-gas density for GERG, Kremser-grade
   absorber for the K-value correlations). A `provisional` model is usable but the UI and the agent
   say so.

## The model advisor

HYSYS's value is the fluid-package wizard, not the list. `ngdesign/thermo/advisor.py`: a rules
table (component classes present, pressure, polarity, electrolytes, phases expected) → ranked
packages with the reason, exposed as the agent tool `recommend_thermo` and in the UI's package
picker. Rules come from Carlson (1996, *Chem. Eng. Prog.*, "Don't gamble with physical
properties") and the Aspen/HYSYS selection charts, cited in the module.

## Dispatch plan (Obvious threads, one spec each, parallel where the packages are disjoint)

| Spec | Scope | Depends on |
|---|---|---|
| T-01 | `thermo_models.yaml` registry-as-data, `validated/provisional` status, validation gate wired into the harness; migrate the 6 packages | — |
| T-02 | Cubic family options: alpha functions (Mathias–Copeman, Twu), volume translation, all `thermo` cubic classes registered with ChemSep k_ij where available | T-01 |
| T-03 | Gamma-phi adapter: NRTL, UNIQUAC, Wilson, UNIFAC variants × ideal/virial/cubic vapour; ChemSep parameter databank; UNIFAC group assignment from `chemicals` | T-01 |
| T-04 | Helmholtz adapter: IAPWS-95, CoolProp pure fluids, GERG-2008 mixtures (optional dependency) | T-01 |
| T-05 | Classic K-value correlations: Chao–Seader, Grayson–Streed, Braun K10, Lee–Kesler–Plöcker | T-01 |
| T-06 | Predictive mixing rules: PSRK, VTPR, MHV2, Wong–Sandler on the cubic adapter | T-02, T-03 |
| T-07 | `teqp` bridge: PC-SAFT, SAFT-VR Mie, CPA | T-01 |
| T-08 | Model advisor + agent tool + UI picker | T-01..T-05 |
| T-09 | General electrolytes (eNRTL, Pitzer) | T-03 |

T-02..T-05 run in parallel after T-01 (disjoint packages under `ngdesign/thermo/`); T-06 and T-08
follow; T-07 and T-09 when the rest is validated. Each PR carries its validation cases and its
numbers in the body; the orchestrator reviews with the harness, not by reading the code alone.

## What this does not promise

Validation data is the real cost: a package without literature cases stays `provisional`. The
`chemicals` databank covers constants for 76,522 species, but binary interaction parameters
exist only where someone measured them; the advisor must say "no parameters for this pair"
rather than silently assuming ideal behaviour (the NRTL package already refuses that).
