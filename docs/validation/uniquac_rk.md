# uniquac_rk — UNIQUAC liquid + Redlich-Kwong vapour

family `gamma_phi` · status **provisional** · adapter `ngdesign.thermo.gamma_phi:GammaPhiPackage`.

## Applicability (Carlson 1996)

- component classes: alcohol, water, hydrocarbon, polar_organic
- polar: True · electrolyte: False
- T window: 250–600 K · P window: 1000–1e+07 Pa
- phases: V, L, VLL

## Parameters

- source: thermo IPDB (ChemSep), 'ChemSep UNIQUAC' binary table
- provenance: in-house case-fitted overrides (MEG/H2O, MeOH/nC4) from data/thermo_params/uniquac/pairs.yaml; r,q from UNIFAC group contributions (data/thermo_params/uniquac/groups.yaml)

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 0 | MeOH@300K bubble 0 dew 0; MeOH@350K bubble 0 dew 0; H2O@350K bubble 0 dew 0 |
| phase_identification | ok | 0 | MeOH@300K ok; MeOH@350K ok; H2O@400K ok |
| round_trip | ok | 1.5e-16 | 380K/50000Pa T_ph 1.5e-16 H 0 T_ps 1.5e-16; 400K/100000Pa T_ph 1.4e-16 H 0 T_ps 0 |
| dhdT_cp | ok | 7e-08 | 380K/50000Pa vapor cp 42.248 dH/dT 42.248 |
| gibbs_duhem | ok | 8.6e-09 | ['H2O', 'MeOH']@350K/100000Pa aqueous 8.6e-09; ['H2O', 'MeOH']@380K/50000Pa vapor 7.5e-11 |
| determinism | ok | 0 | two instances bit-identical at 380K/50000Pa |
| single_liquid_limit | ok | 0 | 298.15K/100000Pa kinds=['hc_liquid'] vf=0.0 |

### L4 cross-model pairs

- n/a — refuses the slice feed: ValueError: ChemSep UNIQUAC databank has no fitted binary parameters for pair C1 (74-82-8) / C2 (74-84-0); refusing to flash a zero-filled (ideal) pair matrix - select a thermo model whose databank covers this component support

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).

## References

- Abrams, D. S. & Prausnitz, J. M., AIChE J. 21(1), 116-128, 1975
- Maurer, G. & Prausnitz, J. M., Fluid Phase Equilib. 2(2), 91-99, 1978 (r,q form)
- Kooijman, H. A. & Taylor, R., The ChemSep Book, 2nd ed., 2000 (IPDB)
