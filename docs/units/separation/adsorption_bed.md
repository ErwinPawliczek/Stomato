# Adsorption bed (TSA/PSA) (`adsorption_bed`)

Family: **separation** · P&ID symbol: `X`

Rigour ladder: R0 provisional, R1 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `feed_in` | yes | gas to the bed |
| outlet | `product_out` | yes | treated product |
| outlet | `regen_out` | no | regeneration (tail-gas) outlet during the cycle |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R0 | provisional | `ngdesign.units.separation.adsorption_bed:AdsorptionBed` | adsorbate split spec to regen_out; product and desorbate flashed at their own T (product_T / regen_T, default feed T) and their own P; info cycle_time_s = capacity * bed_mass / adsorbate mass rate. The default capacity 0.10 kg/kg is the ~10 wt% design water loading GPSA quotes for molecular sieves (Sect. 20, dehydration). V1 gap -- no printed worked example of a split-spec adsorption bed with its printed outlet state was found; the row is checked by closed-form tests only |
| R1 | provisional | `ngdesign.units.separation.adsorption_bed_r1:AdsorptionBedR1` | R0 outlets and duty unchanged; cycle_time_s from extended-Langmuir equilibrium loading (feed-basis partial pressures, Langmuir 1918 / Markham-Benton 1931), optional van 't Hoff affinity rescale (Ruthven 1984 Ch. 2), stoichiometric time on the removed rate and LUB breakthrough (Collins 1967; McCabe-Smith-Harriott 7th ed. Ch. 25; Geankoplis 4th ed. §12.3) — t_b = t_s·(1 − LUB/L), cycle = min over adsorbates. capacity_kg_per_kg is refused at R1. The R0 equivalence (capacity = q*·MW/1000 reproduces the same cycle time) holds to 1e-12. Spec issue recorded on PR no. 295 — the spec's printed CF3/CF4 times (57726.765 s / 50510.9194 s) are 1000× the A4 result for its own stated inputs (the division by the 1000 mol/s adsorbate rate was dropped); A4 is implemented as written. V1 gap — no printed worked example with a verifiable breakthrough time was transcribed: the verified FOSSEE transcription of Geankoplis Ch. 12 (tbc-python.fossee.in) contains only Ex. 12.3-1 (alcohol-in-air scale-up), whose printed outputs are used/unused bed lengths (10.23 / 3.77 cm) and a saturation capacity (0.124 g/g carbon); the book's comparable time appears only as the Part B design input (break point 6.0 hr), never as a printed result for a specified bed, and no isotherm is stated to transcribe. The McCabe-Smith-Harriott Ch. 25 candidate has no verified open transcription. The row is checked by closed-form tests only |

### R0 parameters

```yaml
properties:
  bed_mass_kg:
    description: bed mass, kg
    minimum: 0
    type: number
  capacity_kg_per_kg:
    description: adsorbate loading, kg per kg bed
    minimum: 0
    type: number
  product_P:
    description: product outlet pressure, Pa abs; default feed P
    type: number
  product_T:
    description: product outlet temperature, K; default feed T
    type: number
  regen_P:
    description: desorbate outlet pressure, Pa abs; default feed P
    type: number
  regen_T:
    description: desorbate outlet temperature, K; default feed T
    type: number
  removal_fraction:
    description: component id -> fraction of its molar flow taken to the desorbate
    type: object
required:
- removal_fraction
type: object
```

### R1 parameters

```yaml
properties:
  T_ref_K:
    description: reference temperature of the given b values, K; with dH_ads_J_mol
    minimum: 0
    type: number
  bed_density_kg_m3:
    description: packed-bed density, kg/m3 (geometry form, all three required)
    minimum: 0
    type: number
  bed_diameter_m:
    description: bed inside diameter, m (geometry form)
    minimum: 0
    type: number
  bed_length_m:
    description: packed length, m (geometry form); required for a LUB
    minimum: 0
    type: number
  bed_mass_kg:
    description: bed mass, kg; or the geometry form below, exactly one
    minimum: 0
    type: number
  dH_ads_J_mol:
    description: adsorbate id -> heat of adsorption, J/mol (negative); with T_ref_K,
      rescales b via van t Hoff
    type: object
  langmuir:
    description: adsorbate id -> {q_max_mol_kg, b_1_Pa}; saturation capacity mol/kg
      and Langmuir affinity 1/Pa; extended Langmuir over all adsorbates
    type: object
  lub_m:
    description: length of unused bed, m; default 0
    minimum: 0
    type: number
  product_P:
    description: product outlet pressure, Pa abs; default feed P
    type: number
  product_T:
    description: product outlet temperature, K; default feed T
    type: number
  regen_P:
    description: desorbate outlet pressure, Pa abs; default feed P
    type: number
  regen_T:
    description: desorbate outlet temperature, K; default feed T
    type: number
  removal_fraction:
    description: component id -> fraction of its molar flow taken to the desorbate
    type: object
required:
- removal_fraction
- langmuir
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-D 9

> molecular-sieve dehydration (plan U-G 6) maps onto this row with a cycle — no separate treating row.
