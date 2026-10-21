# regular_solution_rk — regular solution liquid + Redlich-Kwong vapour

family `gamma_phi` · status **provisional** · adapter `ngdesign.thermo.gamma_phi:GammaPhiPackage`.

## Applicability (Carlson 1996)

- component classes: alcohol, water, hydrocarbon, polar_organic
- polar: True · electrolyte: False
- T window: 250–600 K · P window: 1000–1e+07 Pa
- phases: V, L

## Parameters

- source: pure solubility parameters SP_i = sqrt(dHvap_i(T)/V_i(T,P)) from the thermo pure-component correlations at 298.15 K (EnthalpyVaporizations, VolumeLiquids)
- provenance: components whose correlation returns no value raise rather than default

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 0 | MeOH@300K bubble 0 dew 0; MeOH@350K bubble 0 dew 0; H2O@350K bubble 0 dew 0 |
| phase_identification | ok | 0 | MeOH@300K ok; MeOH@350K ok; H2O@400K ok |
| round_trip | ok | 1.5e-16 | 380K/50000Pa T_ph 1.5e-16 H 0 T_ps 1.5e-16; 400K/100000Pa T_ph 1.4e-16 H 0 T_ps 0 |
| dhdT_cp | ok | 7e-08 | 380K/50000Pa vapor cp 42.248 dH/dT 42.248 |
| gibbs_duhem | ok | 1.5e-08 | ['H2O', 'MeOH']@350K/100000Pa aqueous 1.5e-08; ['H2O', 'MeOH']@380K/50000Pa vapor 7.5e-11 |
| determinism | ok | 0 | two instances bit-identical at 380K/50000Pa |
| single_liquid_limit | ok | 0 | 298.15K/100000Pa kinds=['hc_liquid'] vf=0.0 |

### L4 cross-model pairs

- n/a — refuses the slice feed: ValueError: the regular-solution solubility parameter for C1 (74-82-8) cannot be formed: the thermo pure-component correlation returns no liquid molar volume at 298.15 K; refusing rather than defaulting - select a model whose parameters cover this component support

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).

## References

- Scatchard, G., Chem. Rev. 8(2), 321-333, 1931
- Hildebrand, J. H. & Scott, R. L., The Solubility of Nonelectrolytes, 3rd ed., 1950
