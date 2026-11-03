# Calculation provenance

Every number Stomato reports should be traceable to cited sources: the user's own inputs, a
row in a cited database, and the named equations that turned those into the result. This
document describes how the engine records that chain, what a trace looks like, how it is
audited, and how the UI shows it.

## 1. Goals and non-goals

**Goals**

- For any reported value (a stream's T, P, flow, enthalpy or composition; a unit's duty, power or
  `info` entry), produce the directed graph of everything it was computed from, down to leaves.
- Every leaf carries a citation: a source record (citation text, DOI/URL, table, row reference)
  for data, or "user input" for flowsheet specs. Every operation carries the method name, its
  formula in LaTeX and a literature reference.
- An audit lists every output that depends on an uncited leaf, an estimated leaf, or an
  operation with no recorded method.
- Tracing is **off by default**. With tracing off nothing changes: same numbers, same flash
  counts, a cost of one context-variable read per thermo call. With tracing on the numbers
  are still bit-identical, because the recorder only observes.

**Non-goals**

- Recording every iterate of an iterative method. Flash algorithms, column solvers and tear
  loops record the converged value with iteration count and residual.
- Tracing inside the `thermo` library. A flash is one operation whose inputs are the state
  specification and the model's parameters (Tc, Pc, omega, k_ij, ideal-gas Cp correlations).
  Its method node names the EOS and the flash algorithm with their references.
- Symbolic algebra. Equations are recorded as LaTeX for display, not evaluated.

## 2. Graph model

A trace is a bipartite DAG of **value nodes** and **operation nodes**
(`ngdesign.provenance.model`):

```
ValueNode  id, label, value, unit, kind, quality, citation?, stream?, unit_tag?, prop?
OpNode     id, label, method (catalogue key), name, latex, reference?, unit_tag?,
           iterations?, residual?, converged?, note?
Edge       source, target, role, feedback
TraceGraph values, ops, edges, meta
```

Value `kind`:

| kind | meaning | example |
|---|---|---|
| `input` | a flowsheet specification | feed T of S-001, `T_out` of E-101 |
| `constant` | a database constant | Tc of methane, ChemSep PR k_ij matrix |
| `parameter` | a model parameter or correlation | ideal-gas Cp(T) correlation of ethane |
| `intermediate` | computed and consumed inside a unit | outlet P = P_in - dP |
| `output` | a reported number | S-002 enthalpy, E-101 duty_W |

Value `quality`: `cited` (a source record), `user` (a flowsheet input), `estimated` (a cited
estimation method, e.g. Joback, Lee-Kesler for a pseudo-component), `derived` (computed
from other values; carried by intermediates and outputs), `uncited` (nothing known).

`value` is a float, a `dict[str, float]` (composition, per-component flows) or a matrix
(k_ij). Units are SI strings (`K`, `Pa`, `mol/s`, `J/mol`, `W`, `1`).

Edges run from inputs to operations (`role` is the symbol in the formula, e.g. `h_in`) and
from operations to their outputs. A tear stream closes a cycle; that edge is marked
`feedback: true` so consumers can lay the graph out as a DAG.

## 3. Recorder

`ngdesign.provenance.recorder` holds a `Recorder` in a `contextvars.ContextVar`. Nothing in
the engine imports a recorder object; instrumented code asks for the active one:

```python
from ngdesign.provenance import active

if (rec := active()) is not None:
    rec.equation("duty_W", duty_W, "W", "steady_flow_energy_balance",
                 inputs={"F": (inlet, "molar_flow"), "h_in": (inlet, "enthalpy"),
                         "h_out": (outlet, "enthalpy")})
```

`active()` returns `None` unless the caller opened `with recording() as rec:`. This keeps the
off path to a context-variable read, and keeps library functions pure: they never hold a
recorder, never do I/O, and a trace never changes a computed value.

### 3.1 Scopes

The solver opens one scope per unit solve (`rec.unit_scope(tag, kind, inlets, params)`), one
per feed flash and one per tear injection. A scope owns:

- **The value table.** Every value the scope knows (inlet stream properties, numeric params,
  equation results, flash outputs) is indexed by its exact float (compositions by their
  sorted items). When instrumented code passes a plain number as an input, the recorder
  finds the node it came from by value. Exact float equality is the right test: a value
  copied from an inlet is bit-identical, and a value computed by some unrecorded expression
  almost never collides with a recorded one. Code that wants to be explicit passes a
  `(StreamState, "attribute")` tuple or a `ValueRef` returned by an earlier call.
- **Flash records.** Each outermost thermo call made in the scope (flash_pt/ph/ps/tvf/pvf,
  bubble/dew point, k_values, phase_props, pure_psat) is recorded with its inputs resolved
  against the value table and its result object kept for identity lookup. Records are
  materialized into graph nodes only when something downstream uses them; a column making
  10^4 flashes keeps only the ones its outlets come from, and the unit's operation node
  reports how many thermo calls it made in total. At most `FLASH_RECORD_CAP` records are
  kept per scope (oldest dropped).
- **Unattributed values.** A flash or equation input the recorder cannot resolve becomes an
  `intermediate` node with quality `uncited` produced by an operation `unrecorded`. The
  audit then flags everything downstream. This is deliberate: unknown provenance stays
  visible instead of being guessed.

When the unit returns, the solver binds results: each outlet `StreamState` is bound to its
stream id by identity (the flash record whose result object it is), `duty_W`, `power_W` and
numeric `info` entries are bound by value. A result nothing recorded is attached to a
generic operation `unit_model:<kind>` whose inputs are the unit's inlets and params and
which carries no reference, so the audit reports the unit as uninstrumented. A value that
is exactly 1000x or 1/1000x a known value is linked by a `unit_conversion` operation
(`duty_kW` from `duty_W`).

### 3.2 Iterative solves

- **Flashes**: `thermo/_state.run_flash` reports the flash's `flash_convergence`
  (iterations, error) to the recorder; it lands on the flash's operation node.
- **Tear loops**: each pass resets the scopes of the block's units (`rec.begin_pass`), so
  only the converged pass survives. After convergence the solver records one `tear`
  operation per tear stream: input is the computed stream (a feedback edge), outputs are the
  injected state the downstream unit consumed, with acceleration method, iteration count
  and maximum relative residual.
- **Design specs**: each inner solve calls `rec.begin_solve()`; only the final one survives.
- **Unit-internal iterations** (columns, reactors with ODE/Gibbs solvers) record their
  converged outlets and the iteration count/residual from `UnitResult.info` on the unit's
  operation node.

### 3.3 Model parameters

A flash operation consumes one `parameter set` node per (package, component support): the
EOS's per-component constants and correlations. `ThermoSurfaceMixin.trace_parameters(ids)`
builds it from the flasher the flash actually used, so the traced numbers are the numbers
the EOS saw:

- Tc, Pc, omega, MW per component, cited by `ngdesign.provenance.citations`: the `chemicals`
  method that produced the value is identified by re-evaluating each available method and
  taking the first that reproduces it bit-for-bit (`HEOS` -> NIST REFPROP, `IUPAC` ->
  Ambrose-Young series, `CRC`, `PSRK`, `PD`, `YAWS`, ...). The source key maps to
  `data/chemdb/sources.yaml` where one exists, and the matching `data/chemdb/properties.csv`
  row (same CAS, property and value) supplies the row reference. Estimation methods
  (Joback, Wilson-Jasperson, Lee-Kesler for pseudos) are `estimated`.
- Ideal-gas Cp correlation per component: the `HeatCapacityGas.method` thermo selected,
  cited from `data/provenance/sources.yaml` (transcribed from the thermo/chemicals
  docstrings that ship with the installed version).
- Binary interaction parameters: the IPDB table name (`ChemSep PR`) with the per-pair page
  reference the table carries.
- The gas constant R (CODATA 2018) and the enthalpy reference state.

Packages without a flasher (K-value, special gamma-phi) report a parameter set with the
package name and quality `uncited` until they implement `trace_parameters`.

## 4. Method catalogue

`data/provenance/methods.yaml` maps a method key to `{name, latex, reference}`. Every
operation node's `method` must be a catalogue key; a test enforces that every key used by
instrumented code exists and every catalogue entry has a reference. Examples:

```yaml
steady_flow_energy_balance:
  name: Steady-flow energy balance
  latex: '\dot Q = F\,(h_\mathrm{out} - h_\mathrm{in})'
  reference: {citation: "Smith, Van Ness and Abbott, Introduction to Chemical Engineering Thermodynamics, 7th ed., 2005, ch. 2"}
peng_robinson_1976:
  name: Peng-Robinson equation of state
  latex: 'P = \frac{RT}{v-b} - \frac{a\,\alpha(T)}{v(v+b)+b(v-b)}'
  reference: {citation: "Peng, D.-Y. and Robinson, D.B., Ind. Eng. Chem. Fundam. 15(1), 1976, 59-64", doi: 10.1021/i160057a011}
```

Data source citations live where the data lives: `data/chemdb/sources.yaml` for chemdb
sources, `data/provenance/sources.yaml` for the method keys of the `chemicals`/`thermo`
packages. Nothing is cited from memory in code.

## 5. Instrumentation map

| layer | what records | how |
|---|---|---|
| data | component constants, chemdb rows | `provenance.citations` (pure lookups, cached) |
| thermo | every outermost Thermo-protocol call | `ThermoSurfaceMixin.__init_subclass__` wraps the protocol methods; `run_flash` reports convergence |
| solver | feeds, unit scopes, stream binding, tears, passes | `sequential_modular` hooks, all behind `if rec is not None` |
| units | the unit's own equations (duty, power, outlet P, splits, efficiencies) | `rec.equation(...)` beside the existing arithmetic |
| api | traced solve, graph, subgraph, audit | `GET /api/projects/{id}/trace`, `GET /api/projects/{id}/trace/audit` |

The first instrumented families: heater/cooler, flash drum/separators, mixer, splitter,
valve, pump, compressor/expander, heat exchanger, reactors, columns. Uninstrumented units
still trace (their flashes and outlets are recorded) but their op node is flagged.

## 6. API

- `GET /api/projects/{id}/trace` runs a traced solve (cached by project hash, separate from
  the plain solve cache) and returns the full `TraceGraph`.
- Query `?stream=S-002&prop=T` or `?unit=E-101&prop=duty_W` returns the upstream subgraph of
  that value only.
- `GET /api/projects/{id}/trace/audit` returns `{outputs, flagged: [{node, reasons, leaves}]}`.

## 7. Audit

`provenance.audit.audit(graph)` walks upstream from every `output` node and reports it when
it reaches a leaf with quality `uncited` (error) or `estimated` (warning), or an operation
without a reference (error). The report lists the offending leaves/operations so the fix is
obvious: cite the data, or instrument the unit.

## 8. UI

The Trace tab (`frontend/src/views/TraceView.tsx`; layout and depth logic in
`frontend/src/trace.ts`):

- Pick a project (any stored project, e.g. the seeded demo), then a stream property or unit
  result - or click a number in the Results view. The upstream graph is drawn left to right,
  columns anchored at the focused value (feedback edges ignored): circles for values coloured
  by quality (uncited ones ringed in red), rounded boxes for operations (dashed when
  unreferenced), edges labelled with the symbol the input plays in the equation.
- Depth: 2/4/8 operations upstream or all the way to the cited base data; nodes with hidden
  inputs carry a `+` and can be expanded one at a time.
- Click a value: value in user and SI units, kind, quality, full citation (source, DOI link,
  URL, table, row reference, grade), what produced it and what uses it. Click an operation:
  the equation in KaTeX, its inputs and outputs (clickable), iterations/residual, references.
- The audit panel counts outputs/clean/errors/warnings and lists findings; clicking one
  focuses that output with its culprits highlighted.
- Export the drawn graph as SVG, the focused trace as JSON.

Review project: `uv run python scripts/seed_trace_demo.py <database-url>` seeds
"Trace demo: gas processing" (`ngdesign.flowsheets.trace_demo`), refusing to seed if its traced
solve has any audit error.

## 9. Instrumenting a unit

1. `rec = active()` once in `solve`; everything below sits in `if rec is not None:`.
2. Record each intermediate **before** the thermo call that consumes it (inputs are matched
   in event order), with the value the code already computed:
   `rec.equation("P_out", P_out, "Pa", "pressure_drop", {"P_in": (inlet, "P"), "dP": dP})`.
3. Inputs: `(state, "attr")` (`"enthalpy"`, `"composition"`, `"vapor.density"`), a `ValueRef`
   returned by an earlier call, or the plain number/dict the code holds (matched by object
   identity first - the earliest holder of an object is its origin - then by exact value).
4. Outlets that are not flash results: `rec.derived_state(outlet, "phase_split", {...})`.
5. Name equations after the result they explain (`duty_W`, `power_W`, `info` keys); they bind
   by name. Zero duty/power of units without that effect bind automatically.
6. Defaults the code applies: `rec.default("eta", eta, "1", "why")`; hard-coded constants:
   `rec.constant("g_n", G_STD, "m/s2", "bipm_si")` (a key of `data/provenance/sources.yaml`).
7. Add the method key to `data/provenance/methods.yaml` with LaTeX and a reference you can
   verify; `tests/provenance/test_trace.py` fails on an unknown key.

## 10. Status

Instrumented (results come from recorded, referenced equations):

- thermo protocol calls of every package; cubic packages also report cited Tc/Pc/omega/MW/
  Cp_ig/k_ij/R/reference state; other packages add an explicit *not traced* parameter leaf the
  audit flags;
- feeds, tears (converged iterate with iterations and residual), design specs;
- heater/cooler/air cooler/shell & tube (outlet-spec models), separators/scrubber, flash drum,
  mixer, splitter, pump, compressor, expander, JT valve, TEG contactor;
- reactors: conversion, yield, equilibrium, Gibbs, CSTR (R1/R2), PFR (R1-R3); formation
  properties cite the selected chemdb row, H(T)/S(T) shapes their JANAF/Shomate/NASA source;
- columns: rigorous column (R2), absorber R0/R2, reboiled stripper R0/R2, refluxed absorber R2,
  column extensions R2, reactive stages R2, shortcut distillation R0 (one operation each, with
  iterations; per-stage internals are not recorded);
- exchangers: shell_tube R0, air_cooler R0, plate exchanger R0/R1, double pipe R0/R1,
  multi-stream R0.

Still flagged (results from a `unit_model:<kind>` operation): exchangers shell_tube R1/R2,
air_cooler R1, multi_stream R1/R2; columns absorber R3, reboiled stripper R3,
three_phase_stages, divided_wall, liquid_liquid_extractor; reactors batch, fixed bed,
electrolyser, multiphase Gibbs; flow units other than pump/compressor/expander/JT valve; amine,
refining and logical units. Data that is estimated rather than cited (e.g. TEG and MDEA ideal-gas
Cp from Joback in the `thermo` databank) is reported as a warning.

Model citations: cubic EOS packages use the vetted entries in `methods.yaml`; every other package
cites the `references` of its row in `data/thermo_models/*.yaml`.

## 11. Overhead and guarantees

- Off: one `ContextVar.get` per thermo protocol call and per instrumented unit; no
  allocations. Benchmarked against `bench/` before merge.
- On: a few hundred bytes per recorded flash, capped per scope; values copied, never
  mutated; tests assert bit-identical `SolvedFlowsheet` JSON with and without tracing.
