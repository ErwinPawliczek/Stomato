# P0-05: Engineering layer de-duplication

- **Phase:** 0
- **Depends on:** none (do not touch `cli.py` or `api/`; P0-03 owns those)
- **Packages you may edit:** `ngdesign.sizing`, `ngdesign.pid_rules`, `ngdesign.render`, `tests/sizing/`, `tests/pid_rules/`, `tests/render/`
- **Contract change:** no
- **Benchmark delta expected:** none

## Goal
The "new files only" era left copies of engineering code that can silently diverge from the
tested originals. One definition per function.

## Files
- Edit: `src/ngdesign/sizing/machines.py`
  - delete its `npsh_available` (l.134) and `lmtd_counter` (l.152); call
    `ngdesign.sizing.pump_power.npsh_available` and the registered `lmtd_counter` correlation
    (`ngdesign.sizing.lmtd.lmtd_counter`).
- Create: `src/ngdesign/sizing/_nozzles.py` — single `connected`, `nozzle_nps_in`,
  `min_flange_class`, `nozzle` (currently duplicated between `vessels.py` and `machines.py`).
  Where the two copies differ (e.g. `_connected` return type, `role` default), reconcile to one
  signature and adapt both callers; results for the slice must be byte-identical.
- Edit: `src/ngdesign/sizing/vessels.py`, `machines.py` — import from `_nozzles`.
- Create: `src/ngdesign/pid_rules/_common.py` — single `psv_nozzle` (now in both
  `psv_sizing.py:237` and `vessel_psv.py:46`); both rules import it.
- Create: `src/ngdesign/render/_graph.py` — one `topological_layers(nodes, edges)` over plain
  tags/edges; `pfd_svg.py` and `pid_svg.py` build their edge lists and call it. The two `_layout`
  functions stay separate (different inputs) but share the layer function.
- Tests: add a test per shared module (`tests/sizing/test_nozzles.py`,
  `tests/pid_rules/test_common.py`, `tests/render/test_graph.py`) covering the reconciled
  behaviour, including the cases where the old copies differed.

## Method
Behaviour-preserving. `tests/e2e/test_slice.py` (byte-identical SVG/HTML) plus
`tests/property/test_pid_rules.py` and `tests/property/test_isometric.py` are the oracles.
If reconciling two copies reveals a genuine disagreement that changes an output, stop and
write both versions and the delta in the PR — do not pick silently.

## Acceptance criteria
- [ ] Each of `npsh_available`, `lmtd_counter`, `_connected`, `_nozzle_nps_in`, `_min_flange_class`, `_nozzle`, `_psv_nozzle`, `_topological_layers` is defined exactly once under `src/ngdesign/` (grep)
- [ ] `tests/e2e/test_slice.py`, `tests/property/test_pid_rules.py`, `tests/property/test_isometric.py`, all `tests/sizing/`, `tests/pid_rules/`, `tests/render/` PASS unchanged
- [ ] New tests PASS
- [ ] ruff, mypy, lint-imports, full `pytest -rs` green
- [ ] Nothing outside the listed packages changed

## Out of scope
`cli.py`, `api/`, `export.py` (P0-03). The router's 3-D `_layout`. Any sizing-constant change (H-04).
