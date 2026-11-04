# pitzer_hoc — Pitzer with Hayden-O'Connell vapour

family `electrolyte` · status **provisional** · adapter `ngdesign.amine.electrolyte:ElectrolytePitzerHOC`.

## Applicability (Carlson 1996)

- component classes: water
- polar: True · electrolyte: True
- T window: 293.15–303.15 K · P window: 2000–1e+07 Pa
- phases: V, L

## Parameters

- source: data/thermo_params/electrolyte/pitzer.yaml (liquid); data/thermo_params/virial/hoc_eta.yaml (vapour)
- provenance: The liquid is pitzer_nacl_water unchanged. The vapour is the in-house Hayden-O'Connell second-virial phase, the one the *_hoc gamma-phi rows use. Real-vapour water K-value: K_H2O = a_w Psat (phi_sat / phi_V) / P, Poynting term of the brine omitted. At 293-303 K the effect is of order 1e-4 on the bubble pressure, because water's Psat is small; the row exists for the vapour's fugacity and properties, not for a large VLE shift.

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |
| single_liquid_limit | ok | 0 | 298.15K/5e+06Pa kinds=['aqueous'] vf=0.0 |
| round_trip | ok | 6.7e-10 | 298.15K/5e+06Pa T_ph 6.7e-10 H 2.9e-10 T_ps 3.9e-10 |
| determinism | ok | 0 | two instances bit-identical at 298.15K/5e+06Pa |

Declared exclusions (not silent skips):

- `dhdT_cp` — the aqueous cp is the carrier's (no reaction-enthalpy correction is implemented), so the dH/dT == Cp identity rides the carrier surface unchanged
- `gibbs_duhem` — the aqueous ln_phi carries the electrolyte chemistry (f_w == a_w Psat), not a Gibbs-excess composition derivative; flash consistency is pinned by tests/thermo/test_electrolyte_variants.py instead
- `phase_identification` — same basis: the single-liquid limit replaces the vapour-pressure bracket for the electrolyte liquid (flash consistency is pinned by tests/thermo/test_electrolyte_variants.py)
- `pure_psat_limit` — applicability is the aqueous electrolyte liquid; the pure-component saturation limits of the molecular databank components are not this package's claimed surface (the involatile salt has no vapour pressure)

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).

## References

- Pitzer, K. S., Peiper, J. C. & Busey, R. H., J. Phys. Chem. Ref. Data 13(1), 1-102, 1984
- Hayden, J. G. & O'Connell, J. P., Ind. Eng. Chem. Process Des. Dev. 14(3), 209-216, 1975
