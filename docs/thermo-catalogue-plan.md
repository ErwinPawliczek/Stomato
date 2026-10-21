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

## 2. Architecture that makes the catalogue cheap

- **One `Thermo` protocol, eight adapters.** Every package is a plugin behind the existing `Thermo` protocol (`contracts/plugins.py`) built on `ThermoSurfaceMixin` (`thermo/cubic.py`): the cache, saturation solver, TVF/PVF flows, derivatives and the slate context come for free. An adapter implements only `_build_flasher` / `_build_flasher_vl` and, where the library has no driver, `flash_pt` itself. Adapters, one module each under `ngdesign/thermo/`: `cubic.py` (exists), `gamma_phi.py`, `mixing_rules.py`, `helmholtz.py`, `kvalue.py`, `teqp_bridge.py`, `electrolyte.py`, `special.py`.
- **Property methods are data.** `data/thermo_models/<family>.yaml` lists every row above: `id`, `family`, `adapter`, `options` (alpha, translation, vapour model, k_ij table, enthalpy method), `params` (source + file), `applicability` (component classes, T/P window, phases, polar/electrolyte flags), `status` (`validated` | `provisional` | `experimental`), `validation` (case ids). `ngdesign.thermo.catalogue` builds and registers packages from these files at import; `registry.available("thermo")` is the catalogue. One YAML per family means parallel agents never edit the same file.
- **Composable vapour and liquid halves.** Family B is a product: liquid model × vapour model. The adapter takes both as objects; the catalogue row names them. The same virial and cubic vapour objects serve families C, E and G.
- **Parameter databanks as provenance-graded records**, the P1-02 pattern: ChemSep (bundled with `thermo`), `chemicals` constants, published tables shipped under `data/thermo_params/<model>/` with a citation per row, user tables carried on the flowsheet (the P1-07 pattern for pseudo-components, extended to binary parameters). Missing pair parameters are an error with a name, never a silent ideal assumption (the NRTL package already does this).
- **Enthalpy and density methods are options, not packages.** Lee-Kesler departures, Rackett/COSTALD/API liquid densities and the Boston-Mathias extrapolation are option objects on the cubic adapter; a catalogue row selects them.

## 3. Validation layers (the gate for `validated`)

| Layer | What | Oracle | Who writes it |
|---|---|---|---|
| **L0 self-consistency** | Gibbs-Duhem on γ, pure-component limits (γ→1, K→Psat/P), dH/dT = Cp, dG/dP = V, flash round-trips (PT→PH→PT), phase identification above/below Psat (the #124 lesson), determinism | mathematics; no data | shared harness, written once (spec T-01) |
| **L1 pure components** | Psat, liquid density, Hvap, Cp over the model's claimed T window, for every curated component the model applies to | NIST WebBook, DIPPR-derived values already in `chemicals`, IAPWS tables for water | per adapter |
| **L2 binary VLE / LLE** | at least two literature binaries per model, chosen for its applicability (e.g. methanol/water for NRTL, CO2/methane for PR, ethanol/water azeotrope for UNIFAC-Dortmund, water/toluene LLE for UNIFAC-LLE) | published isothermal/isobaric data with citation (DECHEMA-style sets in the open literature, NIST TDE references, Gmehling papers) | per package row |
| **L3 canonical case** | one engineering case per family where the method is the standard: natural-gas dew point and density (cubics, GERG), steam tables (IAPWS), refinery flash and K10 charts (Chao-Seader/BK10), amine loading isotherms and the two loops (G), Kremser-grade absorber (column), azeotropic distillation (B) | textbook/handbook numbers (GPSA, Perry, Kohl & Nielsen, Reid-Prausnitz-Poling, Smith-Van Ness) | per family |
| **L4 cross-model consistency** | the same stream on PR vs SRK vs GERG; NRTL vs UNIQUAC vs UNIFAC on the same binary; bounds on disagreement documented | internal | shared harness |
| **L5 flowsheet regression** | bench cases and goldens unchanged for existing packages; every new package solves the slice with the agent's `recommend_thermo` output recorded | existing bench/golden machinery | CI |

Rules: every case carries a citation and the measured number; a row ships `provisional` when L0+L1 pass but L2/L3 lack data, `validated` only with L0–L3 green; `experimental` is allowed for F/H while parameters are scarce and is hidden from the advisor by default. The harness output (`scripts/validate_properties.py`) becomes a per-model report in `docs/validation/<model>.md`, regenerated in CI.

## 4. Orchestration: many agents, no collisions

The partition is by **file ownership**, so threads can run simultaneously:

| Thread owns | Package / files |
|---|---|
| T-01 registry + harness L0/L4 | `ngdesign/thermo/catalogue.py`, `data/thermo_models/_schema.yaml`, `scripts/validate_properties.py` (L0/L4 sections), `tests/thermo/test_catalogue.py` |
| T-02 cubic options | `thermo/cubic.py` (options only), `data/thermo_models/cubic.yaml`, `data/validation/cubic/` |
| T-03 gamma-phi | `thermo/gamma_phi.py`, `thermo/virial.py`, `data/thermo_models/gamma_phi.yaml`, `data/thermo_params/{nrtl,uniquac,wilson,unifac}/`, `data/validation/gamma_phi/` |
| T-04 Helmholtz | `thermo/helmholtz.py`, `data/thermo_models/helmholtz.yaml`, `data/validation/helmholtz/`, `pyproject` extra `coolprop` |
| T-05 K-value correlations | `thermo/kvalue.py`, `data/thermo_models/kvalue.yaml`, `data/validation/kvalue/` |
| T-06 predictive mixing rules | `thermo/mixing_rules.py`, `data/thermo_models/mixing.yaml` (after T-02, T-03) |
| T-07 teqp bridge | `thermo/teqp_bridge.py`, `data/thermo_models/saft.yaml`, extra `saft` |
| T-08 advisor + agent tool + UI picker | `thermo/advisor.py`, `agent/tools.py` (one tool), `frontend/` picker (separate PR, frontend-only) |
| T-09 general electrolytes | `thermo/electrolyte.py`, `data/thermo_models/electrolyte.yaml` (after T-03) |
| T-10 solids / polymers / special | `thermo/special.py`, `data/thermo_models/special.yaml` (after T-03, T-07) |
| T-11..T-14 validation data sweeps | per family, data-only PRs: `data/validation/<family>/cases.yaml` with citations; these run in parallel with the adapter threads and merge independently |

Waves (each wave = one dispatch burst; a wave starts when its dependencies are on main):

1. **Wave 0 (serial, 1 thread):** T-01. Registry-as-data, status rules, L0/L4 harness, migration of the 6 existing packages into `data/thermo_models/`. Everything else keys on its schema.
2. **Wave 1 (parallel, 8 threads):** T-02, T-03, T-04, T-05, T-07 adapters, plus T-11/T-12/T-13 data sweeps (cubic, gamma-phi, Helmholtz literature cases). Disjoint files; each PR is reviewed and merged independently.
3. **Wave 2 (parallel, 4 threads):** T-06 mixing rules, T-08 advisor, T-09 electrolytes, T-14 data sweep for K-values and electrolytes.
4. **Wave 3 (parallel, 2 threads):** T-10 special models; a sweep that promotes `provisional` rows to `validated` as data lands.
5. **Wave 4 (serial):** catalogue freeze: every row's status audited against its harness report; `docs/validation/` regenerated; the advisor's rules reviewed against the final statuses.

Orchestrator duties per PR (unchanged from tonight): worktree, every gate, the harness report for the rows the PR adds, bench counts byte-identical for existing packages, a probe of the L3 case, then approve and auto-merge. The thermo wave does not start until P1-09 and P1-06 are merged, so column work and thermo work never touch the same files.

Budget: ~16 Obvious threads, most 2–6 h of agent time; the data sweeps are the long tail. Elapsed: Wave 1 is bounded by the gamma-phi adapter (the largest), roughly a day; the whole catalogue with validation lands in about a week of wall time if reviews keep pace.

## 5. Risks and how the plan answers them

- **Parameter availability** is the binding constraint, not code: binary parameters exist where someone measured them. The registry's `status` and the advisor's "no parameters for this pair" refusal keep this visible; data sweeps are their own PRs so missing data never blocks an adapter.
- **Licensing:** `thermo`, `chemicals`, CoolProp and `teqp` are MIT; DIPPR and DECHEMA tables are not redistributable — only open literature values ship, each with a citation. Aspen/HYSYS parameter sets are never copied.
- **Numerical robustness across models** (tonight's pure-phase bug): L0 round-trip and phase-identification tests run on every adapter, not just cubics; the column, saturation solver and tear loops consume only the `Thermo` protocol, so a new package needs no solver change.
- **Performance:** the cache, the VL fast path and the slate-scoped flashers are in the mixin; adapters inherit them. The bench records flash counts and wall time per case per package.
- **Scope creep:** the catalogue is data; a method without an adapter row and a validation set does not exist in the registry, whatever the marketing list says.
