# Thermo property validation report (spec P1-05)

Generated 2026-10-21T14:56:51+00:00 from `data/validation/results.json` (git b5b0eb6, CoolProp 8.0.0).
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
| [amine_enrtl](validation/amine_enrtl.md) | electrolyte | provisional | 3/3 | L1=0 L2=0 | [report](validation/amine_enrtl.md) |
| [amine_ke](validation/amine_ke.md) | electrolyte | provisional | 3/3 | L1=0 L2=0 | [report](validation/amine_ke.md) |
| [nrtl](validation/nrtl.md) | gamma_phi | provisional | 7/7 | L1=0 L2=21 | [report](validation/nrtl.md) |
| [pr](validation/pr.md) | cubic | validated | 7/7 | L1=40 L2=52 | [report](validation/pr.md) |
| [pr78](validation/pr78.md) | cubic | validated | 7/7 | L1=40 L2=52 | [report](validation/pr78.md) |
| [srk](validation/srk.md) | cubic | validated | 7/7 | L1=40 L2=52 | [report](validation/srk.md) |

### L4 cross-model pairs on the natural-gas slice feed

- `nrtl-pr`: ok — n/a — refuses the slice feed: ValueError: ChemSep NRTL databank has no fitted binary parameters for pair C1 (74-82-8) / C2 (74-84-0); refusing to flash a zero-filled (ideal) pair matrix - select a thermo model whose databank covers this component support
- `nrtl-pr78`: ok — n/a — refuses the slice feed: ValueError: ChemSep NRTL databank has no fitted binary parameters for pair C1 (74-82-8) / C2 (74-84-0); refusing to flash a zero-filled (ideal) pair matrix - select a thermo model whose databank covers this component support
- `nrtl-srk`: ok — n/a — refuses the slice feed: ValueError: ChemSep NRTL databank has no fitted binary parameters for pair C1 (74-82-8) / C2 (74-84-0); refusing to flash a zero-filled (ideal) pair matrix - select a thermo model whose databank covers this component support
- `pr-pr78`: ok — dew P 717386 vs 717386 (rel 0); rhoV 6.08846 vs 6.08846 (rel 0); band 20%
- `pr-srk`: ok — dew P 717386 vs 614969 (rel 0.167); rhoV 6.08846 vs 5.18049 (rel 0.175); band 20%
- `pr78-srk`: ok — dew P 717386 vs 614969 (rel 0.167); rhoV 6.08846 vs 5.18049 (rel 0.175); band 20%

## Results

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
| bubble_P | 74 | 66 | 89.2 % |
| dew_P | 43 | 40 | 93.0 % |
| liquid_comp | 18 | 18 | 100.0 % |
| rho_L | 40 | 26 | 65.0 % |
| rho_V | 40 | 36 | 90.0 % |
| vapor_comp | 20 | 15 | 75.0 % |

### package `pr78` — 213/278 pass (76.6 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| Cp | 40 | 11 | 27.5 % |
| K | 3 | 1 | 33.3 % |
| bubble_P | 74 | 66 | 89.2 % |
| dew_P | 43 | 40 | 93.0 % |
| liquid_comp | 18 | 18 | 100.0 % |
| rho_L | 40 | 26 | 65.0 % |
| rho_V | 40 | 36 | 90.0 % |
| vapor_comp | 20 | 15 | 75.0 % |

### package `srk` — 201/278 pass (72.3 %)

| property | n | pass | rate |
| --- | --- | --- | --- |
| Cp | 40 | 11 | 27.5 % |
| K | 3 | 1 | 33.3 % |
| bubble_P | 74 | 64 | 86.5 % |
| dew_P | 43 | 40 | 93.0 % |
| liquid_comp | 18 | 18 | 100.0 % |
| rho_L | 40 | 18 | 45.0 % |
| rho_V | 40 | 33 | 82.5 % |
| vapor_comp | 20 | 16 | 80.0 % |

## Failing comparisons (240)

| case | package | property | expected | got | err | source |
| --- | --- | --- | --- | --- | --- | --- |
| pure-H2O-614.7K | srk | Cp | 151.747 | 229.506 | 0.512425 | coolprop:Water |
| pure-H2O-614.7K | pr | Cp | 151.747 | 220.634 | 0.453959 | coolprop:Water |
| pure-H2O-614.7K | pr78 | Cp | 151.747 | 220.634 | 0.453959 | coolprop:Water |
| pure-H2O-600K | srk | Cp | 125.264 | 178.303 | 0.423422 | coolprop:Water |
| pure-H2O-600K | pr | Cp | 125.264 | 171.879 | 0.372138 | coolprop:Water |
| pure-H2O-600K | pr78 | Cp | 125.264 | 171.879 | 0.372138 | coolprop:Water |
| pure-C1-181K | srk | Cp | 124.139 | 168.599 | 0.358147 | coolprop:CH4 |
| ng-dew-morch-243.4K-0.30MPa | pr | dew_P | 300000 | 406518 | 0.355061 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| ng-dew-morch-243.4K-0.30MPa | pr78 | dew_P | 300000 | 406518 | 0.355061 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| pure-N2-119.9K | srk | Cp | 125.022 | 168.848 | 0.350538 | coolprop:Nitrogen |
| pure-H2O-614.7K | srk | rho_L | 605.554 | 394.072 | 0.349237 | coolprop:Water |
| pure-H2O-600K | srk | rho_L | 649.411 | 432.471 | 0.334057 | coolprop:Water |
| pure-CO2-288.9K | srk | Cp | 155.189 | 206.216 | 0.328801 | coolprop:CO2 |
| pure-C2-290K | srk | Cp | 152.189 | 200.921 | 0.320205 | coolprop:Ethane |
| pure-H2S-354.4K | srk | Cp | 141.924 | 184.717 | 0.301517 | coolprop:H2S |
| pure-C1-181K | pr | Cp | 124.139 | 161.076 | 0.297547 | coolprop:CH4 |
| pure-C1-181K | pr78 | Cp | 124.139 | 161.076 | 0.297547 | coolprop:CH4 |
| pure-N2-119.9K | pr | Cp | 125.022 | 161.28 | 0.29001 | coolprop:Nitrogen |
| pure-N2-119.9K | pr78 | Cp | 125.022 | 161.28 | 0.29001 | coolprop:Nitrogen |
| pure-H2O-520K | srk | rho_L | 803.535 | 571.024 | 0.289359 | coolprop:Water |
| pure-CO2-285K | srk | Cp | 137.895 | 176.26 | 0.278214 | coolprop:CO2 |
| pure-CO2-288.9K | pr | Cp | 155.189 | 198.288 | 0.277714 | coolprop:CO2 |
| pure-CO2-288.9K | pr78 | Cp | 155.189 | 198.288 | 0.277714 | coolprop:CO2 |
| pure-C2-290K | pr | Cp | 152.189 | 193.22 | 0.269605 | coolprop:Ethane |
| pure-C2-290K | pr78 | Cp | 152.189 | 193.22 | 0.269605 | coolprop:Ethane |
| pure-H2O-420K | srk | rho_L | 919.929 | 674.912 | 0.266344 | coolprop:Water |
| pure-C3-351.3K | srk | Cp | 191.089 | 241.865 | 0.265722 | coolprop:Propane |
| pure-H2O-614.7K | pr | rho_L | 605.554 | 444.727 | 0.265587 | coolprop:Water |
| pure-H2O-614.7K | pr78 | rho_L | 605.554 | 444.727 | 0.265587 | coolprop:Water |
| pure-C2-285K | srk | Cp | 132.286 | 167.068 | 0.262933 | coolprop:Ethane |
| ng-dew-morch-243.4K-0.30MPa | srk | dew_P | 300000 | 377792 | 0.259308 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| pure-H2O-323.5K | srk | rho_L | 987.838 | 741.661 | 0.249207 | coolprop:Water |
| pure-H2S-354.4K | pr | Cp | 141.924 | 176.987 | 0.247053 | coolprop:H2S |
| pure-H2S-354.4K | pr78 | Cp | 141.924 | 176.987 | 0.247053 | coolprop:H2S |
| pure-H2O-600K | pr | rho_L | 649.411 | 489.546 | 0.246169 | coolprop:Water |
| pure-H2O-600K | pr78 | rho_L | 649.411 | 489.546 | 0.246169 | coolprop:Water |
| pure-nC4-403.9K | srk | Cp | 236.805 | 293.525 | 0.23952 | coolprop:n-Butane |
| pure-H2O-520K | srk | Cp | 87.149 | 107.501 | 0.233533 | coolprop:Water |
| pure-H2S-345K | srk | Cp | 112.837 | 139.176 | 0.233421 | coolprop:H2S |
| pure-C1-172K | srk | Cp | 87.1299 | 107.453 | 0.233245 | coolprop:CH4 |
| pure-CO2-285K | pr | Cp | 137.895 | 169.831 | 0.231591 | coolprop:CO2 |
| pure-CO2-285K | pr78 | Cp | 137.895 | 169.831 | 0.231591 | coolprop:CO2 |
| pure-C3-351.3K | pr | Cp | 191.089 | 234.044 | 0.224791 | coolprop:Propane |
| pure-C3-351.3K | pr78 | Cp | 191.089 | 234.044 | 0.224791 | coolprop:Propane |
| ng-dew-morch-254.6K-0.68MPa | pr | dew_P | 680000 | 829096 | 0.219259 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| ng-dew-morch-254.6K-0.68MPa | pr78 | dew_P | 680000 | 829096 | 0.219259 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| pure-C2-285K | pr | Cp | 132.286 | 161.185 | 0.218456 | coolprop:Ethane |
| pure-C2-285K | pr78 | Cp | 132.286 | 161.185 | 0.218456 | coolprop:Ethane |
| pure-nC4-403.9K | pr | Cp | 236.805 | 285.411 | 0.205254 | coolprop:n-Butane |
| pure-nC4-403.9K | pr78 | Cp | 236.805 | 285.411 | 0.205254 | coolprop:n-Butane |
| pure-N2-112K | srk | Cp | 81.2659 | 97.1906 | 0.195958 | coolprop:Nitrogen |
| pure-H2O-520K | pr | rho_L | 803.535 | 648.154 | 0.193371 | coolprop:Water |
| pure-H2O-520K | pr78 | rho_L | 803.535 | 648.154 | 0.193371 | coolprop:Water |
| ng-dew-morch-260.8K-1.04MPa | pr | dew_P | 1.04e+06 | 1.2378e+06 | 0.190196 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| ng-dew-morch-260.8K-1.04MPa | pr78 | dew_P | 1.04e+06 | 1.2378e+06 | 0.190196 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| pure-H2S-345K | pr | Cp | 112.837 | 133.856 | 0.186276 | coolprop:H2S |
| pure-H2S-345K | pr78 | Cp | 112.837 | 133.856 | 0.186276 | coolprop:H2S |
| meohh2o-312.91K-9.079kPa | nrtl | bubble_P | 9079 | 10747.1 | 0.183734 | literature:Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 312.91 K; DDB Explorer Edition data set 467; retrieved 2026-10-20 |
| pure-C1-172K | pr | Cp | 87.1299 | 103.117 | 0.183483 | coolprop:CH4 |
| pure-C1-172K | pr78 | Cp | 87.1299 | 103.117 | 0.183483 | coolprop:CH4 |
| pure-nC4-403.9K | srk | rho_L | 397.325 | 324.829 | 0.182461 | coolprop:n-Butane |
| pure-H2O-520K | pr | Cp | 87.149 | 102.925 | 0.181022 | coolprop:Water |
| pure-H2O-520K | pr78 | Cp | 87.149 | 102.925 | 0.181022 | coolprop:Water |
| pure-C3-340K | srk | Cp | 158.07 | 186.594 | 0.180451 | coolprop:Propane |
| pure-CO2-288.9K | srk | rho_L | 814.639 | 672.534 | 0.17444 | coolprop:CO2 |
| pure-MeOH-330K-nrtl | nrtl | Cp | 88.5047 | 73.1651 | 0.173319 | coolprop:Methanol |
| pure-H2O-420K | pr | rho_L | 919.929 | 762.594 | 0.17103 | coolprop:Water |
| pure-H2O-420K | pr78 | rho_L | 919.929 | 762.594 | 0.17103 | coolprop:Water |
| pure-C3-351.3K | srk | rho_L | 379.569 | 314.954 | 0.170233 | coolprop:Propane |
| slice-inlet-K-500psia-300K | srk | K | 5.1 | 5.96141 | 0.168903 | literature:DePriester (1953) Chem. Eng. Prog. Symp. Ser. 49(7), p. 42, high-T nomogram (as Fig. 10.14 in Felder & Rousseau), read at 500 psia / 80.33 F; retrieved 2026-10-20 |
| pure-H2O-420K | srk | Cp | 77.4472 | 90.3881 | 0.167094 | coolprop:Water |
| pure-CO2-285K | srk | rho_L | 847.046 | 709.912 | 0.161897 | coolprop:CO2 |
| pure-C2-290K | srk | rho_L | 351.314 | 295.002 | 0.16029 | coolprop:Ethane |
| meohh2o-312.91K-13.012kPa | nrtl | bubble_P | 13012 | 15092.3 | 0.159878 | literature:Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 312.91 K; DDB Explorer Edition data set 467; retrieved 2026-10-20 |
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
| pure-C3-340K | srk | rho_L | 411.774 | 353.492 | 0.141538 | coolprop:Propane |
| pure-C1-181K | srk | rho_L | 271.913 | 233.607 | 0.140876 | coolprop:CH4 |
| ng-dew-morch-254.6K-0.68MPa | srk | dew_P | 680000 | 774165 | 0.138477 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
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
| pure-CO2-265K | srk | Cp | 103.056 | 115.671 | 0.12241 | coolprop:CO2 |
| pure-H2O-370K-nrtl | nrtl | Cp | 75.8833 | 66.6483 | 0.1217 | coolprop:Water |
| pure-H2S-187.8K | pr | Cp | 68.8292 | 60.4703 | 0.121444 | coolprop:H2S |
| pure-H2S-187.8K | pr78 | Cp | 68.8292 | 60.4703 | 0.121444 | coolprop:H2S |
| pure-CO2-265K | srk | rho_L | 973.254 | 857.989 | 0.118433 | coolprop:CO2 |
| pure-C1-125K | pr | rho_L | 402.111 | 449.652 | 0.11823 | coolprop:CH4 |
| pure-C1-125K | pr78 | rho_L | 402.111 | 449.652 | 0.11823 | coolprop:CH4 |
| meohh2o-312.91K-16.319kPa | nrtl | bubble_P | 16319 | 18215.9 | 0.116242 | literature:Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 312.91 K; DDB Explorer Edition data set 467; retrieved 2026-10-20 |
| pure-H2S-345K | srk | rho_L | 628.082 | 556.936 | 0.113275 | coolprop:H2S |
| pure-MeOH-305K-nrtl | nrtl | Cp | 82.6135 | 73.3846 | 0.111712 | coolprop:Methanol |
| slice-inlet-K-500psia-300K | pr | K | 1.17 | 1.04263 | 0.108863 | literature:DePriester (1953) Chem. Eng. Prog. Symp. Ser. 49(7), p. 42, high-T nomogram (as Fig. 10.14 in Felder & Rousseau), read at 500 psia / 80.33 F; retrieved 2026-10-20 |
| slice-inlet-K-500psia-300K | pr78 | K | 1.17 | 1.04263 | 0.108863 | literature:DePriester (1953) Chem. Eng. Prog. Symp. Ser. 49(7), p. 42, high-T nomogram (as Fig. 10.14 in Felder & Rousseau), read at 500 psia / 80.33 F; retrieved 2026-10-20 |
| ng-dew-morch-260.8K-1.04MPa | srk | dew_P | 1.04e+06 | 1.15189e+06 | 0.107589 | literature:Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21 |
| pure-H2O-614.7K | srk | rho_V | 95.5877 | 85.4882 | 0.105657 | coolprop:Water |
| pure-H2O-420K | pr | Cp | 77.4472 | 85.5571 | 0.104716 | coolprop:Water |
| pure-H2O-420K | pr78 | Cp | 77.4472 | 85.5571 | 0.104716 | coolprop:Water |
| meohh2o-322.91K-15.932kPa | nrtl | bubble_P | 15932 | 17553.7 | 0.101786 | literature:Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 322.91 K; DDB Explorer Edition data set 468; retrieved 2026-10-20 |
| pure-C2-250K | srk | Cp | 90.0242 | 99.0394 | 0.100142 | coolprop:Ethane |
| pure-nC4-350K | srk | rho_L | 505.177 | 454.822 | 0.0996774 | coolprop:n-Butane |
| pure-C1-172K | srk | rho_L | 304.559 | 274.35 | 0.0991902 | coolprop:CH4 |
| slice-inlet-K-500psia-300K | srk | K | 1.17 | 1.05444 | 0.098766 | literature:DePriester (1953) Chem. Eng. Prog. Symp. Ser. 49(7), p. 42, high-T nomogram (as Fig. 10.14 in Felder & Rousseau), read at 500 psia / 80.33 F; retrieved 2026-10-20 |
| pure-N2-100K | pr | rho_L | 689.353 | 756.188 | 0.0969532 | coolprop:Nitrogen |
| pure-N2-100K | pr78 | rho_L | 689.353 | 756.188 | 0.0969532 | coolprop:Nitrogen |
| pure-N2-100K | srk | Cp | 64.9347 | 71.168 | 0.0959925 | coolprop:Nitrogen |
| meohh2o-312.91K-9.079kPa | nrtl | vapor_comp | 0.2559 | 0.350953 | 0.0950533 | literature:Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 312.91 K; DDB Explorer Edition data set 467; retrieved 2026-10-20 |
| meohh2o-322.91K-26.131kPa | nrtl | bubble_P | 26131 | 28604.1 | 0.0946409 | literature:Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 322.91 K; DDB Explorer Edition data set 468; retrieved 2026-10-20 |
| pure-H2S-240K | pr | rho_L | 899.829 | 984.26 | 0.0938308 | coolprop:H2S |
| pure-H2S-240K | pr78 | rho_L | 899.829 | 984.26 | 0.0938308 | coolprop:H2S |
| pure-CO2-240K | srk | rho_L | 1088.87 | 990.451 | 0.090386 | coolprop:CO2 |
| pure-H2S-187.8K | pr | rho_L | 992.142 | 1080.56 | 0.0891218 | coolprop:H2S |
| pure-H2S-187.8K | pr78 | rho_L | 992.142 | 1080.56 | 0.0891218 | coolprop:H2S |
| pure-CO2-216.7K | pr | Cp | 85.9712 | 78.3254 | 0.0889347 | coolprop:CO2 |
| pure-CO2-216.7K | pr78 | Cp | 85.9712 | 78.3254 | 0.0889347 | coolprop:CO2 |
| pure-H2O-600K | srk | rho_V | 72.8423 | 66.4763 | 0.0873949 | coolprop:Water |
| pure-C2-200K | pr | rho_L | 523.977 | 568.762 | 0.0854708 | coolprop:Ethane |
| pure-C2-200K | pr78 | rho_L | 523.977 | 568.762 | 0.0854708 | coolprop:Ethane |
| pure-C2-152.7K | pr | rho_L | 582.054 | 631.691 | 0.0852782 | coolprop:Ethane |
| pure-C2-152.7K | pr78 | rho_L | 582.054 | 631.691 | 0.0852782 | coolprop:Ethane |
| pure-C3-300K | srk | rho_L | 489.447 | 448.204 | 0.0842657 | coolprop:Propane |
| pure-C1-155K | pr | Cp | 67.6129 | 73.2856 | 0.0839003 | coolprop:CH4 |
| pure-C1-155K | pr78 | Cp | 67.6129 | 73.2856 | 0.0839003 | coolprop:CH4 |
| pure-H2S-300K | srk | Cp | 77.0817 | 83.4648 | 0.0828093 | coolprop:H2S |
| pure-N2-63.2K | pr | Cp | 56.0355 | 51.4237 | 0.0823021 | coolprop:Nitrogen |
| pure-N2-63.2K | pr78 | Cp | 56.0355 | 51.4237 | 0.0823021 | coolprop:Nitrogen |
| pure-CO2-265K | pr | Cp | 103.056 | 111.409 | 0.0810613 | coolprop:CO2 |
| pure-CO2-265K | pr78 | Cp | 103.056 | 111.409 | 0.0810613 | coolprop:CO2 |
| pure-H2O-323.5K | pr | Cp | 75.3335 | 81.2495 | 0.0785313 | coolprop:Water |
| pure-H2O-323.5K | pr78 | Cp | 75.3335 | 81.2495 | 0.0785313 | coolprop:Water |
| pure-C3-184.9K | pr | Cp | 91.8478 | 84.9224 | 0.0754009 | coolprop:Propane |
| pure-C3-184.9K | pr78 | Cp | 91.8478 | 84.9224 | 0.0754009 | coolprop:Propane |
| pure-H2O-340K-nrtl | nrtl | Cp | 75.4562 | 70.2529 | 0.0689572 | coolprop:Water |
| pure-C1-125K | srk | Cp | 57.7411 | 61.7209 | 0.0689238 | coolprop:CH4 |
| pure-H2O-614.7K | pr | rho_V | 95.5877 | 89.0623 | 0.0682662 | coolprop:Water |
| pure-H2O-614.7K | pr78 | rho_V | 95.5877 | 89.0623 | 0.0682662 | coolprop:Water |
| pure-C3-300K | srk | Cp | 120.805 | 128.942 | 0.0673599 | coolprop:Propane |
| meohh2o-97.99kPa-353.25K | nrtl | vapor_comp | 0.568 | 0.501294 | 0.0667056 | literature:Bennett (1929) J. Chem. Educ. 6, pp. 1544-1549, isobaric 97.99 kPa; DDB Explorer Edition data set 466; retrieved 2026-10-20 |
| pure-H2S-187.8K | srk | Cp | 68.8292 | 64.4186 | 0.0640809 | coolprop:H2S |
| pure-nC4-350K | srk | Cp | 163.885 | 174.284 | 0.0634523 | coolprop:n-Butane |
| meohh2o-312.91K-20.705kPa | nrtl | bubble_P | 20705 | 22016.4 | 0.0633373 | literature:Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 312.91 K; DDB Explorer Edition data set 467; retrieved 2026-10-20 |
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
| pure-C1-95.3K | srk | Cp | 54.3155 | 57.3174 | 0.0552677 | coolprop:CH4 |
| pure-H2S-240K | pr | Cp | 68.4609 | 64.6799 | 0.0552282 | coolprop:H2S |
| pure-H2S-240K | pr78 | Cp | 68.4609 | 64.6799 | 0.0552282 | coolprop:H2S |
| meohh2o-97.99kPa-349.05K | nrtl | vapor_comp | 0.68 | 0.627719 | 0.0522811 | literature:Bennett (1929) J. Chem. Educ. 6, pp. 1544-1549, isobaric 97.99 kPa; DDB Explorer Edition data set 466; retrieved 2026-10-20 |
| meohh2o-312.91K-13.012kPa | nrtl | vapor_comp | 0.6214 | 0.570676 | 0.0507236 | literature:Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 312.91 K; DDB Explorer Edition data set 467; retrieved 2026-10-20 |
| meohh2o-97.99kPa-360.65K | nrtl | vapor_comp | 0.391 | 0.341179 | 0.049821 | literature:Bennett (1929) J. Chem. Educ. 6, pp. 1544-1549, isobaric 97.99 kPa; DDB Explorer Edition data set 466; retrieved 2026-10-20 |
| c1c3-294.26K-9.653MPa | pr | vapor_comp | 0.7309 | 0.681898 | 0.0490015 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 294.26 K isotherm; retrieved 2026-10-20 |
| c1c3-294.26K-9.653MPa | pr78 | vapor_comp | 0.7309 | 0.681898 | 0.0490015 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 294.26 K isotherm; retrieved 2026-10-20 |
| meohh2o-312.91K-27.518kPa | nrtl | bubble_P | 27518 | 28779.4 | 0.0458403 | literature:Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 312.91 K; DDB Explorer Edition data set 467; retrieved 2026-10-20 |
| meohh2o-312.91K-20.705kPa | nrtl | vapor_comp | 0.8053 | 0.759733 | 0.0455667 | literature:Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 312.91 K; DDB Explorer Edition data set 467; retrieved 2026-10-20 |
| c1c3-327.59K-7.584MPa | pr | vapor_comp | 0.5546 | 0.512239 | 0.0423606 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 327.59 K isotherm; retrieved 2026-10-20 |
| c1c3-327.59K-7.584MPa | pr78 | vapor_comp | 0.5546 | 0.512239 | 0.0423606 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 327.59 K isotherm; retrieved 2026-10-20 |
| c1c3-277.59K-1.724MPa | pr | bubble_P | 1.724e+06 | 1.65127e+06 | 0.0421879 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 270, 277.59 K isotherm; retrieved 2026-10-20 |
| c1c3-277.59K-1.724MPa | pr78 | bubble_P | 1.724e+06 | 1.65127e+06 | 0.0421879 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 270, 277.59 K isotherm; retrieved 2026-10-20 |
| c1c3-327.59K-5.861MPa | srk | bubble_P | 5.861e+06 | 5.61512e+06 | 0.0419517 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 327.59 K isotherm; retrieved 2026-10-20 |
| meohh2o-97.99kPa-369.65K | nrtl | vapor_comp | 0.103 | 0.0615315 | 0.0414685 | literature:Bennett (1929) J. Chem. Educ. 6, pp. 1544-1549, isobaric 97.99 kPa; DDB Explorer Edition data set 466; retrieved 2026-10-20 |
| c1c3-327.59K-5.861MPa | pr | bubble_P | 5.861e+06 | 5.62072e+06 | 0.0409961 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 327.59 K isotherm; retrieved 2026-10-20 |
| c1c3-327.59K-5.861MPa | pr78 | bubble_P | 5.861e+06 | 5.62072e+06 | 0.0409961 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 327.59 K isotherm; retrieved 2026-10-20 |
| c1c3-327.59K-7.584MPa | pr | bubble_P | 7.584e+06 | 7.27362e+06 | 0.0409253 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 327.59 K isotherm; retrieved 2026-10-20 |
| c1c3-327.59K-7.584MPa | pr78 | bubble_P | 7.584e+06 | 7.27362e+06 | 0.0409253 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 327.59 K isotherm; retrieved 2026-10-20 |
| pure-H2O-520K | srk | rho_V | 18.9001 | 18.1349 | 0.0404873 | coolprop:Water |
| c1c3-327.59K-7.239MPa | pr | vapor_comp | 0.5532 | 0.513071 | 0.040129 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 327.59 K isotherm; retrieved 2026-10-20 |
| c1c3-327.59K-7.239MPa | pr78 | vapor_comp | 0.5532 | 0.513071 | 0.040129 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 327.59 K isotherm; retrieved 2026-10-20 |
| c1c3-327.59K-7.584MPa | srk | bubble_P | 7.584e+06 | 7.28246e+06 | 0.0397602 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 327.59 K isotherm; retrieved 2026-10-20 |
| pure-H2S-354.4K | srk | rho_V | 133.989 | 128.7 | 0.0394728 | coolprop:H2S |
| pure-nC4-403.9K | srk | rho_V | 80.697 | 77.5239 | 0.0393202 | coolprop:n-Butane |
| c1c3-327.59K-7.239MPa | pr | bubble_P | 7.239e+06 | 6.95919e+06 | 0.0386531 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 327.59 K isotherm; retrieved 2026-10-20 |
| c1c3-327.59K-7.239MPa | pr78 | bubble_P | 7.239e+06 | 6.95919e+06 | 0.0386531 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 327.59 K isotherm; retrieved 2026-10-20 |
| c1c3-327.59K-7.239MPa | srk | bubble_P | 7.239e+06 | 6.96085e+06 | 0.0384241 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 327.59 K isotherm; retrieved 2026-10-20 |
| meohh2o-312.91K-32.571kPa | nrtl | bubble_P | 32571 | 33760.7 | 0.0365274 | literature:Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 312.91 K; DDB Explorer Edition data set 467; retrieved 2026-10-20 |
| c1c3-327.59K-4.482MPa | pr | bubble_P | 4.482e+06 | 4.3208e+06 | 0.0359663 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 327.59 K isotherm; retrieved 2026-10-20 |
| c1c3-327.59K-4.482MPa | pr78 | bubble_P | 4.482e+06 | 4.3208e+06 | 0.0359663 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 327.59 K isotherm; retrieved 2026-10-20 |
| c1c3-327.59K-4.482MPa | srk | bubble_P | 4.482e+06 | 4.32193e+06 | 0.0357143 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 327.59 K isotherm; retrieved 2026-10-20 |
| meohh2o-322.91K-31.544kPa | nrtl | vapor_comp | 0.758 | 0.723318 | 0.0346816 | literature:Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 322.91 K; DDB Explorer Edition data set 468; retrieved 2026-10-20 |
| c1co2-283.15K-7.24MPa | srk | bubble_P | 7.24e+06 | 6.99089e+06 | 0.0344076 | literature:Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20 |
| c1c3-294.26K-8.963MPa | pr | vapor_comp | 0.7561 | 0.721745 | 0.0343551 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 294.26 K isotherm; retrieved 2026-10-20 |
| c1c3-294.26K-8.963MPa | pr78 | vapor_comp | 0.7561 | 0.721745 | 0.0343551 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 294.26 K isotherm; retrieved 2026-10-20 |
| c1c3-294.26K-9.653MPa | srk | vapor_comp | 0.7309 | 0.69674 | 0.0341599 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 294.26 K isotherm; retrieved 2026-10-20 |
| c1c3-277.59K-2.758MPa | pr | bubble_P | 2.758e+06 | 2.66404e+06 | 0.0340676 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 270, 277.59 K isotherm; retrieved 2026-10-20 |
| c1c3-277.59K-2.758MPa | pr78 | bubble_P | 2.758e+06 | 2.66404e+06 | 0.0340676 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 270, 277.59 K isotherm; retrieved 2026-10-20 |
| c1co2-277.15K-4.69MPa | pr | bubble_P | 4.69e+06 | 4.53373e+06 | 0.03332 | literature:Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20 |
| c1co2-277.15K-4.69MPa | pr78 | bubble_P | 4.69e+06 | 4.53373e+06 | 0.03332 | literature:Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20 |
| meohh2o-322.91K-52.142kPa | nrtl | bubble_P | 52142 | 53876.6 | 0.0332664 | literature:Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 322.91 K; DDB Explorer Edition data set 468; retrieved 2026-10-20 |
| c1co2-288.15K-6.62MPa | srk | bubble_P | 6.62e+06 | 6.40134e+06 | 0.0330304 | literature:Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20 |
| c1co2-277.15K-5.97MPa | srk | bubble_P | 5.97e+06 | 5.77391e+06 | 0.0328465 | literature:Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20 |
| c1co2-277.15K-7.04MPa | srk | bubble_P | 7.04e+06 | 6.80905e+06 | 0.0328052 | literature:Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20 |
| pure-CO2-288.9K | srk | rho_V | 165.146 | 159.741 | 0.0327274 | coolprop:CO2 |
| pure-MeOH-330K-nrtl | nrtl | rho_V | 0.911218 | 0.882017 | 0.0320466 | coolprop:Methanol |
| pure-H2O-520K | pr | rho_V | 18.9001 | 18.2989 | 0.0318087 | coolprop:Water |
| pure-H2O-520K | pr78 | rho_V | 18.9001 | 18.2989 | 0.0318087 | coolprop:Water |
| c1co2-288.15K-6.62MPa | pr | bubble_P | 6.62e+06 | 6.41389e+06 | 0.031134 | literature:Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20 |
| c1co2-288.15K-6.62MPa | pr78 | bubble_P | 6.62e+06 | 6.41389e+06 | 0.031134 | literature:Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20 |
| c1c3-327.59K-7.584MPa | srk | vapor_comp | 0.5546 | 0.523482 | 0.031118 | literature:Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 327.59 K isotherm; retrieved 2026-10-20 |
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

- `c1c3-277.59K-1.724MPa` — k_ij=0 cubic bubble pressure / vapour composition just beyond tolerance near the mixture critical region (model limitation; assessed in docs/validation.md).
- `c1c3-277.59K-2.758MPa` — k_ij=0 cubic bubble pressure / vapour composition just beyond tolerance near the mixture critical region (model limitation; assessed in docs/validation.md).
- `c1c3-294.26K-8.274MPa` — k_ij=0 cubic bubble pressure / vapour composition just beyond tolerance near the mixture critical region (model limitation; assessed in docs/validation.md).
- `c1c3-294.26K-8.963MPa` — k_ij=0 cubic bubble pressure / vapour composition just beyond tolerance near the mixture critical region (model limitation; assessed in docs/validation.md).
- `c1c3-294.26K-9.653MPa` — k_ij=0 cubic bubble pressure / vapour composition just beyond tolerance near the mixture critical region (model limitation; assessed in docs/validation.md).
- `c1c3-327.59K-4.482MPa` — k_ij=0 cubic bubble pressure / vapour composition just beyond tolerance near the mixture critical region (model limitation; assessed in docs/validation.md).
- `c1c3-327.59K-5.861MPa` — k_ij=0 cubic bubble pressure / vapour composition just beyond tolerance near the mixture critical region (model limitation; assessed in docs/validation.md).
- `c1c3-327.59K-7.239MPa` — k_ij=0 cubic bubble pressure / vapour composition just beyond tolerance near the mixture critical region (model limitation; assessed in docs/validation.md).
- `c1c3-327.59K-7.584MPa` — k_ij=0 cubic bubble pressure / vapour composition just beyond tolerance near the mixture critical region (model limitation; assessed in docs/validation.md).
- `c1co2-274.15K-5.90MPa` — k_ij=0 cubic bubble pressure / vapour composition just beyond tolerance near the mixture critical region (model limitation; assessed in docs/validation.md).
- `c1co2-277.15K-4.69MPa` — k_ij=0 cubic bubble pressure / vapour composition just beyond tolerance near the mixture critical region (model limitation; assessed in docs/validation.md).
- `c1co2-277.15K-5.97MPa` — k_ij=0 cubic bubble pressure / vapour composition just beyond tolerance near the mixture critical region (model limitation; assessed in docs/validation.md).
- `c1co2-277.15K-7.04MPa` — k_ij=0 cubic bubble pressure / vapour composition just beyond tolerance near the mixture critical region (model limitation; assessed in docs/validation.md).
- `c1co2-283.15K-7.24MPa` — k_ij=0 cubic bubble pressure / vapour composition just beyond tolerance near the mixture critical region (model limitation; assessed in docs/validation.md).
- `c1co2-288.15K-6.62MPa` — k_ij=0 cubic bubble pressure / vapour composition just beyond tolerance near the mixture critical region (model limitation; assessed in docs/validation.md).
- `c1co2-288.15K-7.63MPa` — k_ij=0 cubic bubble pressure / vapour composition just beyond tolerance near the mixture critical region (model limitation; assessed in docs/validation.md).
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
- `ng-dew-morch-243.4K-0.30MPa` — dew pressures of the asymmetric C1/C2/nC5 synthetic natural gas ternary run 10-35 % above the Mørch et al. (2006) cooled-mirror measurements under databank/zero k_ij (model limitation, issue #130; assessed in docs/validation.md).
- `ng-dew-morch-254.6K-0.68MPa` — dew pressures of the asymmetric C1/C2/nC5 synthetic natural gas ternary run 10-35 % above the Mørch et al. (2006) cooled-mirror measurements under databank/zero k_ij (model limitation, issue #130; assessed in docs/validation.md).
- `ng-dew-morch-260.8K-1.04MPa` — dew pressures of the asymmetric C1/C2/nC5 synthetic natural gas ternary run 10-35 % above the Mørch et al. (2006) cooled-mirror measurements under databank/zero k_ij (model limitation, issue #130; assessed in docs/validation.md).
- `pure-C1-125K` — cubic saturation properties beyond tolerance vs the CoolProp reference EOS (known cubic EOS limitation, worst near Tc; assessed in docs/validation.md).
- `pure-C1-155K` — cubic saturation properties beyond tolerance vs the CoolProp reference EOS (known cubic EOS limitation, worst near Tc; assessed in docs/validation.md).
- `pure-C1-172K` — cubic saturation properties beyond tolerance vs the CoolProp reference EOS (known cubic EOS limitation, worst near Tc; assessed in docs/validation.md).
- `pure-C1-181K` — cubic saturation properties beyond tolerance vs the CoolProp reference EOS (known cubic EOS limitation, worst near Tc; assessed in docs/validation.md).
- `pure-C1-95.3K` — cubic saturation properties beyond tolerance vs the CoolProp reference EOS (known cubic EOS limitation, worst near Tc; assessed in docs/validation.md).
- `pure-C2-152.7K` — cubic saturation properties beyond tolerance vs the CoolProp reference EOS (known cubic EOS limitation, worst near Tc; assessed in docs/validation.md).
- `pure-C2-200K` — cubic saturation properties beyond tolerance vs the CoolProp reference EOS (known cubic EOS limitation, worst near Tc; assessed in docs/validation.md).
- `pure-C2-250K` — cubic saturation properties beyond tolerance vs the CoolProp reference EOS (known cubic EOS limitation, worst near Tc; assessed in docs/validation.md).
- `pure-C2-285K` — cubic saturation properties beyond tolerance vs the CoolProp reference EOS (known cubic EOS limitation, worst near Tc; assessed in docs/validation.md).
- `pure-C2-290K` — cubic saturation properties beyond tolerance vs the CoolProp reference EOS (known cubic EOS limitation, worst near Tc; assessed in docs/validation.md).
- `pure-C3-184.9K` — cubic saturation properties beyond tolerance vs the CoolProp reference EOS (known cubic EOS limitation, worst near Tc; assessed in docs/validation.md).
- `pure-C3-300K` — cubic saturation properties beyond tolerance vs the CoolProp reference EOS (known cubic EOS limitation, worst near Tc; assessed in docs/validation.md).
- `pure-C3-340K` — cubic saturation properties beyond tolerance vs the CoolProp reference EOS (known cubic EOS limitation, worst near Tc; assessed in docs/validation.md).
- `pure-C3-351.3K` — cubic saturation properties beyond tolerance vs the CoolProp reference EOS (known cubic EOS limitation, worst near Tc; assessed in docs/validation.md).
- `pure-CO2-216.7K` — cubic saturation properties beyond tolerance vs the CoolProp reference EOS (known cubic EOS limitation, worst near Tc; assessed in docs/validation.md).
- `pure-CO2-240K` — cubic saturation properties beyond tolerance vs the CoolProp reference EOS (known cubic EOS limitation, worst near Tc; assessed in docs/validation.md).
- `pure-CO2-265K` — cubic saturation properties beyond tolerance vs the CoolProp reference EOS (known cubic EOS limitation, worst near Tc; assessed in docs/validation.md).
- `pure-CO2-285K` — cubic saturation properties beyond tolerance vs the CoolProp reference EOS (known cubic EOS limitation, worst near Tc; assessed in docs/validation.md).
- `pure-CO2-288.9K` — cubic saturation properties beyond tolerance vs the CoolProp reference EOS (known cubic EOS limitation, worst near Tc; assessed in docs/validation.md).
- `pure-H2O-323.5K` — cubic saturation properties beyond tolerance vs the CoolProp reference EOS (known cubic EOS limitation, worst near Tc; assessed in docs/validation.md).
- `pure-H2O-340K-nrtl` — cubic saturation properties beyond tolerance vs the CoolProp reference EOS (known cubic EOS limitation, worst near Tc; assessed in docs/validation.md).
- `pure-H2O-370K-nrtl` — cubic saturation properties beyond tolerance vs the CoolProp reference EOS (known cubic EOS limitation, worst near Tc; assessed in docs/validation.md).
- `pure-H2O-420K` — cubic saturation properties beyond tolerance vs the CoolProp reference EOS (known cubic EOS limitation, worst near Tc; assessed in docs/validation.md).
- `pure-H2O-520K` — cubic saturation properties beyond tolerance vs the CoolProp reference EOS (known cubic EOS limitation, worst near Tc; assessed in docs/validation.md).
- `pure-H2O-600K` — cubic saturation properties beyond tolerance vs the CoolProp reference EOS (known cubic EOS limitation, worst near Tc; assessed in docs/validation.md).
- `pure-H2O-614.7K` — cubic saturation properties beyond tolerance vs the CoolProp reference EOS (known cubic EOS limitation, worst near Tc; assessed in docs/validation.md).
- `pure-H2S-187.8K` — cubic saturation properties beyond tolerance vs the CoolProp reference EOS (known cubic EOS limitation, worst near Tc; assessed in docs/validation.md).
- `pure-H2S-240K` — cubic saturation properties beyond tolerance vs the CoolProp reference EOS (known cubic EOS limitation, worst near Tc; assessed in docs/validation.md).
- `pure-H2S-300K` — cubic saturation properties beyond tolerance vs the CoolProp reference EOS (known cubic EOS limitation, worst near Tc; assessed in docs/validation.md).
- `pure-H2S-345K` — cubic saturation properties beyond tolerance vs the CoolProp reference EOS (known cubic EOS limitation, worst near Tc; assessed in docs/validation.md).
- `pure-H2S-354.4K` — cubic saturation properties beyond tolerance vs the CoolProp reference EOS (known cubic EOS limitation, worst near Tc; assessed in docs/validation.md).
- `pure-MeOH-305K-nrtl` — cubic saturation properties beyond tolerance vs the CoolProp reference EOS (known cubic EOS limitation, worst near Tc; assessed in docs/validation.md).
- `pure-MeOH-330K-nrtl` — cubic saturation properties beyond tolerance vs the CoolProp reference EOS (known cubic EOS limitation, worst near Tc; assessed in docs/validation.md).
- `pure-N2-100K` — cubic saturation properties beyond tolerance vs the CoolProp reference EOS (known cubic EOS limitation, worst near Tc; assessed in docs/validation.md).
- `pure-N2-112K` — cubic saturation properties beyond tolerance vs the CoolProp reference EOS (known cubic EOS limitation, worst near Tc; assessed in docs/validation.md).
- `pure-N2-119.9K` — cubic saturation properties beyond tolerance vs the CoolProp reference EOS (known cubic EOS limitation, worst near Tc; assessed in docs/validation.md).
- `pure-N2-63.2K` — cubic saturation properties beyond tolerance vs the CoolProp reference EOS (known cubic EOS limitation, worst near Tc; assessed in docs/validation.md).
- `pure-N2-82K` — cubic saturation properties beyond tolerance vs the CoolProp reference EOS (known cubic EOS limitation, worst near Tc; assessed in docs/validation.md).
- `pure-nC4-212.6K` — cubic saturation properties beyond tolerance vs the CoolProp reference EOS (known cubic EOS limitation, worst near Tc; assessed in docs/validation.md).
- `pure-nC4-350K` — cubic saturation properties beyond tolerance vs the CoolProp reference EOS (known cubic EOS limitation, worst near Tc; assessed in docs/validation.md).
- `pure-nC4-390K` — cubic saturation properties beyond tolerance vs the CoolProp reference EOS (known cubic EOS limitation, worst near Tc; assessed in docs/validation.md).
- `pure-nC4-403.9K` — cubic saturation properties beyond tolerance vs the CoolProp reference EOS (known cubic EOS limitation, worst near Tc; assessed in docs/validation.md).
- `slice-inlet-K-500psia-300K` — chart-read K values (5-7 % reading precision) vs k_ij=0 cubic K (data + model limitation; assessed in docs/validation.md).

## Reference sources

Pure-fluid expected values are generated from the CoolProp reference EOS (version in `results.json`); `source: coolprop:<fluid>`. Literature values are hand-typed with the retrieval date; unique sources:

- Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 312.91 K; DDB Explorer Edition data set 467; retrieved 2026-10-20
- Bayer (1927) Z. Phys. Chem. (Leipzig) 130, pp. 1-14, isotherm 322.91 K; DDB Explorer Edition data set 468; retrieved 2026-10-20
- Bennett (1929) J. Chem. Educ. 6, pp. 1544-1549, isobaric 97.99 kPa; DDB Explorer Edition data set 466; retrieved 2026-10-20
- Culberson & McKetta (1951) J. Pet. Technol. 3, 223-226; IUPAC SDS 27/28 printed p. 31, 100 F isotherm; retrieved 2026-10-20
- Culberson & McKetta (1951) J. Pet. Technol. 3, 223-226; IUPAC SDS 27/28 printed p. 32, 160 F isotherm; retrieved 2026-10-20
- Culberson & McKetta (1951) J. Pet. Technol. 3, 223-226; IUPAC SDS 27/28 printed p. 32, 280 F isotherm; retrieved 2026-10-20
- DePriester (1953) Chem. Eng. Prog. Symp. Ser. 49(7), p. 42, high-T nomogram (as Fig. 10.14 in Felder & Rousseau), read at 500 psia / 80.33 F; retrieved 2026-10-20
- Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20
- Mørch, Nasrifar, Bolland, Solbraa, Fredheim & Gjertsen (2006) Fluid Phase Equilib. 239(2), 138-145, doi:10.1016/j.fluid.2005.11.010 - cooled mirror dew points for the synthetic natural gas ternary z(C1)=0.94085, z(C2)=0.04468, z(nC5)=0.01447; NIST ThermoML compilation, retrieved 2026-10-21
- Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 270, 277.59 K isotherm; retrieved 2026-10-20
- Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 294.26 K isotherm; retrieved 2026-10-20
- Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 310.93 K isotherm; retrieved 2026-10-20
- Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 327.59 K isotherm; retrieved 2026-10-20

## How to add a case

1. Add an entry to `data/validation/cases.yaml` (`binary_cases`/`multicomponent_cases`) with `id`, `package`, `components`, `z`, `T` (and/or `P`), `expected` (`vf`, `rho_V`, `rho_L`, `H`, `S`, `Cp`, `bubble_P`, `dew_P`, `bubble_T`, `K`, `vapor_comp`, `liquid_comp`), a `source` with authors, journal, year, table/page and retrieval date, and — only where the spec's fixed policy does not apply — a `tolerance`.
2. Pure-fluid points: add a `pure_cases` entry, then run `uv run python scripts/validate_properties.py --regen-coolprop` to fill `expected`.
3. Run `uv run python scripts/validate_properties.py --write-doc`, then commit `cases.yaml`, `results.json` and `docs/validation.md` together. `tests/validation/test_reference_cases.py` picks the case up automatically.

Never loosen a tolerance to make a case pass: a failing case is assessed (model limitation vs bug) and documented, not tuned away.
