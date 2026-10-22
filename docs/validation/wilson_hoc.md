# wilson_hoc — Wilson liquid + Hayden-O'Connell virial vapour

family `gamma_phi` · status **experimental** · adapter `ngdesign.thermo.gamma_phi:GammaPhiPackage`.

## Applicability (Carlson 1996)

- component classes: alcohol, water, hydrocarbon, polar_organic
- polar: True · electrolyte: False
- T window: 250–600 K · P window: 1000–1e+07 Pa
- phases: V, L

## Parameters

- source: no verifiable, citable equation/parameter table found (DWSIM's implementation is GPLv3 and must not be copied)
- provenance: the row registers as experimental and its builder refuses rather than inventing physics - see ngdesign.thermo.virial (spec deviation)

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).

## References

- Hayden-O'Connell, J. P., Ind. Eng. Chem. Process Des. Dev. 14(3), 221-239, 1975 (equation reference; no verifiable open parameter table found this session)
- Nothnagel, K.-H., Abrams, D. S. & Prausnitz, J. M., Ind. Eng. Chem. Process Des. Dev. 12(1), 25-35, 1973 (equation reference; same parameter-table gap)
