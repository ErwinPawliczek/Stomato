# Thermo property validation report (spec P1-05)

Generated 2026-10-22T08:15:25+00:00 from `data/validation/results.json` (git b14eece, CoolProp 8.0.0).
Regenerate with `uv run python scripts/validate_properties.py` and `--write-doc`.

## Tolerance policy (fixed before any result was seen)

| property | tolerance | basis |
| --- | --- | --- |
| density (vapour) | 3 % relative | spec P1-05 |
| density (liquid) | 8 % relative | spec P1-05 — known cubic weakness |
| Cp | 5 % relative | spec P1-05 |
| bubble / dew pressure | 3 % relative | spec P1-05 |
| K-values | 5 % relative | spec P1-05 |
| NRTL MeOH/H2O bubble | 2 % relative | spec P1-05 (written for ethanol/water) |
| NRTL y | 0.02 absolute | spec P1-05 (written for ethanol/water) |
| bubble T (isobaric data) | 0.5 % relative | harness analogue of the 3 % bubble-P tolerance |
| phase compositions (liquid_comp) | 0.02 absolute | spec's composition tolerance |

## Model catalogue (spec T-01)

Property methods are data in `data/thermo_models/*.yaml`; each row's report lives in
`docs/validation/<id>.md`. The audit gate: `uv run python scripts/validate_properties.py --audit`.

## Model catalogue (spec T-01)

Property methods are data in `data/thermo_models/*.yaml`; each row's report lives in
`docs/validation/<id>.md`. The audit gate: `uv run python scripts/validate_properties.py --audit`.

| model | family | status | L0 | L1/L2 cases | report |
| --- | --- | --- | --- | --- | --- |
| [aga8_dc92](validation/aga8_dc92.md) | helmholtz | experimental | — | L1=0 L2=0 | [report](validation/aga8_dc92.md) |
| [amine_enrtl](validation/amine_enrtl.md) | electrolyte | provisional | 3/3 | L1=4 L2=0 | [report](validation/amine_enrtl.md) |
| [amine_ke](validation/amine_ke.md) | electrolyte | validated | 3/3 | L1=4 L2=5 | [report](validation/amine_ke.md) |
| [antoine-ideal-k](validation/antoine-ideal-k.md) | kvalue | provisional | 5/5 | L1=0 L2=0 | [report](validation/antoine-ideal-k.md) |
| [api-srk](validation/api-srk.md) | cubic | provisional | 7/7 | L1=4 L2=2 | [report](validation/api-srk.md) |
| [asme_steam](validation/asme_steam.md) | helmholtz | experimental | — | L1=0 L2=0 | [report](validation/asme_steam.md) |
| [braun-k10](validation/braun-k10.md) | kvalue | provisional | 6/6 | L1=0 L2=0 | [report](validation/braun-k10.md) |
| [bwr_ls](validation/bwr_ls.md) | helmholtz | experimental | — | L1=0 L2=0 | [report](validation/bwr_ls.md) |
| [bwrs](validation/bwrs.md) | helmholtz | provisional | 7/7 | L1=0 L2=0 | [report](validation/bwrs.md) |
| [chao-seader](validation/chao-seader.md) | kvalue | provisional | 6/6 | L1=0 L2=2 | [report](validation/chao-seader.md) |
| [coolprop_heos](validation/coolprop_heos.md) | helmholtz | provisional | 7/7 | L1=0 L2=0 | [report](validation/coolprop_heos.md) |
| [cpa_pr](validation/cpa_pr.md) | saft | experimental | — | L1=0 L2=0 | [report](validation/cpa_pr.md) |
| [cpa_srk](validation/cpa_srk.md) | saft | experimental | — | L1=2 L2=9 | [report](validation/cpa_srk.md) |
| [eos_cg](validation/eos_cg.md) | helmholtz | experimental | — | L1=0 L2=0 | [report](validation/eos_cg.md) |
| [esso-tabular](validation/esso-tabular.md) | kvalue | provisional | 5/5 | L1=0 L2=0 | [report](validation/esso-tabular.md) |
| [flory_huggins](validation/flory_huggins.md) | special | experimental | — | L1=0 L2=0 | [report](validation/flory_huggins.md) |
| [gerg2008](validation/gerg2008.md) | helmholtz | provisional | 7/7 | L1=5 L2=10 | [report](validation/gerg2008.md) |
| [gerg2008_teqp](validation/gerg2008_teqp.md) | saft | experimental | — | L1=0 L2=0 | [report](validation/gerg2008_teqp.md) |
| [grayson-streed](validation/grayson-streed.md) | kvalue | provisional | 5/5 | L1=0 L2=0 | [report](validation/grayson-streed.md) |
| [grayson-streed-extended](validation/grayson-streed-extended.md) | kvalue | provisional | 5/5 | L1=0 L2=0 | [report](validation/grayson-streed-extended.md) |
| [henry-sander](validation/henry-sander.md) | kvalue | provisional | 6/6 | L1=0 L2=2 | [report](validation/henry-sander.md) |
| [hf_hexamer](validation/hf_hexamer.md) | special | experimental | — | L1=0 L2=0 | [report](validation/hf_hexamer.md) |
| [hoc_dimer](validation/hoc_dimer.md) | special | experimental | — | L1=0 L2=0 | [report](validation/hoc_dimer.md) |
| [iapws95](validation/iapws95.md) | helmholtz | provisional | 6/6 | L1=0 L2=5 | [report](validation/iapws95.md) |
| [iapws_if97](validation/iapws_if97.md) | helmholtz | provisional | 6/6 | L1=0 L2=0 | [report](validation/iapws_if97.md) |
| [ideal-lk](validation/ideal-lk.md) | kvalue | provisional | 6/6 | L1=0 L2=0 | [report](validation/ideal-lk.md) |
| [ideal-raoult](validation/ideal-raoult.md) | kvalue | provisional | 6/6 | L1=0 L2=0 | [report](validation/ideal-raoult.md) |
| [ideal_solid](validation/ideal_solid.md) | special | experimental | — | L1=0 L2=0 | [report](validation/ideal_solid.md) |
| [kabadi-danner-srk](validation/kabadi-danner-srk.md) | cubic | provisional | 7/7 | L1=4 L2=2 | [report](validation/kabadi-danner-srk.md) |
| [lee-kesler-ploecker](validation/lee-kesler-ploecker.md) | kvalue | provisional | 6/6 | L1=0 L2=1 | [report](validation/lee-kesler-ploecker.md) |
| [margules_hoc](validation/margules_hoc.md) | gamma_phi | experimental | — | L1=0 L2=0 | [report](validation/margules_hoc.md) |
| [margules_ig](validation/margules_ig.md) | gamma_phi | provisional | 7/7 | L1=0 L2=3 | [report](validation/margules_ig.md) |
| [margules_nothnagel](validation/margules_nothnagel.md) | gamma_phi | experimental | — | L1=0 L2=0 | [report](validation/margules_nothnagel.md) |
| [margules_pr](validation/margules_pr.md) | gamma_phi | provisional | 7/7 | L1=0 L2=0 | [report](validation/margules_pr.md) |
| [margules_rk](validation/margules_rk.md) | gamma_phi | provisional | 7/7 | L1=0 L2=0 | [report](validation/margules_rk.md) |
| [mbwr](validation/mbwr.md) | helmholtz | experimental | — | L1=0 L2=0 | [report](validation/mbwr.md) |
| [multifluid](validation/multifluid.md) | saft | experimental | — | L1=0 L2=0 | [report](validation/multifluid.md) |
| [multifluid_pure](validation/multifluid_pure.md) | saft | experimental | — | L1=0 L2=0 | [report](validation/multifluid_pure.md) |
| [nrtl](validation/nrtl.md) | gamma_phi | provisional | 7/7 | L1=0 L2=21 | [report](validation/nrtl.md) |
| [nrtl_hoc](validation/nrtl_hoc.md) | gamma_phi | experimental | — | L1=0 L2=0 | [report](validation/nrtl_hoc.md) |
| [nrtl_ig](validation/nrtl_ig.md) | gamma_phi | provisional | 7/7 | L1=0 L2=0 | [report](validation/nrtl_ig.md) |
| [nrtl_nothnagel](validation/nrtl_nothnagel.md) | gamma_phi | experimental | — | L1=0 L2=0 | [report](validation/nrtl_nothnagel.md) |
| [nrtl_rk](validation/nrtl_rk.md) | gamma_phi | provisional | 7/7 | L1=0 L2=0 | [report](validation/nrtl_rk.md) |
| [pc_saft](validation/pc_saft.md) | saft | experimental | — | L1=6 L2=4 | [report](validation/pc_saft.md) |
| [pc_saft_assoc](validation/pc_saft_assoc.md) | saft | experimental | — | L1=0 L2=0 | [report](validation/pc_saft_assoc.md) |
| [pc_saft_polar](validation/pc_saft_polar.md) | saft | experimental | — | L1=0 L2=0 | [report](validation/pc_saft_polar.md) |
| [polymer_nrtl](validation/polymer_nrtl.md) | special | experimental | — | L1=0 L2=0 | [report](validation/polymer_nrtl.md) |
| [polymer_pc_saft](validation/polymer_pc_saft.md) | special | experimental | — | L1=0 L2=0 | [report](validation/polymer_pc_saft.md) |
| [pr](validation/pr.md) | cubic | validated | 7/7 | L1=40 L2=52 | [report](validation/pr.md) |
| [pr-bm](validation/pr-bm.md) | cubic | provisional | 7/7 | L1=4 L2=2 | [report](validation/pr-bm.md) |
| [pr-boston-mathias](validation/pr-boston-mathias.md) | cubic | provisional | 7/7 | L1=4 L2=2 | [report](validation/pr-boston-mathias.md) |
| [pr-lee-kesler-enthalpy](validation/pr-lee-kesler-enthalpy.md) | cubic | provisional | 7/7 | L1=4 L2=2 | [report](validation/pr-lee-kesler-enthalpy.md) |
| [pr-mathias-copeman](validation/pr-mathias-copeman.md) | cubic | provisional | 7/7 | L1=4 L2=2 | [report](validation/pr-mathias-copeman.md) |
| [pr-peneloux](validation/pr-peneloux.md) | cubic | provisional | 7/7 | L1=4 L2=2 | [report](validation/pr-peneloux.md) |
| [pr78](validation/pr78.md) | cubic | validated | 7/7 | L1=40 L2=52 | [report](validation/pr78.md) |
| [prsv](validation/prsv.md) | cubic | provisional | 7/7 | L1=4 L2=2 | [report](validation/prsv.md) |
| [prsv2](validation/prsv2.md) | cubic | provisional | 7/7 | L1=4 L2=2 | [report](validation/prsv2.md) |
| [regular_solution_hoc](validation/regular_solution_hoc.md) | gamma_phi | experimental | — | L1=0 L2=0 | [report](validation/regular_solution_hoc.md) |
| [regular_solution_ig](validation/regular_solution_ig.md) | gamma_phi | provisional | 7/7 | L1=0 L2=0 | [report](validation/regular_solution_ig.md) |
| [regular_solution_nothnagel](validation/regular_solution_nothnagel.md) | gamma_phi | experimental | — | L1=0 L2=0 | [report](validation/regular_solution_nothnagel.md) |
| [regular_solution_pr](validation/regular_solution_pr.md) | gamma_phi | provisional | 7/7 | L1=0 L2=0 | [report](validation/regular_solution_pr.md) |
| [regular_solution_rk](validation/regular_solution_rk.md) | gamma_phi | provisional | 7/7 | L1=0 L2=0 | [report](validation/regular_solution_rk.md) |
| [rk](validation/rk.md) | cubic | provisional | 5/7 | L1=4 L2=2 | [report](validation/rk.md) |
| [rks-bm](validation/rks-bm.md) | cubic | provisional | 7/7 | L1=4 L2=2 | [report](validation/rks-bm.md) |
| [saft_vr_mie](validation/saft_vr_mie.md) | saft | experimental | — | L1=0 L2=0 | [report](validation/saft_vr_mie.md) |
| [soft_saft](validation/soft_saft.md) | saft | experimental | — | L1=0 L2=0 | [report](validation/soft_saft.md) |
| [sour-pr](validation/sour-pr.md) | cubic | provisional | 7/7 | L1=4 L2=2 | [report](validation/sour-pr.md) |
| [sour-srk](validation/sour-srk.md) | cubic | provisional | 7/7 | L1=4 L2=2 | [report](validation/sour-srk.md) |
| [srk](validation/srk.md) | cubic | validated | 7/7 | L1=40 L2=52 | [report](validation/srk.md) |
| [srk-boston-mathias](validation/srk-boston-mathias.md) | cubic | provisional | 7/7 | L1=4 L2=2 | [report](validation/srk-boston-mathias.md) |
| [srk-lee-kesler-enthalpy](validation/srk-lee-kesler-enthalpy.md) | cubic | provisional | 7/7 | L1=4 L2=2 | [report](validation/srk-lee-kesler-enthalpy.md) |
| [srk-mathias-copeman](validation/srk-mathias-copeman.md) | cubic | provisional | 7/7 | L1=4 L2=2 | [report](validation/srk-mathias-copeman.md) |
| [srk-peneloux](validation/srk-peneloux.md) | cubic | provisional | 7/7 | L1=4 L2=2 | [report](validation/srk-peneloux.md) |
| [twu-pr](validation/twu-pr.md) | cubic | provisional | 7/7 | L1=4 L2=2 | [report](validation/twu-pr.md) |
| [twu-sim-tassone](validation/twu-sim-tassone.md) | cubic | experimental | — | L1=0 L2=0 | [report](validation/twu-sim-tassone.md) |
| [twu-srk](validation/twu-srk.md) | cubic | provisional | 7/7 | L1=4 L2=2 | [report](validation/twu-srk.md) |
| [unifac_dortmund_hoc](validation/unifac_dortmund_hoc.md) | gamma_phi | experimental | — | L1=0 L2=0 | [report](validation/unifac_dortmund_hoc.md) |
| [unifac_dortmund_ig](validation/unifac_dortmund_ig.md) | gamma_phi | provisional | 7/7 | L1=0 L2=2 | [report](validation/unifac_dortmund_ig.md) |
| [unifac_dortmund_nothnagel](validation/unifac_dortmund_nothnagel.md) | gamma_phi | experimental | — | L1=0 L2=0 | [report](validation/unifac_dortmund_nothnagel.md) |
| [unifac_dortmund_pr](validation/unifac_dortmund_pr.md) | gamma_phi | provisional | 7/7 | L1=0 L2=0 | [report](validation/unifac_dortmund_pr.md) |
| [unifac_dortmund_rk](validation/unifac_dortmund_rk.md) | gamma_phi | provisional | 7/7 | L1=0 L2=0 | [report](validation/unifac_dortmund_rk.md) |
| [unifac_fv](validation/unifac_fv.md) | special | experimental | — | L1=0 L2=0 | [report](validation/unifac_fv.md) |
| [unifac_hoc](validation/unifac_hoc.md) | gamma_phi | experimental | — | L1=0 L2=0 | [report](validation/unifac_hoc.md) |
| [unifac_ig](validation/unifac_ig.md) | gamma_phi | provisional | 7/7 | L1=0 L2=1 | [report](validation/unifac_ig.md) |
| [unifac_lle_hoc](validation/unifac_lle_hoc.md) | gamma_phi | experimental | — | L1=0 L2=0 | [report](validation/unifac_lle_hoc.md) |
| [unifac_lle_ig](validation/unifac_lle_ig.md) | gamma_phi | provisional | 7/7 | L1=0 L2=0 | [report](validation/unifac_lle_ig.md) |
| [unifac_lle_nothnagel](validation/unifac_lle_nothnagel.md) | gamma_phi | experimental | — | L1=0 L2=0 | [report](validation/unifac_lle_nothnagel.md) |
| [unifac_lle_pr](validation/unifac_lle_pr.md) | gamma_phi | provisional | 7/7 | L1=0 L2=0 | [report](validation/unifac_lle_pr.md) |
| [unifac_lle_rk](validation/unifac_lle_rk.md) | gamma_phi | provisional | 7/7 | L1=0 L2=0 | [report](validation/unifac_lle_rk.md) |
| [unifac_lyngby_hoc](validation/unifac_lyngby_hoc.md) | gamma_phi | experimental | — | L1=0 L2=0 | [report](validation/unifac_lyngby_hoc.md) |
| [unifac_lyngby_ig](validation/unifac_lyngby_ig.md) | gamma_phi | provisional | 7/7 | L1=0 L2=0 | [report](validation/unifac_lyngby_ig.md) |
| [unifac_lyngby_nothnagel](validation/unifac_lyngby_nothnagel.md) | gamma_phi | experimental | — | L1=0 L2=0 | [report](validation/unifac_lyngby_nothnagel.md) |
| [unifac_lyngby_pr](validation/unifac_lyngby_pr.md) | gamma_phi | provisional | 7/7 | L1=0 L2=0 | [report](validation/unifac_lyngby_pr.md) |
| [unifac_lyngby_rk](validation/unifac_lyngby_rk.md) | gamma_phi | provisional | 7/7 | L1=0 L2=0 | [report](validation/unifac_lyngby_rk.md) |
| [unifac_nist_hoc](validation/unifac_nist_hoc.md) | gamma_phi | experimental | — | L1=0 L2=0 | [report](validation/unifac_nist_hoc.md) |
| [unifac_nist_ig](validation/unifac_nist_ig.md) | gamma_phi | provisional | 7/7 | L1=0 L2=0 | [report](validation/unifac_nist_ig.md) |
| [unifac_nist_nothnagel](validation/unifac_nist_nothnagel.md) | gamma_phi | experimental | — | L1=0 L2=0 | [report](validation/unifac_nist_nothnagel.md) |
| [unifac_nist_pr](validation/unifac_nist_pr.md) | gamma_phi | provisional | 7/7 | L1=0 L2=0 | [report](validation/unifac_nist_pr.md) |
| [unifac_nist_rk](validation/unifac_nist_rk.md) | gamma_phi | provisional | 7/7 | L1=0 L2=0 | [report](validation/unifac_nist_rk.md) |
| [unifac_nothnagel](validation/unifac_nothnagel.md) | gamma_phi | experimental | — | L1=0 L2=0 | [report](validation/unifac_nothnagel.md) |
| [unifac_pr](validation/unifac_pr.md) | gamma_phi | provisional | 7/7 | L1=0 L2=0 | [report](validation/unifac_pr.md) |
| [unifac_psrk_hoc](validation/unifac_psrk_hoc.md) | gamma_phi | experimental | — | L1=0 L2=0 | [report](validation/unifac_psrk_hoc.md) |
| [unifac_psrk_ig](validation/unifac_psrk_ig.md) | gamma_phi | provisional | 7/7 | L1=0 L2=2 | [report](validation/unifac_psrk_ig.md) |
| [unifac_psrk_nothnagel](validation/unifac_psrk_nothnagel.md) | gamma_phi | experimental | — | L1=0 L2=0 | [report](validation/unifac_psrk_nothnagel.md) |
| [unifac_psrk_pr](validation/unifac_psrk_pr.md) | gamma_phi | provisional | 7/7 | L1=0 L2=0 | [report](validation/unifac_psrk_pr.md) |
| [unifac_psrk_rk](validation/unifac_psrk_rk.md) | gamma_phi | provisional | 7/7 | L1=0 L2=0 | [report](validation/unifac_psrk_rk.md) |
| [unifac_rk](validation/unifac_rk.md) | gamma_phi | provisional | 7/7 | L1=0 L2=0 | [report](validation/unifac_rk.md) |
| [uniquac_hoc](validation/uniquac_hoc.md) | gamma_phi | experimental | — | L1=0 L2=0 | [report](validation/uniquac_hoc.md) |
| [uniquac_ig](validation/uniquac_ig.md) | gamma_phi | provisional | 7/7 | L1=0 L2=3 | [report](validation/uniquac_ig.md) |
| [uniquac_nothnagel](validation/uniquac_nothnagel.md) | gamma_phi | experimental | — | L1=0 L2=0 | [report](validation/uniquac_nothnagel.md) |
| [uniquac_pr](validation/uniquac_pr.md) | gamma_phi | provisional | 7/7 | L1=0 L2=0 | [report](validation/uniquac_pr.md) |
| [uniquac_rk](validation/uniquac_rk.md) | gamma_phi | provisional | 7/7 | L1=0 L2=0 | [report](validation/uniquac_rk.md) |
| [vanlaar_hoc](validation/vanlaar_hoc.md) | gamma_phi | experimental | — | L1=0 L2=0 | [report](validation/vanlaar_hoc.md) |
| [vanlaar_ig](validation/vanlaar_ig.md) | gamma_phi | provisional | 7/7 | L1=0 L2=2 | [report](validation/vanlaar_ig.md) |
| [vanlaar_nothnagel](validation/vanlaar_nothnagel.md) | gamma_phi | experimental | — | L1=0 L2=0 | [report](validation/vanlaar_nothnagel.md) |
| [vanlaar_pr](validation/vanlaar_pr.md) | gamma_phi | provisional | 7/7 | L1=0 L2=0 | [report](validation/vanlaar_pr.md) |
| [vanlaar_rk](validation/vanlaar_rk.md) | gamma_phi | provisional | 7/7 | L1=0 L2=0 | [report](validation/vanlaar_rk.md) |
| [vdw](validation/vdw.md) | cubic | provisional | 5/7 | L1=4 L2=2 | [report](validation/vdw.md) |
| [wilson_hoc](validation/wilson_hoc.md) | gamma_phi | experimental | — | L1=0 L2=0 | [report](validation/wilson_hoc.md) |
| [wilson_ig](validation/wilson_ig.md) | gamma_phi | provisional | 7/7 | L1=0 L2=3 | [report](validation/wilson_ig.md) |
| [wilson_nothnagel](validation/wilson_nothnagel.md) | gamma_phi | experimental | — | L1=0 L2=0 | [report](validation/wilson_nothnagel.md) |
| [wilson_pr](validation/wilson_pr.md) | gamma_phi | provisional | 7/7 | L1=0 L2=0 | [report](validation/wilson_pr.md) |
| [wilson_rk](validation/wilson_rk.md) | gamma_phi | provisional | 7/7 | L1=0 L2=0 | [report](validation/wilson_rk.md) |
| [zudkevitch-joffe-rk](validation/zudkevitch-joffe-rk.md) | cubic | provisional | 7/7 | L1=4 L2=2 | [report](validation/zudkevitch-joffe-rk.md) |

### L4 cross-model pairs on the natural-gas slice feed

- `antoine-ideal-k`: ok — n/a — refuses the slice feed: SaturationError: kvalue saturation at T=293.15 K: Lee-Kesler two-phase region collapses before K crosses unity
- `braun-k10`: ok — n/a — refuses the slice feed: SaturationError: kvalue saturation at T=293.15 K: Lee-Kesler two-phase region collapses before K crosses unity
- `bwrs`: ok — n/a — refuses the slice feed: ComponentNotSupported: BWRSPackage has no parameters for component(s) ['C6+', 'H2O']; supported: ['C1', 'C2', 'C3', 'CO2', 'H2S', 'N2', 'iC4', 'iC5', 'nC4', 'nC5']
- `chao-seader`: ok — n/a — refuses the slice feed: ValueError: no Chao-Seader/Grayson-Streed regular-solution constants for C6+, H2O; extend data/thermo_params/kvalue/regular_solution.yaml from a cited source (pseudo-components, water and alcohols are outside the correlation's scope)
- `coolprop_heos`: ok — n/a — refuses the slice feed: ComponentNotSupported: CoolPropPackage has no parameters for component(s) ['C6+']; supported: ['C1', 'C2', 'C3', 'CO2', 'H2O', 'H2S', 'N2', 'iC4', 'iC5', 'nC4', 'nC5']
- `esso-tabular`: ok — n/a — refuses the slice feed: SaturationError: kvalue saturation at T=293.15 K: Lee-Kesler two-phase region collapses before K crosses unity
- `gerg2008`: ok — n/a — refuses the slice feed: ComponentNotSupported: GERGPackage has no parameters for component(s) ['C6+', 'H2O']; supported: ['C1', 'C2', 'C3', 'CO2', 'H2S', 'N2', 'iC4', 'iC5', 'nC4', 'nC5']
- `grayson-streed`: ok — n/a — refuses the slice feed: ValueError: no Chao-Seader/Grayson-Streed regular-solution constants for C6+, H2O; extend data/thermo_params/kvalue/regular_solution.yaml from a cited source (pseudo-components, water and alcohols are outside the correlation's scope)
- `grayson-streed-extended`: ok — n/a — refuses the slice feed: ValueError: no Chao-Seader/Grayson-Streed regular-solution constants for C6+, H2O; extend data/thermo_params/kvalue/regular_solution.yaml from a cited source (pseudo-components, water and alcohols are outside the correlation's scope)
- `henry-sander`: ok — n/a — refuses the slice feed: SaturationError: kvalue saturation at T=293.15 K: Lee-Kesler two-phase region collapses before K crosses unity
- `ideal-lk`: ok — n/a — refuses the slice feed: SaturationError: kvalue saturation at T=293.15 K: Lee-Kesler two-phase region collapses before K crosses unity
- `ideal-raoult`: ok — n/a — refuses the slice feed: SaturationError: kvalue saturation at T=293.15 K: Lee-Kesler two-phase region collapses before K crosses unity
- `lee-kesler-ploecker`: ok — n/a — refuses the slice feed: SaturationError: kvalue saturation at T=293.15 K did not converge
- `margules_ig`: ok — n/a — refuses the slice feed: ValueError: Margules binary parameters for pair C1 (74-82-8) / C2 (74-84-0) are not available in data/thermo_params/margules/pairs.yaml; refusing to flash a zero-filled (ideal) pair matrix - select a thermo model whose parameter tables cover this component support
- `margules_pr`: ok — n/a — refuses the slice feed: ValueError: Margules binary parameters for pair C1 (74-82-8) / C2 (74-84-0) are not available in data/thermo_params/margules/pairs.yaml; refusing to flash a zero-filled (ideal) pair matrix - select a thermo model whose parameter tables cover this component support
- `margules_rk`: ok — n/a — refuses the slice feed: ValueError: Margules binary parameters for pair C1 (74-82-8) / C2 (74-84-0) are not available in data/thermo_params/margules/pairs.yaml; refusing to flash a zero-filled (ideal) pair matrix - select a thermo model whose parameter tables cover this component support
- `nrtl`: ok — n/a — refuses the slice feed: ValueError: ChemSep NRTL databank has no fitted binary parameters for pair C1 (74-82-8) / C2 (74-84-0); refusing to flash a zero-filled (ideal) pair matrix - select a thermo model whose databank covers this component support
- `nrtl_ig`: ok — n/a — refuses the slice feed: ValueError: ChemSep NRTL databank has no fitted binary parameters for pair C1 (74-82-8) / C2 (74-84-0); refusing to flash a zero-filled (ideal) pair matrix - select a thermo model whose databank covers this component support
- `nrtl_rk`: ok — n/a — refuses the slice feed: ValueError: ChemSep NRTL databank has no fitted binary parameters for pair C1 (74-82-8) / C2 (74-84-0); refusing to flash a zero-filled (ideal) pair matrix - select a thermo model whose databank covers this component support
- `regular_solution_ig`: ok — n/a — refuses the slice feed: ValueError: the regular-solution solubility parameter for C1 (74-82-8) cannot be formed: the thermo pure-component correlation returns no liquid molar volume at 298.15 K; refusing rather than defaulting - select a model whose parameters cover this component support
- `regular_solution_pr`: ok — n/a — refuses the slice feed: ValueError: the regular-solution solubility parameter for C1 (74-82-8) cannot be formed: the thermo pure-component correlation returns no liquid molar volume at 298.15 K; refusing rather than defaulting - select a model whose parameters cover this component support
- `regular_solution_rk`: ok — n/a — refuses the slice feed: ValueError: the regular-solution solubility parameter for C1 (74-82-8) cannot be formed: the thermo pure-component correlation returns no liquid molar volume at 298.15 K; refusing rather than defaulting - select a model whose parameters cover this component support
- `unifac_dortmund_ig`: ok — n/a — refuses the slice feed: ValueError: no UNIFAC group assignment for C1 (74-82-8) in data/thermo_params/unifac/groups.yaml; refusing to predict - the curated maps cover the component support of this variant's catalogue rows (the Magnussen LLE set, for example, is not parameterized for alcohol/glycol systems)
- `unifac_dortmund_pr`: ok — n/a — refuses the slice feed: ValueError: no UNIFAC group assignment for C1 (74-82-8) in data/thermo_params/unifac/groups.yaml; refusing to predict - the curated maps cover the component support of this variant's catalogue rows (the Magnussen LLE set, for example, is not parameterized for alcohol/glycol systems)
- `unifac_dortmund_rk`: ok — n/a — refuses the slice feed: ValueError: no UNIFAC group assignment for C1 (74-82-8) in data/thermo_params/unifac/groups.yaml; refusing to predict - the curated maps cover the component support of this variant's catalogue rows (the Magnussen LLE set, for example, is not parameterized for alcohol/glycol systems)
- `unifac_ig`: ok — n/a — refuses the slice feed: ValueError: no UNIFAC group assignment for C1 (74-82-8) in data/thermo_params/unifac/groups.yaml; refusing to predict - the curated maps cover the component support of this variant's catalogue rows (the Magnussen LLE set, for example, is not parameterized for alcohol/glycol systems)
- `unifac_lle_ig`: ok — n/a — refuses the slice feed: ValueError: no UNIFAC group assignment for C1 (74-82-8) in data/thermo_params/unifac/groups.yaml; refusing to predict - the curated maps cover the component support of this variant's catalogue rows (the Magnussen LLE set, for example, is not parameterized for alcohol/glycol systems)
- `unifac_lle_pr`: ok — n/a — refuses the slice feed: ValueError: no UNIFAC group assignment for C1 (74-82-8) in data/thermo_params/unifac/groups.yaml; refusing to predict - the curated maps cover the component support of this variant's catalogue rows (the Magnussen LLE set, for example, is not parameterized for alcohol/glycol systems)
- `unifac_lle_rk`: ok — n/a — refuses the slice feed: ValueError: no UNIFAC group assignment for C1 (74-82-8) in data/thermo_params/unifac/groups.yaml; refusing to predict - the curated maps cover the component support of this variant's catalogue rows (the Magnussen LLE set, for example, is not parameterized for alcohol/glycol systems)
- `unifac_lyngby_ig`: ok — n/a — refuses the slice feed: ValueError: no UNIFAC group assignment for C1 (74-82-8) in data/thermo_params/unifac/groups.yaml; refusing to predict - the curated maps cover the component support of this variant's catalogue rows (the Magnussen LLE set, for example, is not parameterized for alcohol/glycol systems)
- `unifac_lyngby_pr`: ok — n/a — refuses the slice feed: ValueError: no UNIFAC group assignment for C1 (74-82-8) in data/thermo_params/unifac/groups.yaml; refusing to predict - the curated maps cover the component support of this variant's catalogue rows (the Magnussen LLE set, for example, is not parameterized for alcohol/glycol systems)
- `unifac_lyngby_rk`: ok — n/a — refuses the slice feed: ValueError: no UNIFAC group assignment for C1 (74-82-8) in data/thermo_params/unifac/groups.yaml; refusing to predict - the curated maps cover the component support of this variant's catalogue rows (the Magnussen LLE set, for example, is not parameterized for alcohol/glycol systems)
- `unifac_nist_ig`: ok — n/a — refuses the slice feed: ValueError: no UNIFAC group assignment for C1 (74-82-8) in data/thermo_params/unifac/groups.yaml; refusing to predict - the curated maps cover the component support of this variant's catalogue rows (the Magnussen LLE set, for example, is not parameterized for alcohol/glycol systems)
- `unifac_nist_pr`: ok — n/a — refuses the slice feed: ValueError: no UNIFAC group assignment for C1 (74-82-8) in data/thermo_params/unifac/groups.yaml; refusing to predict - the curated maps cover the component support of this variant's catalogue rows (the Magnussen LLE set, for example, is not parameterized for alcohol/glycol systems)
- `unifac_nist_rk`: ok — n/a — refuses the slice feed: ValueError: no UNIFAC group assignment for C1 (74-82-8) in data/thermo_params/unifac/groups.yaml; refusing to predict - the curated maps cover the component support of this variant's catalogue rows (the Magnussen LLE set, for example, is not parameterized for alcohol/glycol systems)
- `unifac_pr`: ok — n/a — refuses the slice feed: ValueError: no UNIFAC group assignment for C1 (74-82-8) in data/thermo_params/unifac/groups.yaml; refusing to predict - the curated maps cover the component support of this variant's catalogue rows (the Magnussen LLE set, for example, is not parameterized for alcohol/glycol systems)
- `unifac_psrk_ig`: ok — n/a — refuses the slice feed: ValueError: no UNIFAC group assignment for C1 (74-82-8) in data/thermo_params/unifac/groups.yaml; refusing to predict - the curated maps cover the component support of this variant's catalogue rows (the Magnussen LLE set, for example, is not parameterized for alcohol/glycol systems)
- `unifac_psrk_pr`: ok — n/a — refuses the slice feed: ValueError: no UNIFAC group assignment for C1 (74-82-8) in data/thermo_params/unifac/groups.yaml; refusing to predict - the curated maps cover the component support of this variant's catalogue rows (the Magnussen LLE set, for example, is not parameterized for alcohol/glycol systems)
- `unifac_psrk_rk`: ok — n/a — refuses the slice feed: ValueError: no UNIFAC group assignment for C1 (74-82-8) in data/thermo_params/unifac/groups.yaml; refusing to predict - the curated maps cover the component support of this variant's catalogue rows (the Magnussen LLE set, for example, is not parameterized for alcohol/glycol systems)
- `unifac_rk`: ok — n/a — refuses the slice feed: ValueError: no UNIFAC group assignment for C1 (74-82-8) in data/thermo_params/unifac/groups.yaml; refusing to predict - the curated maps cover the component support of this variant's catalogue rows (the Magnussen LLE set, for example, is not parameterized for alcohol/glycol systems)
- `uniquac_ig`: ok — n/a — refuses the slice feed: ValueError: ChemSep UNIQUAC databank has no fitted binary parameters for pair C1 (74-82-8) / C2 (74-84-0); refusing to flash a zero-filled (ideal) pair matrix - select a thermo model whose databank covers this component support
- `uniquac_pr`: ok — n/a — refuses the slice feed: ValueError: ChemSep UNIQUAC databank has no fitted binary parameters for pair C1 (74-82-8) / C2 (74-84-0); refusing to flash a zero-filled (ideal) pair matrix - select a thermo model whose databank covers this component support
- `uniquac_rk`: ok — n/a — refuses the slice feed: ValueError: ChemSep UNIQUAC databank has no fitted binary parameters for pair C1 (74-82-8) / C2 (74-84-0); refusing to flash a zero-filled (ideal) pair matrix - select a thermo model whose databank covers this component support
- `vanlaar_ig`: ok — n/a — refuses the slice feed: ValueError: van Laar binary parameters for pair C1 (74-82-8) / C2 (74-84-0) are not available in data/thermo_params/vanlaar/pairs.yaml; refusing to flash a zero-filled (ideal) pair matrix - select a thermo model whose parameter tables cover this component support
- `vanlaar_pr`: ok — n/a — refuses the slice feed: ValueError: van Laar binary parameters for pair C1 (74-82-8) / C2 (74-84-0) are not available in data/thermo_params/vanlaar/pairs.yaml; refusing to flash a zero-filled (ideal) pair matrix - select a thermo model whose parameter tables cover this component support
- `vanlaar_rk`: ok — n/a — refuses the slice feed: ValueError: van Laar binary parameters for pair C1 (74-82-8) / C2 (74-84-0) are not available in data/thermo_params/vanlaar/pairs.yaml; refusing to flash a zero-filled (ideal) pair matrix - select a thermo model whose parameter tables cover this component support
- `wilson_ig`: ok — n/a — refuses the slice feed: ValueError: ChemSep Wilson databank has no fitted binary parameters for pair C1 (74-82-8) / C2 (74-84-0); refusing to flash a zero-filled (ideal) pair matrix - select a thermo model whose databank covers this component support
- `wilson_pr`: ok — n/a — refuses the slice feed: ValueError: ChemSep Wilson databank has no fitted binary parameters for pair C1 (74-82-8) / C2 (74-84-0); refusing to flash a zero-filled (ideal) pair matrix - select a thermo model whose databank covers this component support
- `wilson_rk`: ok — n/a — refuses the slice feed: ValueError: ChemSep Wilson databank has no fitted binary parameters for pair C1 (74-82-8) / C2 (74-84-0); refusing to flash a zero-filled (ideal) pair matrix - select a thermo model whose databank covers this component support
- `pr-mathias-copeman`: ok — n/a — l4_excluded: The Mathias-Copeman alpha is anchored to each component's vapour pressure; on the multi-component slice dew it runs +22% above the generalised-omega pr-family rows and +41% above the srk family (measured 876389 vs 717386/614969 Pa at 293.15 K) - the deviation the Psat fit exists to produce, declared here rather than loosening the 20% band.
- `rk`: ok — n/a — l4_excluded: RK's databank-anchored alpha overpredicts the 293.15 K slice dew pressure ~16x versus the modern-EOS band (measured 1.18e7 vs 6.2e5-7.2e5 Pa) - the documented RK crudeness recorded in l0_excluded, an EOS-accuracy difference rather than a catalogue inconsistency.
- `srk-mathias-copeman`: ok — n/a — l4_excluded: The Mathias-Copeman alpha is anchored to each component's vapour pressure; on the multi-component slice dew it runs +41% above the generalised-omega srk-family rows and +22% above the pr family (measured 869540 vs 614969/717386 Pa at 293.15 K) - the deviation the Psat fit exists to produce, declared here rather than loosening the 20% band.
- `vdw`: ok — n/a — l4_excluded: van der Waals' constant-alpha overpredicts the 293.15 K slice dew pressure ~14x versus the modern-EOS band (measured 1.02e7 vs 6.2e5-7.2e5 Pa) - the documented vdW crudeness recorded in l0_excluded.
- `api-srk-kabadi-danner-srk`: ok — dew P 615893 vs 643917 (rel 0.0435); rhoV 5.18815 vs 5.42979 (rel 0.0445); band 20%
- `api-srk-pr`: ok — dew P 615893 vs 717386 (rel 0.141); rhoV 5.18815 vs 6.08846 (rel 0.148); band 20%
- `api-srk-pr-bm`: ok — dew P 615893 vs 717633 (rel 0.142); rhoV 5.18815 vs 6.09273 (rel 0.148); band 20%
- `api-srk-pr-boston-mathias`: ok — dew P 615893 vs 717633 (rel 0.142); rhoV 5.18815 vs 6.09273 (rel 0.148); band 20%
- `api-srk-pr-lee-kesler-enthalpy`: ok — dew P 615893 vs 717386 (rel 0.141); rhoV 5.18815 vs 6.08846 (rel 0.148); band 20%
- `api-srk-pr-peneloux`: ok — dew P 615893 vs 717386 (rel 0.141); rhoV 5.18815 vs 6.07898 (rel 0.147); band 20%
- `api-srk-pr78`: ok — dew P 615893 vs 717386 (rel 0.141); rhoV 5.18815 vs 6.08846 (rel 0.148); band 20%
- `api-srk-prsv`: ok — dew P 615893 vs 724017 (rel 0.149); rhoV 5.18815 vs 6.14587 (rel 0.156); band 20%
- `api-srk-prsv2`: ok — dew P 615893 vs 724017 (rel 0.149); rhoV 5.18815 vs 6.14587 (rel 0.156); band 20%
- `api-srk-rks-bm`: ok — dew P 615893 vs 615330 (rel 0.000915); rhoV 5.18815 vs 5.18646 (rel 0.000327); band 20%
- `api-srk-sour-pr`: ok — dew P 615893 vs 717386 (rel 0.141); rhoV 5.18815 vs 6.08845 (rel 0.148); band 20%
- `api-srk-sour-srk`: ok — dew P 615893 vs 614968 (rel 0.0015); rhoV 5.18815 vs 5.18049 (rel 0.00148); band 20%
- `api-srk-srk`: ok — dew P 615893 vs 614969 (rel 0.0015); rhoV 5.18815 vs 5.18049 (rel 0.00148); band 20%
- `api-srk-srk-boston-mathias`: ok — dew P 615893 vs 615330 (rel 0.000915); rhoV 5.18815 vs 5.18646 (rel 0.000327); band 20%
- `api-srk-srk-lee-kesler-enthalpy`: ok — dew P 615893 vs 614969 (rel 0.0015); rhoV 5.18815 vs 5.18049 (rel 0.00148); band 20%
- `api-srk-srk-peneloux`: ok — dew P 615893 vs 614969 (rel 0.0015); rhoV 5.18815 vs 5.18231 (rel 0.00113); band 20%
- `api-srk-twu-pr`: ok — dew P 615893 vs 597284 (rel 0.0312); rhoV 5.18815 vs 5.0462 (rel 0.0281); band 20%
- `api-srk-twu-srk`: ok — dew P 615893 vs 596571 (rel 0.0324); rhoV 5.18815 vs 5.0194 (rel 0.0336); band 20%
- `api-srk-zudkevitch-joffe-rk`: ok — n/a — l4_excluded: See the srk declaration: measured 872333 vs 615893 Pa (rel 0.294) at 293.15 K.
- `kabadi-danner-srk-pr`: ok — dew P 643917 vs 717386 (rel 0.102); rhoV 5.42979 vs 6.08846 (rel 0.108); band 20%
- `kabadi-danner-srk-pr-bm`: ok — dew P 643917 vs 717633 (rel 0.103); rhoV 5.42979 vs 6.09273 (rel 0.109); band 20%
- `kabadi-danner-srk-pr-boston-mathias`: ok — dew P 643917 vs 717633 (rel 0.103); rhoV 5.42979 vs 6.09273 (rel 0.109); band 20%
- `kabadi-danner-srk-pr-lee-kesler-enthalpy`: ok — dew P 643917 vs 717386 (rel 0.102); rhoV 5.42979 vs 6.08846 (rel 0.108); band 20%
- `kabadi-danner-srk-pr-peneloux`: ok — dew P 643917 vs 717386 (rel 0.102); rhoV 5.42979 vs 6.07898 (rel 0.107); band 20%
- `kabadi-danner-srk-pr78`: ok — dew P 643917 vs 717386 (rel 0.102); rhoV 5.42979 vs 6.08846 (rel 0.108); band 20%
- `kabadi-danner-srk-prsv`: ok — dew P 643917 vs 724017 (rel 0.111); rhoV 5.42979 vs 6.14587 (rel 0.117); band 20%
- `kabadi-danner-srk-prsv2`: ok — dew P 643917 vs 724017 (rel 0.111); rhoV 5.42979 vs 6.14587 (rel 0.117); band 20%
- `kabadi-danner-srk-rks-bm`: ok — dew P 643917 vs 615330 (rel 0.0465); rhoV 5.42979 vs 5.18646 (rel 0.0469); band 20%
- `kabadi-danner-srk-sour-pr`: ok — dew P 643917 vs 717386 (rel 0.102); rhoV 5.42979 vs 6.08845 (rel 0.108); band 20%
- `kabadi-danner-srk-sour-srk`: ok — dew P 643917 vs 614968 (rel 0.0471); rhoV 5.42979 vs 5.18049 (rel 0.0481); band 20%
- `kabadi-danner-srk-srk`: ok — dew P 643917 vs 614969 (rel 0.0471); rhoV 5.42979 vs 5.18049 (rel 0.0481); band 20%
- `kabadi-danner-srk-srk-boston-mathias`: ok — dew P 643917 vs 615330 (rel 0.0465); rhoV 5.42979 vs 5.18646 (rel 0.0469); band 20%
- `kabadi-danner-srk-srk-lee-kesler-enthalpy`: ok — dew P 643917 vs 614969 (rel 0.0471); rhoV 5.42979 vs 5.18049 (rel 0.0481); band 20%
- `kabadi-danner-srk-srk-peneloux`: ok — dew P 643917 vs 614969 (rel 0.0471); rhoV 5.42979 vs 5.18231 (rel 0.0478); band 20%
- `kabadi-danner-srk-twu-pr`: ok — dew P 643917 vs 597284 (rel 0.0781); rhoV 5.42979 vs 5.0462 (rel 0.076); band 20%
- `kabadi-danner-srk-twu-srk`: ok — dew P 643917 vs 596571 (rel 0.0794); rhoV 5.42979 vs 5.0194 (rel 0.0818); band 20%
- `kabadi-danner-srk-zudkevitch-joffe-rk`: ok — n/a — l4_excluded: See the srk declaration: measured 872333 vs 643917 Pa (rel 0.262) at 293.15 K.
- `pr-pr-bm`: ok — dew P 717386 vs 717633 (rel 0.000344); rhoV 6.08846 vs 6.09273 (rel 0.000701); band 20%
- `pr-pr-boston-mathias`: ok — dew P 717386 vs 717633 (rel 0.000344); rhoV 6.08846 vs 6.09273 (rel 0.000701); band 20%
- `pr-pr-lee-kesler-enthalpy`: ok — dew P 717386 vs 717386 (rel 0); rhoV 6.08846 vs 6.08846 (rel 0); band 20%
- `pr-pr-peneloux`: ok — dew P 717386 vs 717386 (rel 0); rhoV 6.08846 vs 6.07898 (rel 0.00156); band 20%
- `pr-pr78`: ok — dew P 717386 vs 717386 (rel 0); rhoV 6.08846 vs 6.08846 (rel 0); band 20%
- `pr-prsv`: ok — dew P 717386 vs 724017 (rel 0.00916); rhoV 6.08846 vs 6.14587 (rel 0.00934); band 20%
- `pr-prsv2`: ok — dew P 717386 vs 724017 (rel 0.00916); rhoV 6.08846 vs 6.14587 (rel 0.00934); band 20%
- `pr-rks-bm`: ok — dew P 717386 vs 615330 (rel 0.166); rhoV 6.08846 vs 5.18646 (rel 0.174); band 20%
- `pr-sour-pr`: ok — dew P 717386 vs 717386 (rel 1.38e-07); rhoV 6.08846 vs 6.08845 (rel 1.42e-07); band 20%
- `pr-sour-srk`: ok — dew P 717386 vs 614968 (rel 0.167); rhoV 6.08846 vs 5.18049 (rel 0.175); band 20%
- `pr-srk`: ok — dew P 717386 vs 614969 (rel 0.167); rhoV 6.08846 vs 5.18049 (rel 0.175); band 20%
- `pr-srk-boston-mathias`: ok — dew P 717386 vs 615330 (rel 0.166); rhoV 6.08846 vs 5.18646 (rel 0.174); band 20%
- `pr-srk-lee-kesler-enthalpy`: ok — dew P 717386 vs 614969 (rel 0.167); rhoV 6.08846 vs 5.18049 (rel 0.175); band 20%
- `pr-srk-peneloux`: ok — dew P 717386 vs 614969 (rel 0.167); rhoV 6.08846 vs 5.18231 (rel 0.175); band 20%
- `pr-twu-pr`: ok — n/a — l4_excluded: Twu (1995) alpha is anchored to each component's vapour pressure; on the multi-component slice dew it runs ~17-21% below the generalised-omega pr-family rows (measured 597284 vs 717386-724017 Pa at 293.15 K) - an expected alpha-accuracy difference, declared here rather than loosening the 20% band.
- `pr-twu-srk`: ok — n/a — l4_excluded: Twu (1995) alpha is anchored to each component's vapour pressure; on the multi-component slice dew it runs ~20-21% below the generalised-omega pr-family rows (measured 596571 vs 717386-724017 Pa at 293.15 K) - an expected alpha-accuracy difference, declared here rather than loosening the 20% band.
- `pr-zudkevitch-joffe-rk`: ok — dew P 717386 vs 872333 (rel 0.178); rhoV 6.08846 vs 7.41427 (rel 0.179); band 20%
- `pr-bm-pr-boston-mathias`: ok — dew P 717633 vs 717633 (rel 0); rhoV 6.09273 vs 6.09273 (rel 0); band 20%
- `pr-bm-pr-lee-kesler-enthalpy`: ok — dew P 717633 vs 717386 (rel 0.000344); rhoV 6.09273 vs 6.08846 (rel 0.000702); band 20%
- `pr-bm-pr-peneloux`: ok — dew P 717633 vs 717386 (rel 0.000344); rhoV 6.09273 vs 6.07898 (rel 0.00226); band 20%
- `pr-bm-pr78`: ok — dew P 717633 vs 717386 (rel 0.000344); rhoV 6.09273 vs 6.08846 (rel 0.000702); band 20%
- `pr-bm-prsv`: ok — dew P 717633 vs 724017 (rel 0.00882); rhoV 6.09273 vs 6.14587 (rel 0.00865); band 20%
- `pr-bm-prsv2`: ok — dew P 717633 vs 724017 (rel 0.00882); rhoV 6.09273 vs 6.14587 (rel 0.00865); band 20%
- `pr-bm-rks-bm`: ok — dew P 717633 vs 615330 (rel 0.166); rhoV 6.09273 vs 5.18646 (rel 0.175); band 20%
- `pr-bm-sour-pr`: ok — dew P 717633 vs 717386 (rel 0.000344); rhoV 6.09273 vs 6.08845 (rel 0.000702); band 20%
- `pr-bm-sour-srk`: ok — dew P 717633 vs 614968 (rel 0.167); rhoV 6.09273 vs 5.18049 (rel 0.176); band 20%
- `pr-bm-srk`: ok — dew P 717633 vs 614969 (rel 0.167); rhoV 6.09273 vs 5.18049 (rel 0.176); band 20%
- `pr-bm-srk-boston-mathias`: ok — dew P 717633 vs 615330 (rel 0.166); rhoV 6.09273 vs 5.18646 (rel 0.175); band 20%
- `pr-bm-srk-lee-kesler-enthalpy`: ok — dew P 717633 vs 614969 (rel 0.167); rhoV 6.09273 vs 5.18049 (rel 0.176); band 20%
- `pr-bm-srk-peneloux`: ok — dew P 717633 vs 614969 (rel 0.167); rhoV 6.09273 vs 5.18231 (rel 0.176); band 20%
- `pr-bm-twu-pr`: ok — n/a — l4_excluded: Twu (1995) alpha is anchored to each component's vapour pressure; on the multi-component slice dew it runs ~17-21% below the generalised-omega pr-family rows (measured 597284 vs 717386-724017 Pa at 293.15 K) - an expected alpha-accuracy difference, declared here rather than loosening the 20% band.
- `pr-bm-twu-srk`: ok — n/a — l4_excluded: Twu (1995) alpha is anchored to each component's vapour pressure; on the multi-component slice dew it runs ~20-21% below the generalised-omega pr-family rows (measured 596571 vs 717386-724017 Pa at 293.15 K) - an expected alpha-accuracy difference, declared here rather than loosening the 20% band.
- `pr-bm-zudkevitch-joffe-rk`: ok — dew P 717633 vs 872333 (rel 0.177); rhoV 6.09273 vs 7.41427 (rel 0.178); band 20%
- `pr-boston-mathias-pr-lee-kesler-enthalpy`: ok — dew P 717633 vs 717386 (rel 0.000344); rhoV 6.09273 vs 6.08846 (rel 0.000702); band 20%
- `pr-boston-mathias-pr-peneloux`: ok — dew P 717633 vs 717386 (rel 0.000344); rhoV 6.09273 vs 6.07898 (rel 0.00226); band 20%
- `pr-boston-mathias-pr78`: ok — dew P 717633 vs 717386 (rel 0.000344); rhoV 6.09273 vs 6.08846 (rel 0.000702); band 20%
- `pr-boston-mathias-prsv`: ok — dew P 717633 vs 724017 (rel 0.00882); rhoV 6.09273 vs 6.14587 (rel 0.00865); band 20%
- `pr-boston-mathias-prsv2`: ok — dew P 717633 vs 724017 (rel 0.00882); rhoV 6.09273 vs 6.14587 (rel 0.00865); band 20%
- `pr-boston-mathias-rks-bm`: ok — dew P 717633 vs 615330 (rel 0.166); rhoV 6.09273 vs 5.18646 (rel 0.175); band 20%
- `pr-boston-mathias-sour-pr`: ok — dew P 717633 vs 717386 (rel 0.000344); rhoV 6.09273 vs 6.08845 (rel 0.000702); band 20%
- `pr-boston-mathias-sour-srk`: ok — dew P 717633 vs 614968 (rel 0.167); rhoV 6.09273 vs 5.18049 (rel 0.176); band 20%
- `pr-boston-mathias-srk`: ok — dew P 717633 vs 614969 (rel 0.167); rhoV 6.09273 vs 5.18049 (rel 0.176); band 20%
- `pr-boston-mathias-srk-boston-mathias`: ok — dew P 717633 vs 615330 (rel 0.166); rhoV 6.09273 vs 5.18646 (rel 0.175); band 20%
- `pr-boston-mathias-srk-lee-kesler-enthalpy`: ok — dew P 717633 vs 614969 (rel 0.167); rhoV 6.09273 vs 5.18049 (rel 0.176); band 20%
- `pr-boston-mathias-srk-peneloux`: ok — dew P 717633 vs 614969 (rel 0.167); rhoV 6.09273 vs 5.18231 (rel 0.176); band 20%
- `pr-boston-mathias-twu-pr`: ok — n/a — l4_excluded: Twu (1995) alpha is anchored to each component's vapour pressure; on the multi-component slice dew it runs ~17-21% below the generalised-omega pr-family rows (measured 597284 vs 717386-724017 Pa at 293.15 K) - an expected alpha-accuracy difference, declared here rather than loosening the 20% band.
- `pr-boston-mathias-twu-srk`: ok — n/a — l4_excluded: Twu (1995) alpha is anchored to each component's vapour pressure; on the multi-component slice dew it runs ~20-21% below the generalised-omega pr-family rows (measured 596571 vs 717386-724017 Pa at 293.15 K) - an expected alpha-accuracy difference, declared here rather than loosening the 20% band.
- `pr-boston-mathias-zudkevitch-joffe-rk`: ok — dew P 717633 vs 872333 (rel 0.177); rhoV 6.09273 vs 7.41427 (rel 0.178); band 20%
- `pr-lee-kesler-enthalpy-pr-peneloux`: ok — dew P 717386 vs 717386 (rel 0); rhoV 6.08846 vs 6.07898 (rel 0.00156); band 20%
- `pr-lee-kesler-enthalpy-pr78`: ok — dew P 717386 vs 717386 (rel 0); rhoV 6.08846 vs 6.08846 (rel 0); band 20%
- `pr-lee-kesler-enthalpy-prsv`: ok — dew P 717386 vs 724017 (rel 0.00916); rhoV 6.08846 vs 6.14587 (rel 0.00934); band 20%
- `pr-lee-kesler-enthalpy-prsv2`: ok — dew P 717386 vs 724017 (rel 0.00916); rhoV 6.08846 vs 6.14587 (rel 0.00934); band 20%
- `pr-lee-kesler-enthalpy-rks-bm`: ok — dew P 717386 vs 615330 (rel 0.166); rhoV 6.08846 vs 5.18646 (rel 0.174); band 20%
- `pr-lee-kesler-enthalpy-sour-pr`: ok — dew P 717386 vs 717386 (rel 1.38e-07); rhoV 6.08846 vs 6.08845 (rel 1.42e-07); band 20%
- `pr-lee-kesler-enthalpy-sour-srk`: ok — dew P 717386 vs 614968 (rel 0.167); rhoV 6.08846 vs 5.18049 (rel 0.175); band 20%
- `pr-lee-kesler-enthalpy-srk`: ok — dew P 717386 vs 614969 (rel 0.167); rhoV 6.08846 vs 5.18049 (rel 0.175); band 20%
- `pr-lee-kesler-enthalpy-srk-boston-mathias`: ok — dew P 717386 vs 615330 (rel 0.166); rhoV 6.08846 vs 5.18646 (rel 0.174); band 20%
- `pr-lee-kesler-enthalpy-srk-lee-kesler-enthalpy`: ok — dew P 717386 vs 614969 (rel 0.167); rhoV 6.08846 vs 5.18049 (rel 0.175); band 20%
- `pr-lee-kesler-enthalpy-srk-peneloux`: ok — dew P 717386 vs 614969 (rel 0.167); rhoV 6.08846 vs 5.18231 (rel 0.175); band 20%
- `pr-lee-kesler-enthalpy-twu-pr`: ok — n/a — l4_excluded: Twu (1995) alpha is anchored to each component's vapour pressure; on the multi-component slice dew it runs ~17-21% below the generalised-omega pr-family rows (measured 597284 vs 717386-724017 Pa at 293.15 K) - an expected alpha-accuracy difference, declared here rather than loosening the 20% band.
- `pr-lee-kesler-enthalpy-twu-srk`: ok — n/a — l4_excluded: Twu (1995) alpha is anchored to each component's vapour pressure; on the multi-component slice dew it runs ~20-21% below the generalised-omega pr-family rows (measured 596571 vs 717386-724017 Pa at 293.15 K) - an expected alpha-accuracy difference, declared here rather than loosening the 20% band.
- `pr-lee-kesler-enthalpy-zudkevitch-joffe-rk`: ok — dew P 717386 vs 872333 (rel 0.178); rhoV 6.08846 vs 7.41427 (rel 0.179); band 20%
- `pr-peneloux-pr78`: ok — dew P 717386 vs 717386 (rel 0); rhoV 6.07898 vs 6.08846 (rel 0.00156); band 20%
- `pr-peneloux-prsv`: ok — dew P 717386 vs 724017 (rel 0.00916); rhoV 6.07898 vs 6.14587 (rel 0.0109); band 20%
- `pr-peneloux-prsv2`: ok — dew P 717386 vs 724017 (rel 0.00916); rhoV 6.07898 vs 6.14587 (rel 0.0109); band 20%
- `pr-peneloux-rks-bm`: ok — dew P 717386 vs 615330 (rel 0.166); rhoV 6.07898 vs 5.18646 (rel 0.172); band 20%
- `pr-peneloux-sour-pr`: ok — dew P 717386 vs 717386 (rel 1.38e-07); rhoV 6.07898 vs 6.08845 (rel 0.00156); band 20%
- `pr-peneloux-sour-srk`: ok — dew P 717386 vs 614968 (rel 0.167); rhoV 6.07898 vs 5.18049 (rel 0.173); band 20%
- `pr-peneloux-srk`: ok — dew P 717386 vs 614969 (rel 0.167); rhoV 6.07898 vs 5.18049 (rel 0.173); band 20%
- `pr-peneloux-srk-boston-mathias`: ok — dew P 717386 vs 615330 (rel 0.166); rhoV 6.07898 vs 5.18646 (rel 0.172); band 20%
- `pr-peneloux-srk-lee-kesler-enthalpy`: ok — dew P 717386 vs 614969 (rel 0.167); rhoV 6.07898 vs 5.18049 (rel 0.173); band 20%
- `pr-peneloux-srk-peneloux`: ok — dew P 717386 vs 614969 (rel 0.167); rhoV 6.07898 vs 5.18231 (rel 0.173); band 20%
- `pr-peneloux-twu-pr`: ok — n/a — l4_excluded: Twu (1995) alpha is anchored to each component's vapour pressure; on the multi-component slice dew it runs ~17-21% below the generalised-omega pr-family rows (measured 597284 vs 717386-724017 Pa at 293.15 K) - an expected alpha-accuracy difference, declared here rather than loosening the 20% band.
- `pr-peneloux-twu-srk`: ok — n/a — l4_excluded: Twu (1995) alpha is anchored to each component's vapour pressure; on the multi-component slice dew it runs ~20-21% below the generalised-omega pr-family rows (measured 596571 vs 717386-724017 Pa at 293.15 K) - an expected alpha-accuracy difference, declared here rather than loosening the 20% band.
- `pr-peneloux-zudkevitch-joffe-rk`: ok — dew P 717386 vs 872333 (rel 0.178); rhoV 6.07898 vs 7.41427 (rel 0.18); band 20%
- `pr78-prsv`: ok — dew P 717386 vs 724017 (rel 0.00916); rhoV 6.08846 vs 6.14587 (rel 0.00934); band 20%
- `pr78-prsv2`: ok — dew P 717386 vs 724017 (rel 0.00916); rhoV 6.08846 vs 6.14587 (rel 0.00934); band 20%
- `pr78-rks-bm`: ok — dew P 717386 vs 615330 (rel 0.166); rhoV 6.08846 vs 5.18646 (rel 0.174); band 20%
- `pr78-sour-pr`: ok — dew P 717386 vs 717386 (rel 1.38e-07); rhoV 6.08846 vs 6.08845 (rel 1.42e-07); band 20%
- `pr78-sour-srk`: ok — dew P 717386 vs 614968 (rel 0.167); rhoV 6.08846 vs 5.18049 (rel 0.175); band 20%
- `pr78-srk`: ok — dew P 717386 vs 614969 (rel 0.167); rhoV 6.08846 vs 5.18049 (rel 0.175); band 20%
- `pr78-srk-boston-mathias`: ok — dew P 717386 vs 615330 (rel 0.166); rhoV 6.08846 vs 5.18646 (rel 0.174); band 20%
- `pr78-srk-lee-kesler-enthalpy`: ok — dew P 717386 vs 614969 (rel 0.167); rhoV 6.08846 vs 5.18049 (rel 0.175); band 20%
- `pr78-srk-peneloux`: ok — dew P 717386 vs 614969 (rel 0.167); rhoV 6.08846 vs 5.18231 (rel 0.175); band 20%
- `pr78-twu-pr`: ok — n/a — l4_excluded: Twu (1995) alpha is anchored to each component's vapour pressure; on the multi-component slice dew it runs ~17-21% below the generalised-omega pr-family rows (measured 597284 vs 717386-724017 Pa at 293.15 K) - an expected alpha-accuracy difference, declared here rather than loosening the 20% band.
- `pr78-twu-srk`: ok — n/a — l4_excluded: Twu (1995) alpha is anchored to each component's vapour pressure; on the multi-component slice dew it runs ~20-21% below the generalised-omega pr-family rows (measured 596571 vs 717386-724017 Pa at 293.15 K) - an expected alpha-accuracy difference, declared here rather than loosening the 20% band.
- `pr78-zudkevitch-joffe-rk`: ok — dew P 717386 vs 872333 (rel 0.178); rhoV 6.08846 vs 7.41427 (rel 0.179); band 20%
- `prsv-prsv2`: ok — dew P 724017 vs 724017 (rel 0); rhoV 6.14587 vs 6.14587 (rel 0); band 20%
- `prsv-rks-bm`: ok — dew P 724017 vs 615330 (rel 0.177); rhoV 6.14587 vs 5.18646 (rel 0.185); band 20%
- `prsv-sour-pr`: ok — dew P 724017 vs 717386 (rel 0.00924); rhoV 6.14587 vs 6.08845 (rel 0.00943); band 20%
- `prsv-sour-srk`: ok — dew P 724017 vs 614968 (rel 0.177); rhoV 6.14587 vs 5.18049 (rel 0.186); band 20%
- `prsv-srk`: ok — dew P 724017 vs 614969 (rel 0.177); rhoV 6.14587 vs 5.18049 (rel 0.186); band 20%
- `prsv-srk-boston-mathias`: ok — dew P 724017 vs 615330 (rel 0.177); rhoV 6.14587 vs 5.18646 (rel 0.185); band 20%
- `prsv-srk-lee-kesler-enthalpy`: ok — dew P 724017 vs 614969 (rel 0.177); rhoV 6.14587 vs 5.18049 (rel 0.186); band 20%
- `prsv-srk-peneloux`: ok — dew P 724017 vs 614969 (rel 0.177); rhoV 6.14587 vs 5.18231 (rel 0.186); band 20%
- `prsv-twu-pr`: ok — n/a — l4_excluded: Twu (1995) alpha is anchored to each component's vapour pressure; on the multi-component slice dew it runs ~17-21% below the generalised-omega pr-family rows (measured 597284 vs 717386-724017 Pa at 293.15 K) - an expected alpha-accuracy difference, declared here rather than loosening the 20% band.
- `prsv-twu-srk`: ok — n/a — l4_excluded: Twu (1995) alpha is anchored to each component's vapour pressure; on the multi-component slice dew it runs ~20-21% below the generalised-omega pr-family rows (measured 596571 vs 717386-724017 Pa at 293.15 K) - an expected alpha-accuracy difference, declared here rather than loosening the 20% band.
- `prsv-zudkevitch-joffe-rk`: ok — dew P 724017 vs 872333 (rel 0.17); rhoV 6.14587 vs 7.41427 (rel 0.171); band 20%
- `prsv2-rks-bm`: ok — dew P 724017 vs 615330 (rel 0.177); rhoV 6.14587 vs 5.18646 (rel 0.185); band 20%
- `prsv2-sour-pr`: ok — dew P 724017 vs 717386 (rel 0.00924); rhoV 6.14587 vs 6.08845 (rel 0.00943); band 20%
- `prsv2-sour-srk`: ok — dew P 724017 vs 614968 (rel 0.177); rhoV 6.14587 vs 5.18049 (rel 0.186); band 20%
- `prsv2-srk`: ok — dew P 724017 vs 614969 (rel 0.177); rhoV 6.14587 vs 5.18049 (rel 0.186); band 20%
- `prsv2-srk-boston-mathias`: ok — dew P 724017 vs 615330 (rel 0.177); rhoV 6.14587 vs 5.18646 (rel 0.185); band 20%
- `prsv2-srk-lee-kesler-enthalpy`: ok — dew P 724017 vs 614969 (rel 0.177); rhoV 6.14587 vs 5.18049 (rel 0.186); band 20%
- `prsv2-srk-peneloux`: ok — dew P 724017 vs 614969 (rel 0.177); rhoV 6.14587 vs 5.18231 (rel 0.186); band 20%
- `prsv2-twu-pr`: ok — n/a — l4_excluded: Twu (1995) alpha is anchored to each component's vapour pressure; on the multi-component slice dew it runs ~17-21% below the generalised-omega pr-family rows (measured 597284 vs 717386-724017 Pa at 293.15 K) - an expected alpha-accuracy difference, declared here rather than loosening the 20% band.
- `prsv2-twu-srk`: ok — n/a — l4_excluded: Twu (1995) alpha is anchored to each component's vapour pressure; on the multi-component slice dew it runs ~20-21% below the generalised-omega pr-family rows (measured 596571 vs 717386-724017 Pa at 293.15 K) - an expected alpha-accuracy difference, declared here rather than loosening the 20% band.
- `prsv2-zudkevitch-joffe-rk`: ok — dew P 724017 vs 872333 (rel 0.17); rhoV 6.14587 vs 7.41427 (rel 0.171); band 20%
- `rks-bm-sour-pr`: ok — dew P 615330 vs 717386 (rel 0.142); rhoV 5.18646 vs 6.08845 (rel 0.148); band 20%
- `rks-bm-sour-srk`: ok — dew P 615330 vs 614968 (rel 0.000587); rhoV 5.18646 vs 5.18049 (rel 0.00115); band 20%
- `rks-bm-srk`: ok — dew P 615330 vs 614969 (rel 0.000587); rhoV 5.18646 vs 5.18049 (rel 0.00115); band 20%
- `rks-bm-srk-boston-mathias`: ok — dew P 615330 vs 615330 (rel 0); rhoV 5.18646 vs 5.18646 (rel 0); band 20%
- `rks-bm-srk-lee-kesler-enthalpy`: ok — dew P 615330 vs 614969 (rel 0.000587); rhoV 5.18646 vs 5.18049 (rel 0.00115); band 20%
- `rks-bm-srk-peneloux`: ok — dew P 615330 vs 614969 (rel 0.000587); rhoV 5.18646 vs 5.18231 (rel 0.0008); band 20%
- `rks-bm-twu-pr`: ok — dew P 615330 vs 597284 (rel 0.0302); rhoV 5.18646 vs 5.0462 (rel 0.0278); band 20%
- `rks-bm-twu-srk`: ok — dew P 615330 vs 596571 (rel 0.0314); rhoV 5.18646 vs 5.0194 (rel 0.0333); band 20%
- `rks-bm-zudkevitch-joffe-rk`: ok — n/a — l4_excluded: See the srk declaration: measured 872333 vs 615330 Pa (rel 0.295) at 293.15 K.
- `sour-pr-sour-srk`: ok — dew P 717386 vs 614968 (rel 0.167); rhoV 6.08845 vs 5.18049 (rel 0.175); band 20%
- `sour-pr-srk`: ok — dew P 717386 vs 614969 (rel 0.167); rhoV 6.08845 vs 5.18049 (rel 0.175); band 20%
- `sour-pr-srk-boston-mathias`: ok — dew P 717386 vs 615330 (rel 0.166); rhoV 6.08845 vs 5.18646 (rel 0.174); band 20%
- `sour-pr-srk-lee-kesler-enthalpy`: ok — dew P 717386 vs 614969 (rel 0.167); rhoV 6.08845 vs 5.18049 (rel 0.175); band 20%
- `sour-pr-srk-peneloux`: ok — dew P 717386 vs 614969 (rel 0.167); rhoV 6.08845 vs 5.18231 (rel 0.175); band 20%
- `sour-pr-twu-pr`: ok — n/a — l4_excluded: Twu (1995) alpha is anchored to each component's vapour pressure; on the multi-component slice dew it runs ~17-21% below the generalised-omega pr-family rows (measured 597284 vs 717386-724017 Pa at 293.15 K) - an expected alpha-accuracy difference, declared here rather than loosening the 20% band.
- `sour-pr-twu-srk`: ok — n/a — l4_excluded: Twu (1995) alpha is anchored to each component's vapour pressure; on the multi-component slice dew it runs ~20-21% below the generalised-omega pr-family rows (measured 596571 vs 717386-724017 Pa at 293.15 K) - an expected alpha-accuracy difference, declared here rather than loosening the 20% band.
- `sour-pr-zudkevitch-joffe-rk`: ok — dew P 717386 vs 872333 (rel 0.178); rhoV 6.08845 vs 7.41427 (rel 0.179); band 20%
- `sour-srk-srk`: ok — dew P 614968 vs 614969 (rel 1.09e-07); rhoV 5.18049 vs 5.18049 (rel 1.11e-07); band 20%
- `sour-srk-srk-boston-mathias`: ok — dew P 614968 vs 615330 (rel 0.000587); rhoV 5.18049 vs 5.18646 (rel 0.00115); band 20%
- `sour-srk-srk-lee-kesler-enthalpy`: ok — dew P 614968 vs 614969 (rel 1.09e-07); rhoV 5.18049 vs 5.18049 (rel 1.11e-07); band 20%
- `sour-srk-srk-peneloux`: ok — dew P 614968 vs 614969 (rel 1.09e-07); rhoV 5.18049 vs 5.18231 (rel 0.000352); band 20%
- `sour-srk-twu-pr`: ok — dew P 614968 vs 597284 (rel 0.0296); rhoV 5.18049 vs 5.0462 (rel 0.0266); band 20%
- `sour-srk-twu-srk`: ok — dew P 614968 vs 596571 (rel 0.0308); rhoV 5.18049 vs 5.0194 (rel 0.0321); band 20%
- `sour-srk-zudkevitch-joffe-rk`: ok — n/a — l4_excluded: See the srk declaration: measured 872333 vs 614968 Pa (rel 0.295) at 293.15 K.
- `srk-srk-boston-mathias`: ok — dew P 614969 vs 615330 (rel 0.000587); rhoV 5.18049 vs 5.18646 (rel 0.00115); band 20%
- `srk-srk-lee-kesler-enthalpy`: ok — dew P 614969 vs 614969 (rel 0); rhoV 5.18049 vs 5.18049 (rel 0); band 20%
- `srk-srk-peneloux`: ok — dew P 614969 vs 614969 (rel 0); rhoV 5.18049 vs 5.18231 (rel 0.000352); band 20%
- `srk-twu-pr`: ok — dew P 614969 vs 597284 (rel 0.0296); rhoV 5.18049 vs 5.0462 (rel 0.0266); band 20%
- `srk-twu-srk`: ok — dew P 614969 vs 596571 (rel 0.0308); rhoV 5.18049 vs 5.0194 (rel 0.0321); band 20%
- `srk-zudkevitch-joffe-rk`: ok — n/a — l4_excluded: The Zudkevitch-Joffe Psat-fitted alpha with Omega_b held at the RK constant (documented deviation in params.alpha_parameters) runs +26-32% above the generalised-omega srk-family rows on the multi-component slice dew (measured 872333 vs 614968-643917 Pa at 293.15 K) while the pr-family rows sit within the 20% band (rel 0.17-0.18) - an alpha-accuracy difference, declared here rather than loosening the band.
- `srk-boston-mathias-srk-lee-kesler-enthalpy`: ok — dew P 615330 vs 614969 (rel 0.000587); rhoV 5.18646 vs 5.18049 (rel 0.00115); band 20%
- `srk-boston-mathias-srk-peneloux`: ok — dew P 615330 vs 614969 (rel 0.000587); rhoV 5.18646 vs 5.18231 (rel 0.0008); band 20%
- `srk-boston-mathias-twu-pr`: ok — dew P 615330 vs 597284 (rel 0.0302); rhoV 5.18646 vs 5.0462 (rel 0.0278); band 20%
- `srk-boston-mathias-twu-srk`: ok — dew P 615330 vs 596571 (rel 0.0314); rhoV 5.18646 vs 5.0194 (rel 0.0333); band 20%
- `srk-boston-mathias-zudkevitch-joffe-rk`: ok — n/a — l4_excluded: See the srk declaration: measured 872333 vs 615330 Pa (rel 0.295) at 293.15 K.
- `srk-lee-kesler-enthalpy-srk-peneloux`: ok — dew P 614969 vs 614969 (rel 0); rhoV 5.18049 vs 5.18231 (rel 0.000352); band 20%
- `srk-lee-kesler-enthalpy-twu-pr`: ok — dew P 614969 vs 597284 (rel 0.0296); rhoV 5.18049 vs 5.0462 (rel 0.0266); band 20%
- `srk-lee-kesler-enthalpy-twu-srk`: ok — dew P 614969 vs 596571 (rel 0.0308); rhoV 5.18049 vs 5.0194 (rel 0.0321); band 20%
- `srk-lee-kesler-enthalpy-zudkevitch-joffe-rk`: ok — n/a — l4_excluded: See the srk declaration: measured 872333 vs 614969 Pa (rel 0.295) at 293.15 K.
- `srk-peneloux-twu-pr`: ok — dew P 614969 vs 597284 (rel 0.0296); rhoV 5.18231 vs 5.0462 (rel 0.027); band 20%
- `srk-peneloux-twu-srk`: ok — dew P 614969 vs 596571 (rel 0.0308); rhoV 5.18231 vs 5.0194 (rel 0.0325); band 20%
- `srk-peneloux-zudkevitch-joffe-rk`: ok — n/a — l4_excluded: See the srk declaration: measured 872333 vs 614969 Pa (rel 0.295) at 293.15 K.
- `twu-pr-twu-srk`: ok — dew P 597284 vs 596571 (rel 0.0012); rhoV 5.0462 vs 5.0194 (rel 0.00534); band 20%
- `twu-pr-zudkevitch-joffe-rk`: ok — n/a — l4_excluded: See the srk declaration: measured 872333 vs 597284 Pa (rel 0.315) at 293.15 K.
- `twu-srk-zudkevitch-joffe-rk`: ok — n/a — l4_excluded: See the srk declaration: measured 872333 vs 596571 Pa (rel 0.316) at 293.15 K.

## Results

### package `amine_enrtl` — 8/8 pass (100.0 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| bubble_P | 4 | 4 | 100.0 % |
| dew_P | 4 | 4 | 100.0 % |

### package `amine_ke` — 13/13 pass (100.0 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| K | 5 | 5 | 100.0 % |
| bubble_P | 4 | 4 | 100.0 % |
| dew_P | 4 | 4 | 100.0 % |

### package `antoine-ideal-k` — 8/8 pass (100.0 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| K | 4 | 4 | 100.0 % |
| bubble_P | 4 | 4 | 100.0 % |

### package `api-srk` — 17/26 pass (65.4 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| Cp | 4 | 1 | 25.0 % |
| bubble_P | 6 | 5 | 83.3 % |
| dew_P | 7 | 4 | 57.1 % |
| rho_L | 4 | 2 | 50.0 % |
| rho_V | 4 | 4 | 100.0 % |
| vapor_comp | 1 | 1 | 100.0 % |

### package `braun-k10` — 4/4 pass (100.0 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| K | 2 | 2 | 100.0 % |
| bubble_P | 2 | 2 | 100.0 % |

### package `chao-seader` — 10/10 pass (100.0 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| K | 7 | 7 | 100.0 % |
| bubble_P | 3 | 3 | 100.0 % |

### package `esso-tabular` — 8/8 pass (100.0 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| K | 4 | 4 | 100.0 % |
| bubble_P | 4 | 4 | 100.0 % |

### package `gerg2008` — 42/42 pass (100.0 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| Cp | 5 | 5 | 100.0 % |
| bubble_P | 12 | 12 | 100.0 % |
| dew_P | 8 | 8 | 100.0 % |
| rho_L | 5 | 5 | 100.0 % |
| rho_V | 5 | 5 | 100.0 % |
| vapor_comp | 7 | 7 | 100.0 % |

### package `grayson-streed` — 6/6 pass (100.0 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| K | 3 | 3 | 100.0 % |
| bubble_P | 3 | 3 | 100.0 % |

### package `grayson-streed-extended` — 6/6 pass (100.0 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| K | 3 | 3 | 100.0 % |
| bubble_P | 3 | 3 | 100.0 % |

### package `henry-sander` — 10/10 pass (100.0 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| K | 6 | 6 | 100.0 % |
| bubble_P | 4 | 4 | 100.0 % |

### package `iapws95` — 25/25 pass (100.0 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| Cp | 5 | 5 | 100.0 % |
| bubble_P | 5 | 5 | 100.0 % |
| dew_P | 5 | 5 | 100.0 % |
| rho_L | 5 | 5 | 100.0 % |
| rho_V | 5 | 5 | 100.0 % |

### package `ideal-lk` — 8/8 pass (100.0 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| K | 4 | 4 | 100.0 % |
| bubble_P | 4 | 4 | 100.0 % |

### package `ideal-raoult` — 8/8 pass (100.0 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| K | 4 | 4 | 100.0 % |
| bubble_P | 4 | 4 | 100.0 % |

### package `kabadi-danner-srk` — 17/26 pass (65.4 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| Cp | 4 | 1 | 25.0 % |
| bubble_P | 6 | 5 | 83.3 % |
| dew_P | 7 | 4 | 57.1 % |
| rho_L | 4 | 2 | 50.0 % |
| rho_V | 4 | 4 | 100.0 % |
| vapor_comp | 1 | 1 | 100.0 % |

### package `lee-kesler-ploecker` — 8/8 pass (100.0 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| K | 5 | 5 | 100.0 % |
| bubble_P | 3 | 3 | 100.0 % |

### package `margules_ig` — 6/6 pass (100.0 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| bubble_P | 1 | 1 | 100.0 % |
| bubble_T | 2 | 2 | 100.0 % |
| vapor_comp | 3 | 3 | 100.0 % |

### package `nrtl` — 29/62 pass (46.8 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| Cp | 4 | 0 | 0.0 % |
| bubble_P | 17 | 4 | 23.5 % |
| bubble_T | 8 | 5 | 62.5 % |
| dew_P | 4 | 4 | 100.0 % |
| rho_L | 4 | 4 | 100.0 % |
| rho_V | 4 | 3 | 75.0 % |
| vapor_comp | 21 | 9 | 42.9 % |

### package `pr` — 213/278 pass (76.6 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| Cp | 40 | 11 | 27.5 % |
| K | 3 | 1 | 33.3 % |
| bubble_P | 74 | 65 | 87.8 % |
| dew_P | 43 | 40 | 93.0 % |
| liquid_comp | 18 | 18 | 100.0 % |
| rho_L | 40 | 26 | 65.0 % |
| rho_V | 40 | 36 | 90.0 % |
| vapor_comp | 20 | 16 | 80.0 % |

### package `pr-bm` — 19/26 pass (73.1 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| Cp | 4 | 3 | 75.0 % |
| bubble_P | 6 | 4 | 66.7 % |
| dew_P | 7 | 4 | 57.1 % |
| rho_L | 4 | 3 | 75.0 % |
| rho_V | 4 | 4 | 100.0 % |
| vapor_comp | 1 | 1 | 100.0 % |

### package `pr-boston-mathias` — 19/26 pass (73.1 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| Cp | 4 | 3 | 75.0 % |
| bubble_P | 6 | 4 | 66.7 % |
| dew_P | 7 | 4 | 57.1 % |
| rho_L | 4 | 3 | 75.0 % |
| rho_V | 4 | 4 | 100.0 % |
| vapor_comp | 1 | 1 | 100.0 % |

### package `pr-lee-kesler-enthalpy` — 21/26 pass (80.8 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| Cp | 4 | 3 | 75.0 % |
| bubble_P | 6 | 6 | 100.0 % |
| dew_P | 7 | 4 | 57.1 % |
| rho_L | 4 | 3 | 75.0 % |
| rho_V | 4 | 4 | 100.0 % |
| vapor_comp | 1 | 1 | 100.0 % |

### package `pr-mathias-copeman` — 21/26 pass (80.8 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| Cp | 4 | 3 | 75.0 % |
| bubble_P | 6 | 6 | 100.0 % |
| dew_P | 7 | 4 | 57.1 % |
| rho_L | 4 | 3 | 75.0 % |
| rho_V | 4 | 4 | 100.0 % |
| vapor_comp | 1 | 1 | 100.0 % |

### package `pr-peneloux` — 22/26 pass (84.6 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| Cp | 4 | 3 | 75.0 % |
| bubble_P | 6 | 6 | 100.0 % |
| dew_P | 7 | 4 | 57.1 % |
| rho_L | 4 | 4 | 100.0 % |
| rho_V | 4 | 4 | 100.0 % |
| vapor_comp | 1 | 1 | 100.0 % |

### package `pr78` — 213/278 pass (76.6 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| Cp | 40 | 11 | 27.5 % |
| K | 3 | 1 | 33.3 % |
| bubble_P | 74 | 65 | 87.8 % |
| dew_P | 43 | 40 | 93.0 % |
| liquid_comp | 18 | 18 | 100.0 % |
| rho_L | 40 | 26 | 65.0 % |
| rho_V | 40 | 36 | 90.0 % |
| vapor_comp | 20 | 16 | 80.0 % |

### package `prsv` — 21/26 pass (80.8 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| Cp | 4 | 3 | 75.0 % |
| bubble_P | 6 | 6 | 100.0 % |
| dew_P | 7 | 4 | 57.1 % |
| rho_L | 4 | 3 | 75.0 % |
| rho_V | 4 | 4 | 100.0 % |
| vapor_comp | 1 | 1 | 100.0 % |

### package `prsv2` — 21/26 pass (80.8 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| Cp | 4 | 3 | 75.0 % |
| bubble_P | 6 | 6 | 100.0 % |
| dew_P | 7 | 4 | 57.1 % |
| rho_L | 4 | 3 | 75.0 % |
| rho_V | 4 | 4 | 100.0 % |
| vapor_comp | 1 | 1 | 100.0 % |

### package `rk` — 13/26 pass (50.0 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| Cp | 4 | 0 | 0.0 % |
| bubble_P | 6 | 5 | 83.3 % |
| dew_P | 7 | 4 | 57.1 % |
| rho_L | 4 | 1 | 25.0 % |
| rho_V | 4 | 3 | 75.0 % |
| vapor_comp | 1 | 0 | 0.0 % |

### package `rks-bm` — 16/26 pass (61.5 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| Cp | 4 | 1 | 25.0 % |
| bubble_P | 6 | 4 | 66.7 % |
| dew_P | 7 | 4 | 57.1 % |
| rho_L | 4 | 2 | 50.0 % |
| rho_V | 4 | 4 | 100.0 % |
| vapor_comp | 1 | 1 | 100.0 % |

### package `sour-pr` — 21/26 pass (80.8 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| Cp | 4 | 3 | 75.0 % |
| bubble_P | 6 | 6 | 100.0 % |
| dew_P | 7 | 4 | 57.1 % |
| rho_L | 4 | 3 | 75.0 % |
| rho_V | 4 | 4 | 100.0 % |
| vapor_comp | 1 | 1 | 100.0 % |

### package `sour-srk` — 17/26 pass (65.4 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| Cp | 4 | 1 | 25.0 % |
| bubble_P | 6 | 5 | 83.3 % |
| dew_P | 7 | 4 | 57.1 % |
| rho_L | 4 | 2 | 50.0 % |
| rho_V | 4 | 4 | 100.0 % |
| vapor_comp | 1 | 1 | 100.0 % |

### package `srk` — 201/278 pass (72.3 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| Cp | 40 | 11 | 27.5 % |
| K | 3 | 1 | 33.3 % |
| bubble_P | 74 | 63 | 85.1 % |
| dew_P | 43 | 40 | 93.0 % |
| liquid_comp | 18 | 18 | 100.0 % |
| rho_L | 40 | 18 | 45.0 % |
| rho_V | 40 | 33 | 82.5 % |
| vapor_comp | 20 | 17 | 85.0 % |

### package `srk-boston-mathias` — 16/26 pass (61.5 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| Cp | 4 | 1 | 25.0 % |
| bubble_P | 6 | 4 | 66.7 % |
| dew_P | 7 | 4 | 57.1 % |
| rho_L | 4 | 2 | 50.0 % |
| rho_V | 4 | 4 | 100.0 % |
| vapor_comp | 1 | 1 | 100.0 % |

### package `srk-lee-kesler-enthalpy` — 19/26 pass (73.1 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| Cp | 4 | 3 | 75.0 % |
| bubble_P | 6 | 5 | 83.3 % |
| dew_P | 7 | 4 | 57.1 % |
| rho_L | 4 | 2 | 50.0 % |
| rho_V | 4 | 4 | 100.0 % |
| vapor_comp | 1 | 1 | 100.0 % |

### package `srk-mathias-copeman` — 20/26 pass (76.9 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| Cp | 4 | 3 | 75.0 % |
| bubble_P | 6 | 6 | 100.0 % |
| dew_P | 7 | 4 | 57.1 % |
| rho_L | 4 | 2 | 50.0 % |
| rho_V | 4 | 4 | 100.0 % |
| vapor_comp | 1 | 1 | 100.0 % |

### package `srk-peneloux` — 19/26 pass (73.1 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| Cp | 4 | 1 | 25.0 % |
| bubble_P | 6 | 5 | 83.3 % |
| dew_P | 7 | 4 | 57.1 % |
| rho_L | 4 | 4 | 100.0 % |
| rho_V | 4 | 4 | 100.0 % |
| vapor_comp | 1 | 1 | 100.0 % |

### package `twu-pr` — 21/26 pass (80.8 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| Cp | 4 | 3 | 75.0 % |
| bubble_P | 6 | 6 | 100.0 % |
| dew_P | 7 | 4 | 57.1 % |
| rho_L | 4 | 3 | 75.0 % |
| rho_V | 4 | 4 | 100.0 % |
| vapor_comp | 1 | 1 | 100.0 % |

### package `twu-srk` — 20/26 pass (76.9 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| Cp | 4 | 3 | 75.0 % |
| bubble_P | 6 | 6 | 100.0 % |
| dew_P | 7 | 4 | 57.1 % |
| rho_L | 4 | 2 | 50.0 % |
| rho_V | 4 | 4 | 100.0 % |
| vapor_comp | 1 | 1 | 100.0 % |

### package `unifac_dortmund_ig` — 4/4 pass (100.0 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| bubble_P | 1 | 1 | 100.0 % |
| bubble_T | 1 | 1 | 100.0 % |
| vapor_comp | 2 | 2 | 100.0 % |

### package `unifac_ig` — 2/2 pass (100.0 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| bubble_T | 1 | 1 | 100.0 % |
| vapor_comp | 1 | 1 | 100.0 % |

### package `unifac_psrk_ig` — 4/4 pass (100.0 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| bubble_P | 1 | 1 | 100.0 % |
| bubble_T | 1 | 1 | 100.0 % |
| vapor_comp | 2 | 2 | 100.0 % |

### package `uniquac_ig` — 6/6 pass (100.0 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| bubble_P | 1 | 1 | 100.0 % |
| bubble_T | 2 | 2 | 100.0 % |
| vapor_comp | 3 | 3 | 100.0 % |

### package `vanlaar_ig` — 4/4 pass (100.0 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| bubble_P | 1 | 1 | 100.0 % |
| bubble_T | 1 | 1 | 100.0 % |
| vapor_comp | 2 | 2 | 100.0 % |

### package `vdw` — 11/26 pass (42.3 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| Cp | 4 | 0 | 0.0 % |
| bubble_P | 6 | 5 | 83.3 % |
| dew_P | 7 | 4 | 57.1 % |
| rho_L | 4 | 0 | 0.0 % |
| rho_V | 4 | 2 | 50.0 % |
| vapor_comp | 1 | 0 | 0.0 % |

### package `wilson_ig` — 6/6 pass (100.0 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| bubble_P | 1 | 1 | 100.0 % |
| bubble_T | 2 | 2 | 100.0 % |
| vapor_comp | 3 | 3 | 100.0 % |

### package `zudkevitch-joffe-rk` — 19/26 pass (73.1 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| Cp | 4 | 3 | 75.0 % |
| bubble_P | 6 | 5 | 83.3 % |
| dew_P | 7 | 4 | 57.1 % |
| rho_L | 4 | 2 | 50.0 % |
| rho_V | 4 | 4 | 100.0 % |
| vapor_comp | 1 | 1 | 100.0 % |

## Failing comparisons (396)

| case | package | property | expected | got | err | source |
| --- | --- | --- | --- | --- | --- | --- |
| vdw-ng-dew-morch-243.4K-0.30MPa | vdw | dew_P | 300000 | 8.16458e+06 | 26.2153 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| rk-ng-dew-morch-254.6K-0.68MPa | rk | dew_P | 680000 | 1.036e+07 | 14.2353 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| vdw-ng-dew-morch-254.6K-0.68MPa | vdw | dew_P | 680000 | 8.96451e+06 | 12.1831 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| rk-ng-dew-morch-260.8K-1.04MPa | rk | dew_P | 1.04e+06 | 1.09081e+07 | 9.48855 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| vdw-ng-dew-morch-260.8K-1.04MPa | vdw | dew_P | 1.04e+06 | 9.38871e+06 | 8.02761 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| rk-ng-dew-morch-243.4K-0.30MPa | rk | dew_P | 300000 | 1.05415e+06 | 2.51382 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| rk-pure-C1-125K | rk | Cp | 57.7411 | 88.1237 | 0.526185 | coolprop:CH4 |
| pure-H2O-614.7K | srk | Cp | 151.747 | 229.506 | 0.512425 | coolprop:Water |
| pure-H2O-614.7K | pr | Cp | 151.747 | 220.634 | 0.453959 | coolprop:Water |
| pure-H2O-614.7K | pr78 | Cp | 151.747 | 220.634 | 0.453959 | coolprop:Water |
| pure-H2O-600K | srk | Cp | 125.264 | 178.303 | 0.423422 | coolprop:Water |
| vdw-pure-CO2-265K | vdw | rho_L | 973.254 | 570.303 | 0.414025 | coolprop:CO2 |
| c1c3-294.26K-9.653MPa | srk | bubble_P | 9.653e+06 | 5.87349e+06 | 0.391538 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 294.26 K isotherm; retrieved 2026-10-20 |
| c1c3-294.26K-9.653MPa | pr | bubble_P | 9.653e+06 | 5.93886e+06 | 0.384765 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 294.26 K isotherm; retrieved 2026-10-20 |
| c1c3-294.26K-9.653MPa | pr78 | bubble_P | 9.653e+06 | 5.93886e+06 | 0.384765 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 294.26 K isotherm; retrieved 2026-10-20 |
| vdw-pure-nC4-280K | vdw | rho_L | 593.294 | 367.122 | 0.381214 | coolprop:n-Butane |
| vdw-pure-C3-300K | vdw | rho_L | 489.447 | 303.464 | 0.379987 | coolprop:Propane |
| pure-H2O-600K | pr | Cp | 125.264 | 171.879 | 0.372138 | coolprop:Water |
| pure-H2O-600K | pr78 | Cp | 125.264 | 171.879 | 0.372138 | coolprop:Water |
| prsv-ng-dew-morch-243.4K-0.30MPa | prsv | dew_P | 300000 | 411130 | 0.370433 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| prsv2-ng-dew-morch-243.4K-0.30MPa | prsv2 | dew_P | 300000 | 411130 | 0.370433 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| c1c3-327.59K-7.584MPa | srk | bubble_P | 7.584e+06 | 4.81796e+06 | 0.364721 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 327.59 K isotherm; retrieved 2026-10-20 |
| c1c3-327.59K-7.584MPa | pr | bubble_P | 7.584e+06 | 4.84006e+06 | 0.361806 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 327.59 K isotherm; retrieved 2026-10-20 |
| c1c3-327.59K-7.584MPa | pr78 | bubble_P | 7.584e+06 | 4.84006e+06 | 0.361806 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 327.59 K isotherm; retrieved 2026-10-20 |
| pure-C1-181K | srk | Cp | 124.139 | 168.599 | 0.358147 | coolprop:CH4 |
| pr-mathias-copeman-ng-dew-morch-243.4K-0.30MPa | pr-mathias-copeman | dew_P | 300000 | 406577 | 0.355256 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| pr-peneloux-ng-dew-morch-243.4K-0.30MPa | pr-peneloux | dew_P | 300000 | 406518 | 0.355061 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| sour-pr-ng-dew-morch-243.4K-0.30MPa | sour-pr | dew_P | 300000 | 406518 | 0.355061 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| pr-lee-kesler-enthalpy-ng-dew-morch-243.4K-0.30MPa | pr-lee-kesler-enthalpy | dew_P | 300000 | 406518 | 0.355061 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| ng-dew-morch-243.4K-0.30MPa | pr | dew_P | 300000 | 406518 | 0.355061 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| ng-dew-morch-243.4K-0.30MPa | pr78 | dew_P | 300000 | 406518 | 0.355061 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| pr-boston-mathias-ng-dew-morch-243.4K-0.30MPa | pr-boston-mathias | dew_P | 300000 | 406384 | 0.354613 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| pr-bm-ng-dew-morch-243.4K-0.30MPa | pr-bm | dew_P | 300000 | 406384 | 0.354613 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| pure-N2-119.9K | srk | Cp | 125.022 | 168.848 | 0.350538 | coolprop:Nitrogen |
| pure-H2O-614.7K | srk | rho_L | 605.554 | 394.072 | 0.349237 | coolprop:Water |
| pure-H2O-600K | srk | rho_L | 649.411 | 432.471 | 0.334057 | coolprop:Water |
| pure-CO2-288.9K | srk | Cp | 155.189 | 206.216 | 0.328801 | coolprop:CO2 |
| pure-C2-290K | srk | Cp | 152.189 | 200.921 | 0.320205 | coolprop:Ethane |
| vdw-pure-C1-125K | vdw | rho_L | 402.111 | 274.752 | 0.316724 | coolprop:CH4 |
| zudkevitch-joffe-rk-ng-dew-morch-243.4K-0.30MPa | zudkevitch-joffe-rk | dew_P | 300000 | 390931 | 0.303104 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| pure-H2S-354.4K | srk | Cp | 141.924 | 184.717 | 0.301517 | coolprop:H2S |
| pure-C1-181K | pr | Cp | 124.139 | 161.076 | 0.297547 | coolprop:CH4 |
| pure-C1-181K | pr78 | Cp | 124.139 | 161.076 | 0.297547 | coolprop:CH4 |
| twu-pr-ng-dew-morch-243.4K-0.30MPa | twu-pr | dew_P | 300000 | 387803 | 0.292678 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| pure-N2-119.9K | pr | Cp | 125.022 | 161.28 | 0.29001 | coolprop:Nitrogen |
| pure-N2-119.9K | pr78 | Cp | 125.022 | 161.28 | 0.29001 | coolprop:Nitrogen |
| pure-H2O-520K | srk | rho_L | 803.535 | 571.024 | 0.289359 | coolprop:Water |
| twu-srk-ng-dew-morch-243.4K-0.30MPa | twu-srk | dew_P | 300000 | 386167 | 0.287224 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| vdw-c1c3-294.26K-6.895MPa | vdw | bubble_P | 6.895e+06 | 4.94511e+06 | 0.282797 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 294.26 K isotherm; retrieved 2026-10-20 |
| pure-CO2-285K | srk | Cp | 137.895 | 176.26 | 0.278214 | coolprop:CO2 |
| pure-CO2-288.9K | pr | Cp | 155.189 | 198.288 | 0.277714 | coolprop:CO2 |
| pure-CO2-288.9K | pr78 | Cp | 155.189 | 198.288 | 0.277714 | coolprop:CO2 |
| pure-C2-290K | pr | Cp | 152.189 | 193.22 | 0.269605 | coolprop:Ethane |
| pure-C2-290K | pr78 | Cp | 152.189 | 193.22 | 0.269605 | coolprop:Ethane |
| pure-H2O-420K | srk | rho_L | 919.929 | 674.912 | 0.266344 | coolprop:Water |
| vdw-pure-C1-125K | vdw | Cp | 57.7411 | 42.3955 | 0.265766 | coolprop:CH4 |
| pure-C3-351.3K | srk | Cp | 191.089 | 241.865 | 0.265722 | coolprop:Propane |
| pure-H2O-614.7K | pr | rho_L | 605.554 | 444.727 | 0.265587 | coolprop:Water |
| pure-H2O-614.7K | pr78 | rho_L | 605.554 | 444.727 | 0.265587 | coolprop:Water |
| pure-C2-285K | srk | Cp | 132.286 | 167.068 | 0.262933 | coolprop:Ethane |
| srk-peneloux-ng-dew-morch-243.4K-0.30MPa | srk-peneloux | dew_P | 300000 | 377792 | 0.259308 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| sour-srk-ng-dew-morch-243.4K-0.30MPa | sour-srk | dew_P | 300000 | 377792 | 0.259308 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| kabadi-danner-srk-ng-dew-morch-243.4K-0.30MPa | kabadi-danner-srk | dew_P | 300000 | 377792 | 0.259308 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| srk-lee-kesler-enthalpy-ng-dew-morch-243.4K-0.30MPa | srk-lee-kesler-enthalpy | dew_P | 300000 | 377792 | 0.259308 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| ng-dew-morch-243.4K-0.30MPa | srk | dew_P | 300000 | 377792 | 0.259308 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| srk-mathias-copeman-ng-dew-morch-243.4K-0.30MPa | srk-mathias-copeman | dew_P | 300000 | 377757 | 0.25919 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| srk-boston-mathias-ng-dew-morch-243.4K-0.30MPa | srk-boston-mathias | dew_P | 300000 | 377630 | 0.258768 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| rks-bm-ng-dew-morch-243.4K-0.30MPa | rks-bm | dew_P | 300000 | 377630 | 0.258768 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| api-srk-ng-dew-morch-243.4K-0.30MPa | api-srk | dew_P | 300000 | 376555 | 0.255183 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| pure-H2O-323.5K | srk | rho_L | 987.838 | 741.661 | 0.249207 | coolprop:Water |
| pure-H2S-354.4K | pr | Cp | 141.924 | 176.987 | 0.247053 | coolprop:H2S |
| pure-H2S-354.4K | pr78 | Cp | 141.924 | 176.987 | 0.247053 | coolprop:H2S |
| pure-H2O-600K | pr | rho_L | 649.411 | 489.546 | 0.246169 | coolprop:Water |
| pure-H2O-600K | pr78 | rho_L | 649.411 | 489.546 | 0.246169 | coolprop:Water |
| vdw-pure-nC4-280K | vdw | Cp | 136.28 | 103.265 | 0.242257 | coolprop:n-Butane |
| pure-nC4-403.9K | srk | Cp | 236.805 | 293.525 | 0.23952 | coolprop:n-Butane |
| pure-H2O-520K | srk | Cp | 87.149 | 107.501 | 0.233533 | coolprop:Water |
| pure-H2S-345K | srk | Cp | 112.837 | 139.176 | 0.233421 | coolprop:H2S |
| pure-C1-172K | srk | Cp | 87.1299 | 107.453 | 0.233245 | coolprop:CH4 |
| prsv-ng-dew-morch-254.6K-0.68MPa | prsv | dew_P | 680000 | 838245 | 0.232713 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| prsv2-ng-dew-morch-254.6K-0.68MPa | prsv2 | dew_P | 680000 | 838245 | 0.232713 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| pure-CO2-285K | pr | Cp | 137.895 | 169.831 | 0.231591 | coolprop:CO2 |
| pure-CO2-285K | pr78 | Cp | 137.895 | 169.831 | 0.231591 | coolprop:CO2 |
| pure-C3-351.3K | pr | Cp | 191.089 | 234.044 | 0.224791 | coolprop:Propane |
| pure-C3-351.3K | pr78 | Cp | 191.089 | 234.044 | 0.224791 | coolprop:Propane |
| pr-mathias-copeman-ng-dew-morch-254.6K-0.68MPa | pr-mathias-copeman | dew_P | 680000 | 829293 | 0.219549 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| pr-peneloux-ng-dew-morch-254.6K-0.68MPa | pr-peneloux | dew_P | 680000 | 829096 | 0.219259 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| sour-pr-ng-dew-morch-254.6K-0.68MPa | sour-pr | dew_P | 680000 | 829096 | 0.219259 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| pr-lee-kesler-enthalpy-ng-dew-morch-254.6K-0.68MPa | pr-lee-kesler-enthalpy | dew_P | 680000 | 829096 | 0.219259 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| ng-dew-morch-254.6K-0.68MPa | pr | dew_P | 680000 | 829096 | 0.219259 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| ng-dew-morch-254.6K-0.68MPa | pr78 | dew_P | 680000 | 829096 | 0.219259 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| pr-boston-mathias-ng-dew-morch-254.6K-0.68MPa | pr-boston-mathias | dew_P | 680000 | 828676 | 0.218641 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| pr-bm-ng-dew-morch-254.6K-0.68MPa | pr-bm | dew_P | 680000 | 828676 | 0.218641 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| pure-C2-285K | pr | Cp | 132.286 | 161.185 | 0.218456 | coolprop:Ethane |
| pure-C2-285K | pr78 | Cp | 132.286 | 161.185 | 0.218456 | coolprop:Ethane |
| pure-nC4-403.9K | pr | Cp | 236.805 | 285.411 | 0.205254 | coolprop:n-Butane |
| pure-nC4-403.9K | pr78 | Cp | 236.805 | 285.411 | 0.205254 | coolprop:n-Butane |
| prsv-ng-dew-morch-260.8K-1.04MPa | prsv | dew_P | 1.04e+06 | 1.25191e+06 | 0.20376 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| prsv2-ng-dew-morch-260.8K-1.04MPa | prsv2 | dew_P | 1.04e+06 | 1.25191e+06 | 0.20376 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| pure-N2-112K | srk | Cp | 81.2659 | 97.1906 | 0.195958 | coolprop:Nitrogen |
| vdw-pure-C3-300K | vdw | Cp | 120.805 | 97.2117 | 0.195299 | coolprop:Propane |
| vdw-pure-CO2-265K | vdw | Cp | 103.056 | 83.02 | 0.194416 | coolprop:CO2 |
| pure-H2O-520K | pr | rho_L | 803.535 | 648.154 | 0.193371 | coolprop:Water |
| pure-H2O-520K | pr78 | rho_L | 803.535 | 648.154 | 0.193371 | coolprop:Water |
| pr-mathias-copeman-ng-dew-morch-260.8K-1.04MPa | pr-mathias-copeman | dew_P | 1.04e+06 | 1.23816e+06 | 0.190537 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| pr-peneloux-ng-dew-morch-260.8K-1.04MPa | pr-peneloux | dew_P | 1.04e+06 | 1.2378e+06 | 0.190196 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| sour-pr-ng-dew-morch-260.8K-1.04MPa | sour-pr | dew_P | 1.04e+06 | 1.2378e+06 | 0.190196 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| pr-lee-kesler-enthalpy-ng-dew-morch-260.8K-1.04MPa | pr-lee-kesler-enthalpy | dew_P | 1.04e+06 | 1.2378e+06 | 0.190196 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| ng-dew-morch-260.8K-1.04MPa | pr | dew_P | 1.04e+06 | 1.2378e+06 | 0.190196 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| ng-dew-morch-260.8K-1.04MPa | pr78 | dew_P | 1.04e+06 | 1.2378e+06 | 0.190196 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| pr-boston-mathias-ng-dew-morch-260.8K-1.04MPa | pr-boston-mathias | dew_P | 1.04e+06 | 1.23705e+06 | 0.189472 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| pr-bm-ng-dew-morch-260.8K-1.04MPa | pr-bm | dew_P | 1.04e+06 | 1.23705e+06 | 0.189472 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| pure-H2S-345K | pr | Cp | 112.837 | 133.856 | 0.186276 | coolprop:H2S |
| pure-H2S-345K | pr78 | Cp | 112.837 | 133.856 | 0.186276 | coolprop:H2S |
| meohh2o-312.91K-9.079kPa | nrtl | bubble_P | 9079 | 10747.1 | 0.183734 | literature:Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 312.91 K; DDB Explorer Edition data set 467; retrieved 2026-10-20 |
| pure-C1-172K | pr | Cp | 87.1299 | 103.117 | 0.183483 | coolprop:CH4 |
| pure-C1-172K | pr78 | Cp | 87.1299 | 103.117 | 0.183483 | coolprop:CH4 |
| pure-nC4-403.9K | srk | rho_L | 397.325 | 324.829 | 0.182461 | coolprop:n-Butane |
| pure-H2O-520K | pr | Cp | 87.149 | 102.925 | 0.181022 | coolprop:Water |
| pure-H2O-520K | pr78 | Cp | 87.149 | 102.925 | 0.181022 | coolprop:Water |
| pure-C3-340K | srk | Cp | 158.07 | 186.594 | 0.180451 | coolprop:Propane |
| twu-pr-ng-dew-morch-254.6K-0.68MPa | twu-pr | dew_P | 680000 | 802379 | 0.17997 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| zudkevitch-joffe-rk-ng-dew-morch-254.6K-0.68MPa | zudkevitch-joffe-rk | dew_P | 680000 | 798943 | 0.174917 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| pure-CO2-288.9K | srk | rho_L | 814.639 | 672.534 | 0.17444 | coolprop:CO2 |
| pure-MeOH-330K-nrtl | nrtl | Cp | 88.5047 | 73.1651 | 0.173319 | coolprop:Methanol |
| pure-H2O-420K | pr | rho_L | 919.929 | 762.594 | 0.17103 | coolprop:Water |
| pure-H2O-420K | pr78 | rho_L | 919.929 | 762.594 | 0.17103 | coolprop:Water |
| pure-C3-351.3K | srk | rho_L | 379.569 | 314.954 | 0.170233 | coolprop:Propane |
| slice-inlet-K-500psia-300K | srk | K | 5.1 | 5.96141 | 0.168903 | literature:DePriester (1953) Chem. Eng. Prog. Symp. Ser. 49(7), p. 42, high-T nomogram (as Fig. 10.14 in Felder & Rousseau), read at 500 psia / 80.33 F; retrieved 2026-10-20 |
| pure-H2O-420K | srk | Cp | 77.4472 | 90.3881 | 0.167094 | coolprop:Water |
| twu-srk-ng-dew-morch-254.6K-0.68MPa | twu-srk | dew_P | 680000 | 793289 | 0.166601 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| rk-pure-CO2-265K | rk | rho_L | 973.254 | 814.293 | 0.16333 | coolprop:CO2 |
| pure-CO2-285K | srk | rho_L | 847.046 | 709.912 | 0.161897 | coolprop:CO2 |
| vdw-c1c3-294.26K-6.895MPa | vdw | vapor_comp | 0.7497 | 0.588384 | 0.161316 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 294.26 K isotherm; retrieved 2026-10-20 |
| pure-C2-290K | srk | rho_L | 351.314 | 295.002 | 0.16029 | coolprop:Ethane |
| meohh2o-312.91K-13.012kPa | nrtl | bubble_P | 13012 | 15092.3 | 0.159878 | literature:Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 312.91 K; DDB Explorer Edition data set 467; retrieved 2026-10-20 |
| twu-pr-ng-dew-morch-260.8K-1.04MPa | twu-pr | dew_P | 1.04e+06 | 1.20473e+06 | 0.158392 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| pure-H2O-323.5K | pr | rho_L | 987.838 | 833.88 | 0.155853 | coolprop:Water |
| pure-H2O-323.5K | pr78 | rho_L | 987.838 | 833.88 | 0.155853 | coolprop:Water |
| pure-nC4-390K | srk | Cp | 200.774 | 231.664 | 0.153853 | coolprop:n-Butane |
| pure-nC4-390K | srk | rho_L | 433.172 | 367.728 | 0.151081 | coolprop:n-Butane |
| pure-H2O-323.5K | srk | Cp | 75.3335 | 86.6467 | 0.150175 | coolprop:Water |
| slice-inlet-K-500psia-300K | pr | K | 5.1 | 5.85698 | 0.148427 | literature:DePriester (1953) Chem. Eng. Prog. Symp. Ser. 49(7), p. 42, high-T nomogram (as Fig. 10.14 in Felder & Rousseau), read at 500 psia / 80.33 F; retrieved 2026-10-20 |
| slice-inlet-K-500psia-300K | pr78 | K | 5.1 | 5.85698 | 0.148427 | literature:DePriester (1953) Chem. Eng. Prog. Symp. Ser. 49(7), p. 42, high-T nomogram (as Fig. 10.14 in Felder & Rousseau), read at 500 psia / 80.33 F; retrieved 2026-10-20 |
| pure-C3-340K | pr | Cp | 158.07 | 181.435 | 0.14781 | coolprop:Propane |
| pure-C3-340K | pr78 | Cp | 158.07 | 181.435 | 0.14781 | coolprop:Propane |
| pure-N2-112K | pr | Cp | 81.2659 | 93.1676 | 0.146454 | coolprop:Nitrogen |
| pure-N2-112K | pr78 | Cp | 81.2659 | 93.1676 | 0.146454 | coolprop:Nitrogen |
| pure-C2-285K | srk | rho_L | 368.125 | 315.192 | 0.143792 | coolprop:Ethane |
| zudkevitch-joffe-rk-ng-dew-morch-260.8K-1.04MPa | zudkevitch-joffe-rk | dew_P | 1.04e+06 | 1.18794e+06 | 0.142246 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| pure-C3-340K | srk | rho_L | 411.774 | 353.492 | 0.141538 | coolprop:Propane |
| pure-C1-181K | srk | rho_L | 271.913 | 233.607 | 0.140876 | coolprop:CH4 |
| srk-peneloux-ng-dew-morch-254.6K-0.68MPa | srk-peneloux | dew_P | 680000 | 774165 | 0.138477 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| sour-srk-ng-dew-morch-254.6K-0.68MPa | sour-srk | dew_P | 680000 | 774165 | 0.138477 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| kabadi-danner-srk-ng-dew-morch-254.6K-0.68MPa | kabadi-danner-srk | dew_P | 680000 | 774165 | 0.138477 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| srk-lee-kesler-enthalpy-ng-dew-morch-254.6K-0.68MPa | srk-lee-kesler-enthalpy | dew_P | 680000 | 774165 | 0.138477 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| ng-dew-morch-254.6K-0.68MPa | srk | dew_P | 680000 | 774165 | 0.138477 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| srk-mathias-copeman-ng-dew-morch-254.6K-0.68MPa | srk-mathias-copeman | dew_P | 680000 | 774020 | 0.138265 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| srk-boston-mathias-ng-dew-morch-254.6K-0.68MPa | srk-boston-mathias | dew_P | 680000 | 773659 | 0.137733 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| rks-bm-ng-dew-morch-254.6K-0.68MPa | rks-bm | dew_P | 680000 | 773659 | 0.137733 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| twu-srk-ng-dew-morch-260.8K-1.04MPa | twu-srk | dew_P | 1.04e+06 | 1.18184e+06 | 0.136384 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| api-srk-ng-dew-morch-254.6K-0.68MPa | api-srk | dew_P | 680000 | 771741 | 0.134913 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| pure-H2S-354.4K | srk | rho_L | 583.871 | 505.336 | 0.134507 | coolprop:H2S |
| pure-C1-155K | srk | Cp | 67.6129 | 76.6185 | 0.133194 | coolprop:CH4 |
| pure-N2-63.2K | pr | rho_L | 867.021 | 981.868 | 0.132461 | coolprop:Nitrogen |
| pure-N2-63.2K | pr78 | rho_L | 867.021 | 981.868 | 0.132461 | coolprop:Nitrogen |
| pure-N2-119.9K | srk | rho_L | 524.673 | 456.965 | 0.129048 | coolprop:Nitrogen |
| pure-N2-82K | pr | rho_L | 784.556 | 885.48 | 0.128639 | coolprop:Nitrogen |
| pure-N2-82K | pr78 | rho_L | 784.556 | 885.48 | 0.128639 | coolprop:Nitrogen |
| pure-nC4-390K | pr | Cp | 200.774 | 226.427 | 0.127768 | coolprop:n-Butane |
| pure-nC4-390K | pr78 | Cp | 200.774 | 226.427 | 0.127768 | coolprop:n-Butane |
| pure-C1-95.3K | pr | rho_L | 445.301 | 502.166 | 0.1277 | coolprop:CH4 |
| pure-C1-95.3K | pr78 | rho_L | 445.301 | 502.166 | 0.1277 | coolprop:CH4 |
| api-srk-pure-CO2-265K | api-srk | Cp | 103.056 | 115.742 | 0.123101 | coolprop:CO2 |
| srk-peneloux-pure-CO2-265K | srk-peneloux | Cp | 103.056 | 115.671 | 0.12241 | coolprop:CO2 |
| pure-CO2-265K | srk | Cp | 103.056 | 115.671 | 0.12241 | coolprop:CO2 |
| srk-boston-mathias-pure-CO2-265K | srk-boston-mathias | Cp | 103.056 | 115.671 | 0.12241 | coolprop:CO2 |
| sour-srk-pure-CO2-265K | sour-srk | Cp | 103.056 | 115.671 | 0.12241 | coolprop:CO2 |
| kabadi-danner-srk-pure-CO2-265K | kabadi-danner-srk | Cp | 103.056 | 115.671 | 0.12241 | coolprop:CO2 |
| rks-bm-pure-CO2-265K | rks-bm | Cp | 103.056 | 115.671 | 0.12241 | coolprop:CO2 |
| pure-H2O-370K-nrtl | nrtl | Cp | 75.8833 | 66.6483 | 0.1217 | coolprop:Water |
| pure-H2S-187.8K | pr | Cp | 68.8292 | 60.4703 | 0.121444 | coolprop:H2S |
| pure-H2S-187.8K | pr78 | Cp | 68.8292 | 60.4703 | 0.121444 | coolprop:H2S |
| prsv-pure-C1-125K | prsv | rho_L | 402.111 | 449.914 | 0.118882 | coolprop:CH4 |
| prsv2-pure-C1-125K | prsv2 | rho_L | 402.111 | 449.914 | 0.118882 | coolprop:CH4 |
| pr-mathias-copeman-pure-C1-125K | pr-mathias-copeman | rho_L | 402.111 | 449.888 | 0.118816 | coolprop:CH4 |
| twu-pr-pure-C1-125K | twu-pr | rho_L | 402.111 | 449.803 | 0.118606 | coolprop:CH4 |
| pure-CO2-265K | srk | rho_L | 973.254 | 857.989 | 0.118433 | coolprop:CO2 |
| srk-boston-mathias-pure-CO2-265K | srk-boston-mathias | rho_L | 973.254 | 857.989 | 0.118433 | coolprop:CO2 |
| sour-srk-pure-CO2-265K | sour-srk | rho_L | 973.254 | 857.989 | 0.118433 | coolprop:CO2 |
| kabadi-danner-srk-pure-CO2-265K | kabadi-danner-srk | rho_L | 973.254 | 857.989 | 0.118433 | coolprop:CO2 |
| rks-bm-pure-CO2-265K | rks-bm | rho_L | 973.254 | 857.989 | 0.118433 | coolprop:CO2 |
| srk-lee-kesler-enthalpy-pure-CO2-265K | srk-lee-kesler-enthalpy | rho_L | 973.254 | 857.989 | 0.118433 | coolprop:CO2 |
| api-srk-pure-CO2-265K | api-srk | rho_L | 973.254 | 858.135 | 0.118283 | coolprop:CO2 |
| pure-C1-125K | pr | rho_L | 402.111 | 449.652 | 0.11823 | coolprop:CH4 |
| pure-C1-125K | pr78 | rho_L | 402.111 | 449.652 | 0.11823 | coolprop:CH4 |
| pr-boston-mathias-pure-C1-125K | pr-boston-mathias | rho_L | 402.111 | 449.652 | 0.11823 | coolprop:CH4 |
| sour-pr-pure-C1-125K | sour-pr | rho_L | 402.111 | 449.652 | 0.11823 | coolprop:CH4 |
| pr-bm-pure-C1-125K | pr-bm | rho_L | 402.111 | 449.652 | 0.11823 | coolprop:CH4 |
| pr-lee-kesler-enthalpy-pure-C1-125K | pr-lee-kesler-enthalpy | rho_L | 402.111 | 449.652 | 0.11823 | coolprop:CH4 |
| srk-mathias-copeman-pure-CO2-265K | srk-mathias-copeman | rho_L | 973.254 | 859.249 | 0.117138 | coolprop:CO2 |
| twu-srk-pure-CO2-265K | twu-srk | rho_L | 973.254 | 859.886 | 0.116484 | coolprop:CO2 |
| meohh2o-312.91K-16.319kPa | nrtl | bubble_P | 16319 | 18215.9 | 0.116242 | literature:Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 312.91 K; DDB Explorer Edition data set 467; retrieved 2026-10-20 |
| zudkevitch-joffe-rk-pure-CO2-265K | zudkevitch-joffe-rk | rho_L | 973.254 | 860.146 | 0.116216 | coolprop:CO2 |
| pure-H2S-345K | srk | rho_L | 628.082 | 556.936 | 0.113275 | coolprop:H2S |
| pure-MeOH-305K-nrtl | nrtl | Cp | 82.6135 | 73.3846 | 0.111712 | coolprop:Methanol |
| rk-pure-C3-300K | rk | rho_L | 489.447 | 435.239 | 0.110755 | coolprop:Propane |
| slice-inlet-K-500psia-300K | pr | K | 1.17 | 1.04263 | 0.108863 | literature:DePriester (1953) Chem. Eng. Prog. Symp. Ser. 49(7), p. 42, high-T nomogram (as Fig. 10.14 in Felder & Rousseau), read at 500 psia / 80.33 F; retrieved 2026-10-20 |
| slice-inlet-K-500psia-300K | pr78 | K | 1.17 | 1.04263 | 0.108863 | literature:DePriester (1953) Chem. Eng. Prog. Symp. Ser. 49(7), p. 42, high-T nomogram (as Fig. 10.14 in Felder & Rousseau), read at 500 psia / 80.33 F; retrieved 2026-10-20 |
| srk-peneloux-ng-dew-morch-260.8K-1.04MPa | srk-peneloux | dew_P | 1.04e+06 | 1.15189e+06 | 0.107589 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| sour-srk-ng-dew-morch-260.8K-1.04MPa | sour-srk | dew_P | 1.04e+06 | 1.15189e+06 | 0.107589 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| kabadi-danner-srk-ng-dew-morch-260.8K-1.04MPa | kabadi-danner-srk | dew_P | 1.04e+06 | 1.15189e+06 | 0.107589 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| srk-lee-kesler-enthalpy-ng-dew-morch-260.8K-1.04MPa | srk-lee-kesler-enthalpy | dew_P | 1.04e+06 | 1.15189e+06 | 0.107589 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| ng-dew-morch-260.8K-1.04MPa | srk | dew_P | 1.04e+06 | 1.15189e+06 | 0.107589 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| srk-mathias-copeman-ng-dew-morch-260.8K-1.04MPa | srk-mathias-copeman | dew_P | 1.04e+06 | 1.15151e+06 | 0.10722 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| srk-boston-mathias-ng-dew-morch-260.8K-1.04MPa | srk-boston-mathias | dew_P | 1.04e+06 | 1.15101e+06 | 0.106741 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| rks-bm-ng-dew-morch-260.8K-1.04MPa | rks-bm | dew_P | 1.04e+06 | 1.15101e+06 | 0.106741 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| pure-H2O-614.7K | srk | rho_V | 95.5877 | 85.4882 | 0.105657 | coolprop:Water |
| pure-H2O-420K | pr | Cp | 77.4472 | 85.5571 | 0.104716 | coolprop:Water |
| pure-H2O-420K | pr78 | Cp | 77.4472 | 85.5571 | 0.104716 | coolprop:Water |
| api-srk-ng-dew-morch-260.8K-1.04MPa | api-srk | dew_P | 1.04e+06 | 1.14824e+06 | 0.104073 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| meohh2o-322.91K-15.932kPa | nrtl | bubble_P | 15932 | 17553.7 | 0.101786 | literature:Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 322.91 K; DDB Explorer Edition data set 468; retrieved 2026-10-20 |
| pure-C2-250K | srk | Cp | 90.0242 | 99.0394 | 0.100142 | coolprop:Ethane |
| pure-nC4-350K | srk | rho_L | 505.177 | 454.822 | 0.0996774 | coolprop:n-Butane |
| rk-pure-C3-300K | rk | Cp | 120.805 | 132.831 | 0.0995539 | coolprop:Propane |
| pure-C1-172K | srk | rho_L | 304.559 | 274.35 | 0.0991902 | coolprop:CH4 |
| slice-inlet-K-500psia-300K | srk | K | 1.17 | 1.05444 | 0.098766 | literature:DePriester (1953) Chem. Eng. Prog. Symp. Ser. 49(7), p. 42, high-T nomogram (as Fig. 10.14 in Felder & Rousseau), read at 500 psia / 80.33 F; retrieved 2026-10-20 |
| c1c3-327.59K-7.584MPa | pr | vapor_comp | 0.5546 | 0.456645 | 0.0979547 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 327.59 K isotherm; retrieved 2026-10-20 |
| c1c3-327.59K-7.584MPa | pr78 | vapor_comp | 0.5546 | 0.456645 | 0.0979547 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 327.59 K isotherm; retrieved 2026-10-20 |
| pure-N2-100K | pr | rho_L | 689.353 | 756.188 | 0.0969532 | coolprop:Nitrogen |
| pure-N2-100K | pr78 | rho_L | 689.353 | 756.188 | 0.0969532 | coolprop:Nitrogen |
| pure-N2-100K | srk | Cp | 64.9347 | 71.168 | 0.0959925 | coolprop:Nitrogen |
| c1c3-327.59K-7.584MPa | srk | vapor_comp | 0.5546 | 0.45901 | 0.0955899 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 327.59 K isotherm; retrieved 2026-10-20 |
| meohh2o-312.91K-9.079kPa | nrtl | vapor_comp | 0.2559 | 0.350953 | 0.0950533 | literature:Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 312.91 K; DDB Explorer Edition data set 467; retrieved 2026-10-20 |
| meohh2o-322.91K-26.131kPa | nrtl | bubble_P | 26131 | 28604.1 | 0.0946409 | literature:Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 322.91 K; DDB Explorer Edition data set 468; retrieved 2026-10-20 |
| pure-H2S-240K | pr | rho_L | 899.829 | 984.26 | 0.0938308 | coolprop:H2S |
| pure-H2S-240K | pr78 | rho_L | 899.829 | 984.26 | 0.0938308 | coolprop:H2S |
| rk-pure-nC4-280K | rk | rho_L | 593.294 | 538.199 | 0.0928631 | coolprop:n-Butane |
| rk-pure-nC4-280K | rk | Cp | 136.28 | 148.75 | 0.0915054 | coolprop:n-Butane |
| vdw-pure-CO2-265K | vdw | rho_V | 75.4708 | 68.5717 | 0.0914138 | coolprop:CO2 |
| pure-CO2-240K | srk | rho_L | 1088.87 | 990.451 | 0.090386 | coolprop:CO2 |
| pure-H2S-187.8K | pr | rho_L | 992.142 | 1080.56 | 0.0891218 | coolprop:H2S |
| pure-H2S-187.8K | pr78 | rho_L | 992.142 | 1080.56 | 0.0891218 | coolprop:H2S |
| pure-CO2-216.7K | pr | Cp | 85.9712 | 78.3254 | 0.0889347 | coolprop:CO2 |
| pure-CO2-216.7K | pr78 | Cp | 85.9712 | 78.3254 | 0.0889347 | coolprop:CO2 |
| pure-H2O-600K | srk | rho_V | 72.8423 | 66.4763 | 0.0873949 | coolprop:Water |
| zudkevitch-joffe-rk-pure-CO2-265K | zudkevitch-joffe-rk | Cp | 103.056 | 111.975 | 0.0865463 | coolprop:CO2 |
| twu-pr-pure-CO2-265K | twu-pr | Cp | 103.056 | 111.963 | 0.0864371 | coolprop:CO2 |
| twu-srk-pure-CO2-265K | twu-srk | Cp | 103.056 | 111.892 | 0.0857434 | coolprop:CO2 |
| pure-C2-200K | pr | rho_L | 523.977 | 568.762 | 0.0854708 | coolprop:Ethane |
| pure-C2-200K | pr78 | rho_L | 523.977 | 568.762 | 0.0854708 | coolprop:Ethane |
| pure-C2-152.7K | pr | rho_L | 582.054 | 631.691 | 0.0852782 | coolprop:Ethane |
| pure-C2-152.7K | pr78 | rho_L | 582.054 | 631.691 | 0.0852782 | coolprop:Ethane |
| pure-C3-300K | srk | rho_L | 489.447 | 448.204 | 0.0842657 | coolprop:Propane |
| srk-boston-mathias-pure-C3-300K | srk-boston-mathias | rho_L | 489.447 | 448.204 | 0.0842657 | coolprop:Propane |
| sour-srk-pure-C3-300K | sour-srk | rho_L | 489.447 | 448.204 | 0.0842657 | coolprop:Propane |
| kabadi-danner-srk-pure-C3-300K | kabadi-danner-srk | rho_L | 489.447 | 448.204 | 0.0842657 | coolprop:Propane |
| rks-bm-pure-C3-300K | rks-bm | rho_L | 489.447 | 448.204 | 0.0842657 | coolprop:Propane |
| srk-lee-kesler-enthalpy-pure-C3-300K | srk-lee-kesler-enthalpy | rho_L | 489.447 | 448.204 | 0.0842657 | coolprop:Propane |
| api-srk-pure-C3-300K | api-srk | rho_L | 489.447 | 448.355 | 0.0839575 | coolprop:Propane |
| pure-C1-155K | pr | Cp | 67.6129 | 73.2856 | 0.0839003 | coolprop:CH4 |
| pure-C1-155K | pr78 | Cp | 67.6129 | 73.2856 | 0.0839003 | coolprop:CH4 |
| twu-srk-pure-C3-300K | twu-srk | rho_L | 489.447 | 448.891 | 0.082861 | coolprop:Propane |
| pure-H2S-300K | srk | Cp | 77.0817 | 83.4648 | 0.0828093 | coolprop:H2S |
| pure-N2-63.2K | pr | Cp | 56.0355 | 51.4237 | 0.0823021 | coolprop:Nitrogen |
| pure-N2-63.2K | pr78 | Cp | 56.0355 | 51.4237 | 0.0823021 | coolprop:Nitrogen |
| zudkevitch-joffe-rk-pure-C3-300K | zudkevitch-joffe-rk | rho_L | 489.447 | 449.204 | 0.0822229 | coolprop:Propane |
| srk-mathias-copeman-pure-C3-300K | srk-mathias-copeman | rho_L | 489.447 | 449.628 | 0.0813561 | coolprop:Propane |
| pr-peneloux-pure-CO2-265K | pr-peneloux | Cp | 103.056 | 111.409 | 0.0810613 | coolprop:CO2 |
| pure-CO2-265K | pr | Cp | 103.056 | 111.409 | 0.0810613 | coolprop:CO2 |
| pure-CO2-265K | pr78 | Cp | 103.056 | 111.409 | 0.0810613 | coolprop:CO2 |
| pr-boston-mathias-pure-CO2-265K | pr-boston-mathias | Cp | 103.056 | 111.409 | 0.0810613 | coolprop:CO2 |
| sour-pr-pure-CO2-265K | sour-pr | Cp | 103.056 | 111.409 | 0.0810613 | coolprop:CO2 |
| pr-bm-pure-CO2-265K | pr-bm | Cp | 103.056 | 111.409 | 0.0810613 | coolprop:CO2 |
| pr-mathias-copeman-pure-CO2-265K | pr-mathias-copeman | Cp | 103.056 | 111.333 | 0.0803195 | coolprop:CO2 |
| prsv-pure-CO2-265K | prsv | Cp | 103.056 | 111.252 | 0.0795349 | coolprop:CO2 |
| prsv2-pure-CO2-265K | prsv2 | Cp | 103.056 | 111.252 | 0.0795349 | coolprop:CO2 |
| pure-H2O-323.5K | pr | Cp | 75.3335 | 81.2495 | 0.0785313 | coolprop:Water |
| pure-H2O-323.5K | pr78 | Cp | 75.3335 | 81.2495 | 0.0785313 | coolprop:Water |
| rk-c1c3-294.26K-6.895MPa | rk | bubble_P | 6.895e+06 | 6.3692e+06 | 0.0762584 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 294.26 K isotherm; retrieved 2026-10-20 |
| pure-C3-184.9K | pr | Cp | 91.8478 | 84.9224 | 0.0754009 | coolprop:Propane |
| pure-C3-184.9K | pr78 | Cp | 91.8478 | 84.9224 | 0.0754009 | coolprop:Propane |
| api-srk-pure-C1-125K | api-srk | Cp | 57.7411 | 61.9476 | 0.0728507 | coolprop:CH4 |
| pr-lee-kesler-enthalpy-pure-CO2-265K | pr-lee-kesler-enthalpy | Cp | 103.056 | 95.6672 | 0.0716929 | coolprop:CO2 |
| srk-lee-kesler-enthalpy-pure-CO2-265K | srk-lee-kesler-enthalpy | Cp | 103.056 | 95.6672 | 0.0716929 | coolprop:CO2 |
| srk-mathias-copeman-pure-CO2-265K | srk-mathias-copeman | Cp | 103.056 | 110.429 | 0.0715475 | coolprop:CO2 |
| pure-H2O-340K-nrtl | nrtl | Cp | 75.4562 | 70.2529 | 0.0689572 | coolprop:Water |
| pure-C1-125K | srk | Cp | 57.7411 | 61.7209 | 0.0689238 | coolprop:CH4 |
| srk-peneloux-pure-C1-125K | srk-peneloux | Cp | 57.7411 | 61.7209 | 0.0689238 | coolprop:CH4 |
| sour-srk-pure-C1-125K | sour-srk | Cp | 57.7411 | 61.7209 | 0.0689238 | coolprop:CH4 |
| kabadi-danner-srk-pure-C1-125K | kabadi-danner-srk | Cp | 57.7411 | 61.7209 | 0.0689238 | coolprop:CH4 |
| srk-boston-mathias-pure-C1-125K | srk-boston-mathias | Cp | 57.7411 | 61.7209 | 0.0689238 | coolprop:CH4 |
| rks-bm-pure-C1-125K | rks-bm | Cp | 57.7411 | 61.7209 | 0.0689238 | coolprop:CH4 |
| api-srk-pure-C3-300K | api-srk | Cp | 120.805 | 129.067 | 0.0683894 | coolprop:Propane |
| pure-H2O-614.7K | pr | rho_V | 95.5877 | 89.0623 | 0.0682662 | coolprop:Water |
| pure-H2O-614.7K | pr78 | rho_V | 95.5877 | 89.0623 | 0.0682662 | coolprop:Water |
| srk-peneloux-pure-C3-300K | srk-peneloux | Cp | 120.805 | 128.942 | 0.0673599 | coolprop:Propane |
| srk-boston-mathias-pure-C3-300K | srk-boston-mathias | Cp | 120.805 | 128.942 | 0.0673599 | coolprop:Propane |
| rks-bm-pure-C3-300K | rks-bm | Cp | 120.805 | 128.942 | 0.0673599 | coolprop:Propane |
| pure-C3-300K | srk | Cp | 120.805 | 128.942 | 0.0673599 | coolprop:Propane |
| sour-srk-pure-C3-300K | sour-srk | Cp | 120.805 | 128.942 | 0.0673599 | coolprop:Propane |
| kabadi-danner-srk-pure-C3-300K | kabadi-danner-srk | Cp | 120.805 | 128.942 | 0.0673599 | coolprop:Propane |
| meohh2o-97.99kPa-353.25K | nrtl | vapor_comp | 0.568 | 0.501294 | 0.0667056 | literature:Bennett (1929) J. Chem. Educ. 6, pp. 1544-1549, isobaric 97.99 kPa; DDB Explorer Edition data set 466; retrieved 2026-10-20 |
| pure-H2S-187.8K | srk | Cp | 68.8292 | 64.4186 | 0.0640809 | coolprop:H2S |
| pure-nC4-350K | srk | Cp | 163.885 | 174.284 | 0.0634523 | coolprop:n-Butane |
| meohh2o-312.91K-20.705kPa | nrtl | bubble_P | 20705 | 22016.4 | 0.0633373 | literature:Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 312.91 K; DDB Explorer Edition data set 467; retrieved 2026-10-20 |
| vdw-pure-C3-300K | vdw | rho_V | 21.6295 | 20.2625 | 0.0632025 | coolprop:Propane |
| meohh2o-322.91K-40.850kPa | nrtl | bubble_P | 40850 | 43428.3 | 0.0631156 | literature:Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 322.91 K; DDB Explorer Edition data set 468; retrieved 2026-10-20 |
| pure-C2-152.7K | pr | Cp | 70.3296 | 65.9027 | 0.0629441 | coolprop:Ethane |
| pure-C2-152.7K | pr78 | Cp | 70.3296 | 65.9027 | 0.0629441 | coolprop:Ethane |
| pure-nC4-212.6K | pr | Cp | 121.621 | 114.033 | 0.0623892 | coolprop:n-Butane |
| pure-nC4-212.6K | pr78 | Cp | 121.621 | 114.033 | 0.0623892 | coolprop:n-Butane |
| meohh2o-312.91K-23.385kPa | nrtl | bubble_P | 23385 | 24833.8 | 0.0619549 | literature:Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 312.91 K; DDB Explorer Edition data set 467; retrieved 2026-10-20 |
| meohh2o-322.91K-15.932kPa | nrtl | vapor_comp | 0.2741 | 0.334853 | 0.0607532 | literature:Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 322.91 K; DDB Explorer Edition data set 468; retrieved 2026-10-20 |
| pure-C2-250K | pr | Cp | 90.0242 | 95.4911 | 0.0607269 | coolprop:Ethane |
| pure-C2-250K | pr78 | Cp | 90.0242 | 95.4911 | 0.0607269 | coolprop:Ethane |
| meohh2o-97.99kPa-365.45K | nrtl | vapor_comp | 0.227 | 0.166878 | 0.0601223 | literature:Bennett (1929) J. Chem. Educ. 6, pp. 1544-1549, isobaric 97.99 kPa; DDB Explorer Edition data set 466; retrieved 2026-10-20 |
| pure-H2O-600K | pr | rho_V | 72.8423 | 68.6719 | 0.0572533 | coolprop:Water |
| pure-H2O-600K | pr78 | rho_V | 72.8423 | 68.6719 | 0.0572533 | coolprop:Water |
| meohh2o-322.91K-31.544kPa | nrtl | bubble_P | 31544 | 33347.3 | 0.0571669 | literature:Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 322.91 K; DDB Explorer Edition data set 468; retrieved 2026-10-20 |
| meohh2o-322.91K-46.450kPa | nrtl | bubble_P | 46450 | 49105.1 | 0.0571601 | literature:Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 322.91 K; DDB Explorer Edition data set 468; retrieved 2026-10-20 |
| rk-pure-CO2-265K | rk | Cp | 103.056 | 108.903 | 0.0567427 | coolprop:CO2 |
| zudkevitch-joffe-rk-c1c3-294.26K-6.895MPa | zudkevitch-joffe-rk | bubble_P | 6.895e+06 | 6.51215e+06 | 0.0555254 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 294.26 K isotherm; retrieved 2026-10-20 |
| pure-C1-95.3K | srk | Cp | 54.3155 | 57.3174 | 0.0552677 | coolprop:CH4 |
| pure-H2S-240K | pr | Cp | 68.4609 | 64.6799 | 0.0552282 | coolprop:H2S |
| pure-H2S-240K | pr78 | Cp | 68.4609 | 64.6799 | 0.0552282 | coolprop:H2S |
| meohh2o-97.99kPa-349.05K | nrtl | vapor_comp | 0.68 | 0.627719 | 0.0522811 | literature:Bennett (1929) J. Chem. Educ. 6, pp. 1544-1549, isobaric 97.99 kPa; DDB Explorer Edition data set 466; retrieved 2026-10-20 |
| meohh2o-312.91K-13.012kPa | nrtl | vapor_comp | 0.6214 | 0.570676 | 0.0507236 | literature:Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 312.91 K; DDB Explorer Edition data set 467; retrieved 2026-10-20 |
| meohh2o-97.99kPa-360.65K | nrtl | vapor_comp | 0.391 | 0.341179 | 0.049821 | literature:Bennett (1929) J. Chem. Educ. 6, pp. 1544-1549, isobaric 97.99 kPa; DDB Explorer Edition data set 466; retrieved 2026-10-20 |
| meohh2o-312.91K-27.518kPa | nrtl | bubble_P | 27518 | 28779.4 | 0.0458403 | literature:Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 312.91 K; DDB Explorer Edition data set 467; retrieved 2026-10-20 |
| meohh2o-312.91K-20.705kPa | nrtl | vapor_comp | 0.8053 | 0.759733 | 0.0455667 | literature:Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 312.91 K; DDB Explorer Edition data set 467; retrieved 2026-10-20 |
| srk-boston-mathias-c1co2-277.15K-5.97MPa | srk-boston-mathias | bubble_P | 5.97e+06 | 5.70042e+06 | 0.0451553 | literature:Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20 |
| rks-bm-c1co2-277.15K-5.97MPa | rks-bm | bubble_P | 5.97e+06 | 5.70042e+06 | 0.0451553 | literature:Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20 |
| srk-boston-mathias-c1c3-294.26K-6.895MPa | srk-boston-mathias | bubble_P | 6.895e+06 | 6.59772e+06 | 0.0431157 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 294.26 K isotherm; retrieved 2026-10-20 |
| rks-bm-c1c3-294.26K-6.895MPa | rks-bm | bubble_P | 6.895e+06 | 6.59772e+06 | 0.0431157 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 294.26 K isotherm; retrieved 2026-10-20 |
| c1c3-277.59K-1.724MPa | pr | bubble_P | 1.724e+06 | 1.65127e+06 | 0.0421879 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 270, 277.59 K isotherm; retrieved 2026-10-20 |
| c1c3-277.59K-1.724MPa | pr78 | bubble_P | 1.724e+06 | 1.65127e+06 | 0.0421879 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 270, 277.59 K isotherm; retrieved 2026-10-20 |
| c1c3-327.59K-5.861MPa | srk | bubble_P | 5.861e+06 | 5.61512e+06 | 0.0419517 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 327.59 K isotherm; retrieved 2026-10-20 |
| meohh2o-97.99kPa-369.65K | nrtl | vapor_comp | 0.103 | 0.0615315 | 0.0414685 | literature:Bennett (1929) J. Chem. Educ. 6, pp. 1544-1549, isobaric 97.99 kPa; DDB Explorer Edition data set 466; retrieved 2026-10-20 |
| c1c3-327.59K-5.861MPa | pr | bubble_P | 5.861e+06 | 5.62072e+06 | 0.0409961 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 327.59 K isotherm; retrieved 2026-10-20 |
| c1c3-327.59K-5.861MPa | pr78 | bubble_P | 5.861e+06 | 5.62072e+06 | 0.0409961 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 327.59 K isotherm; retrieved 2026-10-20 |
| pure-H2O-520K | srk | rho_V | 18.9001 | 18.1349 | 0.0404873 | coolprop:Water |
| c1c3-327.59K-7.239MPa | pr | vapor_comp | 0.5532 | 0.513071 | 0.040129 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 327.59 K isotherm; retrieved 2026-10-20 |
| c1c3-327.59K-7.239MPa | pr78 | vapor_comp | 0.5532 | 0.513071 | 0.040129 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 327.59 K isotherm; retrieved 2026-10-20 |
| pure-H2S-354.4K | srk | rho_V | 133.989 | 128.7 | 0.0394728 | coolprop:H2S |
| pure-nC4-403.9K | srk | rho_V | 80.697 | 77.5239 | 0.0393202 | coolprop:n-Butane |
| rk-pure-CO2-265K | rk | rho_V | 75.4708 | 72.5521 | 0.0386723 | coolprop:CO2 |
| c1c3-327.59K-7.239MPa | pr | bubble_P | 7.239e+06 | 6.95919e+06 | 0.0386531 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 327.59 K isotherm; retrieved 2026-10-20 |
| c1c3-327.59K-7.239MPa | pr78 | bubble_P | 7.239e+06 | 6.95919e+06 | 0.0386531 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 327.59 K isotherm; retrieved 2026-10-20 |
| c1c3-327.59K-7.239MPa | srk | bubble_P | 7.239e+06 | 6.96085e+06 | 0.0384241 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 327.59 K isotherm; retrieved 2026-10-20 |
| pr-boston-mathias-c1co2-277.15K-5.97MPa | pr-boston-mathias | bubble_P | 5.97e+06 | 5.7503e+06 | 0.0368013 | literature:Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20 |
| pr-bm-c1co2-277.15K-5.97MPa | pr-bm | bubble_P | 5.97e+06 | 5.7503e+06 | 0.0368013 | literature:Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20 |
| meohh2o-312.91K-32.571kPa | nrtl | bubble_P | 32571 | 33760.7 | 0.0365274 | literature:Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 312.91 K; DDB Explorer Edition data set 467; retrieved 2026-10-20 |
| c1c3-327.59K-4.482MPa | pr | bubble_P | 4.482e+06 | 4.3208e+06 | 0.0359663 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 327.59 K isotherm; retrieved 2026-10-20 |
| c1c3-327.59K-4.482MPa | pr78 | bubble_P | 4.482e+06 | 4.3208e+06 | 0.0359663 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 327.59 K isotherm; retrieved 2026-10-20 |
| c1c3-327.59K-4.482MPa | srk | bubble_P | 4.482e+06 | 4.32193e+06 | 0.0357143 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 327.59 K isotherm; retrieved 2026-10-20 |
| meohh2o-322.91K-31.544kPa | nrtl | vapor_comp | 0.758 | 0.723318 | 0.0346816 | literature:Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 322.91 K; DDB Explorer Edition data set 468; retrieved 2026-10-20 |
| c1co2-283.15K-7.24MPa | srk | bubble_P | 7.24e+06 | 6.99089e+06 | 0.0344076 | literature:Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20 |
| c1c3-294.26K-8.963MPa | pr | vapor_comp | 0.7561 | 0.721745 | 0.0343551 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 294.26 K isotherm; retrieved 2026-10-20 |
| c1c3-294.26K-8.963MPa | pr78 | vapor_comp | 0.7561 | 0.721745 | 0.0343551 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 294.26 K isotherm; retrieved 2026-10-20 |
| c1c3-277.59K-2.758MPa | pr | bubble_P | 2.758e+06 | 2.66404e+06 | 0.0340676 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 270, 277.59 K isotherm; retrieved 2026-10-20 |
| c1c3-277.59K-2.758MPa | pr78 | bubble_P | 2.758e+06 | 2.66404e+06 | 0.0340676 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 270, 277.59 K isotherm; retrieved 2026-10-20 |
| c1co2-277.15K-4.69MPa | pr | bubble_P | 4.69e+06 | 4.53373e+06 | 0.03332 | literature:Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20 |
| c1co2-277.15K-4.69MPa | pr78 | bubble_P | 4.69e+06 | 4.53373e+06 | 0.03332 | literature:Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20 |
| meohh2o-322.91K-52.142kPa | nrtl | bubble_P | 52142 | 53876.6 | 0.0332664 | literature:Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 322.91 K; DDB Explorer Edition data set 468; retrieved 2026-10-20 |
| c1co2-288.15K-6.62MPa | srk | bubble_P | 6.62e+06 | 6.40134e+06 | 0.0330304 | literature:Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20 |
| rk-c1c3-294.26K-6.895MPa | rk | vapor_comp | 0.7497 | 0.716679 | 0.033021 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 294.26 K isotherm; retrieved 2026-10-20 |
| c1co2-277.15K-5.97MPa | srk | bubble_P | 5.97e+06 | 5.77391e+06 | 0.0328465 | literature:Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20 |
| srk-peneloux-c1co2-277.15K-5.97MPa | srk-peneloux | bubble_P | 5.97e+06 | 5.77391e+06 | 0.0328465 | literature:Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20 |
| sour-srk-c1co2-277.15K-5.97MPa | sour-srk | bubble_P | 5.97e+06 | 5.77391e+06 | 0.0328465 | literature:Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20 |
| kabadi-danner-srk-c1co2-277.15K-5.97MPa | kabadi-danner-srk | bubble_P | 5.97e+06 | 5.77391e+06 | 0.0328465 | literature:Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20 |
| srk-lee-kesler-enthalpy-c1co2-277.15K-5.97MPa | srk-lee-kesler-enthalpy | bubble_P | 5.97e+06 | 5.77391e+06 | 0.0328465 | literature:Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20 |
| c1co2-277.15K-7.04MPa | srk | bubble_P | 7.04e+06 | 6.80905e+06 | 0.0328052 | literature:Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20 |
| pure-CO2-288.9K | srk | rho_V | 165.146 | 159.741 | 0.0327274 | coolprop:CO2 |
| pure-MeOH-330K-nrtl | nrtl | rho_V | 0.911218 | 0.882017 | 0.0320466 | coolprop:Methanol |
| api-srk-c1co2-277.15K-5.97MPa | api-srk | bubble_P | 5.97e+06 | 5.77937e+06 | 0.0319319 | literature:Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20 |
| pr-boston-mathias-c1c3-294.26K-6.895MPa | pr-boston-mathias | bubble_P | 6.895e+06 | 6.67541e+06 | 0.0318473 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 294.26 K isotherm; retrieved 2026-10-20 |
| pr-bm-c1c3-294.26K-6.895MPa | pr-bm | bubble_P | 6.895e+06 | 6.67541e+06 | 0.0318473 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 294.26 K isotherm; retrieved 2026-10-20 |
| pure-H2O-520K | pr | rho_V | 18.9001 | 18.2989 | 0.0318087 | coolprop:Water |
| pure-H2O-520K | pr78 | rho_V | 18.9001 | 18.2989 | 0.0318087 | coolprop:Water |
| c1co2-288.15K-6.62MPa | pr | bubble_P | 6.62e+06 | 6.41389e+06 | 0.031134 | literature:Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20 |
| c1co2-288.15K-6.62MPa | pr78 | bubble_P | 6.62e+06 | 6.41389e+06 | 0.031134 | literature:Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20 |
| pure-C3-351.3K | srk | rho_V | 79.9466 | 77.4636 | 0.0310573 | coolprop:Propane |
| pure-N2-119.9K | pr | rho_V | 124.118 | 127.964 | 0.0309824 | coolprop:Nitrogen |
| pure-N2-119.9K | pr78 | rho_V | 124.118 | 127.964 | 0.0309824 | coolprop:Nitrogen |
| c1co2-288.15K-7.63MPa | srk | bubble_P | 7.63e+06 | 7.39464e+06 | 0.0308463 | literature:Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20 |
| c1c3-327.59K-7.239MPa | srk | vapor_comp | 0.5532 | 0.522939 | 0.0302611 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 327.59 K isotherm; retrieved 2026-10-20 |
| c1co2-274.15K-5.90MPa | srk | bubble_P | 5.9e+06 | 5.72244e+06 | 0.0300952 | literature:Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20 |
| meohh2o-312.91K-23.385kPa | nrtl | vapor_comp | 0.8457 | 0.816434 | 0.029266 | literature:Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 312.91 K; DDB Explorer Edition data set 467; retrieved 2026-10-20 |
| meohh2o-312.91K-16.319kPa | nrtl | vapor_comp | 0.6954 | 0.669234 | 0.0261658 | literature:Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 312.91 K; DDB Explorer Edition data set 467; retrieved 2026-10-20 |
| c1c3-294.26K-8.963MPa | srk | vapor_comp | 0.7561 | 0.732695 | 0.0234047 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 294.26 K isotherm; retrieved 2026-10-20 |
| c1c3-294.26K-8.274MPa | pr | vapor_comp | 0.7567 | 0.736645 | 0.020055 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 294.26 K isotherm; retrieved 2026-10-20 |
| c1c3-294.26K-8.274MPa | pr78 | vapor_comp | 0.7567 | 0.736645 | 0.020055 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 294.26 K isotherm; retrieved 2026-10-20 |
| meohh2o-97.99kPa-353.25K | nrtl | bubble_T | 353.25 | 356.827 | 0.010127 | literature:Bennett (1929) J. Chem. Educ. 6, pp. 1544-1549, isobaric 97.99 kPa; DDB Explorer Edition data set 466; retrieved 2026-10-20 |
| meohh2o-97.99kPa-349.05K | nrtl | bubble_T | 349.05 | 351.756 | 0.00775345 | literature:Bennett (1929) J. Chem. Educ. 6, pp. 1544-1549, isobaric 97.99 kPa; DDB Explorer Edition data set 466; retrieved 2026-10-20 |
| meohh2o-97.99kPa-365.45K | nrtl | bubble_T | 365.45 | 367.631 | 0.0059681 | literature:Bennett (1929) J. Chem. Educ. 6, pp. 1544-1549, isobaric 97.99 kPa; DDB Explorer Edition data set 466; retrieved 2026-10-20 |

## Case assessments (marked xfail in the test suite)

- `api-srk-c1co2-277.15K-5.97MPa` — bubble_P -3.2% (5.77937e+06 vs 5.97e+06) - API kappa correlation on SRK: light-component Cp and VLE limits of the SRK form (measured 2026-10-22, PR #161 table).
- `api-srk-ng-dew-morch-243.4K-0.30MPa` — dew_P +25.5% (376555 vs 300000) - API kappa correlation on SRK: light-component Cp and VLE limits of the SRK form (measured 2026-10-22, PR #161 table).
- `api-srk-ng-dew-morch-254.6K-0.68MPa` — dew_P +13.5% (771741 vs 680000) - API kappa correlation on SRK: light-component Cp and VLE limits of the SRK form (measured 2026-10-22, PR #161 table).
- `api-srk-ng-dew-morch-260.8K-1.04MPa` — dew_P +10.4% (1.14824e+06 vs 1.04e+06) - API kappa correlation on SRK: light-component Cp and VLE limits of the SRK form (measured 2026-10-22, PR #161 table).
- `api-srk-pure-C1-125K` — Cp +7.3% (61.9476 vs 57.7411) - API kappa correlation on SRK: light-component Cp and VLE limits of the SRK form (measured 2026-10-22, PR #161 table).
- `api-srk-pure-C3-300K` — Cp +6.8% (129.067 vs 120.805); rho_L -8.4% (448.355 vs 489.447) - API kappa correlation on SRK: light-component Cp and VLE limits of the SRK form (measured 2026-10-22, PR #161 table).
- `api-srk-pure-CO2-265K` — Cp +12.3% (115.742 vs 103.056); rho_L -11.8% (858.135 vs 973.254) - API kappa correlation on SRK: light-component Cp and VLE limits of the SRK form (measured 2026-10-22, PR #161 table).
- `c1c3-277.59K-1.724MPa (pr)` — bubble_P -4.2% (1.65127e+06 vs 1.724e+06) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `c1c3-277.59K-1.724MPa (pr78)` — bubble_P -4.2% (1.65127e+06 vs 1.724e+06) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `c1c3-277.59K-2.758MPa (pr)` — bubble_P -3.4% (2.66404e+06 vs 2.758e+06) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `c1c3-277.59K-2.758MPa (pr78)` — bubble_P -3.4% (2.66404e+06 vs 2.758e+06) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `c1c3-294.26K-8.274MPa (pr)` — vapor_comp -2.0% (0.736645 vs 0.7567) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `c1c3-294.26K-8.274MPa (pr78)` — vapor_comp -2.0% (0.736645 vs 0.7567) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `c1c3-294.26K-8.963MPa (pr)` — vapor_comp -3.4% (0.721745 vs 0.7561) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `c1c3-294.26K-8.963MPa (pr78)` — vapor_comp -3.4% (0.721745 vs 0.7561) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `c1c3-294.26K-8.963MPa (srk)` — vapor_comp -2.3% (0.732695 vs 0.7561) - cubic-EOS limits of SRK (severe liquid-density deficit, Cp departure errors including CO2, optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `c1c3-294.26K-9.653MPa (pr)` — bubble_P -38.5% (5.93886e+06 vs 9.653e+06) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `c1c3-294.26K-9.653MPa (pr78)` — bubble_P -38.5% (5.93886e+06 vs 9.653e+06) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `c1c3-294.26K-9.653MPa (srk)` — bubble_P -39.2% (5.87349e+06 vs 9.653e+06) - cubic-EOS limits of SRK (severe liquid-density deficit, Cp departure errors including CO2, optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `c1c3-327.59K-4.482MPa (pr)` — bubble_P -3.6% (4.3208e+06 vs 4.482e+06) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `c1c3-327.59K-4.482MPa (pr78)` — bubble_P -3.6% (4.3208e+06 vs 4.482e+06) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `c1c3-327.59K-4.482MPa (srk)` — bubble_P -3.6% (4.32193e+06 vs 4.482e+06) - cubic-EOS limits of SRK (severe liquid-density deficit, Cp departure errors including CO2, optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `c1c3-327.59K-5.861MPa (pr)` — bubble_P -4.1% (5.62072e+06 vs 5.861e+06) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `c1c3-327.59K-5.861MPa (pr78)` — bubble_P -4.1% (5.62072e+06 vs 5.861e+06) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `c1c3-327.59K-5.861MPa (srk)` — bubble_P -4.2% (5.61512e+06 vs 5.861e+06) - cubic-EOS limits of SRK (severe liquid-density deficit, Cp departure errors including CO2, optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `c1c3-327.59K-7.239MPa (pr)` — bubble_P -3.9% (6.95919e+06 vs 7.239e+06); vapor_comp -4.0% (0.513071 vs 0.5532) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `c1c3-327.59K-7.239MPa (pr78)` — bubble_P -3.9% (6.95919e+06 vs 7.239e+06); vapor_comp -4.0% (0.513071 vs 0.5532) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `c1c3-327.59K-7.239MPa (srk)` — bubble_P -3.8% (6.96085e+06 vs 7.239e+06); vapor_comp -3.0% (0.522939 vs 0.5532) - cubic-EOS limits of SRK (severe liquid-density deficit, Cp departure errors including CO2, optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `c1c3-327.59K-7.584MPa (pr)` — bubble_P -36.2% (4.84006e+06 vs 7.584e+06); vapor_comp -9.8% (0.456645 vs 0.5546) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `c1c3-327.59K-7.584MPa (pr78)` — bubble_P -36.2% (4.84006e+06 vs 7.584e+06); vapor_comp -9.8% (0.456645 vs 0.5546) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `c1c3-327.59K-7.584MPa (srk)` — bubble_P -36.5% (4.81796e+06 vs 7.584e+06); vapor_comp -9.6% (0.45901 vs 0.5546) - cubic-EOS limits of SRK (severe liquid-density deficit, Cp departure errors including CO2, optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `c1co2-274.15K-5.90MPa` — bubble_P -3.0% (5.72244e+06 vs 5.9e+06) - cubic-EOS limits of SRK (severe liquid-density deficit, Cp departure errors including CO2, optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `c1co2-277.15K-4.69MPa (pr)` — bubble_P -3.3% (4.53373e+06 vs 4.69e+06) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `c1co2-277.15K-4.69MPa (pr78)` — bubble_P -3.3% (4.53373e+06 vs 4.69e+06) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `c1co2-277.15K-5.97MPa` — bubble_P -3.3% (5.77391e+06 vs 5.97e+06) - cubic-EOS limits of SRK (severe liquid-density deficit, Cp departure errors including CO2, optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `c1co2-277.15K-7.04MPa` — bubble_P -3.3% (6.80905e+06 vs 7.04e+06) - cubic-EOS limits of SRK (severe liquid-density deficit, Cp departure errors including CO2, optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `c1co2-283.15K-7.24MPa` — bubble_P -3.4% (6.99089e+06 vs 7.24e+06) - cubic-EOS limits of SRK (severe liquid-density deficit, Cp departure errors including CO2, optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `c1co2-288.15K-6.62MPa (pr)` — bubble_P -3.1% (6.41389e+06 vs 6.62e+06) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `c1co2-288.15K-6.62MPa (pr78)` — bubble_P -3.1% (6.41389e+06 vs 6.62e+06) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `c1co2-288.15K-6.62MPa (srk)` — bubble_P -3.3% (6.40134e+06 vs 6.62e+06) - cubic-EOS limits of SRK (severe liquid-density deficit, Cp departure errors including CO2, optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `c1co2-288.15K-7.63MPa` — bubble_P -3.1% (7.39464e+06 vs 7.63e+06) - cubic-EOS limits of SRK (severe liquid-density deficit, Cp departure errors including CO2, optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `kabadi-danner-srk-c1co2-277.15K-5.97MPa` — bubble_P -3.3% (5.77391e+06 vs 5.97e+06) - Kabadi-Danner water interaction inactive in these H2O-free cases; SRK limits inherited (measured 2026-10-22, PR #161 table).
- `kabadi-danner-srk-ng-dew-morch-243.4K-0.30MPa` — dew_P +25.9% (377792 vs 300000) - Kabadi-Danner water interaction inactive in these H2O-free cases; SRK limits inherited (measured 2026-10-22, PR #161 table).
- `kabadi-danner-srk-ng-dew-morch-254.6K-0.68MPa` — dew_P +13.8% (774165 vs 680000) - Kabadi-Danner water interaction inactive in these H2O-free cases; SRK limits inherited (measured 2026-10-22, PR #161 table).
- `kabadi-danner-srk-ng-dew-morch-260.8K-1.04MPa` — dew_P +10.8% (1.15189e+06 vs 1.04e+06) - Kabadi-Danner water interaction inactive in these H2O-free cases; SRK limits inherited (measured 2026-10-22, PR #161 table).
- `kabadi-danner-srk-pure-C1-125K` — Cp +6.9% (61.7209 vs 57.7411) - Kabadi-Danner water interaction inactive in these H2O-free cases; SRK limits inherited (measured 2026-10-22, PR #161 table).
- `kabadi-danner-srk-pure-C3-300K` — Cp +6.7% (128.942 vs 120.805); rho_L -8.4% (448.204 vs 489.447) - Kabadi-Danner water interaction inactive in these H2O-free cases; SRK limits inherited (measured 2026-10-22, PR #161 table).
- `kabadi-danner-srk-pure-CO2-265K` — Cp +12.2% (115.671 vs 103.056); rho_L -11.8% (857.989 vs 973.254) - Kabadi-Danner water interaction inactive in these H2O-free cases; SRK limits inherited (measured 2026-10-22, PR #161 table).
- `meohh2o-312.91K-13.012kPa` — NRTL databank MeOH/H2O parameters do not reproduce the 1927/1929 isotherms within 2 % bubble P / 0.02 abs y (databank limitation; assessed in docs/validation.md).
- `meohh2o-312.91K-16.319kPa` — NRTL databank MeOH/H2O parameters do not reproduce the 1927/1929 isotherms within 2 % bubble P / 0.02 abs y (databank limitation; assessed in docs/validation.md).
- `meohh2o-312.91K-20.705kPa` — NRTL databank MeOH/H2O parameters do not reproduce the 1927/1929 isotherms within 2 % bubble P / 0.02 abs y (databank limitation; assessed in docs/validation.md).
- `meohh2o-312.91K-23.385kPa` — NRTL databank MeOH/H2O parameters do not reproduce the 1927/1929 isotherms within 2 % bubble P / 0.02 abs y (databank limitation; assessed in docs/validation.md).
- `meohh2o-312.91K-27.518kPa` — NRTL databank MeOH/H2O parameters do not reproduce the 1927/1929 isotherms within 2 % bubble P / 0.02 abs y (databank limitation; assessed in docs/validation.md).
- `meohh2o-312.91K-32.571kPa` — NRTL databank MeOH/H2O parameters do not reproduce the 1927/1929 isotherms within 2 % bubble P / 0.02 abs y (databank limitation; assessed in docs/validation.md).
- `meohh2o-312.91K-9.079kPa` — NRTL databank MeOH/H2O parameters do not reproduce the 1927/1929 isotherms within 2 % bubble P / 0.02 abs y (databank limitation; assessed in docs/validation.md).
- `meohh2o-322.91K-15.932kPa` — NRTL databank MeOH/H2O parameters do not reproduce the 1927/1929 isotherms within 2 % bubble P / 0.02 abs y (databank limitation; assessed in docs/validation.md).
- `meohh2o-322.91K-26.131kPa` — NRTL databank MeOH/H2O parameters do not reproduce the 1927/1929 isotherms within 2 % bubble P / 0.02 abs y (databank limitation; assessed in docs/validation.md).
- `meohh2o-322.91K-31.544kPa` — NRTL databank MeOH/H2O parameters do not reproduce the 1927/1929 isotherms within 2 % bubble P / 0.02 abs y (databank limitation; assessed in docs/validation.md).
- `meohh2o-322.91K-40.850kPa` — NRTL databank MeOH/H2O parameters do not reproduce the 1927/1929 isotherms within 2 % bubble P / 0.02 abs y (databank limitation; assessed in docs/validation.md).
- `meohh2o-322.91K-46.450kPa` — NRTL databank MeOH/H2O parameters do not reproduce the 1927/1929 isotherms within 2 % bubble P / 0.02 abs y (databank limitation; assessed in docs/validation.md).
- `meohh2o-322.91K-52.142kPa` — NRTL databank MeOH/H2O parameters do not reproduce the 1927/1929 isotherms within 2 % bubble P / 0.02 abs y (databank limitation; assessed in docs/validation.md).
- `meohh2o-97.99kPa-349.05K` — NRTL databank MeOH/H2O parameters do not reproduce the 1927/1929 isotherms within 2 % bubble P / 0.02 abs y (databank limitation; assessed in docs/validation.md).
- `meohh2o-97.99kPa-353.25K` — NRTL databank MeOH/H2O parameters do not reproduce the 1927/1929 isotherms within 2 % bubble P / 0.02 abs y (databank limitation; assessed in docs/validation.md).
- `meohh2o-97.99kPa-360.65K` — NRTL databank MeOH/H2O parameters do not reproduce the 1927/1929 isotherms within 2 % bubble P / 0.02 abs y (databank limitation; assessed in docs/validation.md).
- `meohh2o-97.99kPa-365.45K` — NRTL databank MeOH/H2O parameters do not reproduce the 1927/1929 isotherms within 2 % bubble P / 0.02 abs y (databank limitation; assessed in docs/validation.md).
- `meohh2o-97.99kPa-369.65K` — NRTL databank MeOH/H2O parameters do not reproduce the 1927/1929 isotherms within 2 % bubble P / 0.02 abs y (databank limitation; assessed in docs/validation.md).
- `ng-dew-morch-243.4K-0.30MPa (pr)` — dew_P +35.5% (406518 vs 300000) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `ng-dew-morch-243.4K-0.30MPa (pr78)` — dew_P +35.5% (406518 vs 300000) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `ng-dew-morch-243.4K-0.30MPa (srk)` — dew_P +25.9% (377792 vs 300000) - cubic-EOS limits of SRK (severe liquid-density deficit, Cp departure errors including CO2, optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `ng-dew-morch-254.6K-0.68MPa (pr)` — dew_P +21.9% (829096 vs 680000) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `ng-dew-morch-254.6K-0.68MPa (pr78)` — dew_P +21.9% (829096 vs 680000) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `ng-dew-morch-254.6K-0.68MPa (srk)` — dew_P +13.8% (774165 vs 680000) - cubic-EOS limits of SRK (severe liquid-density deficit, Cp departure errors including CO2, optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `ng-dew-morch-260.8K-1.04MPa (pr)` — dew_P +19.0% (1.2378e+06 vs 1.04e+06) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `ng-dew-morch-260.8K-1.04MPa (pr78)` — dew_P +19.0% (1.2378e+06 vs 1.04e+06) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `ng-dew-morch-260.8K-1.04MPa (srk)` — dew_P +10.8% (1.15189e+06 vs 1.04e+06) - cubic-EOS limits of SRK (severe liquid-density deficit, Cp departure errors including CO2, optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pr-bm-c1c3-294.26K-6.895MPa` — bubble_P -3.2% (6.67541e+06 vs 6.895e+06) - Boston-Mathias alpha on the ChemSep IPDB databank parameters inherits PR property limits (measured 2026-10-22, PR #161 table).
- `pr-bm-c1co2-277.15K-5.97MPa` — bubble_P -3.7% (5.7503e+06 vs 5.97e+06) - Boston-Mathias alpha on the ChemSep IPDB databank parameters inherits PR property limits (measured 2026-10-22, PR #161 table).
- `pr-bm-ng-dew-morch-243.4K-0.30MPa` — dew_P +35.5% (406384 vs 300000) - Boston-Mathias alpha on the ChemSep IPDB databank parameters inherits PR property limits (measured 2026-10-22, PR #161 table).
- `pr-bm-ng-dew-morch-254.6K-0.68MPa` — dew_P +21.9% (828676 vs 680000) - Boston-Mathias alpha on the ChemSep IPDB databank parameters inherits PR property limits (measured 2026-10-22, PR #161 table).
- `pr-bm-ng-dew-morch-260.8K-1.04MPa` — dew_P +18.9% (1.23705e+06 vs 1.04e+06) - Boston-Mathias alpha on the ChemSep IPDB databank parameters inherits PR property limits (measured 2026-10-22, PR #161 table).
- `pr-bm-pure-C1-125K` — rho_L +11.8% (449.652 vs 402.111) - Boston-Mathias alpha on the ChemSep IPDB databank parameters inherits PR property limits (measured 2026-10-22, PR #161 table).
- `pr-bm-pure-CO2-265K` — Cp +8.1% (111.409 vs 103.056) - Boston-Mathias alpha on the ChemSep IPDB databank parameters inherits PR property limits (measured 2026-10-22, PR #161 table).
- `pr-boston-mathias-c1c3-294.26K-6.895MPa` — bubble_P -3.2% (6.67541e+06 vs 6.895e+06) - Boston-Mathias alpha (finite supercritical continuation) inherits PR property limits (measured 2026-10-22, PR #161 table).
- `pr-boston-mathias-c1co2-277.15K-5.97MPa` — bubble_P -3.7% (5.7503e+06 vs 5.97e+06) - Boston-Mathias alpha (finite supercritical continuation) inherits PR property limits (measured 2026-10-22, PR #161 table).
- `pr-boston-mathias-ng-dew-morch-243.4K-0.30MPa` — dew_P +35.5% (406384 vs 300000) - Boston-Mathias alpha (finite supercritical continuation) inherits PR property limits (measured 2026-10-22, PR #161 table).
- `pr-boston-mathias-ng-dew-morch-254.6K-0.68MPa` — dew_P +21.9% (828676 vs 680000) - Boston-Mathias alpha (finite supercritical continuation) inherits PR property limits (measured 2026-10-22, PR #161 table).
- `pr-boston-mathias-ng-dew-morch-260.8K-1.04MPa` — dew_P +18.9% (1.23705e+06 vs 1.04e+06) - Boston-Mathias alpha (finite supercritical continuation) inherits PR property limits (measured 2026-10-22, PR #161 table).
- `pr-boston-mathias-pure-C1-125K` — rho_L +11.8% (449.652 vs 402.111) - Boston-Mathias alpha (finite supercritical continuation) inherits PR property limits (measured 2026-10-22, PR #161 table).
- `pr-boston-mathias-pure-CO2-265K` — Cp +8.1% (111.409 vs 103.056) - Boston-Mathias alpha (finite supercritical continuation) inherits PR property limits (measured 2026-10-22, PR #161 table).
- `pr-lee-kesler-enthalpy-ng-dew-morch-243.4K-0.30MPa` — dew_P +35.5% (406518 vs 300000 Pa, 3 % tolerance) - the asymmetric C1/C2/nC5 dew points run 10-35 % above the Morch et al. (2006) cooled-mirror measurements under databank/zero k_ij; VLE and density are the cubic EOS's (the Lee-Kesler path serves enthalpy only) and the same case assesses the shipped packages (issue #130) (measured 2026-10-22 after the Lee-Kesler D-term fix, PR #161 table).
- `pr-lee-kesler-enthalpy-ng-dew-morch-254.6K-0.68MPa` — dew_P +21.9% (829096 vs 680000 Pa, 3 % tolerance) - the asymmetric C1/C2/nC5 dew points run 10-35 % above the Morch et al. (2006) cooled-mirror measurements under databank/zero k_ij; VLE and density are the cubic EOS's (the Lee-Kesler path serves enthalpy only) and the same case assesses the shipped packages (issue #130) (measured 2026-10-22 after the Lee-Kesler D-term fix, PR #161 table).
- `pr-lee-kesler-enthalpy-ng-dew-morch-260.8K-1.04MPa` — dew_P +19.0% (1237804 vs 1040000 Pa, 3 % tolerance) - the asymmetric C1/C2/nC5 dew points run 10-35 % above the Morch et al. (2006) cooled-mirror measurements under databank/zero k_ij; VLE and density are the cubic EOS's (the Lee-Kesler path serves enthalpy only) and the same case assesses the shipped packages (issue #130) (measured 2026-10-22 after the Lee-Kesler D-term fix, PR #161 table).
- `pr-lee-kesler-enthalpy-pure-C1-125K` — rho_L +11.8% (449.652 vs 402.111 kg/m3, 8 % tolerance) - PR liquid density at 125 K, the cubic liquid-density weakness (the pr-peneloux row is its volume-translation correction); the Lee-Kesler enthalpy path checks clean on this case: Cp +3.7% (59.896 vs 57.741 J/mol/K), bubble/dew P within 1e-7; the simple-fluid liquid-branch (Cp-Cp0)/R at Tr=0.65/Pr=0.06 measures 3.053 vs the published Lee-Kesler table 3.047-3.051 (Reid-Prausnitz-Sherwood 1977, residual-Cp simple-fluid table, Tr=0.65 row; independent vle_thermo port 3.0535) - within 0.2 %, so the +3.7 % is the correlation's own accuracy, per issue #162 (measured 2026-10-22 after the Lee-Kesler D-term fix, PR #161 table).
- `pr-lee-kesler-enthalpy-pure-CO2-265K` — Cp -7.2% (95.667 vs 103.056 J/mol/K, 5 % tolerance) - the Lee-Kesler correlation's own CO2 sat-liquid Cp accuracy near its critical region (Tr=0.87); the implementation reproduces the published Lee-Kesler form (max 3.3e-8 deviation from the analytic Helmholtz derivative over a 224-state sweep), so the residual is the correlation's, not a coding error (measured 2026-10-22 after the D-term fix, PR #161 table).
- `pr-mathias-copeman-ng-dew-morch-243.4K-0.30MPa` — dew_P +35.5% (406577 vs 300000) - Mathias-Copeman alpha (published constants where fitted) inherits PR property limits (measured 2026-10-22, PR #161 table).
- `pr-mathias-copeman-ng-dew-morch-254.6K-0.68MPa` — dew_P +22.0% (829293 vs 680000) - Mathias-Copeman alpha (published constants where fitted) inherits PR property limits (measured 2026-10-22, PR #161 table).
- `pr-mathias-copeman-ng-dew-morch-260.8K-1.04MPa` — dew_P +19.1% (1.23816e+06 vs 1.04e+06) - Mathias-Copeman alpha (published constants where fitted) inherits PR property limits (measured 2026-10-22, PR #161 table).
- `pr-mathias-copeman-pure-C1-125K` — rho_L +11.9% (449.888 vs 402.111) - Mathias-Copeman alpha (published constants where fitted) inherits PR property limits (measured 2026-10-22, PR #161 table).
- `pr-mathias-copeman-pure-CO2-265K` — Cp +8.0% (111.333 vs 103.056) - Mathias-Copeman alpha (published constants where fitted) inherits PR property limits (measured 2026-10-22, PR #161 table).
- `pr-peneloux-ng-dew-morch-243.4K-0.30MPa` — dew_P +35.5% (406518 vs 300000) - Jhaveri-Youngren translation corrects liquid volume only; VLE and Cp deviations inherited from PR (measured 2026-10-22, PR #161 table).
- `pr-peneloux-ng-dew-morch-254.6K-0.68MPa` — dew_P +21.9% (829096 vs 680000) - Jhaveri-Youngren translation corrects liquid volume only; VLE and Cp deviations inherited from PR (measured 2026-10-22, PR #161 table).
- `pr-peneloux-ng-dew-morch-260.8K-1.04MPa` — dew_P +19.0% (1.2378e+06 vs 1.04e+06) - Jhaveri-Youngren translation corrects liquid volume only; VLE and Cp deviations inherited from PR (measured 2026-10-22, PR #161 table).
- `pr-peneloux-pure-CO2-265K` — Cp +8.1% (111.409 vs 103.056) - Jhaveri-Youngren translation corrects liquid volume only; VLE and Cp deviations inherited from PR (measured 2026-10-22, PR #161 table).
- `prsv-ng-dew-morch-243.4K-0.30MPa` — dew_P +37.0% (411130 vs 300000) - PRSV alpha (improved heavy ends) inherits PR liquid-density and light-alkane Cp limits (measured 2026-10-22, PR #161 table).
- `prsv-ng-dew-morch-254.6K-0.68MPa` — dew_P +23.3% (838245 vs 680000) - PRSV alpha (improved heavy ends) inherits PR liquid-density and light-alkane Cp limits (measured 2026-10-22, PR #161 table).
- `prsv-ng-dew-morch-260.8K-1.04MPa` — dew_P +20.4% (1.25191e+06 vs 1.04e+06) - PRSV alpha (improved heavy ends) inherits PR liquid-density and light-alkane Cp limits (measured 2026-10-22, PR #161 table).
- `prsv-pure-C1-125K` — rho_L +11.9% (449.914 vs 402.111) - PRSV alpha (improved heavy ends) inherits PR liquid-density and light-alkane Cp limits (measured 2026-10-22, PR #161 table).
- `prsv-pure-CO2-265K` — Cp +8.0% (111.252 vs 103.056) - PRSV alpha (improved heavy ends) inherits PR liquid-density and light-alkane Cp limits (measured 2026-10-22, PR #161 table).
- `prsv2-ng-dew-morch-243.4K-0.30MPa` — dew_P +37.0% (411130 vs 300000) - PRSV2 alpha inherits PR liquid-density and light-alkane Cp limits (measured 2026-10-22, PR #161 table).
- `prsv2-ng-dew-morch-254.6K-0.68MPa` — dew_P +23.3% (838245 vs 680000) - PRSV2 alpha inherits PR liquid-density and light-alkane Cp limits (measured 2026-10-22, PR #161 table).
- `prsv2-ng-dew-morch-260.8K-1.04MPa` — dew_P +20.4% (1.25191e+06 vs 1.04e+06) - PRSV2 alpha inherits PR liquid-density and light-alkane Cp limits (measured 2026-10-22, PR #161 table).
- `prsv2-pure-C1-125K` — rho_L +11.9% (449.914 vs 402.111) - PRSV2 alpha inherits PR liquid-density and light-alkane Cp limits (measured 2026-10-22, PR #161 table).
- `prsv2-pure-CO2-265K` — Cp +8.0% (111.252 vs 103.056) - PRSV2 alpha inherits PR liquid-density and light-alkane Cp limits (measured 2026-10-22, PR #161 table).
- `pure-C1-125K (pr)` — rho_L +11.8% (449.652 vs 402.111) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-C1-125K (pr78)` — rho_L +11.8% (449.652 vs 402.111) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-C1-125K (srk)` — Cp +6.9% (61.7209 vs 57.7411) - cubic-EOS limits of SRK (severe liquid-density deficit, Cp departure errors including CO2, optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-C1-155K (pr)` — Cp +8.4% (73.2856 vs 67.6129) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-C1-155K (pr78)` — Cp +8.4% (73.2856 vs 67.6129) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-C1-155K (srk)` — Cp +13.3% (76.6185 vs 67.6129) - cubic-EOS limits of SRK (severe liquid-density deficit, Cp departure errors including CO2, optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-C1-172K (pr)` — Cp +18.3% (103.117 vs 87.1299) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-C1-172K (pr78)` — Cp +18.3% (103.117 vs 87.1299) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-C1-172K (srk)` — Cp +23.3% (107.453 vs 87.1299); rho_L -9.9% (274.35 vs 304.559) - cubic-EOS limits of SRK (severe liquid-density deficit, Cp departure errors including CO2, optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-C1-181K (pr)` — Cp +29.8% (161.076 vs 124.139) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-C1-181K (pr78)` — Cp +29.8% (161.076 vs 124.139) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-C1-181K (srk)` — Cp +35.8% (168.599 vs 124.139); rho_L -14.1% (233.607 vs 271.913) - cubic-EOS limits of SRK (severe liquid-density deficit, Cp departure errors including CO2, optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-C1-95.3K (pr)` — rho_L +12.8% (502.166 vs 445.301) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-C1-95.3K (pr78)` — rho_L +12.8% (502.166 vs 445.301) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-C1-95.3K (srk)` — Cp +5.5% (57.3174 vs 54.3155) - cubic-EOS limits of SRK (severe liquid-density deficit, Cp departure errors including CO2, optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-C2-152.7K (pr)` — Cp -6.3% (65.9027 vs 70.3296); rho_L +8.5% (631.691 vs 582.054) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-C2-152.7K (pr78)` — Cp -6.3% (65.9027 vs 70.3296); rho_L +8.5% (631.691 vs 582.054) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-C2-200K (pr)` — rho_L +8.5% (568.762 vs 523.977) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-C2-200K (pr78)` — rho_L +8.5% (568.762 vs 523.977) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-C2-250K (pr)` — Cp +6.1% (95.4911 vs 90.0242) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-C2-250K (pr78)` — Cp +6.1% (95.4911 vs 90.0242) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-C2-250K (srk)` — Cp +10.0% (99.0394 vs 90.0242) - cubic-EOS limits of SRK (severe liquid-density deficit, Cp departure errors including CO2, optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-C2-285K (pr)` — Cp +21.8% (161.185 vs 132.286) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-C2-285K (pr78)` — Cp +21.8% (161.185 vs 132.286) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-C2-285K (srk)` — Cp +26.3% (167.068 vs 132.286); rho_L -14.4% (315.192 vs 368.125) - cubic-EOS limits of SRK (severe liquid-density deficit, Cp departure errors including CO2, optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-C2-290K (pr)` — Cp +27.0% (193.22 vs 152.189) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-C2-290K (pr78)` — Cp +27.0% (193.22 vs 152.189) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-C2-290K (srk)` — Cp +32.0% (200.921 vs 152.189); rho_L -16.0% (295.002 vs 351.314) - cubic-EOS limits of SRK (severe liquid-density deficit, Cp departure errors including CO2, optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-C3-184.9K (pr)` — Cp -7.5% (84.9224 vs 91.8478) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-C3-184.9K (pr78)` — Cp -7.5% (84.9224 vs 91.8478) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-C3-300K` — Cp +6.7% (128.942 vs 120.805); rho_L -8.4% (448.204 vs 489.447) - cubic-EOS limits of SRK (severe liquid-density deficit, Cp departure errors including CO2, optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-C3-340K (pr)` — Cp +14.8% (181.435 vs 158.07) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-C3-340K (pr78)` — Cp +14.8% (181.435 vs 158.07) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-C3-340K (srk)` — Cp +18.0% (186.594 vs 158.07); rho_L -14.2% (353.492 vs 411.774) - cubic-EOS limits of SRK (severe liquid-density deficit, Cp departure errors including CO2, optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-C3-351.3K (pr)` — Cp +22.5% (234.044 vs 191.089) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-C3-351.3K (pr78)` — Cp +22.5% (234.044 vs 191.089) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-C3-351.3K (srk)` — Cp +26.6% (241.865 vs 191.089); rho_L -17.0% (314.954 vs 379.569); rho_V -3.1% (77.4636 vs 79.9466) - cubic-EOS limits of SRK (severe liquid-density deficit, Cp departure errors including CO2, optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-CO2-216.7K (pr)` — Cp -8.9% (78.3254 vs 85.9712) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-CO2-216.7K (pr78)` — Cp -8.9% (78.3254 vs 85.9712) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-CO2-240K` — rho_L -9.0% (990.451 vs 1088.87) - cubic-EOS limits of SRK (severe liquid-density deficit, Cp departure errors including CO2, optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-CO2-265K (pr)` — Cp +8.1% (111.409 vs 103.056) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-CO2-265K (pr78)` — Cp +8.1% (111.409 vs 103.056) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-CO2-265K (srk)` — Cp +12.2% (115.671 vs 103.056); rho_L -11.8% (857.989 vs 973.254) - cubic-EOS limits of SRK (severe liquid-density deficit, Cp departure errors including CO2, optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-CO2-285K (pr)` — Cp +23.2% (169.831 vs 137.895) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-CO2-285K (pr78)` — Cp +23.2% (169.831 vs 137.895) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-CO2-285K (srk)` — Cp +27.8% (176.26 vs 137.895); rho_L -16.2% (709.912 vs 847.046) - cubic-EOS limits of SRK (severe liquid-density deficit, Cp departure errors including CO2, optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-CO2-288.9K (pr)` — Cp +27.8% (198.288 vs 155.189) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-CO2-288.9K (pr78)` — Cp +27.8% (198.288 vs 155.189) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-CO2-288.9K (srk)` — Cp +32.9% (206.216 vs 155.189); rho_L -17.4% (672.534 vs 814.639); rho_V -3.3% (159.741 vs 165.146) - cubic-EOS limits of SRK (severe liquid-density deficit, Cp departure errors including CO2, optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-H2O-323.5K (pr)` — Cp +7.9% (81.2495 vs 75.3335); rho_L -15.6% (833.88 vs 987.838) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-H2O-323.5K (pr78)` — Cp +7.9% (81.2495 vs 75.3335); rho_L -15.6% (833.88 vs 987.838) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-H2O-323.5K (srk)` — Cp +15.0% (86.6467 vs 75.3335); rho_L -24.9% (741.661 vs 987.838) - cubic-EOS limits of SRK (severe liquid-density deficit, Cp departure errors including CO2, optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-H2O-340K-nrtl` — Cp -6.9% (70.2529 vs 75.4562) - NRTL databank carries no residual liquid-Cp contribution for pure MeOH/H2O (Cp under-predicted); vapour density at the 3% band edge (measured 2026-10-22, PR #161 table).
- `pure-H2O-370K-nrtl` — Cp -12.2% (66.6483 vs 75.8833) - NRTL databank carries no residual liquid-Cp contribution for pure MeOH/H2O (Cp under-predicted); vapour density at the 3% band edge (measured 2026-10-22, PR #161 table).
- `pure-H2O-420K (pr)` — Cp +10.5% (85.5571 vs 77.4472); rho_L -17.1% (762.594 vs 919.929) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-H2O-420K (pr78)` — Cp +10.5% (85.5571 vs 77.4472); rho_L -17.1% (762.594 vs 919.929) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-H2O-420K (srk)` — Cp +16.7% (90.3881 vs 77.4472); rho_L -26.6% (674.912 vs 919.929) - cubic-EOS limits of SRK (severe liquid-density deficit, Cp departure errors including CO2, optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-H2O-520K (pr)` — Cp +18.1% (102.925 vs 87.149); rho_L -19.3% (648.154 vs 803.535); rho_V -3.2% (18.2989 vs 18.9001) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-H2O-520K (pr78)` — Cp +18.1% (102.925 vs 87.149); rho_L -19.3% (648.154 vs 803.535); rho_V -3.2% (18.2989 vs 18.9001) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-H2O-520K (srk)` — Cp +23.4% (107.501 vs 87.149); rho_L -28.9% (571.024 vs 803.535); rho_V -4.0% (18.1349 vs 18.9001) - cubic-EOS limits of SRK (severe liquid-density deficit, Cp departure errors including CO2, optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-H2O-600K (pr)` — Cp +37.2% (171.879 vs 125.264); rho_L -24.6% (489.546 vs 649.411); rho_V -5.7% (68.6719 vs 72.8423) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-H2O-600K (pr78)` — Cp +37.2% (171.879 vs 125.264); rho_L -24.6% (489.546 vs 649.411); rho_V -5.7% (68.6719 vs 72.8423) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-H2O-600K (srk)` — Cp +42.3% (178.303 vs 125.264); rho_L -33.4% (432.471 vs 649.411); rho_V -8.7% (66.4763 vs 72.8423) - cubic-EOS limits of SRK (severe liquid-density deficit, Cp departure errors including CO2, optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-H2O-614.7K (pr)` — Cp +45.4% (220.634 vs 151.747); rho_L -26.6% (444.727 vs 605.554); rho_V -6.8% (89.0623 vs 95.5877) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-H2O-614.7K (pr78)` — Cp +45.4% (220.634 vs 151.747); rho_L -26.6% (444.727 vs 605.554); rho_V -6.8% (89.0623 vs 95.5877) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-H2O-614.7K (srk)` — Cp +51.2% (229.506 vs 151.747); rho_L -34.9% (394.072 vs 605.554); rho_V -10.6% (85.4882 vs 95.5877) - cubic-EOS limits of SRK (severe liquid-density deficit, Cp departure errors including CO2, optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-H2S-187.8K (pr)` — Cp -12.1% (60.4703 vs 68.8292); rho_L +8.9% (1080.56 vs 992.142) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-H2S-187.8K (pr78)` — Cp -12.1% (60.4703 vs 68.8292); rho_L +8.9% (1080.56 vs 992.142) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-H2S-187.8K (srk)` — Cp -6.4% (64.4186 vs 68.8292) - cubic-EOS limits of SRK (severe liquid-density deficit, Cp departure errors including CO2, optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-H2S-240K (pr)` — Cp -5.5% (64.6799 vs 68.4609); rho_L +9.4% (984.26 vs 899.829) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-H2S-240K (pr78)` — Cp -5.5% (64.6799 vs 68.4609); rho_L +9.4% (984.26 vs 899.829) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-H2S-300K` — Cp +8.3% (83.4648 vs 77.0817) - cubic-EOS limits of SRK (severe liquid-density deficit, Cp departure errors including CO2, optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-H2S-345K (pr)` — Cp +18.6% (133.856 vs 112.837) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-H2S-345K (pr78)` — Cp +18.6% (133.856 vs 112.837) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-H2S-345K (srk)` — Cp +23.3% (139.176 vs 112.837); rho_L -11.3% (556.936 vs 628.082) - cubic-EOS limits of SRK (severe liquid-density deficit, Cp departure errors including CO2, optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-H2S-354.4K (pr)` — Cp +24.7% (176.987 vs 141.924) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-H2S-354.4K (pr78)` — Cp +24.7% (176.987 vs 141.924) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-H2S-354.4K (srk)` — Cp +30.2% (184.717 vs 141.924); rho_L -13.5% (505.336 vs 583.871); rho_V -3.9% (128.7 vs 133.989) - cubic-EOS limits of SRK (severe liquid-density deficit, Cp departure errors including CO2, optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-MeOH-305K-nrtl` — Cp -11.2% (73.3846 vs 82.6135) - NRTL databank carries no residual liquid-Cp contribution for pure MeOH/H2O (Cp under-predicted); vapour density at the 3% band edge (measured 2026-10-22, PR #161 table).
- `pure-MeOH-330K-nrtl` — Cp -17.3% (73.1651 vs 88.5047); rho_V -3.2% (0.882017 vs 0.911218) - NRTL databank carries no residual liquid-Cp contribution for pure MeOH/H2O (Cp under-predicted); vapour density at the 3% band edge (measured 2026-10-22, PR #161 table).
- `pure-N2-100K (pr)` — rho_L +9.7% (756.188 vs 689.353) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-N2-100K (pr78)` — rho_L +9.7% (756.188 vs 689.353) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-N2-100K (srk)` — Cp +9.6% (71.168 vs 64.9347) - cubic-EOS limits of SRK (severe liquid-density deficit, Cp departure errors including CO2, optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-N2-112K (pr)` — Cp +14.6% (93.1676 vs 81.2659) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-N2-112K (pr78)` — Cp +14.6% (93.1676 vs 81.2659) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-N2-112K (srk)` — Cp +19.6% (97.1906 vs 81.2659) - cubic-EOS limits of SRK (severe liquid-density deficit, Cp departure errors including CO2, optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-N2-119.9K (pr)` — Cp +29.0% (161.28 vs 125.022); rho_V +3.1% (127.964 vs 124.118) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-N2-119.9K (pr78)` — Cp +29.0% (161.28 vs 125.022); rho_V +3.1% (127.964 vs 124.118) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-N2-119.9K (srk)` — Cp +35.1% (168.848 vs 125.022); rho_L -12.9% (456.965 vs 524.673) - cubic-EOS limits of SRK (severe liquid-density deficit, Cp departure errors including CO2, optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-N2-63.2K (pr)` — Cp -8.2% (51.4237 vs 56.0355); rho_L +13.2% (981.868 vs 867.021) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-N2-63.2K (pr78)` — Cp -8.2% (51.4237 vs 56.0355); rho_L +13.2% (981.868 vs 867.021) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-N2-82K (pr)` — rho_L +12.9% (885.48 vs 784.556) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-N2-82K (pr78)` — rho_L +12.9% (885.48 vs 784.556) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-nC4-212.6K (pr)` — Cp -6.2% (114.033 vs 121.621) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-nC4-212.6K (pr78)` — Cp -6.2% (114.033 vs 121.621) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-nC4-350K` — Cp +6.3% (174.284 vs 163.885); rho_L -10.0% (454.822 vs 505.177) - cubic-EOS limits of SRK (severe liquid-density deficit, Cp departure errors including CO2, optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-nC4-390K (pr)` — Cp +12.8% (226.427 vs 200.774) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-nC4-390K (pr78)` — Cp +12.8% (226.427 vs 200.774) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-nC4-390K (srk)` — Cp +15.4% (231.664 vs 200.774); rho_L -15.1% (367.728 vs 433.172) - cubic-EOS limits of SRK (severe liquid-density deficit, Cp departure errors including CO2, optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-nC4-403.9K (pr)` — Cp +20.5% (285.411 vs 236.805) - cubic-EOS limits of PR (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-nC4-403.9K (pr78)` — Cp +20.5% (285.411 vs 236.805) - cubic-EOS limits of PR78 (light-alkane liquid-density and Cp departure errors; CO2 liquid Cp/density outside the cubic form; optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `pure-nC4-403.9K (srk)` — Cp +24.0% (293.525 vs 236.805); rho_L -18.2% (324.829 vs 397.325); rho_V -3.9% (77.5239 vs 80.697) - cubic-EOS limits of SRK (severe liquid-density deficit, Cp departure errors including CO2, optimistic dew P on the nC5-heavy Morch ternary) (measured 2026-10-22, PR #161 table).
- `rk-c1c3-294.26K-6.895MPa` — bubble_P -7.6% (6.3692e+06 vs 6.895e+06); vapor_comp -3.3% (0.716679 vs 0.7497) - no attraction tuning (crudest EOS form): VLE and density outside bands by design (measured 2026-10-22, PR #161 table).
- `rk-ng-dew-morch-243.4K-0.30MPa` — dew_P +251.4% (1.05415e+06 vs 300000) - no attraction tuning (crudest EOS form): VLE and density outside bands by design (measured 2026-10-22, PR #161 table).
- `rk-ng-dew-morch-254.6K-0.68MPa` — dew_P +1423.5% (1.036e+07 vs 680000) - no attraction tuning (crudest EOS form): VLE and density outside bands by design (measured 2026-10-22, PR #161 table).
- `rk-ng-dew-morch-260.8K-1.04MPa` — dew_P +948.9% (1.09081e+07 vs 1.04e+06) - no attraction tuning (crudest EOS form): VLE and density outside bands by design (measured 2026-10-22, PR #161 table).
- `rk-pure-C1-125K` — Cp +52.6% (88.1237 vs 57.7411) - no attraction tuning (crudest EOS form): VLE and density outside bands by design (measured 2026-10-22, PR #161 table).
- `rk-pure-C3-300K` — Cp +10.0% (132.831 vs 120.805); rho_L -11.1% (435.239 vs 489.447) - no attraction tuning (crudest EOS form): VLE and density outside bands by design (measured 2026-10-22, PR #161 table).
- `rk-pure-CO2-265K` — Cp +5.7% (108.903 vs 103.056); rho_L -16.3% (814.293 vs 973.254); rho_V -3.9% (72.5521 vs 75.4708) - no attraction tuning (crudest EOS form): VLE and density outside bands by design (measured 2026-10-22, PR #161 table).
- `rk-pure-nC4-280K` — Cp +9.2% (148.75 vs 136.28); rho_L -9.3% (538.199 vs 593.294) - no attraction tuning (crudest EOS form): VLE and density outside bands by design (measured 2026-10-22, PR #161 table).
- `rks-bm-c1c3-294.26K-6.895MPa` — bubble_P -4.3% (6.59772e+06 vs 6.895e+06) - Boston-Mathias alpha on RKS inherits SRK property limits (measured 2026-10-22, PR #161 table).
- `rks-bm-c1co2-277.15K-5.97MPa` — bubble_P -4.5% (5.70042e+06 vs 5.97e+06) - Boston-Mathias alpha on RKS inherits SRK property limits (measured 2026-10-22, PR #161 table).
- `rks-bm-ng-dew-morch-243.4K-0.30MPa` — dew_P +25.9% (377630 vs 300000) - Boston-Mathias alpha on RKS inherits SRK property limits (measured 2026-10-22, PR #161 table).
- `rks-bm-ng-dew-morch-254.6K-0.68MPa` — dew_P +13.8% (773659 vs 680000) - Boston-Mathias alpha on RKS inherits SRK property limits (measured 2026-10-22, PR #161 table).
- `rks-bm-ng-dew-morch-260.8K-1.04MPa` — dew_P +10.7% (1.15101e+06 vs 1.04e+06) - Boston-Mathias alpha on RKS inherits SRK property limits (measured 2026-10-22, PR #161 table).
- `rks-bm-pure-C1-125K` — Cp +6.9% (61.7209 vs 57.7411) - Boston-Mathias alpha on RKS inherits SRK property limits (measured 2026-10-22, PR #161 table).
- `rks-bm-pure-C3-300K` — Cp +6.7% (128.942 vs 120.805); rho_L -8.4% (448.204 vs 489.447) - Boston-Mathias alpha on RKS inherits SRK property limits (measured 2026-10-22, PR #161 table).
- `rks-bm-pure-CO2-265K` — Cp +12.2% (115.671 vs 103.056); rho_L -11.8% (857.989 vs 973.254) - Boston-Mathias alpha on RKS inherits SRK property limits (measured 2026-10-22, PR #161 table).
- `slice-inlet-K-500psia-300K (pr)` — chart-read K values (5-7 % reading precision) vs k_ij=0 cubic K (data + model limitation; assessed in docs/validation.md).
- `slice-inlet-K-500psia-300K (pr78)` — chart-read K values (5-7 % reading precision) vs k_ij=0 cubic K (data + model limitation; assessed in docs/validation.md).
- `slice-inlet-K-500psia-300K (srk)` — chart-read K values (5-7 % reading precision) vs k_ij=0 cubic K (data + model limitation; assessed in docs/validation.md).
- `sour-pr-ng-dew-morch-243.4K-0.30MPa` — dew_P +35.5% (406518 vs 300000) - sour-water term inactive in these H2O-free cases; PR limits inherited (measured 2026-10-22, PR #161 table).
- `sour-pr-ng-dew-morch-254.6K-0.68MPa` — dew_P +21.9% (829096 vs 680000) - sour-water term inactive in these H2O-free cases; PR limits inherited (measured 2026-10-22, PR #161 table).
- `sour-pr-ng-dew-morch-260.8K-1.04MPa` — dew_P +19.0% (1.2378e+06 vs 1.04e+06) - sour-water term inactive in these H2O-free cases; PR limits inherited (measured 2026-10-22, PR #161 table).
- `sour-pr-pure-C1-125K` — rho_L +11.8% (449.652 vs 402.111) - sour-water term inactive in these H2O-free cases; PR limits inherited (measured 2026-10-22, PR #161 table).
- `sour-pr-pure-CO2-265K` — Cp +8.1% (111.409 vs 103.056) - sour-water term inactive in these H2O-free cases; PR limits inherited (measured 2026-10-22, PR #161 table).
- `sour-srk-c1co2-277.15K-5.97MPa` — bubble_P -3.3% (5.77391e+06 vs 5.97e+06) - sour-water term inactive in these H2O-free cases; SRK limits inherited (measured 2026-10-22, PR #161 table).
- `sour-srk-ng-dew-morch-243.4K-0.30MPa` — dew_P +25.9% (377792 vs 300000) - sour-water term inactive in these H2O-free cases; SRK limits inherited (measured 2026-10-22, PR #161 table).
- `sour-srk-ng-dew-morch-254.6K-0.68MPa` — dew_P +13.8% (774165 vs 680000) - sour-water term inactive in these H2O-free cases; SRK limits inherited (measured 2026-10-22, PR #161 table).
- `sour-srk-ng-dew-morch-260.8K-1.04MPa` — dew_P +10.8% (1.15189e+06 vs 1.04e+06) - sour-water term inactive in these H2O-free cases; SRK limits inherited (measured 2026-10-22, PR #161 table).
- `sour-srk-pure-C1-125K` — Cp +6.9% (61.7209 vs 57.7411) - sour-water term inactive in these H2O-free cases; SRK limits inherited (measured 2026-10-22, PR #161 table).
- `sour-srk-pure-C3-300K` — Cp +6.7% (128.942 vs 120.805); rho_L -8.4% (448.204 vs 489.447) - sour-water term inactive in these H2O-free cases; SRK limits inherited (measured 2026-10-22, PR #161 table).
- `sour-srk-pure-CO2-265K` — Cp +12.2% (115.671 vs 103.056); rho_L -11.8% (857.989 vs 973.254) - sour-water term inactive in these H2O-free cases; SRK limits inherited (measured 2026-10-22, PR #161 table).
- `srk-boston-mathias-c1c3-294.26K-6.895MPa` — bubble_P -4.3% (6.59772e+06 vs 6.895e+06) - Boston-Mathias alpha (finite supercritical continuation) inherits SRK property limits (measured 2026-10-22, PR #161 table).
- `srk-boston-mathias-c1co2-277.15K-5.97MPa` — bubble_P -4.5% (5.70042e+06 vs 5.97e+06) - Boston-Mathias alpha (finite supercritical continuation) inherits SRK property limits (measured 2026-10-22, PR #161 table).
- `srk-boston-mathias-ng-dew-morch-243.4K-0.30MPa` — dew_P +25.9% (377630 vs 300000) - Boston-Mathias alpha (finite supercritical continuation) inherits SRK property limits (measured 2026-10-22, PR #161 table).
- `srk-boston-mathias-ng-dew-morch-254.6K-0.68MPa` — dew_P +13.8% (773659 vs 680000) - Boston-Mathias alpha (finite supercritical continuation) inherits SRK property limits (measured 2026-10-22, PR #161 table).
- `srk-boston-mathias-ng-dew-morch-260.8K-1.04MPa` — dew_P +10.7% (1.15101e+06 vs 1.04e+06) - Boston-Mathias alpha (finite supercritical continuation) inherits SRK property limits (measured 2026-10-22, PR #161 table).
- `srk-boston-mathias-pure-C1-125K` — Cp +6.9% (61.7209 vs 57.7411) - Boston-Mathias alpha (finite supercritical continuation) inherits SRK property limits (measured 2026-10-22, PR #161 table).
- `srk-boston-mathias-pure-C3-300K` — Cp +6.7% (128.942 vs 120.805); rho_L -8.4% (448.204 vs 489.447) - Boston-Mathias alpha (finite supercritical continuation) inherits SRK property limits (measured 2026-10-22, PR #161 table).
- `srk-boston-mathias-pure-CO2-265K` — Cp +12.2% (115.671 vs 103.056); rho_L -11.8% (857.989 vs 973.254) - Boston-Mathias alpha (finite supercritical continuation) inherits SRK property limits (measured 2026-10-22, PR #161 table).
- `srk-lee-kesler-enthalpy-c1co2-277.15K-5.97MPa` — bubble_P -3.3% (5773906 vs 5970000 Pa, 3 % tolerance) - k_ij=0 SRK VLE just beyond tolerance near the mixture critical region; VLE and density are the cubic EOS's (the Lee-Kesler path serves enthalpy only) (measured 2026-10-22 after the Lee-Kesler D-term fix, PR #161 table).
- `srk-lee-kesler-enthalpy-ng-dew-morch-243.4K-0.30MPa` — dew_P +25.9% (377792 vs 300000 Pa, 3 % tolerance) - the asymmetric C1/C2/nC5 dew points run 10-35 % above the Morch et al. (2006) cooled-mirror measurements under databank/zero k_ij; VLE and density are the cubic EOS's (the Lee-Kesler path serves enthalpy only) and the same case assesses the shipped packages (issue #130) (measured 2026-10-22 after the Lee-Kesler D-term fix, PR #161 table).
- `srk-lee-kesler-enthalpy-ng-dew-morch-254.6K-0.68MPa` — dew_P +13.8% (774165 vs 680000 Pa, 3 % tolerance) - the asymmetric C1/C2/nC5 dew points run 10-35 % above the Morch et al. (2006) cooled-mirror measurements under databank/zero k_ij; VLE and density are the cubic EOS's (the Lee-Kesler path serves enthalpy only) and the same case assesses the shipped packages (issue #130) (measured 2026-10-22 after the Lee-Kesler D-term fix, PR #161 table).
- `srk-lee-kesler-enthalpy-ng-dew-morch-260.8K-1.04MPa` — dew_P +10.8% (1151892 vs 1040000 Pa, 3 % tolerance) - the asymmetric C1/C2/nC5 dew points run 10-35 % above the Morch et al. (2006) cooled-mirror measurements under databank/zero k_ij; VLE and density are the cubic EOS's (the Lee-Kesler path serves enthalpy only) and the same case assesses the shipped packages (issue #130) (measured 2026-10-22 after the Lee-Kesler D-term fix, PR #161 table).
- `srk-lee-kesler-enthalpy-pure-C3-300K` — rho_L -8.4% (448.204 vs 489.447 kg/m3, 8 % tolerance, marginal) - SRK liquid density at 300 K, the cubic liquid-density weakness (the srk-peneloux row is its volume-translation correction); the Lee-Kesler enthalpy path checks clean on this case: Cp -1.4% (119.068 vs 120.805 J/mol/K) (measured 2026-10-22 after the Lee-Kesler D-term fix, PR #161 table).
- `srk-lee-kesler-enthalpy-pure-CO2-265K` — rho_L -11.8% (857.989 vs 973.254 kg/m3, 8 % tolerance) and Cp -7.2% (95.667 vs 103.056 J/mol/K, 5 % tolerance) - SRK liquid density near the CO2 critical region plus the Lee-Kesler correlation's own CO2 sat-liquid Cp accuracy (Tr=0.87); the implementation reproduces the published Lee-Kesler form (max 3.3e-8 deviation from the analytic Helmholtz derivative over a 224-state sweep) and the published tables (simple-fluid liquid-branch (Cp-Cp0)/R at Tr=0.65/Pr=0.06: 3.053 vs Reid-Prausnitz-Sherwood 1977 Table 5-8 3.047-3.051, within 0.2 %, issue #162), so the residual is the correlation's, not a coding error (measured 2026-10-22 after the D-term fix, PR #161 table).
- `srk-mathias-copeman-ng-dew-morch-243.4K-0.30MPa` — dew_P +25.9% (377757 vs 300000) - Mathias-Copeman alpha (published constants where fitted) inherits SRK property limits (measured 2026-10-22, PR #161 table).
- `srk-mathias-copeman-ng-dew-morch-254.6K-0.68MPa` — dew_P +13.8% (774020 vs 680000) - Mathias-Copeman alpha (published constants where fitted) inherits SRK property limits (measured 2026-10-22, PR #161 table).
- `srk-mathias-copeman-ng-dew-morch-260.8K-1.04MPa` — dew_P +10.7% (1.15151e+06 vs 1.04e+06) - Mathias-Copeman alpha (published constants where fitted) inherits SRK property limits (measured 2026-10-22, PR #161 table).
- `srk-mathias-copeman-pure-C3-300K` — rho_L -8.1% (449.628 vs 489.447) - Mathias-Copeman alpha (published constants where fitted) inherits SRK property limits (measured 2026-10-22, PR #161 table).
- `srk-mathias-copeman-pure-CO2-265K` — Cp +7.2% (110.429 vs 103.056); rho_L -11.7% (859.249 vs 973.254) - Mathias-Copeman alpha (published constants where fitted) inherits SRK property limits (measured 2026-10-22, PR #161 table).
- `srk-peneloux-c1co2-277.15K-5.97MPa` — bubble_P -3.3% (5.77391e+06 vs 5.97e+06) - Peneloux-Rauzy-Freze translation corrects liquid volume only; VLE and Cp deviations inherited from SRK (measured 2026-10-22, PR #161 table).
- `srk-peneloux-ng-dew-morch-243.4K-0.30MPa` — dew_P +25.9% (377792 vs 300000) - Peneloux-Rauzy-Freze translation corrects liquid volume only; VLE and Cp deviations inherited from SRK (measured 2026-10-22, PR #161 table).
- `srk-peneloux-ng-dew-morch-254.6K-0.68MPa` — dew_P +13.8% (774165 vs 680000) - Peneloux-Rauzy-Freze translation corrects liquid volume only; VLE and Cp deviations inherited from SRK (measured 2026-10-22, PR #161 table).
- `srk-peneloux-ng-dew-morch-260.8K-1.04MPa` — dew_P +10.8% (1.15189e+06 vs 1.04e+06) - Peneloux-Rauzy-Freze translation corrects liquid volume only; VLE and Cp deviations inherited from SRK (measured 2026-10-22, PR #161 table).
- `srk-peneloux-pure-C1-125K` — Cp +6.9% (61.7209 vs 57.7411) - Peneloux-Rauzy-Freze translation corrects liquid volume only; VLE and Cp deviations inherited from SRK (measured 2026-10-22, PR #161 table).
- `srk-peneloux-pure-C3-300K` — Cp +6.7% (128.942 vs 120.805) - Peneloux-Rauzy-Freze translation corrects liquid volume only; VLE and Cp deviations inherited from SRK (measured 2026-10-22, PR #161 table).
- `srk-peneloux-pure-CO2-265K` — Cp +12.2% (115.671 vs 103.056) - Peneloux-Rauzy-Freze translation corrects liquid volume only; VLE and Cp deviations inherited from SRK (measured 2026-10-22, PR #161 table).
- `twu-pr-ng-dew-morch-243.4K-0.30MPa` — dew_P +29.3% (387803 vs 300000) - Twu alpha (generalized omega correlation) inherits PR property limits (measured 2026-10-22, PR #161 table).
- `twu-pr-ng-dew-morch-254.6K-0.68MPa` — dew_P +18.0% (802379 vs 680000) - Twu alpha (generalized omega correlation) inherits PR property limits (measured 2026-10-22, PR #161 table).
- `twu-pr-ng-dew-morch-260.8K-1.04MPa` — dew_P +15.8% (1.20473e+06 vs 1.04e+06) - Twu alpha (generalized omega correlation) inherits PR property limits (measured 2026-10-22, PR #161 table).
- `twu-pr-pure-C1-125K` — rho_L +11.9% (449.803 vs 402.111) - Twu alpha (generalized omega correlation) inherits PR property limits (measured 2026-10-22, PR #161 table).
- `twu-pr-pure-CO2-265K` — Cp +8.6% (111.963 vs 103.056) - Twu alpha (generalized omega correlation) inherits PR property limits (measured 2026-10-22, PR #161 table).
- `twu-srk-ng-dew-morch-243.4K-0.30MPa` — dew_P +28.7% (386167 vs 300000) - Twu alpha (generalized omega correlation) inherits SRK property limits (measured 2026-10-22, PR #161 table).
- `twu-srk-ng-dew-morch-254.6K-0.68MPa` — dew_P +16.7% (793289 vs 680000) - Twu alpha (generalized omega correlation) inherits SRK property limits (measured 2026-10-22, PR #161 table).
- `twu-srk-ng-dew-morch-260.8K-1.04MPa` — dew_P +13.6% (1.18184e+06 vs 1.04e+06) - Twu alpha (generalized omega correlation) inherits SRK property limits (measured 2026-10-22, PR #161 table).
- `twu-srk-pure-C3-300K` — rho_L -8.3% (448.891 vs 489.447) - Twu alpha (generalized omega correlation) inherits SRK property limits (measured 2026-10-22, PR #161 table).
- `twu-srk-pure-CO2-265K` — Cp +8.6% (111.892 vs 103.056); rho_L -11.6% (859.886 vs 973.254) - Twu alpha (generalized omega correlation) inherits SRK property limits (measured 2026-10-22, PR #161 table).
- `vdw-c1c3-294.26K-6.895MPa` — bubble_P -28.3% (4.94511e+06 vs 6.895e+06); vapor_comp -16.1% (0.588384 vs 0.7497) - van der Waals attraction term (crudest EOS form): VLE and density outside bands by design (measured 2026-10-22, PR #161 table).
- `vdw-ng-dew-morch-243.4K-0.30MPa` — dew_P +2621.5% (8.16458e+06 vs 300000) - van der Waals attraction term (crudest EOS form): VLE and density outside bands by design (measured 2026-10-22, PR #161 table).
- `vdw-ng-dew-morch-254.6K-0.68MPa` — dew_P +1218.3% (8.96451e+06 vs 680000) - van der Waals attraction term (crudest EOS form): VLE and density outside bands by design (measured 2026-10-22, PR #161 table).
- `vdw-ng-dew-morch-260.8K-1.04MPa` — dew_P +802.8% (9.38871e+06 vs 1.04e+06) - van der Waals attraction term (crudest EOS form): VLE and density outside bands by design (measured 2026-10-22, PR #161 table).
- `vdw-pure-C1-125K` — Cp -26.6% (42.3955 vs 57.7411); rho_L -31.7% (274.752 vs 402.111) - van der Waals attraction term (crudest EOS form): VLE and density outside bands by design (measured 2026-10-22, PR #161 table).
- `vdw-pure-C3-300K` — Cp -19.5% (97.2117 vs 120.805); rho_L -38.0% (303.464 vs 489.447); rho_V -6.3% (20.2625 vs 21.6295) - van der Waals attraction term (crudest EOS form): VLE and density outside bands by design (measured 2026-10-22, PR #161 table).
- `vdw-pure-CO2-265K` — Cp -19.4% (83.02 vs 103.056); rho_L -41.4% (570.303 vs 973.254); rho_V -9.1% (68.5717 vs 75.4708) - van der Waals attraction term (crudest EOS form): VLE and density outside bands by design (measured 2026-10-22, PR #161 table).
- `vdw-pure-nC4-280K` — Cp -24.2% (103.265 vs 136.28); rho_L -38.1% (367.122 vs 593.294) - van der Waals attraction term (crudest EOS form): VLE and density outside bands by design (measured 2026-10-22, PR #161 table).
- `zudkevitch-joffe-rk-c1c3-294.26K-6.895MPa` — bubble_P -5.6% (6.51215e+06 vs 6.895e+06) - ZJ fit targets Psat and Rackett volume only; other properties outside bands by design (measured 2026-10-22, PR #161 table).
- `zudkevitch-joffe-rk-ng-dew-morch-243.4K-0.30MPa` — dew_P +30.3% (390931 vs 300000) - ZJ fit targets Psat and Rackett volume only; other properties outside bands by design (measured 2026-10-22, PR #161 table).
- `zudkevitch-joffe-rk-ng-dew-morch-254.6K-0.68MPa` — dew_P +17.5% (798943 vs 680000) - ZJ fit targets Psat and Rackett volume only; other properties outside bands by design (measured 2026-10-22, PR #161 table).
- `zudkevitch-joffe-rk-ng-dew-morch-260.8K-1.04MPa` — dew_P +14.2% (1.18794e+06 vs 1.04e+06) - ZJ fit targets Psat and Rackett volume only; other properties outside bands by design (measured 2026-10-22, PR #161 table).
- `zudkevitch-joffe-rk-pure-C3-300K` — rho_L -8.2% (449.204 vs 489.447) - ZJ fit targets Psat and Rackett volume only; other properties outside bands by design (measured 2026-10-22, PR #161 table).
- `zudkevitch-joffe-rk-pure-CO2-265K` — Cp +8.7% (111.975 vs 103.056); rho_L -11.6% (860.146 vs 973.254) - ZJ fit targets Psat and Rackett volume only; other properties outside bands by design (measured 2026-10-22, PR #161 table).

## Reference sources

Pure-fluid expected values are generated from the CoolProp reference EOS (version in `results.json`); `source: coolprop:<fluid>`. Literature values are hand-typed with the retrieval date; unique sources:

- AGA Report No. 8 Part 1&2 supplementary test data tables (NIST AGA8 distribution, pages.nist.gov/AGA8, Test Data.xls, Binary Mixture Calculations sheet, GERG-2008 column, methane/nitrogen 50/50 mol %); retrieved 2026-10-21
- Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 312.91 K; DDB Explorer Edition data set 467; retrieved 2026-10-20
- Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 322.91 K; DDB Explorer Edition data set 468; retrieved 2026-10-20
- Bennett (1929) J. Chem. Educ. 6, pp. 1544-1549, isobaric 97.99 kPa; DDB Explorer Edition data set 466; retrieved 2026-10-20
- Coker, Perry's Chemical Engineers' Handbook, McGraw-Hill, T-x-y table for ethylene glycol/water at 760 mmHg (Elsevier companion Fig. M-46); retrieved 2026-10-21
- Courtial, Soo, Coquelet, Paricaud, Ramjugernath & Richon (2009) Fluid Phase Equilib. 277, pp. 152-161, Table 4, 323.22 K isotherm; retrieved 2026-10-21
- Culberson & McKetta (1951) J. Pet. Technol. 3, 223-226; IUPAC SDS 27/28 printed p. 31, 100 F isotherm; retrieved 2026-10-20
- Culberson & McKetta (1951) J. Pet. Technol. 3, 223-226; IUPAC SDS 27/28 printed p. 32, 160 F isotherm; retrieved 2026-10-20
- Culberson & McKetta (1951) J. Pet. Technol. 3, 223-226; IUPAC SDS 27/28 printed p. 32, 280 F isotherm; retrieved 2026-10-20
- Culberson & McKetta, methane in water, J. Petrol. Technol., vol. 3, p. 223, 1951, as compiled in the IUPAC Solubility Data Series vol. 27/28 (Methane), pp. 31-32, https://iupac.github.io/SolubilityDataSeries/volumes/SDS-27-28.pdf; x_C1 0.001000 at 4.54 MPa; retrieved 2026-10-21
- Culberson & McKetta, methane in water, J. Petrol. Technol., vol. 3, p. 223, 1951, as compiled in the IUPAC Solubility Data Series vol. 27/28 (Methane), pp. 31-32, https://iupac.github.io/SolubilityDataSeries/volumes/SDS-27-28.pdf; x_C1 0.001123 at 6.55 MPa; retrieved 2026-10-21
- DePriester (1953) Chem. Eng. Prog. Symp. Ser. 49(7), p. 42, high-T nomogram (as Fig. 10.14 in Felder & Rousseau), read at 500 psia / 80.33 F; retrieved 2026-10-20
- Ethanol/water azeotrope at 760 mmHg: b.p. 78.20 C, 4.40 wt% water (x_EtOH = 0.8947 mole fraction) - Edinburgh Azeotrope Database (homepages.ed.ac.uk/jwp/Chemeng/azeotrope/EE.html, CRC Handbook/Lange compilation); retrieved 2026-10-21
- Janisch, Raabe & Kohler (2007) J. Chem. Eng. Data 52, 1897-1903, via NIST ThermoML (doi 10.1021/je700210n), CH4+N2 149.989 K isotherm; retrieved 2026-10-21
- Janisch, Raabe & Kohler (2007) J. Chem. Eng. Data 52, 1897-1903, via NIST ThermoML (doi 10.1021/je700210n), CH4+N2 159.972 K isotherm; retrieved 2026-10-21
- Janisch, Raabe & Kohler (2007) J. Chem. Eng. Data 52, 1897-1903, via NIST ThermoML (doi 10.1021/je700210n), CH4+N2 179.976 K isotherm; retrieved 2026-10-21
- Jou, Mather & Otto 1982 H2S isotherm, 4.28 kmol/m3 aqueous MDEA at 313.15 K (I&EC Process Des. Dev., vol. 21, p. 539, 1982): p_H2S 0.0108 kPa at loading 0.01, 3.31 kPa at 0.165, 36.9 kPa at 0.453, as curated in tests/units/test_mdea_equilibrium.py; retrieved 2026-10-21
- Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20
- Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21
- NIST Chemistry WebBook, NIST Standard Reference Database 69, water (C7732185) saturation table (IAPWS-95 based fluid data), webbook.nist.gov; retrieved 2026-10-21
- Petropoulou, Voutsas, Westman, Austegard, Lovseth & Stang (2018) Fluid Phase Equilib. 462, 44-58, via NIST ThermoML (doi 10.1016/j.fluid.2018.01.011), 293.13 K isotherm; retrieved 2026-10-21
- Petropoulou, Voutsas, Westman, Austegard, Lovseth & Stang (2018) Fluid Phase Equilib. 462, 44-58, via NIST ThermoML (doi 10.1016/j.fluid.2018.01.011), 298.14 K isotherm; retrieved 2026-10-21
- Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 270, 277.59 K isotherm; retrieved 2026-10-20
- Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 294.26 K isotherm; retrieved 2026-10-20
- Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 310.93 K isotherm; retrieved 2026-10-20
- Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 327.59 K isotherm; retrieved 2026-10-20
- Reamer, Sage & Lacey, methane-propane VLE, Ind. Eng. Chem., vol. 42, p. 534, 1950, as compiled in the IUPAC Solubility Data Series vol. 27/28 (Methane), pp. 270-271, https://iupac.github.io/SolubilityDataSeries/volumes/SDS-27-28.pdf; x_C1 0.1987, y_C1 0.7038; retrieved 2026-10-21
- Reamer, Sage & Lacey, methane-propane VLE, Ind. Eng. Chem., vol. 42, p. 534, 1950, as compiled in the IUPAC Solubility Data Series vol. 27/28 (Methane), pp. 270-271, https://iupac.github.io/SolubilityDataSeries/volumes/SDS-27-28.pdf; x_C1 0.2834, y_C1 0.8135; retrieved 2026-10-21
- p_CO2 at fixed loading, 4.3638 kmol/m3 (50 wt%) aqueous MDEA at 313.15 K: 0.0093 bara at loading 0.10 and 0.229 bara at loading 0.40 — NeqSim MDEA-model regression anchors (apparent constants fitted to Jou, Mather & Otto, I&EC Process Des. Dev., vol. 21, p. 539, 1982), as curated in tests/units/test_mdea_equilibrium.py; retrieved 2026-10-21

## How to add a case

1. Add an entry to `data/validation/cases.yaml` (`binary_cases`/`multicomponent_cases`) with `id`, `package`, `components`, `z`, `T` (and/or `P`), `expected` (`vf`, `rho_V`, `rho_L`, `H`, `S`, `Cp`, `bubble_P`, `dew_P`, `bubble_T`, `K`, `vapor_comp`, `liquid_comp`), a `source` with authors, journal, year, table/page and retrieval date, and — only where the spec's fixed policy does not apply — a `tolerance`.
2. Pure-fluid points: add a `pure_cases` entry, then run `uv run python scripts/validate_properties.py --regen-coolprop` to fill `expected`.
3. Run `uv run python scripts/validate_properties.py --write-doc`, then commit `cases.yaml`, `results.json` and `docs/validation.md` together. `tests/validation/test_reference_cases.py` picks the case up automatically.

Never loosen a tolerance to make a case pass: a failing case is assessed (model limitation vs bug) and documented, not tuned away.
