# T-01: Thermo catalogue as data — registry, status, L0/L4 validation layers

- **Phase:** Thermo catalogue, wave 0 (serial root; every T-spec keys on this schema). Plan: `docs/thermo-catalogue-plan.md`, rationale: `docs/thermo-roadmap.md`
- **Depends on:** P1-05 (validation harness), P1-07 (slate context), hotfix #124; **dispatch only after P1-09 and P1-06 are merged** (they touch `amine/package.py`)
- **Packages you may edit:** `ngdesign.thermo` (new `catalogue.py`, new `options.py`; `pr.py`/`pr78.py`/`srk.py`/`nrtl.py` only to become catalogue rows), `ngdesign.amine` (`__init__.py` only, to register through the catalogue), `ngdesign.registry` (one hook: `discover()` loads the catalogue), `data/thermo_models/` (new), `scripts/validate_properties.py` (L0/L4 sections + per-model report), `tests/thermo/`, `docs/validation/` (generated)
- **Contract change:** no (`Thermo` protocol unchanged; `Flowsheet.thermo` stays a string id)
- **Benchmark delta expected:** none — the six existing packages must be byte-identical through the catalogue (bench `--check` unchanged on every case, e2e slice byte-identical, goldens unchanged)

## Goal
Today a property method is a Python class with a `@register("thermo", name)` decorator. The
catalogue plan needs ~170 methods, most of which are the same adapter with different options and
parameters. This spec makes a property method **data**: one YAML row per method, an adapter that
builds it, a `status` the harness controls, and two validation layers every adapter must pass
regardless of its physics.

## Files
- Create `data/thermo_models/_schema.yaml` (documented schema) and `data/thermo_models/cubic.yaml`,
  `gamma_phi.yaml`, `electrolyte.yaml` holding the six existing packages as rows:
  ```yaml
  - id: pr                       # registry name; stable; what Flowsheet.thermo names
    name: Peng-Robinson
    family: cubic                # cubic | gamma_phi | mixing | helmholtz | kvalue | saft | electrolyte | special
    adapter: ngdesign.thermo.cubic:CubicEOS
    options: {eos: PRMIX, kij_table: "ChemSep PR", alpha: default, translation: none, enthalpy: eos}
    params: {source: "thermo IPDB ChemSep PR", provenance: "Kooijman & Taylor, ChemSep"}
    applicability:
      component_classes: [hydrocarbon, light_gas, inert]   # from a fixed vocabulary in _schema.yaml
      polar: false
      electrolyte: false
      T_K: [90, 700]
      P_Pa: [1.0e3, 2.0e8]
      phases: [V, L, VLL]
    status: validated            # validated | provisional | experimental
    validation: [pure-C1-95.3K, pure-C1-125K, binary-C1-C3-..., ...]   # case ids in data/validation/
    references: ["Peng & Robinson 1976, Ind. Eng. Chem. Fundam. 15, 59"]
  ```
  Rows for `pr78`, `srk`, `nrtl`, `amine_ke`, `amine_enrtl` likewise; their `validation` lists are
  the P1-05 case ids that already run against them.
- Create `src/ngdesign/thermo/catalogue.py`: `load_catalogue() -> dict[str, ModelRow]` (pydantic
  model for a row, schema-validated, duplicate ids and unknown adapters raise at import with the
  file and row named), `build(row) -> Thermo` (imports the adapter, applies `options`), and
  `register_all()` which `registry.discover()` calls once: every row becomes
  `registry.register("thermo", row.id)` of a *factory* that builds the package — the existing
  class-based registrations in `pr.py`, `srk.py`, `pr78.py`, `nrtl.py` and `amine/package.py` are
  replaced by rows; the classes stay as adapters. `registry.available("thermo")` is the catalogue.
  `catalogue.describe(id) -> ModelRow` serves the API (`/api/meta` lists thermo ids with name,
  family, status, applicability) and the future advisor.
- Create `src/ngdesign/thermo/options.py`: the typed option objects the cubic adapter accepts now
  (`AlphaFunction` = default | twu | mathias_copeman, `VolumeTranslation` = none | peneloux,
  `EnthalpyMethod` = eos | lee_kesler) as *declarations* with the default implementations only;
  T-02 fills the non-default ones. Unknown option values fail at catalogue load.
- `scripts/validate_properties.py`:
  - **L0 self-consistency** (runs for every catalogue row, no data needed): pure-component limits
    (one-component feed: bubble P = dew P = Psat within 1e-6 relative; phase kind liquid above
    Psat and vapour below — the #124 regression), flash round-trips PT→PH→PT and PT→PS→PT within
    1e-6 on T, derivative identities on `derivatives()` (dH/dT = Cp within 1e-4 relative;
    central-difference check), Gibbs–Duhem on `ln_phi` for binaries (Σ x_i d ln φ_i = 0 at fixed
    T, P within 1e-6 on the slate binaries), determinism (two identical flashes bit-identical).
  - **L4 cross-model** (runs for every pair of rows sharing an applicability class): natural-gas
    dew point and density of the slice feed; agreement bounds per family pair recorded in the
    report, not asserted beyond a loose sanity band (20 %).
  - `status` enforcement: `--audit` exits non-zero if a row marked `validated` has a failing L0,
    or lacks L1+L2 cases in its `validation` list; `provisional` requires L0 green only;
    `experimental` is exempt but excluded from `--audit` output tables.
  - per-model report: `docs/validation/<id>.md` with layers, cases, measured values, status;
    `docs/validation.md` becomes the index. Regenerated with `--write-doc`; CI diffs it.
- `tests/thermo/test_catalogue.py`: schema rejects a bad row with file:row named; the six rows
  build and are the same classes as before (`type(registry.create("thermo","pr")) is
  PengRobinsonThermo`); `registry.available("thermo")` equals the catalogue ids; `Flowsheet(thermo=
  "pr")` solves the slice byte-identically (reuse the e2e slice oracle); L0 passes for all six
  (the amine packages' L0 on their own applicability: single-liquid limits, round trips); the
  `--audit` fails on a planted `validated` row without cases (tmp catalogue file via env
  `STOMATO_THERMO_MODELS_DIR`).
- `AGENTS.md` is locked: do not edit. Instead add `docs/thermo-catalogue-howto.md`: "adding a
  property method = one YAML row + its validation cases; code only for a new adapter".

## Method
Registry-as-data is the P1-02 pattern (components) applied to packages; status rules follow
`docs/thermo-catalogue-plan.md` §3. Cite Carlson 1996 (*Chem. Eng. Prog.* 92(10), 35) for the
applicability vocabulary (component classes, polarity, electrolytes, pressure ranges).

## Acceptance criteria
- [ ] Six rows load; `registry.available("thermo")` == catalogue ids; every existing test, golden, e2e and bench case unchanged (counts byte-identical)
- [ ] L0 green for all six; `docs/validation/<id>.md` generated for each; `--audit` green
- [ ] A planted bad row fails at load with file and row named; a planted unvalidated `validated` row fails `--audit`
- [ ] ruff, mypy, lint-imports (no new ignore lines; `catalogue` lives in `ngdesign.thermo`, imports only contracts/registry/data), full `pytest -rs` green; nothing outside the listed packages changed

## Out of scope
New adapters or options beyond the declarations (T-02..T-10), the advisor (T-08), new validation data (T-11..T-14), UI.
