# P1-02: Open component registry — any databank species, pseudo-components, per-flowsheet slate

- **Phase:** 1
- **Depends on:** P0-01 (units no longer import the slice), P1-01 (merged first; both edit `stream.py`)
- **Packages you may edit:** `ngdesign.contracts` (`stream.py`, `flowsheet.py`, new `components.py`), `ngdesign.data`, `data/components.yaml`, `ngdesign.thermo`, `ngdesign.solver`, `ngdesign.flowsheets`, `ngdesign.units` (only where `COMPONENTS` is referenced), `tests/contracts/`, `tests/data/`, `tests/solver/`
- **Contract change:** yes — composition validation, `Flowsheet.components`, tear-vector indexing
- **Benchmark delta expected:** none

## Goal
`contracts/stream.py:9-28` hard-codes 18 species as the universe; the solver's tear vector is
indexed by that tuple (`solver/sequential_modular.py:69-70`). `data/components.yaml` carries
Tc/Pc/ω that nothing reads (the EOS pulls constants from `chemicals` by CAS). Stomato must
simulate anything the `chemicals` databank knows (~20 k species) plus user pseudo-components,
with one provenance-graded source of truth per property.

## Files
- Create: `src/ngdesign/contracts/components.py`
  - `Component(Model)`: `id` (user-facing short id, e.g. "C1", "n-heptane", "C7+"), `name`,
    `cas: str | None`, `formula: str | None`, `mw`, `Tc`, `Pc`, `omega`, `Tb: float | None`,
    `sg: float | None`, `kind: Literal["databank","curated","pseudo"]`,
    `provenance: dict[str, str]` (property → source string, e.g. `"Tc": "chemicals/CRC"`).
  - `ComponentSet(Model)`: ordered list of `Component`, unique ids, `index(cid)`, `ids`.
- Create: `src/ngdesign/data/components.py` (or extend `data.py`) — resolution order:
  1. `data/components.yaml` curated entries (keep the 18; **remove** Tc/Pc/ω from the YAML and
     keep only id, name, CAS, and any *deliberate* override with a `provenance` note — the
     C6+ = n-hexane choice stays, documented);
  2. `chemicals` databank by CAS, then by name (`chemicals.identifiers.search_chemical`), with
     provenance strings taken from the databank's source fields;
  3. pseudo-component from `Tb` + `sg` via Lee–Kesler (Tc, Pc; Kesler & Lee 1976, *Hydrocarbon
     Processing* 55(3) 153) and the Lee–Kesler ω correlation; MW from Riazi–Daubert (1980).
     Use `chemicals`/`thermo` implementations where they exist; cite otherwise.
  - `resolve(id_or_cas_or_name) -> Component`; `resolve_set(ids) -> ComponentSet`.
- Edit: `src/ngdesign/contracts/stream.py`
  - `COMPONENTS` becomes `DEFAULT_SLATE` (same 18 ids) and is used **only** by sample
    flowsheets. `_check_composition` validates non-negativity and sum-to-1 only; membership is
    validated by `Flowsheet` (below) and by the thermo factory.
- Edit: `src/ngdesign/contracts/flowsheet.py`
  - `Flowsheet.components: list[str]` (default: the ids present in its feeds, computed by a
    validator when omitted, for backwards compatibility with every existing sample).
  - `_topology` validator also checks every feed composition's keys ⊆ `components`.
- Edit: `src/ngdesign/thermo/cubic.py`, `nrtl.py` — build EOS constants from `ComponentSet`
  (Tc/Pc/ω/Cp via the `Component`, not by re-querying `chemicals` separately), so pseudo-
  components flash. `nrtl` keeps refusing pairs without BIPs.
- Edit: `src/ngdesign/solver/sequential_modular.py` — tear vector indexed by the flowsheet's
  `components` list; `_T_IDX/_P_IDX` derived from its length.
- Edit: `src/ngdesign/units/*` — any reference to `COMPONENTS` for iteration uses the stream's
  own composition keys instead.
- Tests:
  - `tests/data/test_components.py`: resolve "C1" (curated), "n-heptane" (databank by name),
    "142-82-5" (by CAS), and a pseudo `C7+`(Tb=372 K, sg=0.73) → Tc/Pc/ω within 3 % of
    Lee–Kesler reference values stated in the test with their source; provenance populated.
  - `tests/contracts/test_components.py`: `Flowsheet` rejects a feed with an id outside
    `components`; defaults populate from feeds.
  - `tests/solver/test_open_components.py`: a mixer + splitter + recycle flowsheet with
    `["C1", "n-heptane", "C7+"]` solves and closes component balances.
  - `tests/thermo/test_pseudo_flash.py`: PT flash of C1/C7+ at 300 K, 30 bar is two-phase with
    the pseudo in the liquid; H consistent across phases (P1-01 identity).

## Method
No numeric change for existing flowsheets: all 18 curated ids must resolve to the **same CAS**
and therefore the same `chemicals` constants as today (`tests/e2e/test_slice.py` byte-identical,
`tests/golden/test_thermo.py` unchanged). Document the resolution order and provenance format
in `data/README.md` (create).

## Acceptance criteria
- [ ] `grep -rn "COMPONENTS" src/ngdesign` only hits `DEFAULT_SLATE` definition and sample flowsheets
- [ ] `data/components.yaml` holds no Tc/Pc/ω values without a `provenance` override note
- [ ] All tests above PASS; `tests/e2e/test_slice.py` byte-identical; golden thermo unchanged
- [ ] `bench/baseline.json --check` unchanged
- [ ] ruff, mypy, lint-imports, full `pytest -rs` green
- [ ] Nothing outside the listed packages changed

## Out of scope
UNIFAC group assignment, BIP regression, a UI for components, electrolyte species.
