# Adding a thermo model to the catalogue (spec T-01)

Property methods are **data**: one row in `data/thermo_models/*.yaml`, validated and
registered by `src/ngdesign/thermo/catalogue.py`. The adapter class stays as code in
`src/ngdesign/thermo/` (or `src/ngdesign/amine/`); the row carries identity, options,
provenance, applicability, status and evidence. The full field schema — including the
family/status/component-class/phase vocabularies — is documented in
`data/thermo_models/_schema.yaml`.

## 1. Write the adapter class

A class satisfying the `Thermo` protocol (`src/ngdesign/contracts/plugins.py`) over the
`thermo`-library primitives, in `src/ngdesign/thermo/<name>.py`. Pin the EOS on a class
attribute when the family is `cubic` (`eos = PRMIX`) — the catalogue cross-checks the
row's `options.eos` against it at load time.

Do **not** add an `@register` decorator: the catalogue registers the class as a factory
under the row's id when `registry.discover()` runs.

## 2. Add the row

Append to the family's YAML file (or open a new one — file layout is free; ids must be
unique across all files):

```yaml
- id: mymodel
  name: My Model
  family: cubic                      # vocabulary in _schema.yaml
  adapter: ngdesign.thermo.mymodel:MyModelThermo
  options: {eos: PRMIX, kij_table: ChemSep PR, alpha: default, translation: none, enthalpy: eos}
  params:
    source: thermo IPDB (ChemSep)
    provenance: "where the numbers come from, with the citation"
  applicability:
    component_classes: [hydrocarbon, light_gas]   # subset of the vocabulary
    polar: false
    electrolyte: false
    T_K: [90.0, 700.0]
    P_Pa: [1000.0, 2.0e8]
    phases: [V, L, VLL]
  status: provisional                # validated needs L1+L2 evidence (see §4)
  validation: []                     # P1-05 case ids from data/validation/cases.yaml
  references: ["Author, Title, Journal vol, pages, year"]
  l0: {}                             # see §3
  l0_excluded: {}                    # check -> reason, for checks that cannot apply
```

Load errors are fatal and name the file and row: duplicate ids, unknown vocabulary
values, unknown adapters, bad option values.

## 3. Declare the L0 self-consistency checks

Every row must either **declare parameters** for each applicable L0 check or
**exclude** it with a written reason in `l0_excluded`. The seven checks the harness
implements (`scripts/validate_properties.py`):

| check | what it proves | tolerance |
| --- | --- | --- |
| `pure_psat_limit` | bubble P = dew P = databank Psat on pure feeds | 1e-6 relative |
| `phase_identification` | pure component liquid above its own bubble P, vapour below (the #124 lesson; the bracket anchors on the package's own bubble pressure) | exact classification |
| `round_trip` | PT→PH→PT and PT→PS→PT recover the state | 1e-6 relative |
| `dhdT_cp` | dH/dT equals Cp at fixed P | 1e-4 relative |
| `gibbs_duhem` | Σ xᵢ d(ln φᵢ) path integral over a composition loop | 1e-6 (normalized; ε=0.01, n=100) |
| `single_liquid_limit` | the applicability point state is a single liquid | exact classification |
| `determinism` | two instances produce bit-identical states | exact |

`l0_note` carries measured caveats — e.g. NRTL's phase-identification points are
MeOH/H2O because thermo's pure-nC4 vapour-pressure correlation sits ~8 % above the
ChemSep databank Psat, so a databank-Psat bracket would land inside the model's own
two-phase region. Exclusions are printed in every audit and per-model report; an
undeclared check or an empty exclusion reason fails the audit.

## 4. Status and evidence

`scripts/validate_properties.py --audit` enforces, per row:

- **validated** — L0 green **and** ≥ 1 `pure_cases` (L1) and ≥ 1 `binary_cases` (L2)
  case id in `validation`, all of which exist in `cases.yaml`;
- **provisional** — L0 green;
- **experimental** — exempt, hidden from the audit table.

To promote a row to `validated`: add/declare the reference cases per
`docs/validation.md` ("How to add a case"), list their ids in `validation`, and run
`--write-doc` so the per-model report (`docs/validation/<id>.md`) carries the outcomes.

## 5. Run the gates

```bash
uv run python scripts/validate_properties.py --audit   # catalogue consistency
uv run python scripts/validate_properties.py --write-doc  # regenerate reports
uv run pytest tests/thermo/test_catalogue.py           # load/build/L0/audit tests
```

Commit the row, the regenerated `docs/validation.md` + `docs/validation/<id>.md`, and
(if you added cases) `cases.yaml`/`results.json` together.

## Registry mechanics (why there is no decorator)

`registry.discover()` imports every plugin package, then calls
`ngdesign.thermo.catalogue.register_all`, which registers one factory per row under
the row's id. The import is dynamic because `ngdesign.registry` sits **below**
`ngdesign.thermo` in the layer contract (`.importlinter`) — a static import would be
a lint failure, and ignore_imports lines are not allowed. A row whose id a decorator
already registered with the same class is tolerated (metadata attaches to the class
registration); that tolerance exists only for the amine packages and disappears when
#125 (P1-09) moves them into catalogue rows.
