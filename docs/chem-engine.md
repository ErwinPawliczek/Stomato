# Chemistry engine

Three layers added on top of the flowsheet simulator. They do not change any flowsheet
result: reactor units keep their own paths, and the new layers are reachable from
Python and the `ngdesign chem` command.

```
ngdesign.chem   stoichiometry, thermochem, equilibrium, kinetics, phase   (above ngdesign.units)
ngdesign.data.chemdb   cited chemical database                            (data layer)
ngdesign.uom    dimensions, units, quantities                             (bottom layer)
```

`ngdesign.units` means unit *operations* in this codebase, so units of measure are `uom`.

## Units of measure

SI floats stay the engine's currency; `uom` is how edges get in and out.

```python
from ngdesign.uom.quantity import Q, convert, coerce

Q("500 psia").magnitude("bar")              # 34.47
convert(212, "degF", "degC")                # 100.0
convert(1, "Btu/lb-degF", "kJ/(kg K)")      # 4.1868
convert(50, "MMSCFD", "mol/s")              # gas-industry standard volume, as moles
convert(100, "kg/h", "kmol/h", mw=16.04)    # basis change, only with an explicit molar mass
Q(25, "degC") * Q(8.314, "J/(mol K)")       # uses 298.15 K
Q(20, "degC") + Q(5, "degC")                # OffsetUnitError: two points on a scale
coerce("1 bar", "temperature")              # DimensionError
```

Rules worth knowing:

- A space, hyphen or `·` binds tighter than `/`, so `Btu/lb-degF` and `J/kg·K` read as an
  engineer means them. `*` after a `/` is refused: code and print disagree on it.
- `degC` and `psig` are shifted scales alone and intervals inside a compound (`degC/min`).
- `F`, `C` and `R` are refused as ambiguous: write `degF` or `farad`, and so on.
- `Nm3`, `Sm3` and `scf` are ideal-gas amounts at their stated reference states, so
  `MMSCFD` is a molar flow.
- A public function decorated `@si_arguments(T="temperature")` takes `350.0` (SI),
  `"77 degC"` or `Q(...)`, and rejects a wrong dimension at the call.

Unit sets for display: `SI`, `METRIC`, `FIELD`; see `ngdesign.uom.sets`.

## Chemical database

See [data/chemdb/README.md](../data/chemdb/README.md) for the file formats, grading and rebuild.

```python
from ngdesign.data import chemdb

chemdb.find("MEK")                     # CAS, name, formula, InChIKey, SMILES, CID
chemdb.value("methane", "Hf_gas")      # selected value + source, grade, uncertainty
chemdb.values("methane", "Hf_gas")     # every source that states it
chemdb.find("C4H10")                   # AmbiguousSpeciesError: butane, isobutane
```

A formula never silently picks an isomer. Pass a name or a CAS number.

## Stoichiometry

```python
from ngdesign.chem.stoichiometry import balance, limiting_reagent, reaction_space, to_reaction

balance("MnO4- + Fe+2 + H+ -> Mn+2 + Fe+3 + H2O")   # exact, rational; charge conserved
reaction_space(["CH4", "H2O", "CO", "CO2", "H2"])   # rank 3, 2 independent reactions
limiting_reagent("N2 + 3 H2 -> 2 NH3", {"N2": 1, "H2": 2})
to_reaction("CH4 + H2O -> CO + 3 H2", reaction_id="smr", provenance="...")   # flowsheet contract
```

An equation with several independent balances is refused, not guessed. So are the
charges that cannot be read safely: `Fe3+` and `NH4+` are told apart by context, but
`SO42-` and `O2-` need a caret (`SO4^2-`). `balance` reduces to smallest integers;
everything else keeps your basis, so `H2 + 1/2 O2 -> H2O` stays per mole of H2.

## Thermochemistry

```python
from ngdesign.chem.thermochem import reaction_thermo, heating_value, adiabatic_flame_temperature

r = reaction_thermo("N2 + 3 H2 -> 2 NH3", "400 degC")
r.dH, r.dS, r.dG, r.K, r.provenance()
heating_value("methane").lhv_mass
adiabatic_flame_temperature("propane", phi=0.8)
```

Species models, best first: NIST-JANAF table (Hermite-interpolated), NIST Shomate, gas Cp
fit (TRC, Poling), constant Cp (condensed only, and named so). A temperature outside the
model's range is refused. Standard states: 1 bar ideal gas; pure condensed phase. With no
phase given, a term takes its stable phase at T, so `2 H2 + O2 -> 2 H2O` forms liquid
water at 298 K and steam at 500 K; `(g)`/`(l)`/`(s)` overrides that. An unqualified element
means its JANAF reference state, so `S` at 1000 K is the S2-rich reference vapour, while
`S(g)` is the atomic gas.

## Equilibrium

```python
from ngdesign.chem.equilibrium import gibbs_equilibrium, adiabatic_equilibrium, reaction_equilibrium
from ngdesign import registry

gibbs_equilibrium({"CH4": 1}, ["CH4", "H2", "C(s)"], "930 degC", "1 bar")     # carbon deposits
gibbs_equilibrium({"N2": 1, "H2": 3}, ["N2", "H2", "NH3"], 700, "300 bar",
                  thermo=registry.create("thermo", "pr"))                     # real-gas fugacity
adiabatic_equilibrium({"CH4": 1, "O2": 2, "N2": 7.52}, [...])                  # flame with dissociation
reaction_equilibrium(["CO + H2O -> CO2 + H2"], feed, 900)                     # only listed reactions run
```

The Gibbs solver covers an ideal-gas mixture plus pure condensed species, with fugacity
coefficients from any registered package. It does not model liquid solutions: a condensing
mixture of two organics is outside it.

## Kinetics

```python
from ngdesign.chem.kinetics import ArrheniusLaw, Mechanism, Step, simulate_batch, solve_cstr
from ngdesign.chem.kinetics import fit_arrhenius, fit_order, rate_constant, integrate_reaction_set

rate_constant(1.2, "L/(mol s)", order=2)      # SI; a mis-stated order raises DimensionError
mech = Mechanism([Step("N2O4 -> 2 NO2", ArrheniusLaw(A, Ea), reversible=True)])
simulate_batch(mech, {"N2O4": 40.0}, 300.0, t_end=1.0)    # stiff, reverse rate from K_c(T)
```

`reversible=True` takes the reverse constant from detailed balance, so a mechanism cannot
overshoot equilibrium. `adiabatic=True` adds the energy balance. Flowsheet reaction sets stay
on their own rate laws through `integrate_reaction_set`, which calls the reactor units' `rate`.

## Phase behaviour

```python
from ngdesign.chem import phase
from ngdesign import registry

phase.psat("benzene", "80 degC").P
phase.pure_phase("water", 700, "300 bar")                 # "supercritical"
phase.raoult_flash({"benzene": .4, "toluene": .6}, 365, 8.5e4)
pkg = registry.create("thermo", "wilson_ig")
phase.txy(pkg, "EtOH", "H2O", "1 atm")
phase.find_azeotrope(pkg, "EtOH", "H2O", "1 atm")
phase.eutectic("naphthalene", "biphenyl")
```

## Command line

```bash
ngdesign chem lookup methane
ngdesign chem balance "C3H8 + O2 -> CO2 + H2O"
ngdesign chem react "N2 + H2 -> NH3" --T "400 degC" --units METRIC
ngdesign chem equilibrium --feed CH4=1 H2O=3 --species CH4 H2O CO CO2 H2 --T "800 degC" --P "1 bar"
ngdesign chem saturation water --P "10 bar"
ngdesign chem convert 50 MMSCFD mol/s
ngdesign chem info
```

## How it was checked

| Claim | Oracle, independent of the code under test |
|---|---|
| Equilibrium constants | JANAF's own log Kf columns against ln K rebuilt from H and S |
| Reaction enthalpies | NIST-measured heats of combustion, through Hess's law |
| Ideal-gas Cp, critical points, Psat, Hvap | CoolProp reference equations of state |
| Gibbs solver | Each independent reaction's K at the solution; a second solver; G rises off the solution |
| Kinetics | Closed forms (Bateman, integrated rate laws, CSTR); Radau on Robertson's stiff problem |
| Conversions | Exact definitions |
