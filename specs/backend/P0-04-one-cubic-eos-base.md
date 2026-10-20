# P0-04: One cubic-EOS base; PR, SRK, PR78 become registrations

- **Phase:** 0
- **Depends on:** none
- **Packages you may edit:** `ngdesign.thermo`, `tests/thermo/`
- **Contract change:** no
- **Benchmark delta expected:** none (same flashes; wall may improve slightly)

## Goal
`thermo/pr.py`, `srk.py`, `pr78.py` are ~95 % identical (diff them: docstrings, the
`thermo`-library EOS class, the register name). `nrtl.py` repeats ~75 % of the same helpers
(StreamState mapping, aqueous classification, stability re-check, PH/PS wrappers). ~1060 lines
should be ~350. One base, parameterised by the EOS class, is the single place future Phase 1
contract methods (K-values, fugacities, phase enthalpies) get added.

## Files
- Create: `src/ngdesign/thermo/_state.py` — shared helpers, moved verbatim from `pr.py`:
  flasher construction from the component list, `FlashVLN` result → `StreamState` mapping, the
  aqueous-phase classification (water > 0.5 rule, keep as is), the stability re-check, and the
  PH/PS wrappers over PT.
- Create: `src/ngdesign/thermo/cubic.py` — `class CubicEOS` implementing the `Thermo` protocol,
  constructed with the `thermo`-library mixture EOS class (`PRMIX`, `SRKMIX`, `PR78MIX`) and the
  k_ij source used today.
- Edit: `src/ngdesign/thermo/pr.py`, `srk.py`, `pr78.py` — each becomes a ≤ 25-line module:
  docstring with the EOS citation, `@register("thermo", "<name>")`, subclass or factory of
  `CubicEOS`. Public names that tests import must survive (check `tests/thermo/` and
  `tests/golden/test_thermo.py` first).
- Edit: `src/ngdesign/thermo/nrtl.py` — use `_state.py` helpers; keep its own `GibbsExcessLiquid`
  construction and its BIP-provenance refusal exactly.
- Edit/Create: `tests/thermo/test_cubic_identity.py` — for each of pr/srk/pr78 and for 6 states
  spanning the slice feed (two-phase, dense gas, liquid, near-critical, water-rich, sour), the
  `StreamState` produced after this change equals the one produced by the pre-change module to
  1e-12 relative. Generate the expected values **once from current `main`** and commit them as
  a small YAML fixture under `tests/thermo/fixtures/`; say in the PR how they were generated.

## Method
Pure refactor; numerics are the `thermo` library's. No change in tolerances, iteration caps,
stability logic or phase labelling. The docstring in `contracts/plugins.py` still says
"Peng-Robinson package" — leave it; Phase 1 rewrites that contract.

## Acceptance criteria
- [ ] `wc -l src/ngdesign/thermo/*.py` total ≤ 650
- [ ] `tests/golden/test_thermo.py`, all `tests/thermo/`, `tests/e2e/test_slice.py` PASS unchanged
- [ ] `tests/thermo/test_cubic_identity.py` PASS with fixtures generated from pre-change main
- [ ] `uv run python -c "from ngdesign import registry; print(sorted(registry.available('thermo')))"` lists the same names as before
- [ ] ruff, mypy, lint-imports, full `pytest -rs` green
- [ ] Nothing outside the listed packages changed

## Out of scope
New contract methods, caching, speed work, UNIFAC/PC-SAFT (Phase 1).
