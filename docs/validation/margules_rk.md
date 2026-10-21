# margules_rk — Margules liquid + Redlich-Kwong vapour

family `gamma_phi` · status **provisional** · adapter `ngdesign.thermo.gamma_phi:GammaPhiPackage`.

## Applicability (Carlson 1996)

- component classes: alcohol, water, hydrocarbon, polar_organic
- polar: True · electrolyte: False
- T window: 250–600 K · P window: 1000–1e+07 Pa
- phases: V, L

## Parameters

- source: in-house case-fitted parameters (data/thermo_params/margules/pairs.yaml), least-squares fitted to ln-gamma targets from the cited literature points
- provenance: DECHEMA (Gmehling & Onken) open example tables were not retrievable (documented deviation)

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| pure_psat_limit | ok | 0 | MeOH@300K bubble 0 dew 0; MeOH@350K bubble 0 dew 0; H2O@350K bubble 0 dew 0 |
| phase_identification | ok | 0 | MeOH@300K ok; MeOH@350K ok; H2O@400K ok |
| round_trip | ok | 1.1e-15 | 380K/50000Pa T_ph 0 H 0 T_ps 1.5e-16; 400K/100000Pa T_ph 1.4e-16 H 0 T_ps 1.1e-15 |
| dhdT_cp | ok | 1.4e-08 | 380K/50000Pa vapor cp 56.3428 dH/dT 56.3428 |
| gibbs_duhem | ok | 4.5e-09 | ['EtOH', 'H2O']@350K/100000Pa aqueous 4.5e-09; ['EtOH', 'H2O']@380K/50000Pa vapor 1.2e-10 |
| determinism | ok | 0 | two instances bit-identical at 380K/50000Pa |
| single_liquid_limit | ok | 0 | 298.15K/100000Pa kinds=['hc_liquid'] vf=0.0 |

### L4 cross-model pairs

- n/a — refuses the slice feed: ValueError: Margules binary parameters for pair C1 (74-82-8) / C2 (74-84-0) are not available in data/thermo_params/margules/pairs.yaml; refusing to flash a zero-filled (ideal) pair matrix - select a thermo model whose parameter tables cover this component support

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).

## References

- Margules, M., Sitzungsber. Akad. Wiss. Wien 104, 1243-1278, 1895
- Bennett, J. P., J. Phys. Chem. 33(2), 258-270, 1929 (MeOH/H2O fit source point)
