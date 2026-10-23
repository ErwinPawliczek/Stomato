# twu-sim-tassone — Twu-Sim-Tassone cubic EOS

family `cubic` · status **experimental** · adapter `ngdesign.thermo.cubic:TwuSimTassoneThermo`.

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

Note: Fitted alpha table covers C1-nC6; CO2/N2/H2S in the slate use the generalised Twu alpha.

Declared exclusions (not silent skips):

- `gibbs_duhem` — The C1/C3 hc_liquid probe at 250 K sits above the TST internal methane pseudo-critical line, so the liquid root switches along the composition path; the vapour probe passes.
- `phase_identification` — The TST alpha is fitted to hydrogen/hydrocarbon systems; for the probe components at 300 K the internal vapour-pressure correlation deviates beyond the databank-anchored 0.5x/2x bracket.

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).

Declared case ids:

- `twu-sim-tassone-pure-C1-125K` — 
- `twu-sim-tassone-pure-C3-300K` — 
- `twu-sim-tassone-pure-nC4-280K` — 
- `twu-sim-tassone-pure-CO2-265K` — 
- `twu-sim-tassone-c1c3-294.26K-6.895MPa` — 
- `twu-sim-tassone-c1co2-277.15K-5.97MPa` — 
- `twu-sim-tassone-ng-dew-morch-243.4K-0.30MPa` — 
- `twu-sim-tassone-ng-dew-morch-254.6K-0.68MPa` — 
- `twu-sim-tassone-ng-dew-morch-260.8K-1.04MPa` — 

## References

- Twu, C. H.; Sim, W. D.; Tassone, V. A new cubic equation of state with a Twu-form alpha for hydrogen/hydrocarbon systems, 2002; constants and form as implemented in the Clapeyron.jl TSTEOS (github.com/ClapeyronThermo/Clapeyron.jl), retrieved 2026-10. Full journal citation unavailable offline; see PR body.
- Twu, C. H.; Bluck, D.; Coon, J. E.; Cunningham, J. R. A Cubic Equation of State with a New Alpha Function and a New Mixing Rule. Fluid Phase Equilib. 1991, 69 (1), 33-50 (generalised alpha used for components outside the fitted table).
