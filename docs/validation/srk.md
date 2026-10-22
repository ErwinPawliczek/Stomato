# srk — Soave-Redlich-Kwong

family `cubic` · status **validated** · adapter `ngdesign.thermo.srk:SoaveRedlichKwongThermo`.

## Applicability (Carlson 1996)

- component classes: hydrocarbon, light_gas, inert, water
- polar: False · electrolyte: False
- T window: 90–700 K · P window: 1000–2e+08 Pa
- phases: V, L, VLL

## Parameters

- source: thermo IPDB (ChemSep)
- provenance: Kooijman & Taylor, ChemSep IPDB; critical constants and acentric factors from the ChemSep pure-component database; binary interaction parameters from the 'ChemSep PR' table, 0 where the table has no pair

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 0 | C1@160K bubble 0 dew 0; C3@300K bubble 0 dew 0; nC4@300K bubble 0 dew 0; H2O@400K bubble 0 dew 0 |
| phase_identification | ok | 0 | nC4@300K ok; C3@300K ok; H2O@300K ok |
| round_trip | ok | 3.2e-16 | 350K/3.447e+06Pa T_ph 0 H 0 T_ps 3.2e-16 |
| dhdT_cp | ok | 4.8e-07 | 350K/3.447e+06Pa vapor cp 47.6557 dH/dT 47.6557 |
| gibbs_duhem | ok | 2.3e-07 | ['C1', 'C3']@250K/2e+06Pa hc_liquid 2.3e-07; ['C1', 'CO2']@250K/2e+06Pa vapor 2.8e-09 |
| single_liquid_limit | ok | 0 | 250K/2e+06Pa kinds=['hc_liquid'] vf=0.0 |
| determinism | ok | 0 | two instances bit-identical at 350K/3.447e+06Pa |

### L4 cross-model pairs

- vs `mathias`: ok — n/a — l4_excluded: The Mathias-Copeman alpha is anchored to each component's vapour pressure; on the multi-component slice dew it runs +41% above the generalised-omega srk-family rows and +22% above the pr family (measured 869540 vs 614969/717386 Pa at 293.15 K) - the deviation the Psat fit exists to produce, declared here rather than loosening the 20% band.
- vs `api`: ok — dew P 615893 vs 643917 (rel 0.0435); rhoV 5.18815 vs 5.42979 (rel 0.0445); band 20%
- vs `api`: ok — dew P 615893 vs 717386 (rel 0.141); rhoV 5.18815 vs 6.08846 (rel 0.148); band 20%
- vs `api`: ok — dew P 615893 vs 717633 (rel 0.142); rhoV 5.18815 vs 6.09273 (rel 0.148); band 20%
- vs `api`: ok — dew P 615893 vs 717633 (rel 0.142); rhoV 5.18815 vs 6.09273 (rel 0.148); band 20%
- vs `api`: ok — dew P 615893 vs 717386 (rel 0.141); rhoV 5.18815 vs 6.08846 (rel 0.148); band 20%
- vs `api`: ok — dew P 615893 vs 717386 (rel 0.141); rhoV 5.18815 vs 6.07898 (rel 0.147); band 20%
- vs `api`: ok — dew P 615893 vs 717386 (rel 0.141); rhoV 5.18815 vs 6.08846 (rel 0.148); band 20%
- vs `api`: ok — dew P 615893 vs 724017 (rel 0.149); rhoV 5.18815 vs 6.14587 (rel 0.156); band 20%
- vs `api`: ok — dew P 615893 vs 724017 (rel 0.149); rhoV 5.18815 vs 6.14587 (rel 0.156); band 20%
- vs `api`: ok — dew P 615893 vs 615330 (rel 0.000915); rhoV 5.18815 vs 5.18646 (rel 0.000327); band 20%
- vs `api`: ok — dew P 615893 vs 717386 (rel 0.141); rhoV 5.18815 vs 6.08845 (rel 0.148); band 20%
- vs `api`: ok — dew P 615893 vs 614968 (rel 0.0015); rhoV 5.18815 vs 5.18049 (rel 0.00148); band 20%
- vs `api`: ok — dew P 615893 vs 614969 (rel 0.0015); rhoV 5.18815 vs 5.18049 (rel 0.00148); band 20%
- vs `api`: ok — dew P 615893 vs 615330 (rel 0.000915); rhoV 5.18815 vs 5.18646 (rel 0.000327); band 20%
- vs `api`: ok — dew P 615893 vs 614969 (rel 0.0015); rhoV 5.18815 vs 5.18049 (rel 0.00148); band 20%
- vs `api`: ok — dew P 615893 vs 614969 (rel 0.0015); rhoV 5.18815 vs 5.18231 (rel 0.00113); band 20%
- vs `api`: ok — dew P 615893 vs 597284 (rel 0.0312); rhoV 5.18815 vs 5.0462 (rel 0.0281); band 20%
- vs `api`: ok — dew P 615893 vs 596571 (rel 0.0324); rhoV 5.18815 vs 5.0194 (rel 0.0336); band 20%
- vs `api`: ok — n/a — l4_excluded: See the srk declaration: measured 872333 vs 615893 Pa (rel 0.294) at 293.15 K.
- vs `kabadi`: ok — dew P 643917 vs 717386 (rel 0.102); rhoV 5.42979 vs 6.08846 (rel 0.108); band 20%
- vs `kabadi`: ok — dew P 643917 vs 717633 (rel 0.103); rhoV 5.42979 vs 6.09273 (rel 0.109); band 20%
- vs `kabadi`: ok — dew P 643917 vs 717633 (rel 0.103); rhoV 5.42979 vs 6.09273 (rel 0.109); band 20%
- vs `kabadi`: ok — dew P 643917 vs 717386 (rel 0.102); rhoV 5.42979 vs 6.08846 (rel 0.108); band 20%
- vs `kabadi`: ok — dew P 643917 vs 717386 (rel 0.102); rhoV 5.42979 vs 6.07898 (rel 0.107); band 20%
- vs `kabadi`: ok — dew P 643917 vs 717386 (rel 0.102); rhoV 5.42979 vs 6.08846 (rel 0.108); band 20%
- vs `kabadi`: ok — dew P 643917 vs 724017 (rel 0.111); rhoV 5.42979 vs 6.14587 (rel 0.117); band 20%
- vs `kabadi`: ok — dew P 643917 vs 724017 (rel 0.111); rhoV 5.42979 vs 6.14587 (rel 0.117); band 20%
- vs `kabadi`: ok — dew P 643917 vs 615330 (rel 0.0465); rhoV 5.42979 vs 5.18646 (rel 0.0469); band 20%
- vs `kabadi`: ok — dew P 643917 vs 717386 (rel 0.102); rhoV 5.42979 vs 6.08845 (rel 0.108); band 20%
- vs `kabadi`: ok — dew P 643917 vs 614968 (rel 0.0471); rhoV 5.42979 vs 5.18049 (rel 0.0481); band 20%
- vs `kabadi`: ok — dew P 643917 vs 614969 (rel 0.0471); rhoV 5.42979 vs 5.18049 (rel 0.0481); band 20%
- vs `kabadi`: ok — dew P 643917 vs 615330 (rel 0.0465); rhoV 5.42979 vs 5.18646 (rel 0.0469); band 20%
- vs `kabadi`: ok — dew P 643917 vs 614969 (rel 0.0471); rhoV 5.42979 vs 5.18049 (rel 0.0481); band 20%
- vs `kabadi`: ok — dew P 643917 vs 614969 (rel 0.0471); rhoV 5.42979 vs 5.18231 (rel 0.0478); band 20%
- vs `kabadi`: ok — dew P 643917 vs 597284 (rel 0.0781); rhoV 5.42979 vs 5.0462 (rel 0.076); band 20%
- vs `kabadi`: ok — dew P 643917 vs 596571 (rel 0.0794); rhoV 5.42979 vs 5.0194 (rel 0.0818); band 20%
- vs `kabadi`: ok — n/a — l4_excluded: See the srk declaration: measured 872333 vs 643917 Pa (rel 0.262) at 293.15 K.
- vs `pr`: ok — dew P 717386 vs 614968 (rel 0.167); rhoV 6.08846 vs 5.18049 (rel 0.175); band 20%
- vs `pr`: ok — dew P 717386 vs 614969 (rel 0.167); rhoV 6.08846 vs 5.18049 (rel 0.175); band 20%
- vs `pr`: ok — dew P 717386 vs 615330 (rel 0.166); rhoV 6.08846 vs 5.18646 (rel 0.174); band 20%
- vs `pr`: ok — dew P 717386 vs 614969 (rel 0.167); rhoV 6.08846 vs 5.18049 (rel 0.175); band 20%
- vs `pr`: ok — dew P 717386 vs 614969 (rel 0.167); rhoV 6.08846 vs 5.18231 (rel 0.175); band 20%
- vs `pr`: ok — n/a — l4_excluded: Twu (1995) alpha is anchored to each component's vapour pressure; on the multi-component slice dew it runs ~20-21% below the generalised-omega pr-family rows (measured 596571 vs 717386-724017 Pa at 293.15 K) - an expected alpha-accuracy difference, declared here rather than loosening the 20% band.
- vs `pr`: ok — dew P 717633 vs 614968 (rel 0.167); rhoV 6.09273 vs 5.18049 (rel 0.176); band 20%
- vs `pr`: ok — dew P 717633 vs 614969 (rel 0.167); rhoV 6.09273 vs 5.18049 (rel 0.176); band 20%
- vs `pr`: ok — dew P 717633 vs 615330 (rel 0.166); rhoV 6.09273 vs 5.18646 (rel 0.175); band 20%
- vs `pr`: ok — dew P 717633 vs 614969 (rel 0.167); rhoV 6.09273 vs 5.18049 (rel 0.176); band 20%
- vs `pr`: ok — dew P 717633 vs 614969 (rel 0.167); rhoV 6.09273 vs 5.18231 (rel 0.176); band 20%
- vs `pr`: ok — n/a — l4_excluded: Twu (1995) alpha is anchored to each component's vapour pressure; on the multi-component slice dew it runs ~20-21% below the generalised-omega pr-family rows (measured 596571 vs 717386-724017 Pa at 293.15 K) - an expected alpha-accuracy difference, declared here rather than loosening the 20% band.
- vs `pr`: ok — dew P 717633 vs 614968 (rel 0.167); rhoV 6.09273 vs 5.18049 (rel 0.176); band 20%
- vs `pr`: ok — dew P 717633 vs 614969 (rel 0.167); rhoV 6.09273 vs 5.18049 (rel 0.176); band 20%
- vs `pr`: ok — dew P 717633 vs 615330 (rel 0.166); rhoV 6.09273 vs 5.18646 (rel 0.175); band 20%
- vs `pr`: ok — dew P 717633 vs 614969 (rel 0.167); rhoV 6.09273 vs 5.18049 (rel 0.176); band 20%
- vs `pr`: ok — dew P 717633 vs 614969 (rel 0.167); rhoV 6.09273 vs 5.18231 (rel 0.176); band 20%
- vs `pr`: ok — n/a — l4_excluded: Twu (1995) alpha is anchored to each component's vapour pressure; on the multi-component slice dew it runs ~20-21% below the generalised-omega pr-family rows (measured 596571 vs 717386-724017 Pa at 293.15 K) - an expected alpha-accuracy difference, declared here rather than loosening the 20% band.
- vs `pr`: ok — dew P 717386 vs 614968 (rel 0.167); rhoV 6.08846 vs 5.18049 (rel 0.175); band 20%
- vs `pr`: ok — dew P 717386 vs 614969 (rel 0.167); rhoV 6.08846 vs 5.18049 (rel 0.175); band 20%
- vs `pr`: ok — dew P 717386 vs 615330 (rel 0.166); rhoV 6.08846 vs 5.18646 (rel 0.174); band 20%
- vs `pr`: ok — dew P 717386 vs 614969 (rel 0.167); rhoV 6.08846 vs 5.18049 (rel 0.175); band 20%
- vs `pr`: ok — dew P 717386 vs 614969 (rel 0.167); rhoV 6.08846 vs 5.18231 (rel 0.175); band 20%
- vs `pr`: ok — n/a — l4_excluded: Twu (1995) alpha is anchored to each component's vapour pressure; on the multi-component slice dew it runs ~20-21% below the generalised-omega pr-family rows (measured 596571 vs 717386-724017 Pa at 293.15 K) - an expected alpha-accuracy difference, declared here rather than loosening the 20% band.
- vs `pr`: ok — dew P 717386 vs 614968 (rel 0.167); rhoV 6.07898 vs 5.18049 (rel 0.173); band 20%
- vs `pr`: ok — dew P 717386 vs 614969 (rel 0.167); rhoV 6.07898 vs 5.18049 (rel 0.173); band 20%
- vs `pr`: ok — dew P 717386 vs 615330 (rel 0.166); rhoV 6.07898 vs 5.18646 (rel 0.172); band 20%
- vs `pr`: ok — dew P 717386 vs 614969 (rel 0.167); rhoV 6.07898 vs 5.18049 (rel 0.173); band 20%
- vs `pr`: ok — dew P 717386 vs 614969 (rel 0.167); rhoV 6.07898 vs 5.18231 (rel 0.173); band 20%
- vs `pr`: ok — n/a — l4_excluded: Twu (1995) alpha is anchored to each component's vapour pressure; on the multi-component slice dew it runs ~20-21% below the generalised-omega pr-family rows (measured 596571 vs 717386-724017 Pa at 293.15 K) - an expected alpha-accuracy difference, declared here rather than loosening the 20% band.
- vs `pr78`: ok — dew P 717386 vs 614968 (rel 0.167); rhoV 6.08846 vs 5.18049 (rel 0.175); band 20%
- vs `pr78`: ok — dew P 717386 vs 614969 (rel 0.167); rhoV 6.08846 vs 5.18049 (rel 0.175); band 20%
- vs `pr78`: ok — dew P 717386 vs 615330 (rel 0.166); rhoV 6.08846 vs 5.18646 (rel 0.174); band 20%
- vs `pr78`: ok — dew P 717386 vs 614969 (rel 0.167); rhoV 6.08846 vs 5.18049 (rel 0.175); band 20%
- vs `pr78`: ok — dew P 717386 vs 614969 (rel 0.167); rhoV 6.08846 vs 5.18231 (rel 0.175); band 20%
- vs `pr78`: ok — n/a — l4_excluded: Twu (1995) alpha is anchored to each component's vapour pressure; on the multi-component slice dew it runs ~20-21% below the generalised-omega pr-family rows (measured 596571 vs 717386-724017 Pa at 293.15 K) - an expected alpha-accuracy difference, declared here rather than loosening the 20% band.
- vs `prsv`: ok — dew P 724017 vs 614968 (rel 0.177); rhoV 6.14587 vs 5.18049 (rel 0.186); band 20%
- vs `prsv`: ok — dew P 724017 vs 614969 (rel 0.177); rhoV 6.14587 vs 5.18049 (rel 0.186); band 20%
- vs `prsv`: ok — dew P 724017 vs 615330 (rel 0.177); rhoV 6.14587 vs 5.18646 (rel 0.185); band 20%
- vs `prsv`: ok — dew P 724017 vs 614969 (rel 0.177); rhoV 6.14587 vs 5.18049 (rel 0.186); band 20%
- vs `prsv`: ok — dew P 724017 vs 614969 (rel 0.177); rhoV 6.14587 vs 5.18231 (rel 0.186); band 20%
- vs `prsv`: ok — n/a — l4_excluded: Twu (1995) alpha is anchored to each component's vapour pressure; on the multi-component slice dew it runs ~20-21% below the generalised-omega pr-family rows (measured 596571 vs 717386-724017 Pa at 293.15 K) - an expected alpha-accuracy difference, declared here rather than loosening the 20% band.
- vs `prsv2`: ok — dew P 724017 vs 614968 (rel 0.177); rhoV 6.14587 vs 5.18049 (rel 0.186); band 20%
- vs `prsv2`: ok — dew P 724017 vs 614969 (rel 0.177); rhoV 6.14587 vs 5.18049 (rel 0.186); band 20%
- vs `prsv2`: ok — dew P 724017 vs 615330 (rel 0.177); rhoV 6.14587 vs 5.18646 (rel 0.185); band 20%
- vs `prsv2`: ok — dew P 724017 vs 614969 (rel 0.177); rhoV 6.14587 vs 5.18049 (rel 0.186); band 20%
- vs `prsv2`: ok — dew P 724017 vs 614969 (rel 0.177); rhoV 6.14587 vs 5.18231 (rel 0.186); band 20%
- vs `prsv2`: ok — n/a — l4_excluded: Twu (1995) alpha is anchored to each component's vapour pressure; on the multi-component slice dew it runs ~20-21% below the generalised-omega pr-family rows (measured 596571 vs 717386-724017 Pa at 293.15 K) - an expected alpha-accuracy difference, declared here rather than loosening the 20% band.
- vs `rks`: ok — dew P 615330 vs 614968 (rel 0.000587); rhoV 5.18646 vs 5.18049 (rel 0.00115); band 20%
- vs `rks`: ok — dew P 615330 vs 614969 (rel 0.000587); rhoV 5.18646 vs 5.18049 (rel 0.00115); band 20%
- vs `rks`: ok — dew P 615330 vs 615330 (rel 0); rhoV 5.18646 vs 5.18646 (rel 0); band 20%
- vs `rks`: ok — dew P 615330 vs 614969 (rel 0.000587); rhoV 5.18646 vs 5.18049 (rel 0.00115); band 20%
- vs `rks`: ok — dew P 615330 vs 614969 (rel 0.000587); rhoV 5.18646 vs 5.18231 (rel 0.0008); band 20%
- vs `rks`: ok — dew P 615330 vs 596571 (rel 0.0314); rhoV 5.18646 vs 5.0194 (rel 0.0333); band 20%
- vs `sour`: ok — dew P 717386 vs 614968 (rel 0.167); rhoV 6.08845 vs 5.18049 (rel 0.175); band 20%
- vs `sour`: ok — dew P 717386 vs 614969 (rel 0.167); rhoV 6.08845 vs 5.18049 (rel 0.175); band 20%
- vs `sour`: ok — dew P 717386 vs 615330 (rel 0.166); rhoV 6.08845 vs 5.18646 (rel 0.174); band 20%
- vs `sour`: ok — dew P 717386 vs 614969 (rel 0.167); rhoV 6.08845 vs 5.18049 (rel 0.175); band 20%
- vs `sour`: ok — dew P 717386 vs 614969 (rel 0.167); rhoV 6.08845 vs 5.18231 (rel 0.175); band 20%
- vs `sour`: ok — n/a — l4_excluded: Twu (1995) alpha is anchored to each component's vapour pressure; on the multi-component slice dew it runs ~20-21% below the generalised-omega pr-family rows (measured 596571 vs 717386-724017 Pa at 293.15 K) - an expected alpha-accuracy difference, declared here rather than loosening the 20% band.
- vs `sour`: ok — dew P 614968 vs 614969 (rel 1.09e-07); rhoV 5.18049 vs 5.18049 (rel 1.11e-07); band 20%
- vs `sour`: ok — dew P 614968 vs 615330 (rel 0.000587); rhoV 5.18049 vs 5.18646 (rel 0.00115); band 20%
- vs `sour`: ok — dew P 614968 vs 614969 (rel 1.09e-07); rhoV 5.18049 vs 5.18049 (rel 1.11e-07); band 20%
- vs `sour`: ok — dew P 614968 vs 614969 (rel 1.09e-07); rhoV 5.18049 vs 5.18231 (rel 0.000352); band 20%
- vs `sour`: ok — dew P 614968 vs 597284 (rel 0.0296); rhoV 5.18049 vs 5.0462 (rel 0.0266); band 20%
- vs `sour`: ok — dew P 614968 vs 596571 (rel 0.0308); rhoV 5.18049 vs 5.0194 (rel 0.0321); band 20%
- vs `sour`: ok — n/a — l4_excluded: See the srk declaration: measured 872333 vs 614968 Pa (rel 0.295) at 293.15 K.
- vs `srk`: ok — dew P 614969 vs 615330 (rel 0.000587); rhoV 5.18049 vs 5.18646 (rel 0.00115); band 20%
- vs `srk`: ok — dew P 614969 vs 614969 (rel 0); rhoV 5.18049 vs 5.18049 (rel 0); band 20%
- vs `srk`: ok — dew P 614969 vs 614969 (rel 0); rhoV 5.18049 vs 5.18231 (rel 0.000352); band 20%
- vs `twu`: ok — dew P 614969 vs 597284 (rel 0.0296); rhoV 5.18049 vs 5.0462 (rel 0.0266); band 20%
- vs `twu`: ok — dew P 614969 vs 596571 (rel 0.0308); rhoV 5.18049 vs 5.0194 (rel 0.0321); band 20%
- vs `zudkevitch`: ok — n/a — l4_excluded: The Zudkevitch-Joffe Psat-fitted alpha with Omega_b held at the RK constant (documented deviation in params.alpha_parameters) runs +26-32% above the generalised-omega srk-family rows on the multi-component slice dew (measured 872333 vs 614968-643917 Pa at 293.15 K) while the pr-family rows sit within the 20% band (rel 0.17-0.18) - an alpha-accuracy difference, declared here rather than loosening the band.
- vs `boston`: ok — dew P 615330 vs 614969 (rel 0.000587); rhoV 5.18646 vs 5.18049 (rel 0.00115); band 20%
- vs `boston`: ok — dew P 615330 vs 614969 (rel 0.000587); rhoV 5.18646 vs 5.18231 (rel 0.0008); band 20%
- vs `boston`: ok — dew P 615330 vs 597284 (rel 0.0302); rhoV 5.18646 vs 5.0462 (rel 0.0278); band 20%
- vs `boston`: ok — dew P 615330 vs 596571 (rel 0.0314); rhoV 5.18646 vs 5.0194 (rel 0.0333); band 20%
- vs `boston`: ok — n/a — l4_excluded: See the srk declaration: measured 872333 vs 615330 Pa (rel 0.295) at 293.15 K.
- vs `lee`: ok — dew P 614969 vs 614969 (rel 0); rhoV 5.18049 vs 5.18231 (rel 0.000352); band 20%
- vs `lee`: ok — dew P 614969 vs 597284 (rel 0.0296); rhoV 5.18049 vs 5.0462 (rel 0.0266); band 20%
- vs `lee`: ok — dew P 614969 vs 596571 (rel 0.0308); rhoV 5.18049 vs 5.0194 (rel 0.0321); band 20%
- vs `lee`: ok — n/a — l4_excluded: See the srk declaration: measured 872333 vs 614969 Pa (rel 0.295) at 293.15 K.
- vs `peneloux`: ok — dew P 614969 vs 597284 (rel 0.0296); rhoV 5.18231 vs 5.0462 (rel 0.027); band 20%
- vs `peneloux`: ok — dew P 614969 vs 596571 (rel 0.0308); rhoV 5.18231 vs 5.0194 (rel 0.0325); band 20%
- vs `peneloux`: ok — n/a — l4_excluded: See the srk declaration: measured 872333 vs 614969 Pa (rel 0.295) at 293.15 K.
- vs `twu`: ok — dew P 597284 vs 596571 (rel 0.0012); rhoV 5.0462 vs 5.0194 (rel 0.00534); band 20%
- vs `twu`: ok — n/a — l4_excluded: See the srk declaration: measured 872333 vs 596571 Pa (rel 0.316) at 293.15 K.

## L1/L2 reference-case outcomes

201/278 comparisons pass. Failing comparisons are assessed in the
main [validation report](../validation.md); the raw rows are in `data/validation/results.json`.

Declared case ids:

- `pure-C1-95.3K` — coolprop:CH4
- `pure-C1-125K` — coolprop:CH4
- `pure-C1-155K` — coolprop:CH4
- `pure-C1-172K` — coolprop:CH4
- `pure-C1-181K` — coolprop:CH4
- `pure-C2-152.7K` — coolprop:Ethane
- `pure-C2-200K` — coolprop:Ethane
- `pure-C2-250K` — coolprop:Ethane
- `pure-C2-285K` — coolprop:Ethane
- `pure-C2-290K` — coolprop:Ethane
- `pure-C3-184.9K` — coolprop:Propane
- `pure-C3-240K` — coolprop:Propane
- `pure-C3-300K` — coolprop:Propane
- `pure-C3-340K` — coolprop:Propane
- `pure-C3-351.3K` — coolprop:Propane
- `pure-nC4-212.6K` — coolprop:n-Butane
- `pure-nC4-280K` — coolprop:n-Butane
- `pure-nC4-350K` — coolprop:n-Butane
- `pure-nC4-390K` — coolprop:n-Butane
- `pure-nC4-403.9K` — coolprop:n-Butane
- `pure-CO2-216.7K` — coolprop:CO2
- `pure-CO2-240K` — coolprop:CO2
- `pure-CO2-265K` — coolprop:CO2
- `pure-CO2-285K` — coolprop:CO2
- `pure-CO2-288.9K` — coolprop:CO2
- `pure-H2S-187.8K` — coolprop:H2S
- `pure-H2S-240K` — coolprop:H2S
- `pure-H2S-300K` — coolprop:H2S
- `pure-H2S-345K` — coolprop:H2S
- `pure-H2S-354.4K` — coolprop:H2S
- `pure-N2-63.2K` — coolprop:Nitrogen
- `pure-N2-82K` — coolprop:Nitrogen
- `pure-N2-100K` — coolprop:Nitrogen
- `pure-N2-112K` — coolprop:Nitrogen
- `pure-N2-119.9K` — coolprop:Nitrogen
- `pure-H2O-323.5K` — coolprop:Water
- `pure-H2O-420K` — coolprop:Water
- `pure-H2O-520K` — coolprop:Water
- `pure-H2O-600K` — coolprop:Water
- `pure-H2O-614.7K` — coolprop:Water
- `c1c3-277.59K-0.689MPa` — Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 270, 277.59 K isotherm; retrieved 2026-10-20
- `c1c3-277.59K-1.724MPa` — Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 270, 277.59 K isotherm; retrieved 2026-10-20
- `c1c3-277.59K-2.758MPa` — Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 270, 277.59 K isotherm; retrieved 2026-10-20
- `c1c3-277.59K-4.137MPa` — Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 270, 277.59 K isotherm; retrieved 2026-10-20
- `c1c3-277.59K-5.516MPa` — Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 270, 277.59 K isotherm; retrieved 2026-10-20
- `c1c3-277.59K-6.895MPa` — Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 270, 277.59 K isotherm; retrieved 2026-10-20
- `c1c3-294.26K-6.895MPa` — Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 294.26 K isotherm; retrieved 2026-10-20
- `c1c3-294.26K-7.584MPa` — Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 294.26 K isotherm; retrieved 2026-10-20
- `c1c3-294.26K-8.274MPa` — Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 294.26 K isotherm; retrieved 2026-10-20
- `c1c3-294.26K-8.963MPa` — Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 294.26 K isotherm; retrieved 2026-10-20
- `c1c3-294.26K-9.653MPa` — Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 294.26 K isotherm; retrieved 2026-10-20
- `c1c3-310.93K-1.379MPa` — Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 310.93 K isotherm; retrieved 2026-10-20
- `c1c3-310.93K-1.724MPa` — Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 310.93 K isotherm; retrieved 2026-10-20
- `c1c3-310.93K-2.068MPa` — Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 310.93 K isotherm; retrieved 2026-10-20
- `c1c3-310.93K-2.413MPa` — Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 310.93 K isotherm; retrieved 2026-10-20
- `c1c3-327.59K-3.103MPa` — Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 327.59 K isotherm; retrieved 2026-10-20
- `c1c3-327.59K-4.482MPa` — Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 327.59 K isotherm; retrieved 2026-10-20
- `c1c3-327.59K-5.861MPa` — Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 327.59 K isotherm; retrieved 2026-10-20
- `c1c3-327.59K-7.239MPa` — Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 327.59 K isotherm; retrieved 2026-10-20
- `c1c3-327.59K-7.584MPa` — Reamer, Sage & Lacey (1950) Ind. Eng. Chem. 42, 534-539; IUPAC SDS 27/28 printed p. 271, 327.59 K isotherm; retrieved 2026-10-20
- `c1co2-274.15K-4.11MPa` — Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20
- `c1co2-274.15K-4.99MPa` — Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20
- `c1co2-274.15K-5.90MPa` — Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20
- `c1co2-274.15K-6.60MPa` — Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20
- `c1co2-274.15K-7.56MPa` — Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20
- `c1co2-274.15K-8.04MPa` — Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20
- `c1co2-277.15K-4.69MPa` — Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20
- `c1co2-277.15K-5.97MPa` — Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20
- `c1co2-277.15K-7.04MPa` — Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20
- `c1co2-277.15K-8.02MPa` — Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20
- `c1co2-283.15K-5.37MPa` — Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20
- `c1co2-283.15K-7.24MPa` — Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20
- `c1co2-288.15K-6.62MPa` — Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20
- `c1co2-288.15K-7.63MPa` — Legoix, Ruffine, Donval & Haeckel (2017) Energies 10(12), 2034, Table 4, doi:10.3390/en10122034; retrieved 2026-10-20
- `c1h2o-310.9K-2.28MPa` — Culberson & McKetta (1951) J. Pet. Technol. 3, 223-226; IUPAC SDS 27/28 printed p. 31, 100 F isotherm; retrieved 2026-10-20
- `c1h2o-310.9K-6.55MPa` — Culberson & McKetta (1951) J. Pet. Technol. 3, 223-226; IUPAC SDS 27/28 printed p. 31, 100 F isotherm; retrieved 2026-10-20
- `c1h2o-310.9K-13.10MPa` — Culberson & McKetta (1951) J. Pet. Technol. 3, 223-226; IUPAC SDS 27/28 printed p. 31, 100 F isotherm; retrieved 2026-10-20
- `c1h2o-310.9K-24.37MPa` — Culberson & McKetta (1951) J. Pet. Technol. 3, 223-226; IUPAC SDS 27/28 printed p. 31, 100 F isotherm; retrieved 2026-10-20
- `c1h2o-310.9K-44.99MPa` — Culberson & McKetta (1951) J. Pet. Technol. 3, 223-226; IUPAC SDS 27/28 printed p. 31, 100 F isotherm; retrieved 2026-10-20
- `c1h2o-310.9K-68.22MPa` — Culberson & McKetta (1951) J. Pet. Technol. 3, 223-226; IUPAC SDS 27/28 printed p. 31, 100 F isotherm; retrieved 2026-10-20
- `c1h2o-344.3K-2.28MPa` — Culberson & McKetta (1951) J. Pet. Technol. 3, 223-226; IUPAC SDS 27/28 printed p. 32, 160 F isotherm; retrieved 2026-10-20
- `c1h2o-344.3K-6.50MPa` — Culberson & McKetta (1951) J. Pet. Technol. 3, 223-226; IUPAC SDS 27/28 printed p. 32, 160 F isotherm; retrieved 2026-10-20
- `c1h2o-344.3K-12.96MPa` — Culberson & McKetta (1951) J. Pet. Technol. 3, 223-226; IUPAC SDS 27/28 printed p. 32, 160 F isotherm; retrieved 2026-10-20
- `c1h2o-344.3K-24.37MPa` — Culberson & McKetta (1951) J. Pet. Technol. 3, 223-226; IUPAC SDS 27/28 printed p. 32, 160 F isotherm; retrieved 2026-10-20
- `c1h2o-344.3K-44.99MPa` — Culberson & McKetta (1951) J. Pet. Technol. 3, 223-226; IUPAC SDS 27/28 printed p. 32, 160 F isotherm; retrieved 2026-10-20
- `c1h2o-344.3K-68.02MPa` — Culberson & McKetta (1951) J. Pet. Technol. 3, 223-226; IUPAC SDS 27/28 printed p. 32, 160 F isotherm; retrieved 2026-10-20
- `c1h2o-410.9K-2.32MPa` — Culberson & McKetta (1951) J. Pet. Technol. 3, 223-226; IUPAC SDS 27/28 printed p. 32, 280 F isotherm; retrieved 2026-10-20
- `c1h2o-410.9K-6.49MPa` — Culberson & McKetta (1951) J. Pet. Technol. 3, 223-226; IUPAC SDS 27/28 printed p. 32, 280 F isotherm; retrieved 2026-10-20
- `c1h2o-410.9K-13.10MPa` — Culberson & McKetta (1951) J. Pet. Technol. 3, 223-226; IUPAC SDS 27/28 printed p. 32, 280 F isotherm; retrieved 2026-10-20
- `c1h2o-410.9K-24.51MPa` — Culberson & McKetta (1951) J. Pet. Technol. 3, 223-226; IUPAC SDS 27/28 printed p. 32, 280 F isotherm; retrieved 2026-10-20
- `c1h2o-410.9K-44.99MPa` — Culberson & McKetta (1951) J. Pet. Technol. 3, 223-226; IUPAC SDS 27/28 printed p. 32, 280 F isotherm; retrieved 2026-10-20
- `c1h2o-410.9K-67.81MPa` — Culberson & McKetta (1951) J. Pet. Technol. 3, 223-226; IUPAC SDS 27/28 printed p. 32, 280 F isotherm; retrieved 2026-10-20
- `slice-inlet-K-500psia-300K` — DePriester (1953) Chem. Eng. Prog. Symp. Ser. 49(7), p. 42, high-T nomogram (as Fig. 10.14 in Felder & Rousseau), read at 500 psia / 80.33 F; retrieved 2026-10-20

## References

- Soave, G., 'Equilibrium Constants from a Modified Redlich-Kwong Equation of State', Chem. Eng. Sci. 27(6), 1197-1203, 1972
- Kooijman, H. A. & Taylor, R., The ChemSep Book, 2nd ed., 2000 (IPDB)
