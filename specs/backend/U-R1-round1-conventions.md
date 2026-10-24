# U-R1: Round-1 conventions (every family thread U-A..U-H2 follows this)

- **Phase:** Unit catalogue round 1, palette R0 (docs/unit-catalogue-plan.md §5, round 1)
- **Depends on:** U-00 (#197), U-R (#199), U-01 (#205, the V1 runner)
- **Contract change:** no; any thread needing one stops and posts `BLOCKED:` on its issue

## What every family thread delivers
For every unit listed in its family spec:
1. An R0 adapter class implementing `contracts.plugins.UnitModel`: `inlet_ports`, `outlet_ports`,
   `solve(inlets, params, thermo) -> UnitResult`, and `example_case()` returning the unit's own feeds
   (P0-01 pattern; reuse `units/_examples.py` helpers). R0 means *balances plus a spec*: no sizing physics.
2. Its catalogue row flipped in `data/unit_models/<family>.yaml`:
   - set R0 `status: provisional`, `adapter: "ngdesign.units.<family_pkg>.<module>:<Class>"`;
   - fill R0 `params` with a JSON-schema fragment of every parameter, a one-line `note`, and V1 ids in
     `validation`;
   - reactive rows set `balance: mass_elements`, and rows that cannot run on `pr` set `example_thermo`.
   - Change nothing else in the row, and touch no other row.
   - Registration comes from the YAML (`units.catalogue.register_all`); add no `@register` decorator.
3. At least one **V1 worked case** in `data/validation_units/<family>/cases.yaml`, using the schema in
   the `scripts/validate_units.py` docstring (U-01).
   - Each case is a published, cited example with page or equation numbers, and the expected values
     carry the book's own rounding as tolerance.
   - Single published numbers with a citation are fine. Never copy proprietary tables wholesale
     (DIPPR/DECHEMA/Aspen/HYSYS/REFPROP) or GPL code or data (DWSIM).
   - When no open worked example exists, the unit ships `provisional` without one. Record the gap and
     what was searched in the row `notes`.
   - A measured miss is recorded with an `assessed:` note giving the measured numbers and the cause.
     Never widen a tolerance to make a case pass.
4. At least one **closed-form test** per unit in `tests/units/<family_pkg>/test_<unit>.py`. It checks an
   analytic or hand-computed result, not only balances.
   - Wrong constants pass balance tests: every constant you type is checked against its source, and
     the check is listed in the PR body.

## Rules
- **Location.** The new adapters go in a new subpackage `src/ngdesign/units/<family_pkg>/`, named in the
  family spec. Existing unit modules stay where they are and are not edited; import from them if you
  reuse their physics.
- **One owner per invariant.** Correlations already in the repo are called, never re-derived:
  - `ngdesign.sizing.*`: `cv_liquid`, `cv_liquid_isa`, `psv_api520_gas`, `darcy_colebrook`, `kremser`,
    `hammerschmidt_formation`, `nielsen_bucklin_suppression`, `souders_brown`, `lmtd_counter`;
  - `ngdesign.units._physics.kinetics` for any reaction.
  - Units consume the `Thermo` protocol only; they never import a property package.
- **Energy and material.** Every adapter closes V0 at 1e-8: moles, or mass plus elements on
  `mass_elements` rows; energy as `ΣnH in + duty_W + power_W = ΣnH out`, on the formation basis for
  reactive rows.
- **Outlet states.** Produce them with `thermo.flash_*`; never assemble a `StreamState` by hand except
  for zero-flow outlets.
- **Refusals.** Refuse a bad spec with a typed `ValueError` subclass naming the parameter. Never clamp
  silently.
- **Byte-identical.** `scripts/bench_baseline.py --check`, goldens, e2e and every existing unit's
  results stay unchanged.
- **Do not edit:**
  - `units/column/`, `amine/`, `contracts/`, `thermo/`, `scripts/validate_units.py`, or
    `units/catalogue.py`/`levels.py`;
  - other families' YAML or validation files;
  - `solver/`, except where the family spec explicitly grants one hook.
- **Generated docs.**
  - Write them with `uv run python scripts/validate_units.py`, then audit with
    `uv run python scripts/validate_units.py --audit` as a *separate* command, and commit them.
  - Never hand-edit `docs/units.md` or `docs/units/**`. On a merge conflict there, take main's version
    and regenerate.

## Survival and reporting
- **First action, within 10 minutes:** comment on your issue that you have started, with the main head
  you fetched.
- **Branch and pushes:** work in your own git worktree on branch `u-r1/<family>`, branched from current
  origin/main. Commit and push WIP at least every 30 minutes; unpushed work is lost on a sandbox reset.
  After a reset, re-fetch the branch and continue from it.
- **Checkpoints:** post one on the issue after each unit, with its V0 result, V1 result and the
  closed-form test.
- **Gates:**
  - `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src tests`, `uv run lint-imports`;
  - `uv run python scripts/bench_baseline.py --check`;
  - the harness `--audit` (exit 0: V0 green, no V1 findings);
  - targeted `pytest tests/units/<family_pkg>/ tests/units/test_unit_catalogue.py
    tests/property/test_unit_balances.py`.
  - Do not loop the full local pytest; GitHub CI is the full-suite gate.
- **PR:**
  - Open one PR against main titled `U-<X>: <family> R0`, with `Closes #<issue>` once every unit in the
    family spec is done (or documented as refused, with the measured reason).
  - The body carries a per-unit table: R0 method, V1 source and result, closed-form test, and constant
    checks.
  - Comment the PR link on the issue. Do not merge.
