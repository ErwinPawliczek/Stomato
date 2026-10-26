# absorber R2: zero-tear MESH absorber via the column API

- **Family / package:** column, `src/ngdesign/units/column_shortcut/` (the R0 package of this row; the R2 adapter is a new module there, no new package)
- **Levels delivered:** R2, from `planned` to `provisional`. R3 (rate-based) stays `planned`.
- **Depends on:** U-R2 conventions, U-01d (#243). Calls the public column API only; edits nothing in `src/ngdesign/units/column/`. S0-1c may run concurrently, because this adapter uses only the long-standing zero-tear configuration (no side strippers, no decant).
- **Wave/order:** parallel-safe.
- **Branch:** `u-lv/absorber` · **Issue:** (orchestrator fills in)
- **Owned files (exhaustive):**
  - `src/ngdesign/units/column_shortcut/absorber_r2.py` (new)
  - `tests/units/column_shortcut/test_absorber_r2.py` (new)
  - `data/validation_units/column/cases/absorber.yaml` (new; U-01d per-unit file)
  - `data/unit_models/column.yaml`: only `levels.R2` of row `absorber`, plus its `notes` line if a V1 gap is recorded
- **Read-only imports (verified to exist on main, 2026-10-25):**
  - `ngdesign.units.column.Column` — `Column().solve(inlets: dict[str, StreamState], params: dict[str, Any], thermo: Thermo) -> UnitResult`; outlets `distillate`, `bottoms`, `side_draw`; info keys `stage_{j}_T_K`, `stage_{j}_L_mol_s`, `stage_{j}_V_mol_s`, `stage_{j}_x_{cid}`, `stage_{j}_y_{cid}`, `n_stages`, `outer_iterations`, `inner_iterations`, `ns_used`
  - `ngdesign.units.column.ColumnSpecError` (ValueError), `ngdesign.units.column.ColumnConvergenceError` (RuntimeError)
  - `ngdesign.contracts.StreamState`, `ngdesign.contracts.UnitResult`, `ngdesign.contracts.plugins.Thermo`
- **Current state:** R0 = `ngdesign.units.column_shortcut.absorber:Absorber` (Kremser, params `N`, `k_overrides`). Ports: inlets `gas_in` (feed gas), `solvent_in` (lean solvent); outlets `gas_out`, `rich_out`. V1 `V1-kremser-absorber-seader53`.

## Method
### Equations
The absorber is the MESH equilibrium-stage column (Material, Equilibrium, Summation and entHalpy balances per stage) with no condenser and no reboiler. It has zero tear variables: the two feeds determine the column (P1-09; Boston & Sullivan 1974 inside-out with Naphtali & Sandholm 1971 fallback, as implemented in `ngdesign.units.column`). Stage numbering is 1..N top to bottom.
1. Lean solvent enters stage 1 as a liquid feed; feed gas enters stage N.
2. `gas_out` is the vapour leaving stage 1 (the column's `distillate` outlet when `condenser = "none"`).
3. `rich_out` is the liquid leaving stage N (the column's `bottoms`).

No new equations are introduced: R2 is the column row's absorber configuration, wrapped behind this row's ports.

### Algorithm
1. Read `n_stages` (int ≥ 2) and the optional `pressure_profile` (Pa; a scalar or a list of N floats). The default is the scalar `gas_in.P`. Validate both; see Refusals.
2. Build the column params:
   ```python
   {"n_stages": N, "condenser": "none", "reboiler": "none",
    "pressure_profile": pressure_profile, "feed_stage": N,
    "feeds": [{"stage": 1, "T": solvent_in.T, "P": solvent_in.P,
               "molar_flow": solvent_in.molar_flow,
               "composition": dict(solvent_in.composition)}]}
   ```
   `gas_in` is passed as the column's `feed` port: `Column().solve({"feed": gas_in}, params, thermo)`.
3. Map the outlets: `gas_out = result.outlets["distillate"]`, `rich_out = result.outlets["bottoms"]`. The column's `side_draw` is a zero-flow placeholder and is dropped.
4. **Energy, reported honestly.** The column feeds the solvent by re-flashing it at (T, P), and a zero-hardware column closes its enthalpy only to its stage-H gate (`_MESH_H_TOL = 1e-2` relative, measured P1-09: 4.8e-3 of throughput at N=2, 3.8e-7 at N=20). Compute the adapter's own boundary residual from the ACTUAL inlet states:
   `Q_res = Σ(n·h)_out − (gas_in.molar_flow·gas_in.enthalpy + solvent_in.molar_flow·solvent_in.enthalpy)`.
   Return `duty_W = Q_res`. That closes V0 exactly, and it is reported as `info["mesh_energy_residual_W"] = Q_res` and `info["mesh_energy_residual_rel"] = |Q_res| / max(|ΣH_in|, |ΣH_out|, 1)`. An adiabatic absorber has no real duty: `duty_W` is the solver's residual, documented as such in the module docstring, never a modelled exchanger.
5. Copy the column's per-stage info keys into `info` unchanged, plus `n_stages`.

No iteration of its own: every iteration lives in the column, with its own bounded budgets and typed `ColumnConvergenceError`.

### Reduction to the lower level
None exact: R0 (Kremser with a constant absorption factor) and R2 (MESH) are different models. The documented relation, measured P1-09 V2b (`tests/units/column_shortcut/test_v2_vs_mesh.py`): Kremser and MESH C3 recoveries differ by stage count (0.62276 vs Kremser at N=2). The identity this level must hold is to the column row itself. Step 1's test: the adapter's outlets equal a direct `Column().solve` with the mapped params, bit-for-bit (the same floats).

### Refusals
| Condition | Error | Message fragment |
|---|---|---|
| `n_stages` missing, not an int, or < 2 | `AbsorberR2Error(ValueError)` (new, in the owned module) | `n_stages` |
| `pressure_profile` a list whose length ≠ n_stages, or any value ≤ 0 | `AbsorberR2Error` | `pressure_profile` |
| `gas_in` or `solvent_in` with zero molar flow | `AbsorberR2Error` | `gas_in` / `solvent_in` |
| `solvent_in` vapour fraction > 0.5 (the solvent must be mainly liquid; the zero-tear seed assumes a liquid top feed) | `AbsorberR2Error` | `solvent_in` |
| Any key other than `n_stages`, `pressure_profile` | `AbsorberR2Error` | `unknown` |
| Column convergence failure | re-raised `ColumnConvergenceError` unchanged (never caught or converted) | (column's own message) |

## Params
| name | type | unit | required/default | range | meaning |
|---|---|---|---|---|---|
| `n_stages` | integer | — | required | ≥ 2 | equilibrium stages |
| `pressure_profile` | number or array of numbers | Pa abs | default `gas_in.P` | > 0, length n_stages if array | stage pressures, top to bottom |

```yaml
params:
  type: object
  required: [n_stages]
  additionalProperties: false
  properties:
    n_stages: {type: integer, minimum: 2, description: equilibrium stages (top = 1)}
    pressure_profile:
      description: stage pressures, Pa abs (scalar = uniform; list = per stage, top to bottom); default gas_in.P
      oneOf:
      - {type: number, exclusiveMinimum: 0}
      - {type: array, items: {type: number, exclusiveMinimum: 0}}
```

## Outputs
- `gas_out`: the column `distillate` (stage-1 vapour, flashed by the column at stage-1 T, P).
- `rich_out`: the column `bottoms` (stage-N liquid).
- `duty_W`: the boundary energy residual Q_res (see Algorithm step 4). `power_W` = 0.
- `info`:
  - every `stage_{j}_*` key from the column, unchanged;
  - `n_stages`, `outer_iterations`, `inner_iterations`, `ns_used`;
  - `mesh_energy_residual_W`, `mesh_energy_residual_rel`.

## Tests
- **Closed-form (equilibrium-pair limit):** `gas_in` and `solvent_in` are the vapour and liquid phases of ONE PT flash. The counter-current column then transfers nothing at any N: `gas_out = gas_in`, `rich_out = solvent_in`.
  - Case: z = {C1: 0.6, C3: 0.2, nC5: 0.2}, 300 K, 2.0 MPa, 100 mol/s, `pr` thermo.
  - Flash results (from `thermo.flash_pt`, never from the column; script `calc_absorber.py`): VF = 0.7338662501196833, so V = 73.38662501196833 mol/s and L = 26.613374988031666 mol/s.
    - vapour y: C1 0.7852356746600246, C3 0.17445492761918677, nC5 0.04030939772078857;
    - liquid x: C1 0.08921093242674073, C3 0.27044077079879525, nC5 0.640348296774464.
  - Build `gas_in = flash_pt(y, 300, 2e6, V)` and `solvent_in = flash_pt(x, 300, 2e6, L)`, then run N = 2, 4, 8.
  - Assert: `gas_out.molar_flow == V` (rel 1e-8); each `gas_out.composition[c] == y[c]` (abs 1e-8); top stage T = 300 K (abs 1e-5 K); `rich_out.molar_flow == L` (rel 1e-7).
  - Measured on main through the column directly: dD/V = −2.45e-9 (N=2), −2.65e-9 (N=4), −2.77e-9 (N=8); max |Δy| 2.9e-9 to 3.4e-9; T_top − 300 = −8e-7 K; 0.1 s per solve.
- **Identity to the column row:** for the R0 `example_case` feeds with N = 4, the adapter's `gas_out`/`rich_out` equal `Column().solve` with the mapped params, field by field with `==`.
- **Balances:** total moles closed at 1e-8, per-component closed at the column's documented gate (P1-09 measured 5e-8 at N = 2, 4, 20; do NOT use N = 8 for a component-closure assertion, whose measured floor is 3.4e-2). Also `|mesh_energy_residual_rel| ≤ 1e-2` (the column's `_MESH_H_TOL`), and the measured value goes in the assertion comment.
- **Refusals:** one test per row of the refusal table, each `pytest.raises(AbsorberR2Error, match=...)`.
- **V1 candidates:** I know of no specific example number I have seen printed, so this is a **V1 gap** unless the implementer finds one.
  - Search the rigorous (sum-rates or Newton) absorber examples in Seader, Henley & Roper, *Separation Process Principles* (3rd ed.), in the chapter on rigorous multicomponent methods. Use one only if it prints both the feed and solvent specs and the product flows or stage temperatures.
  - Also search Henley & Seader, *Equilibrium-Stage Separation Operations in Chemical Engineering* (1981), the absorber chapter.
  - A case must use the book's own K or thermo basis. If it uses a K basis this repo can't reproduce (for example tabulated K-values), the miss goes in `assessed` with the measured numbers. Never reconstruct numbers.

## Steps
1. **Adapter, identity and refusals (≈35 min).** Write `absorber_r2.py`: class `AbsorberR2` with `inlet_ports = ("gas_in", "solvent_in")`, `outlet_ports = ("gas_out", "rich_out")`, `solve`, and `example_case`. The example case is R0's feeds (call `Absorber.example_case()` and replace the params with `{"n_stages": 4}`). Add the identity test and the refusal tests. Push and open the PR.
2. **Closed-form and balance tests (≈30 min).** Add the equilibrium-pair test (N = 2, 4, 8), the balance tests and the energy-residual bound. Push.
3. **Catalogue flip and harness (≈30 min).** Set `levels.R2` of row `absorber`: `status: provisional`, `adapter: ngdesign.units.column_shortcut.absorber_r2:AbsorberR2`, the params schema above, the note "zero-tear MESH via the column API (inside-out + NS fallback); duty_W = boundary energy residual", and `validation: []` unless step 4 lands a case. Regenerate the docs, run `--audit` and the gates. Push.
4. **V1 (≈30 min, optional).** Only with a printed source in hand: add `data/validation_units/column/cases/absorber.yaml`. Otherwise record the V1 gap in the row `notes`, naming what was searched. Push.

## Review checklist
- The adapter passes `condenser="none"`, `reboiler="none"`, `feed_stage=N`, and the solvent on stage 1 with its own T/P/flow/composition.
- `gas_out` is mapped from `distillate` and `rich_out` from `bottoms`.
- `duty_W` is computed from the ACTUAL inlet `StreamState` enthalpies, and is documented as a solver residual.
- No `except ColumnConvergenceError` anywhere in the module.
- The equilibrium-pair expected values come from the flash in the test, never from a column call.
- The component-closure test avoids N = 8, or carries the measured floor.
- No file under `src/ngdesign/units/column/` is touched.
