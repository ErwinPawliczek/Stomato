# Plan: the full property-method catalogue (≈170) with validation, orchestrated in parallel

Written 2026-10-21. Companion to `docs/thermo-roadmap.md` (the why); this is the what, who and when.

Catalogue size: **138 named methods + 30 parameter-form and databank variants = 168**, grouped into eight families. The number is Aspen/HYSYS-shaped on purpose; what matters below is that every row names its adapter, its physics source, its parameter source and its validation set, and that no row ships as `validated` without passing that set.

## 1. Catalogue

Columns: adapter = the Stomato module that builds it; physics = where the equations come from; params = where the numbers come from; validation = the layers (section 3) it must pass.

### A cubic — cubic equations of state (25)

| # | method | adapter | physics | params | validation |
|---|---|---|---|---|---|
| 1 | PR | cubic | thermo eos_mix + in-house alpha/translation/sour terms | ChemSep k_ij, user k_ij, none | L0 L1 L2 L3-natural-gas |
| 2 | PR78 | cubic | thermo eos_mix + in-house alpha/translation/sour terms | ChemSep k_ij, user k_ij, none | L0 L1 L2 L3-natural-gas |
| 3 | SRK | cubic | thermo eos_mix + in-house alpha/translation/sour terms | ChemSep k_ij, user k_ij, none | L0 L1 L2 L3-natural-gas |
| 4 | RK | cubic | thermo eos_mix + in-house alpha/translation/sour terms | ChemSep k_ij, user k_ij, none | L0 L1 L2 L3-natural-gas |
| 5 | VdW | cubic | thermo eos_mix + in-house alpha/translation/sour terms | ChemSep k_ij, user k_ij, none | L0 L1 L2 L3-natural-gas |
| 6 | PRSV | cubic | thermo eos_mix + in-house alpha/translation/sour terms | ChemSep k_ij, user k_ij, none | L0 L1 L2 L3-natural-gas |
| 7 | PRSV2 | cubic | thermo eos_mix + in-house alpha/translation/sour terms | ChemSep k_ij, user k_ij, none | L0 L1 L2 L3-natural-gas |
| 8 | Twu-PR | cubic | thermo eos_mix + in-house alpha/translation/sour terms | ChemSep k_ij, user k_ij, none | L0 L1 L2 L3-natural-gas |
| 9 | Twu-SRK | cubic | thermo eos_mix + in-house alpha/translation/sour terms | ChemSep k_ij, user k_ij, none | L0 L1 L2 L3-natural-gas |
| 10 | API-SRK | cubic | thermo eos_mix + in-house alpha/translation/sour terms | ChemSep k_ij, user k_ij, none | L0 L1 L2 L3-natural-gas |
| 11 | PR-Boston-Mathias | cubic | thermo eos_mix + in-house alpha/translation/sour terms | ChemSep k_ij, user k_ij, none | L0 L1 L2 L3-natural-gas |
| 12 | SRK-Boston-Mathias | cubic | thermo eos_mix + in-house alpha/translation/sour terms | ChemSep k_ij, user k_ij, none | L0 L1 L2 L3-natural-gas |
| 13 | PR-Mathias-Copeman | cubic | thermo eos_mix + in-house alpha/translation/sour terms | ChemSep k_ij, user k_ij, none | L0 L1 L2 L3-natural-gas |
| 14 | SRK-Mathias-Copeman | cubic | thermo eos_mix + in-house alpha/translation/sour terms | ChemSep k_ij, user k_ij, none | L0 L1 L2 L3-natural-gas |
| 15 | PR volume-translated (Peneloux) | cubic | thermo eos_mix + in-house alpha/translation/sour terms | ChemSep k_ij, user k_ij, none | L0 L1 L2 L3-natural-gas |
| 16 | SRK volume-translated (Peneloux) | cubic | thermo eos_mix + in-house alpha/translation/sour terms | ChemSep k_ij, user k_ij, none | L0 L1 L2 L3-natural-gas |
| 17 | Sour PR | cubic | thermo eos_mix + in-house alpha/translation/sour terms | ChemSep k_ij, user k_ij, none | L0 L1 L2 L3-natural-gas |
| 18 | Sour SRK | cubic | thermo eos_mix + in-house alpha/translation/sour terms | ChemSep k_ij, user k_ij, none | L0 L1 L2 L3-natural-gas |
| 19 | Kabadi-Danner SRK | cubic | thermo eos_mix + in-house alpha/translation/sour terms | ChemSep k_ij, user k_ij, none | L0 L1 L2 L3-natural-gas |
| 20 | Zudkevitch-Joffe RK | cubic | thermo eos_mix + in-house alpha/translation/sour terms | ChemSep k_ij, user k_ij, none | L0 L1 L2 L3-natural-gas |
| 21 | Twu-Sim-Tassone | cubic | thermo eos_mix + in-house alpha/translation/sour terms | ChemSep k_ij, user k_ij, none | L0 L1 L2 L3-natural-gas |
| 22 | PR-BM (Aspen PR-BM) | cubic | thermo eos_mix + in-house alpha/translation/sour terms | ChemSep k_ij, user k_ij, none | L0 L1 L2 L3-natural-gas |
| 23 | RKS-BM (Aspen RKS-BM) | cubic | thermo eos_mix + in-house alpha/translation/sour terms | ChemSep k_ij, user k_ij, none | L0 L1 L2 L3-natural-gas |
| 24 | PR Lee-Kesler enthalpy | cubic | thermo eos_mix + in-house alpha/translation/sour terms | ChemSep k_ij, user k_ij, none | L0 L1 L2 L3-natural-gas |
| 25 | SRK Lee-Kesler enthalpy | cubic | thermo eos_mix + in-house alpha/translation/sour terms | ChemSep k_ij, user k_ij, none | L0 L1 L2 L3-natural-gas |

### B gamma-phi — activity-coefficient liquid × vapour model (60)

| # | method | adapter | physics | params | validation |
|---|---|---|---|---|---|
| 1 | NRTL / ideal gas | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 2 | NRTL / virial Hayden-O'Connell | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 3 | NRTL / virial Nothnagel | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 4 | NRTL / RK vapour | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 5 | NRTL / PR vapour | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 6 | UNIQUAC / ideal gas | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 7 | UNIQUAC / virial Hayden-O'Connell | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 8 | UNIQUAC / virial Nothnagel | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 9 | UNIQUAC / RK vapour | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 10 | UNIQUAC / PR vapour | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 11 | Wilson / ideal gas | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 12 | Wilson / virial Hayden-O'Connell | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 13 | Wilson / virial Nothnagel | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 14 | Wilson / RK vapour | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 15 | Wilson / PR vapour | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 16 | van Laar / ideal gas | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 17 | van Laar / virial Hayden-O'Connell | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 18 | van Laar / virial Nothnagel | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 19 | van Laar / RK vapour | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 20 | van Laar / PR vapour | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 21 | Margules / ideal gas | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 22 | Margules / virial Hayden-O'Connell | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 23 | Margules / virial Nothnagel | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 24 | Margules / RK vapour | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 25 | Margules / PR vapour | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 26 | Regular Solution / ideal gas | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 27 | Regular Solution / virial Hayden-O'Connell | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 28 | Regular Solution / virial Nothnagel | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 29 | Regular Solution / RK vapour | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 30 | Regular Solution / PR vapour | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 31 | UNIFAC / ideal gas | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 32 | UNIFAC / virial Hayden-O'Connell | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 33 | UNIFAC / virial Nothnagel | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 34 | UNIFAC / RK vapour | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 35 | UNIFAC / PR vapour | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 36 | UNIFAC-Dortmund / ideal gas | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 37 | UNIFAC-Dortmund / virial Hayden-O'Connell | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 38 | UNIFAC-Dortmund / virial Nothnagel | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 39 | UNIFAC-Dortmund / RK vapour | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 40 | UNIFAC-Dortmund / PR vapour | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 41 | UNIFAC-PSRK / ideal gas | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 42 | UNIFAC-PSRK / virial Hayden-O'Connell | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 43 | UNIFAC-PSRK / virial Nothnagel | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 44 | UNIFAC-PSRK / RK vapour | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 45 | UNIFAC-PSRK / PR vapour | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 46 | UNIFAC-NIST / ideal gas | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 47 | UNIFAC-NIST / virial Hayden-O'Connell | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 48 | UNIFAC-NIST / virial Nothnagel | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 49 | UNIFAC-NIST / RK vapour | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 50 | UNIFAC-NIST / PR vapour | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 51 | UNIFAC-LLE / ideal gas | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 52 | UNIFAC-LLE / virial Hayden-O'Connell | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 53 | UNIFAC-LLE / virial Nothnagel | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 54 | UNIFAC-LLE / RK vapour | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 55 | UNIFAC-LLE / PR vapour | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 56 | UNIFAC-Lyngby / ideal gas | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 57 | UNIFAC-Lyngby / virial Hayden-O'Connell | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 58 | UNIFAC-Lyngby / virial Nothnagel | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 59 | UNIFAC-Lyngby / RK vapour | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |
| 60 | UNIFAC-Lyngby / PR vapour | gamma-phi | thermo GibbsExcessLiquid + VirialGas/CEOSGas; HOC and Nothnagel virial in-house | ChemSep NRTL/UNIQUAC/Wilson tables, UNIFAC groups via chemicals, user tables | L0 L1 L2 L3-azeotrope |

### C predictive mixing — predictive gE mixing rules on cubics (9)

| # | method | adapter | physics | params | validation |
|---|---|---|---|---|---|
| 1 | PSRK | cubic+gE mixing rule | in-house mixing rules on thermo cubics; UNIFAC/NRTL gE from family B | UNIFAC groups, NRTL tables | L0 L1 L2 L3-polar-high-P |
| 2 | VTPR | cubic+gE mixing rule | in-house mixing rules on thermo cubics; UNIFAC/NRTL gE from family B | UNIFAC groups, NRTL tables | L0 L1 L2 L3-polar-high-P |
| 3 | PR-MHV1 | cubic+gE mixing rule | in-house mixing rules on thermo cubics; UNIFAC/NRTL gE from family B | UNIFAC groups, NRTL tables | L0 L1 L2 L3-polar-high-P |
| 4 | PR-MHV2 | cubic+gE mixing rule | in-house mixing rules on thermo cubics; UNIFAC/NRTL gE from family B | UNIFAC groups, NRTL tables | L0 L1 L2 L3-polar-high-P |
| 5 | SRK-MHV2 | cubic+gE mixing rule | in-house mixing rules on thermo cubics; UNIFAC/NRTL gE from family B | UNIFAC groups, NRTL tables | L0 L1 L2 L3-polar-high-P |
| 6 | PR-Wong-Sandler | cubic+gE mixing rule | in-house mixing rules on thermo cubics; UNIFAC/NRTL gE from family B | UNIFAC groups, NRTL tables | L0 L1 L2 L3-polar-high-P |
| 7 | SRK-Wong-Sandler | cubic+gE mixing rule | in-house mixing rules on thermo cubics; UNIFAC/NRTL gE from family B | UNIFAC groups, NRTL tables | L0 L1 L2 L3-polar-high-P |
| 8 | PR-Huron-Vidal | cubic+gE mixing rule | in-house mixing rules on thermo cubics; UNIFAC/NRTL gE from family B | UNIFAC groups, NRTL tables | L0 L1 L2 L3-polar-high-P |
| 9 | LCVM | cubic+gE mixing rule | in-house mixing rules on thermo cubics; UNIFAC/NRTL gE from family B | UNIFAC groups, NRTL tables | L0 L1 L2 L3-polar-high-P |

### D Helmholtz / reference — reference and Helmholtz equations (10)

| # | method | adapter | physics | params | validation |
|---|---|---|---|---|---|
| 1 | IAPWS-95 steam | helmholtz | thermo IAPWS95 phases, CoolProp (optional dep); BWRS in-house | built-in reference parameters | L0 L1 L3-steam-tables L3-GERG-density |
| 2 | IAPWS-IF97 steam | helmholtz | thermo IAPWS95 phases, CoolProp (optional dep); BWRS in-house | built-in reference parameters | L0 L1 L3-steam-tables L3-GERG-density |
| 3 | ASME/NBS steam | helmholtz | thermo IAPWS95 phases, CoolProp (optional dep); BWRS in-house | built-in reference parameters | L0 L1 L3-steam-tables L3-GERG-density |
| 4 | CoolProp pure Helmholtz (Span-Wagner family) | helmholtz | thermo IAPWS95 phases, CoolProp (optional dep); BWRS in-house | built-in reference parameters | L0 L1 L3-steam-tables L3-GERG-density |
| 5 | GERG-2008 | helmholtz | thermo IAPWS95 phases, CoolProp (optional dep); BWRS in-house | built-in reference parameters | L0 L1 L3-steam-tables L3-GERG-density |
| 6 | EOS-CG | helmholtz | thermo IAPWS95 phases, CoolProp (optional dep); BWRS in-house | built-in reference parameters | L0 L1 L3-steam-tables L3-GERG-density |
| 7 | AGA8-DC92 | helmholtz | thermo IAPWS95 phases, CoolProp (optional dep); BWRS in-house | built-in reference parameters | L0 L1 L3-steam-tables L3-GERG-density |
| 8 | MBWR (methane, nitrogen...) | helmholtz | thermo IAPWS95 phases, CoolProp (optional dep); BWRS in-house | built-in reference parameters | L0 L1 L3-steam-tables L3-GERG-density |
| 9 | BWRS | helmholtz | thermo IAPWS95 phases, CoolProp (optional dep); BWRS in-house | built-in reference parameters | L0 L1 L3-steam-tables L3-GERG-density |
| 10 | BWR-Lee-Starling | helmholtz | thermo IAPWS95 phases, CoolProp (optional dep); BWRS in-house | built-in reference parameters | L0 L1 L3-steam-tables L3-GERG-density |

### E K-value correlations — classic K-value correlations (10)

| # | method | adapter | physics | params | validation |
|---|---|---|---|---|---|
| 1 | Chao-Seader | kvalue | in-house correlations with Lee-Kesler departure enthalpies | published coefficients | L0 L1 L3-refinery-flash |
| 2 | Grayson-Streed | kvalue | in-house correlations with Lee-Kesler departure enthalpies | published coefficients | L0 L1 L3-refinery-flash |
| 3 | Grayson-Streed extended | kvalue | in-house correlations with Lee-Kesler departure enthalpies | published coefficients | L0 L1 L3-refinery-flash |
| 4 | Braun K10 | kvalue | in-house correlations with Lee-Kesler departure enthalpies | published coefficients | L0 L1 L3-refinery-flash |
| 5 | Lee-Kesler-Plöcker | kvalue | in-house correlations with Lee-Kesler departure enthalpies | published coefficients | L0 L1 L3-refinery-flash |
| 6 | Esso tabular | kvalue | in-house correlations with Lee-Kesler departure enthalpies | published coefficients | L0 L1 L3-refinery-flash |
| 7 | Antoine ideal K | kvalue | in-house correlations with Lee-Kesler departure enthalpies | published coefficients | L0 L1 L3-refinery-flash |
| 8 | Ideal (Raoult) | kvalue | in-house correlations with Lee-Kesler departure enthalpies | published coefficients | L0 L1 L3-refinery-flash |
| 9 | Henry's law (Sander) ideal liquid | kvalue | in-house correlations with Lee-Kesler departure enthalpies | published coefficients | L0 L1 L3-refinery-flash |
| 10 | Ideal gas / ideal liquid with Lee-Kesler departures | kvalue | in-house correlations with Lee-Kesler departure enthalpies | published coefficients | L0 L1 L3-refinery-flash |

### F SAFT / CPA — SAFT and CPA through the teqp bridge (8)

| # | method | adapter | physics | params | validation |
|---|---|---|---|---|---|
| 1 | PC-SAFT | teqp bridge | teqp (NIST, MIT licence) Python bindings | published pure-component parameters; k_ij | L0 L1 L2 L3-associating |
| 2 | PC-SAFT polar | teqp bridge | teqp (NIST, MIT licence) Python bindings | published pure-component parameters; k_ij | L0 L1 L2 L3-associating |
| 3 | SAFT-VR Mie | teqp bridge | teqp (NIST, MIT licence) Python bindings | published pure-component parameters; k_ij | L0 L1 L2 L3-associating |
| 4 | soft-SAFT | teqp bridge | teqp (NIST, MIT licence) Python bindings | published pure-component parameters; k_ij | L0 L1 L2 L3-associating |
| 5 | CPA-SRK | teqp bridge | teqp (NIST, MIT licence) Python bindings | published pure-component parameters; k_ij | L0 L1 L2 L3-associating |
| 6 | CPA-PR | teqp bridge | teqp (NIST, MIT licence) Python bindings | published pure-component parameters; k_ij | L0 L1 L2 L3-associating |
| 7 | multi-fluid Helmholtz via teqp | teqp bridge | teqp (NIST, MIT licence) Python bindings | published pure-component parameters; k_ij | L0 L1 L2 L3-associating |
| 8 | GERG via teqp (cross-check of D) | teqp bridge | teqp (NIST, MIT licence) Python bindings | published pure-component parameters; k_ij | L0 L1 L2 L3-associating |

### G electrolytes / reactive — electrolytes and reactive solvents (10)

| # | method | adapter | physics | params | validation |
|---|---|---|---|---|---|
| 1 | Kent-Eisenberg amines (done) | electrolyte / reactive | in-house (amine package pattern) | literature speciation constants | L0 L1 L2-loading-isotherms L3-loop-cases |
| 2 | electrolyte-NRTL amines (done) | electrolyte / reactive | in-house (amine package pattern) | literature speciation constants | L0 L1 L2-loading-isotherms L3-loop-cases |
| 3 | general electrolyte NRTL | electrolyte / reactive | in-house (amine package pattern) | literature speciation constants | L0 L1 L2-loading-isotherms L3-loop-cases |
| 4 | eNRTL-RK | electrolyte / reactive | in-house (amine package pattern) | literature speciation constants | L0 L1 L2-loading-isotherms L3-loop-cases |
| 5 | Pitzer | electrolyte / reactive | in-house (amine package pattern) | literature speciation constants | L0 L1 L2-loading-isotherms L3-loop-cases |
| 6 | Pitzer-Debye-Hückel | electrolyte / reactive | in-house (amine package pattern) | literature speciation constants | L0 L1 L2-loading-isotherms L3-loop-cases |
| 7 | extended UNIQUAC | electrolyte / reactive | in-house (amine package pattern) | literature speciation constants | L0 L1 L2-loading-isotherms L3-loop-cases |
| 8 | sour water (API) | electrolyte / reactive | in-house (amine package pattern) | literature speciation constants | L0 L1 L2-loading-isotherms L3-loop-cases |
| 9 | physical solvents (Selexol-type) in gamma-phi | electrolyte / reactive | in-house (amine package pattern) | literature speciation constants | L0 L1 L2-loading-isotherms L3-loop-cases |
| 10 | glycol package (TEG/MEG dehydration, tuned PR) | electrolyte / reactive | in-house (amine package pattern) | literature speciation constants | L0 L1 L2-loading-isotherms L3-loop-cases |

### H solids / polymers / special — solids, polymers, special chemistry (6)

| # | method | adapter | physics | params | validation |
|---|---|---|---|---|---|
| 1 | Solids (ideal solid + solubility product) | special | in-house; polymer SAFT via teqp | literature | L0 L1 L3-special |
| 2 | Polymer NRTL | special | in-house; polymer SAFT via teqp | literature | L0 L1 L3-special |
| 3 | Polymer PC-SAFT | special | in-house; polymer SAFT via teqp | literature | L0 L1 L3-special |
| 4 | Polymer SRK | special | in-house; polymer SAFT via teqp | literature | L0 L1 L3-special |
| 5 | Hayden-O'Connell carboxylic acid dimerisation | special | in-house; polymer SAFT via teqp | literature | L0 L1 L3-special |
| 6 | HF hexamerisation model | special | in-house; polymer SAFT via teqp | literature | L0 L1 L3-special |

### Parameter-form and databank variants (30)

Same adapter as their family; they differ in parameter form, reference state or paired vapour/density model, and each is a registry entry with its own validation cases.

| # | variant | family |
|---|---|---|
| 1 | NRTL two-parameter / five-parameter (T-dependent) forms | B |
| 2 | UNIQUAC two-parameter / T-dependent forms | B |
| 3 | Wilson two-parameter / T-dependent forms | B |
| 4 | Wilson liquid-reference (Wilson-LR, Wilson-GLR) | B |
| 5 | NRTL-SAC (segment activity) | B |
| 6 | COSMO-SAC (sigma profiles) | B |
| 7 | UNIFAC with Lyngby / Dortmund T-dependence switch | B |
| 8 | Van Laar / Margules three-suffix forms | B |
| 9 | PR with Boston-Mathias extrapolation above Tc | A |
| 10 | SRK with Boston-Mathias extrapolation above Tc | A |
| 11 | PR / SRK with Rackett liquid density | A |
| 12 | PR / SRK with COSTALD liquid density | A |
| 13 | PR / SRK with API liquid density | A |
| 14 | Schwartzentruber-Renon (SR-POLAR) | C |
| 15 | Predictive SRK with Gmehling T-dependent groups | C |
| 16 | Steam tables selectable per water stream (free-water decant) | D |
| 17 | Water/hydrocarbon free-water method (Kabadi-Danner + NBS) | D |
| 18 | Grayson-Streed with Lee-Kesler enthalpies | E |
| 19 | Chao-Seader with Lee-Kesler enthalpies | E |
| 20 | BK10 with ideal enthalpies | E |
| 21 | ENRTL with Redlich-Kwong vapour | G |
| 22 | ENRTL with Hayden-O'Connell vapour | G |
| 23 | Pitzer with Hayden-O'Connell vapour | G |
| 24 | Amine package with physical-solvent co-absorption (Sulfolane) | G |
| 25 | Mixed amines (MDEA+PZ) | G |
| 26 | DEA / DGA / DIPA / AMP speciation sets | G |
| 27 | Electrolyte NRTL with crystallisation (solids) | H |
| 28 | Ideal + Henry for dilute gases in water | E |
| 29 | Polymer UNIFAC-FV | H |
| 30 | Flory-Huggins | H |

**COSMO-SAC (variant 6): built 2026-11-04 as `cosmo_sac_ig`** (provisional). The earlier licence block
(UD profiles: "non-profit, academic purposes", no redistribution) is lifted by the 2026-11-04
decision that defers licensing; the profiles shipped are recorded with that licence text. See the
"Closed 2026-11-04" entry in section 6.

## 6. Methods still open, and what was checked (2026-11-01, rechecked 2026-11-03 and 2026-11-04)

Each stays open because a parameter or definition could not be sourced openly; no row was
written around the gap.

- **COSMO-SAC**: closed 2026-11-04 (`cosmo_sac_ig`, provisional); see "Closed 2026-11-04 (blocked-methods pass)" below.
- **PR / SRK with API liquid density**: for real components the method is Rackett with ideal mixing (Aspen 10.1, p. 3-92), which `pr-rackett` covers. The pseudo-component branch is a fit to API TDB Figure 6A3.5 that is not published.
  - **Rechecked 2026-11-04 (licences deferred):** the Aspen 10.1 manual (sites.chemengr.ucsb.edu/~ceweb/courses/che184b/aspenplus/PhysPropMeth&Models.pdf, p. 3-92) was re-read: V = x_p V_p + x_r V_r, with V_p = fcn(T, Tb, API) "a correlation based on API Figure 6A3.5 (API Technical Data Book, 4th ed.)" and the mixture Rackett (VL2RKT, Chueh-Prausnitz Vc-weighted Tc, p. 3-100) for real components. The only closed form found for 6A3.5 is commented-out code in pychemqt (raw.githubusercontent.com/jjgomera/pychemqt/master/lib/petro.py, "API procedure 6A3.5, pag 494", 6th ed.): rho [lb/ft3] = 62.3636 sqrt(SG^2 - (1.2655 SG - 0.5098 + 8.011e-5 Tb[R]) (T[R] - 519.67)/Tb[R]). It is secondary, uncited to an edition Aspen uses, and has no worked example; the API TDB itself was not retrievable (only paywalled stores: ASTM, accuristech, normservis; Scribd copies are login-walled; eprints.kfupm.edu.sa returned 401; jmcampbell.com prints equations as images). No row was built: the pseudo-component branch would rest on an unverified constant set with no reference value to check it against. Next step: a library copy of API TDB ch. 6 (procedure 6A3.5 and its example).
- **SR-POLAR**: equations are in the Aspen documentation, but no citable polar-parameter table was found. Schwartzentruber et al. 1989 is closed; NeqSim's columns are uncited. Rechecked 2026-11-03:
  - **Mangold et al. 2019** (J. Supercrit. Fluids 153, 104476, doi:10.1016/j.supflu.2019.02.016, CC BY 4.0) prints an SR-type alpha (eq. 22) and Table 5 polar parameters for H2O, O2, N2 and CO2. They do not close the row. They were fitted in Aspen Plus to enthalpy and Cp, not to vapour pressure. Water carries separate liquid and vapour sets, which cannot drive a VLE flash. The paper validates volume, enthalpy and Cp errors only, with no vapour pressures to check a VLE implementation against.
  - **The alpha form itself is ambiguous in open print.** Mangold and Alanazi et al. 2022 (Energy Convers. Manage. X 15, 100257, CC BY) write the polar term with (1 - Tr). The Aspen 2006.5 manual (p. 61, eq. 11) writes it with (1 - Tr^0.5). The original paper that would settle it, Ind. Eng. Chem. Res. 28 (1989) 1049, is still closed.
  - **Young, Pessoa & Ahon 2016** (Ind. Eng. Chem. Res. 55, 6506): only the CC BY-NC supplement is open. Its "SRW" SC1-SC3 values for 56 compounds are Peng-Robinson-based, and the closed main text holds their formula.
  - **NIST TDE help page:** prints the PR-SRW alpha but no values.
  - **2026-11-03 (later):** a web search for an open table of Schwartzentruber-Renon polar parameters found nothing new.
  - **2026-11-03 (third pass):** a further search for the p1-p3 polar parameters returned no chemical-engineering source.
  - **2026-11-04 (licences deferred):** the equations are now settled from two Aspen manuals read as page images (Aspen 10.1, sites.chemengr.ucsb.edu/.../PhysPropMeth&Models.pdf pp. 3-34/35, 3-46, 3-47; a later "Thermodynamic Property Models" chapter, sites.poli.usp.br/d/pqi2408/physpropmodels.pdf pp. 43, 59-62). SR-POLAR uses the extended Mathias alpha with the (1 - Tr^0.5) polar term (RKUPP0-2; eq. 11) and Boston-Mathias above Tc with d = 1 + m/2 - p1(1 + p2 + p3); the (1 - Tr) form of Mangold et al. is the different Schwartzentruber-Renon-Watanasiri alpha (RKSSRP, eq. 15). Mixing: a = sum x_i x_j (a_i a_j)^0.5 [1 - k_a,ij - l_ij (x_i - x_j)], b = sum x_i x_j (b_i + b_j)/2 (1 - k_b,ij), l_ij = -l_ji. Still missing: the volume-translation function c_i(T/Tc) (neither manual prints it) and any published p1-p3 for a real compound in the RKUPP form. Fetch failures: IECR 28 (1989) 1049 (doi:10.1021/ie00091a026) 403 at doi.org and pubs.acs.org; FPE 52 (1989) 127 (doi:10.1016/0378-3812(89)80319-x) ScienceDirect 403; web.ist.utl.pt Aspen PDF 403; molakirlee.github.io Aspen PDFs 404; Semantic Scholar API 429. Mangold's Table 5 values (FHNW copy, irf.fhnw.ch) belong to the SRW (1 - Tr) alpha and were fitted to enthalpy/Cp, so they cannot parameterise SR-POLAR. Still BLOCKED on parameters; no row.
- **Polymer SRK**: no model equations or pure-polymer parameters were obtained; Orbey & Sandler 1994 was not reachable. Rechecked 2026-11-03:
  - **Orbey, Bokis & Chen 1998** (Ind. Eng. Chem. Res. 37, 4481) is closed (OpenAlex).
  - **The only open trace** is a third-party seminar deck (Korea Univ.; pdfs.semanticscholar.org/7970/1dfc...). It scans Table 1: LDPE segment c1 1.0, c2 0, c3 0; ethylene c1 0.656855, c2 -0.362904, c3 0.676711. It retypes the polymer Tc/Pc rules, (Tc - 1300)/(Tc,m - 1300) = D_P^-0.25 and (Pc - 5)/(Pc,m - 5) = 1/D_P. These are secondary and unlicensed. The deck leaves the reference state "m" and the gE model undefined, and omits the separator pressures and chi needed to rerun the paper's Table 2c flash.
  - **Guerrieri et al. 2012** (IntechOpen, doi:10.5772/48391) covers the method qualitatively only.
  - **2026-11-04 (licences deferred):** the equations were found in the Aspen Polymers Plus User Guide vol. 2, v3 for Aspen Plus 10 (sites.chemengr.ucsb.edu/~ceweb/courses/che184b/aspenplus/PolymersPlusUserGuideVolume1.pdf, sec. 3.10, pp. 3-115 to 3-122): POLYSRK = SRK with Mathias-Copeman alpha (RKSMCP), b = sum x_i b_i, and a/(bRT) = sum x_i a_i/(RT b_i) - 1.546 (G^E/RT + sum x_i ln(b/b_i)) over POLYNRTL. The manual gives no degree-of-polymerisation Tc/Pc rule; it recommends Tc > 1000 K, Pc < 1e6 Pa and zero Mathias-Copeman parameters for polymers, and supplies none of them. The only open parameter set is Kiss, Dimian & Iedema, Studia UBB Chemia 54(2) 121 (2009) (studia.reviste.ubbcluj.ro/index.php/chemia/issue/download/801/2835), Tables 6-7: ethylene/PE Tc, Pc, RKSMCP and FHCHI regressed by the authors to the very ethylene-LDPE TPXY table (Hao et al. DECHEMA) they print, the Pc units are not stated (130.67 for ethylene fits neither bar nor kPa), and the gE term is Flory-Huggins, not POLYNRTL. A row on it would validate on its own fitted points with ambiguous units. Not reachable: IECR 37 (1998) 4481 (doi:10.1021/ie980220+), FPE 145 (1998) 169 (doi:10.1016/s0378-3812(97)00340-3), IECR 37 (1998) 1567 (doi:10.1021/ie970674r) - not OA per OpenAlex/Unpaywall; AIChE J 40 (1994) 1203 (doi:10.1002/aic.690400711) METU handle without a file; ResearchGate/ScienceDirect 403; the Korea Univ. deck link now 404s. Still BLOCKED; no row.
- **Sulfolane co-absorption**: Jalili et al. 2015 raw data fix CO2 and H2S Henry constants in sulfolane, but no fetched source gives a mixed-solvent rule, and the OSTI Sulfinol report gives conditions without data points. Rechecked 2026-11-03:
  - **MacGregor 1988** (Univ. of Alberta MSc thesis, sulfolane + MDEA + water at 40 and 100 C) is the only open source found with both a mixed-solvent rule and tabulated data. It uses Deshmukh-Mather, with sulfolane + water lumped as one solvent and a mixture dielectric constant scaling the equilibrium constants. Its terms ("solely for non-commercial purposes ... may not otherwise be copied or reproduced") exclude a proprietary repository, so it is refused and nothing from it ships. Roberts 1983 (AMP + sulfolane, same archive) carries the same terms.
  - **NIST ThermoML files** (NIST open licence, posted with the publishers' permission) give CO2 and H2S solubility in aqueous sulfolane: Shokouhi et al., J. Chem. Thermodyn. 132 (2019) 62 and 106 (2017) 232. They are usable as validation anchors, but they contain no amine. The sulfolane + MDEA + water file (Shirazizadeh & Haghtalab, J. Chem. Thermodyn. 133 (2019) 111) holds no CO2 data in the quaternary.
  - **Not reachable openly:** the Isaacs/Otto/Mather Sulfinol paper (OSTI abstract only), Qian et al. 1995 (OSTI record only), and Hirohama et al. 2021.
  - **Net:** there is still no open, redistributable mixed-solvent rule for amine + sulfolane.
- **DEA / DGA / DIPA / AMP speciation sets**: DEA is `amine_ke`, DGA and AMP are `amine_ke_dga_amp`. DIPA has a pKa but no carbamate constant and no tabulated VLE anchor, so the item stays open. Rechecked 2026-11-03:
  - **MacGregor 1988** (Univ. of Alberta thesis, ERA) has DIPA and Sulfinol data, but its terms say "solely for non-commercial purposes ... may not otherwise be copied or reproduced". Refused: none of its constants or data ship.
  - **A DIPA pKa** can be converted from the delta-G and delta-H values cited in the secondary Hamborg report, but the carbamate constant is still missing. No partial DIPA speciation model is built; one without carbamate formation would misstate CO2 loading.
  - **NIST ThermoML files** ship under the NIST open licence "with permission of the journal publishers". They are acceptable as validation anchors, with the DOI cited, once a full model exists.
  - **2026-11-03 (third pass):** a search for an openly licensed DIPA carbamate stability constant found Gupta & Svendsen 2020 (Int. J. Greenh. Gas Control, modelled carbamate constants, licence not shown) and Lee et al. 2024 (J. Mol. Liq., DIPA + AMP solubility, no open file). Neither is usable: the first models rather than states the constant, and the second is not open.

- **Special family, five rows still `experimental`** (re-decided 2026-11-03, updated 2026-11-04; each row's notes in `data/thermo_models/special.yaml` carry the full reason):
  - `polymer_nrtl`: blocked on parameters. The shipped segment tau/alpha are illustrative; no open, licensed Chen (1993) table was found.
  - `flory_huggins`: no published-reference test (only hand reductions of the closed form). The POLY_PS segment count r = 962 cites a course note and is the repeat-unit count, not the FH molar-volume ratio (about 890). The chi primary (Gunduz & Dincer 1980) is paywalled and was not re-read. Open polystyrene/toluene data searched: Pavlicek, Bogdanic & Wichterle, Chem. Biochem. Eng. Q. 29(1) 1 (2015), doi:10.15255/CABEQ.2015.2183, sits behind a bot challenge on hrcak.srce.hr and its licence could not be verified; the Gupta & Prausnitz eScholarship report returned HTTP 403.
  - `unifac_fv`: the 2026-11-03 physics gaps are fixed (2026-11-04 entry below). It stays experimental because no open polystyrene/toluene solvent-activity table exists to test against, the free-volume term uses fixed reference specific volumes rather than volumes at the flash T, and whether Oishi & Prausnitz include the Staverman-Guggenheim surface term in the combinatorial could not be checked against the paywalled paper.
  - `hf_hexamer`: the association vapour is now its flash vapour (2026-11-04 entry below). It stays experimental because the databank HF vapour-pressure correlation ("Fit 2023", fitted over 293-454 K) has a nearly flat d ln Psat/dT across 300-320 K. The PhiSat liquid enthalpy therefore gives a saturated-liquid Cp of 0.1 J/(mol K) at 300 K (-152 J/(mol K) with no association), and the latent heat misses the VDI Heat Atlas table by -14.4 % at the boiling point. Fixing that is a databank change.
  - `polymer_pc_saft`: teqp is still absent locally, no licensed polystyrene/toluene binary table was retrieved, and k_ij = 0 is uncited.
- **General eNRTL and extended UNIQUAC beyond NaCl** (2026-11-04): the adapters are generalised, but no salt was added, because no open, redistributable, primary-cited parameter set was found.
  - **Generalised** (`ngdesign.amine.electrolyte`):
    - Both models are now single-salt forms with the salt parameters as data, keyed by salt id and ion pair. They use the same `salts` keys as `pitzer.yaml`: cation, anion, z, nu and molality_cap.
    - **eNRTL:** the PDH term runs on I_x = (z_c^2 x_c + z_a^2 x_a)/2, and the Chen & Evans 1986 single-salt local-composition G^E runs on X_i = z_i x_i.
    - **Extended UNIQUAC:** species order is (H2O, cation, anion), with Debye-Hueckel on I, z_i^2 ion terms and a nu-weighted mean. A salt whose ions lack r, q or a u_ij pair refuses.
    - **Shared with Pitzer:** the ion-pair parsing, the unknown-salt refusal and the SLE solve now come from one owner (`SaltIons`, `_salt_entry`, `_sle_molality`).
    - **Package wiring:** supports, caps, the a_w dispatch and the multi-salt refusal are data-driven per model. The crystallisation row takes its salt from the feed.
    - **NaCl bit-identical:** a 1125-line repr snapshot was diffed before and after. It covers the activity, osmotic and saturation functions, PT/PH/PS/TVF/PVF flashes, bubble and dew points, K-values, phase props, derivatives and refusal messages on all eight NaCl rows.
    - **Tests:** the charge and stoichiometry branches are exercised in tests/thermo/test_electrolyte_general.py, with a synthetic test-only 2:1 entry that is never shipped. They check the limiting law with |z_c z_a|, Gibbs-Duhem with nu = 3, and the flash running on the salt's own a_w.
    - **Measured limit:** the eNRTL numeric-derivative infinite-dilution reference biases ln gamma by about 2|z_c z_a| A_phi sqrt(I(h)). That is 1.1e-3 for NaCl at 2 m and 3.8e-3 for a 2:1 salt. It is kept so NaCl stays bit-identical.
  - **What was checked for parameters and refused:**
    - **Kwaterski & Herri on HAL:** hal-00978703 (Fluid Phase Equilib. 371, 2014, doi:10.1016/j.fluid.2014.02.032), hal-00617438 and hal-00617434. The HAL API `licence_s` of all three is `hal-authorisation-v1`: copyright reserved, and reproduction or adaptation needs the rights holder's permission. Its KCl/CaCl2 tau are therefore not usable. **This is also the copy the shipped NaCl tau pair was read from**, so the NaCl row's licence basis needs review; the values are Chen & Evans 1986's published numbers.
    - **Chen & Evans 1986 / Chen et al. 1982** (AIChE J.): paywalled, and no openly licensed transcription was found.
    - **IDAES** (`idaes-pse`, BSD-3): its examples carry eNRTL tau for KCl (8.1354 / -4.1341) and NaBr (9.527 / -4.790, a Song & Chen 2009 mixed-solvent fit). These are secondary code copies whose primary table is not cited; a web search for the KCl pair found no primary. Refused as not primary-cited.
    - **Leal et al., Applied Geochemistry 180, 106274 (2025)**, doi:10.1016/j.apgeochem.2024.106274: CC BY 4.0 per Crossref. The ChemRxiv preprint is CC BY-NC-ND and must not be used. Whether its tables carry ions beyond Na+/Cl- could not be read: ScienceDirect and ChemRxiv returned HTTP 403 to this session.
    - **Thomsen thesis 1997** (doi:10.11581/dtu:00000074, DTU Orbit): "all rights reserved".
    - **CERE DTU extended-UNIQUAC database:** members only. **phasediagram.dk:** no tables, (c) notice.
    - **Reaktoro `ExtendedUNIQUAC.v2023.yaml`:** LGPL-2.1, verification only.
    - **Hashemi et al., J. Chem. Petrol. Eng. 54 (2020)** (CC BY): prints no r/q/u values.
    - **Arrad, Thomsen et al., FPE 580 (2024) 114037** (CC BY): Cs+ only.
    - **Frontiers in Chemistry 2019/2020** salt papers (CC BY): a different (Xu) model, not Chen eNRTL.
    - **Not read:** CC BY extended-UNIQUAC papers whose full text was bot-blocked: Fosbøl, Stenby & Thomsen, FPE 584 (2024) 114126; Neerup et al., CES 285 (2024) 119605 and 270 (2023) 118549. These are leads if the Leal tables do not carry the ions.
  - **Next step if a set is found:** add a `salts` entry (and, for extended UNIQUAC, the ions' r, q and u0/u1 pairs). Validate it against the Hamer & Wu 1972 / Goldberg & Nuttall 1978 anchors already transcribed in tests/thermo/test_electrolyte_salts.py.

Closed 2026-11-04 (blocked-methods pass):

- **COSMO-SAC** (`cosmo_sac_ig`, provisional): COSMO-SAC 2010 (Hsieh, Sandler & Lin 2010) on three sigma profiles (NHB/OH/OT), the constants of Bell et al., J. Chem. Theory Comput. 16, 2635 (2020), Table 2 (PMC7675222, read 2026-11-04), with an ideal-gas vapour (`ngdesign.thermo.cosmo_sac`, gamma-phi liquid option `cosmo_sac`).
  - **Profiles:** 17 components (water, methanol, ethanol, acetone, chloroform, n-hexane, n-pentane, n-heptane, benzene, toluene, n-butane, 1,2-dichloroethane, acetonitrile, 1-butanol, cyclohexane, triethylamine, ethyl acetate) copied unmodified from usnistgov/COSMOSAC `profiles/UD/sigma3` (commit 1b82456b) into `data/thermo_params/cosmo_sac/profiles.yaml`, with the UD licence text in the header. Any other component refuses.
  - **Benchmark:** reproduces the reference implementation's ln gamma (`profiles/validation_data.zip`, 298.15 K, z = 0.3/0.7, dsp term removed) to 1e-6 on all 8 pairs among the shipped components, and the Hsieh, Lin & Vrabec 2014 Table 6 infinite-dilution values (12 pairs) within 2e-3 (tests/thermo/test_cosmo_sac.py).
  - **Not included:** the Hsieh 2014 dispersion term (COSMO-SAC-dsp), which the reference defines for binaries only.
  - **Validation** (bound cases; all misses assessed in the row):
    - L1 cosmo-sac-ig-pure-MeOH-330K / -H2O-370K: Psat and rho_L pass; liquid Cp -17 % / -12 % and MeOH rho_V -4.6 % miss: the gamma-phi vapour-route and ideal-gas limitations, not COSMO-SAC.
    - L2, predictive (no fitted binary parameter): MeOH/H2O Gao 2012 bubble_T +0.39 % passes but y -0.033 misses; Bayer 312.91 K bubble_P -1.4 % passes but y -0.063 misses; EtOH/H2O azeotrope bubble_T +0.20 % passes but y +0.020 just misses; MeOH/nC4 Courtial bubble_P -21.9 % misses.
    - Stays provisional: no bound case passes on every property.

Closed 2026-11-04:

- **Dimerizing-acid vapour** (`hoc_dimer`, experimental to provisional): the association kernel was only a callable function, and every flash of the row ran plain Raoult with an `IdealGas` vapour (the liquid's gE also lacked `d2GE_dT2`, so even Cp failed).
  - **Vapour phase:** `special.AssociatingGas`, a thermo `IdealGas` subclass for the chemical theory (Marek & Standart, Collect. Czech. Chem. Commun. 19, 1074 (1954); Prausnitz, Lichtenthaler & de Azevedo, Molecular Thermodynamics of Fluid-Phase Equilibria, 3rd ed., sec. 5.8-5.9). Monomer, n-mer and every non-associating component form an ideal-gas mixture in equilibrium Kp = p_n/p_M^n. The apparent fugacity coefficient of the acid is z_M/y_A, that of every other component is 1/Z, and H_dep = xi dH. V, Cp and the ln phi derivatives are analytic. Every second-order IdealGas closed form the phase does not implement raises instead of being inherited. thermo's `FlashVL` has an ideal-gas shortcut only for composition-independent K-values; the phase declares itself composition-dependent, so the library's general path is used.
  - **Liquid:** ideal on apparent composition, on thermo's `PhiSat` basis, with the acid's saturation fugacity coefficient (the pure chemical-theory vapour at (T, Psat)). A pure acid therefore still boils at its databank Psat, and the latent heat obeys Clapeyron with the associated vapour's Z.
  - **Library limitation:** thermo 0.6.1's PT stability test divides by N - 1. A small `FlashVL` subclass decides pure feeds by Gibbs energy, which is also what the PH/PS secant needs.
  - **Checks** (tests/thermo/test_special_association.py):
    - the closed form against a true-species reconstruction;
    - Gibbs-Helmholtz H_dep and V_dep, Cp, d ln phi/dT, d ln phi/dP, Gibbs-Duhem and phi_sat derivatives by finite differences;
    - Clapeyron at saturation to 1e-9;
    - all seven L0 checks, which now pass.
  - **Published data through the flash:**
    - vapour Z at 399.35 K / 1 bar: 0.6537 vs Mehling & Kleiber's measured 0.6299 (+3.8 %);
    - latent heat vs the CRC Handbook (95th ed.): 23.17 vs 23.36 kJ/mol at 298.15 K (-0.8 %) and 24.54 vs 23.70 kJ/mol at the normal boiling point (+3.5 %). An ideal-gas vapour would give 39.1 kJ/mol.
  - **Applicability narrowed to 290-400 K / 0.2 MPa:** against the VDI Heat Atlas table the latent-heat miss grows from +7.0 % at 391 K to +12.6 % at 420 K and +27 % at 460 K. Dimer-only theory on the Ritter & Simons constant under-associates at elevated pressure.
  - **Not done:** acetic acid/water VLE is not bound. Liquid non-ideality dominates its K-values, and no activity parameters regressed with this vapour model are shipped. Saturated-liquid Cp is ~20 % low, the known gamma-phi vapour-route limitation.
- **HF hexamer vapour** (`hf_hexamer`, stays experimental): the same `AssociatingGas` with n = 6 on the Jarry & Davis (1953) constants is now the flash vapour. The hexamer kernel function is a thin call into the shared state. Through the flash the saturated vapour gives association factors of 3.486 and 3.395 vs the published 3.580 and 3.438 (-2.6 %, -1.2 %), and the L0 checks pass by hand. The blocking reason is the databank vapour pressure (bullet above).
- **UNIFAC-FV fixes** (`unifac_fv`, stays experimental). Each fix is pinned by a test that fails on the old code (tests/thermo/test_special.py):
  - The residual is evaluated at the model's T; dGE/dT, d2GE/dT2 and dgamma/dT are differences of the T-dependent GE.
  - The residual runs on whole-molecule group fractions: the repeat-unit fraction N x2/(x1 + N x2), with N = Mn/m(C8H8) = 960.1, equals thermo's UNIFAC on the full molecule.
  - r is summed from the shipped UFSG R_k (Hansen et al. 1991). Toluene is 3.9228 (was a hand-typed 3.87), and the polymer's r is N times the repeat-unit sum.
  - Toluene and the repeat unit use ACCH3 and ACCH, following the DDBST assignments shipped with thermo (they were CH3 + AC and CH + AC: the same r and q, but the wrong main groups for the residual).
  - **Further bug found:** the specific volumes, stored in m3/kg, were used as cm3/g, so the reduced volumes were ~1.5e-3 instead of ~1.2-1.6. Toluene's v_spec also matched neither its stated density nor the databank; it is now 1/862.24 kg/m3.

Closed 2026-11-03/04:

- **Pitzer for more salts** (`pitzer_nacl_water`, `pitzer_hoc`, provisional): the adapter was NaCl-only. It is now the general single-salt Pitzer form (Pitzer 1991 ch. 3; |z_M z_X|, nu and the B/C stoichiometric weights per ion pair), with salt parameters as data keyed by salt id and ion pair in `data/thermo_params/electrolyte/pitzer.yaml`.
  - **Byte-identical:** for 1:1 salts the weights are exactly 1.0, so the NaCl outputs are bit-for-bit unchanged. This was checked with a repr snapshot of the Pitzer functions and of flashes, bubble points, phase properties, K-values and derivatives on all eight NaCl rows, before and after. Only the formerly-refused KCl feeds differ.
  - **Salts added:** KCl, KBr, LiCl, NaBr and MgCl2, at the PHRQPITZ 25 C values printed in USGS WRI 88-4153 (Plummer, Parkhurst, Fleming & Dunkle 1988, doi:10.3133/wri884153), Attachment C.6, pp. 190-192. The scanned pages were read as images, not OCR. Each value carries the report's own primary reference: Harvie, Moller & Weare 1984 for KCl and MgCl2, Pitzer & Mayorga 1973 for KBr, LiCl and NaBr.
  - **Licence:** the report is a U.S. Government work. The PHREEQC User Rights Notice (`doc/NOTICE.TXT`, usgs-coupled/phreeqc3) permits use, copy, modification and distribution, commercial included, with acknowledgement; it is acknowledged in the params file.
  - **Why not the current pitzer.dat:** it refits NaCl, KCl and MgCl2 with T-terms (Appelo 2015, Appl. Geochem. 55, 62, paywalled). That is not the 25 C set the NaCl row was validated on, so the 1988 set is used.
  - **Validation** (tests/thermo/test_electrolyte_salts.py):
    - KCl, KBr, LiCl and NaBr against Hamer & Wu (1972), J. Phys. Chem. Ref. Data 1, 1047, Tables 9/17/28/29: phi within 0.6 % and gamma within 0.9 % up to each salt's cap.
    - MgCl2 against Goldberg & Nuttall (1978), J. Phys. Chem. Ref. Data 7, 263, Table 17: a_w within 0.2 % and phi within 1.9 %. Gamma is 1.2-3.2 % low (assessed); the flash surface is a_w.
  - **Molality caps per salt** are the verified range: KCl 4.803 (saturation), KBr 5.5, LiCl 6, NaBr 6 (at 9 m phi is 6 % high), MgCl2 5.84. Two salts together refuse, because theta/psi mixing terms are not shipped. CaCl2 and Na2SO4 do not resolve in the open component registry, and 2:2 salts (beta2) are not implemented.
- **Ideal-solid SLE** (`ideal_solid`, experimental to provisional): the physics is complete for its claim (van't Hoff, gamma = 1).
  - **Parameters:** fusion properties are now tabulated only. Tm comes from the first non-Joback chemicals source and Hfus from the CRC table; Joback estimates refuse.
  - **Harness:** `scripts/validate_properties.py` gained a `solubility` case type (expected {solute: x_sat} at T, 5 % band). tests/thermo/test_special_solubility_case.py drives it with the IUPAC-NIST points: naphthalene +3.4 % passes, anthracene +32 % fails visibly.
  - **L0:** all seven L0 checks are flash-surface checks, and the row refuses every flash by design. They are excluded with reasons, and the equivalent self-consistency (x(Tm) = 1, monotone in T, bit-identical instances) is pinned in tests.
  - **Advisor:** a row claiming no vapour phase now sinks below every VLE flash package.
  - **Not done:** binding the IUPAC-NIST points as L2 cases needs the locked `data/validation/` tree.

Closed 2026-11-03:

- **soft-SAFT** (`soft_saft`, provisional): the earlier "no engine" finding was wrong; teqp
  0.23.2 ships a `SoftSAFT` kind (Johnson-Zollweg-Gubbins 1993 LJ reference, TPT1 chain with the
  Johnson-Muller-Gubbins 1994 contact value, vdW-1f mixing, no association). Its JZG constants match
  the paper's Table 10 and reproduce the paper's imposed critical point (T* 1.313, rho* 0.310).
  Parameters come from the open-access Pamies thesis (URV 2003, repositori.urv.cat TDX:304), Tables
  4.1 (PV set, C1-nC8), 4.6 (H2, nC10, nC16) and 4.10 (CO2). Validation (tests/thermo/test_soft_saft.py):
  the kernel reproduces the thesis's own soft-SAFT critical temperatures (Table 4.4, n-C12 to n-C48,
  within 0.35 K) and critical densities (Table 4.5, within 1 kg/m3). Measured deviations: Table 4.4
  Pc is 1-4 % high with the rounded PVrP correlation; C1-C3 Psat is 5-25 % high (density-weighted
  fit); nC4-nC8 Psat is within 5 % and rho_L within 2.5 %. No L1/L2 case is bound, because binding
  needs a new file under the locked `data/validation/`. Binary parameters (eta, xi) are not exposed
  by teqp, so mixtures run Lorentz-Berthelot.

- **Wilson T-dependent form** (`wilson_tdep_ig`, provisional): ln Lambda_ij = a_ij + b_ij/T for six binaries, keyed by CAS, from two Proc. Estonian Acad. Sci. Chem. papers. Siimer et al. 2002, 51(1) 19, doi:10.3176/chem.2002.1.02, covers hexan-2-one / o-xylene / nonane; Kirss et al. 2002, 51(4) 215, doi:10.3176/chem.2002.4.03, covers toluene / p-xylene / 1,2-dichloroethane. Table 4 of each supplies the coefficients.
  - **Licence:** both papers are gold open access, but no licence is named. The article pages say "Open Access Journal" and the PDFs carry no notice. The publisher's terms are quoted in `data/thermo_params/wilson/tdep_pairs.yaml`.
  - **Equation form:** both papers misprint Eq. 1 with (x_i - Lambda_ij x_j). The standard + form is used.
  - **Validation:** the model reproduces the papers' own ternary activity coefficients (Siimer Table 3, Kirss Table 7) to the printed digits. The package bubble point, using databank vapour pressures, lands within 0.3 K of the measured boiling points (tests/thermo/test_gamma_phi_variants.py).

Partial closures: `glycol_pr` is TEG only (MEG's open values carry no primary citation);
`depg_henry` is 25 C only with tetraglyme as proxy (Xu et al. 1992 was unreachable);
`kabadi-danner-free-water` uses IAPWS-95, not NBS/NRC 1984; `amine_mdea_pz` runs Bishnoi's
constants with unit activity coefficients, 0.23 to 2.7 times his measured pressures.
