<p align="center"><img src="docs/assets/stomato-mark.png" alt="Stomato brand mark" width="240"></p>

# Stomato

Stomato is a process simulation and engineering-design engine for natural gas processing, inspired by the stomatopod — small, precise, and it hits hard. Describe a flowsheet once and Stomato solves it with a Peng–Robinson thermodynamic model, sizes every piece of equipment, and generates the deliverables an engineering team actually produces: the PFD, the P&ID, routed 3D piping and one isometric drawing per line. One validated model, no re-keying between tools.

The engine is plugin-first. Thermodynamic packages, unit operations, sizers, P&ID rules, routing, renderers and engineering correlations are all self-registering plugins — the core never lists them, so new capability is a new module, not a core edit.

## Quickstart

```bash
uv sync --all-groups          # install
uv run pytest -rs             # run the test suite
```

Run the end-to-end demo on the built-in sample flowsheet:

```bash
python -m ngdesign.cli slice
```

## The demo: one flowsheet, every deliverable

`python -m ngdesign.cli slice` runs the full chain on the locked sample slice — a 50 MMSCFD rich wet sweet gas train at 500 psia: a 3-phase inlet separator (V-101), a gas compressor (K-101), an air cooler (E-101) and a TEG dehydration contactor (T-101), plus a pumped-and-heated condensate leg (P-101, E-102). With `--out DIR` (default `out/`) it writes every artefact to that directory:

| File | What it is |
|---|---|
| `pfd.svg` | Process flow diagram of the solved flowsheet, with the stream table |
| `pid.svg` | P&ID: equipment, instruments and every piping line after rule review |
| `iso_*.svg` | One isometric drawing per routed line (13 for the sample slice) |
| `index.html` | Landing page linking every drawing, plus the full stream table (T, P, flow, mass flow, vapour fraction) and any remaining rule violations |

On the console you see each stage land — this is the actual output of a run:

```
solver: converged in 1 pass(es)
sizers: 5 datasheet(s): E-101, E-102, K-101, T-101, V-101
p&id: 13 line(s) over 6 equipment, 0 violation(s) remaining
```

What happens under the hood, in order: PR thermo → sequential-modular solve of the flowsheet → registered sizers attach datasheets per unit → the P&ID builder lays out equipment, instruments and lines → every registered P&ID rule runs repeatedly to a fixed point (rules create work for each other — a new PSV line needs isolation valves, for example) → the orthogonal router routes every line → the isometric renderer draws one sheet per routed line → `index.html` ties it all together. The golden test that guards this exact chain is `tests/e2e/test_slice.py`.

## Architecture: the plugin kinds

Everything the engine does is a plugin registered under one of ten kinds. A plugin is any module under a plugin package whose class carries the decorator — discovery is automatic, nothing is ever listed by hand:

```python
from ngdesign.registry import register


@register("unit", "compressor")
class Compressor: ...
```

| Kind | Role | Registered today |
|---|---|---|
| `thermo` | Thermodynamic model behind every flash and property call | `pr` (Peng–Robinson) |
| `unit` | Unit-operation physics (duty, pressure, split) | `separator_3phase`, `compressor`, `air_cooler`, `shell_tube`, `teg_contactor`, `pump`, `heater`, `cooler`, `jt_valve`, `mixer`, `splitter`, `scrubber` |
| `sizer` | Equipment sizing datasheets from solved results | `separator_3phase`, `compressor`, `air_cooler`, `shell_tube`, `teg_contactor`, `pump`, `scrubber` |
| `solver` | Flowsheet solution strategy | `sequential_modular` |
| `pid_builder` | Turns the solved flowsheet into a P&ID | `default` |
| `pid_rule` | Engineering review rules applied to the P&ID to a fixed point | `vessel_psv`, `psv_sizing`, `vessel_instruments`, `pump_instruments`, `nozzle_isolation`, `discharge_check_valve`, `drains_vents` |
| `router` | Routes P&ID lines into 3D-ish geometry for isometrics | `orthogonal` |
| `iso_renderer` | Renders one routed line as a drawing | `svg` |
| `diagram` | Whole-drawing renderers | `pfd`, `pid` |
| `correlation` | Engineering calculations: line sizing, wall thickness, flange ratings, PSV relief, LMTD, erosional velocity, Kremser absorption, and more | `line_size`, `wall_thickness_b313`, `flange_rating_b165`, `psv_api520_gas`, `lmtd_counter`, `erosional_api14e`, `darcy_colebrook`, `cv_liquid`, `pump_power`, `souders_brown`, `kremser` |

Plugin packages live under `src/ngdesign/`: `thermo`, `units`, `sizing`, `solver`, `pid_rules`, `piping` and `render`. Drop a decorated class in any of them and the registry finds it — no imports to add, no list to edit.

Around the engine: the data model (flowsheets, solved results, P&IDs) lives in `src/ngdesign/contracts/`, reference data (ASME B36.10, B16.5, pipe classes, component constants) in `data/`, and a FastAPI wrapper of the engine in `src/ngdesign/api/`.

- Architecture and rules for contributors (human or agent): `AGENTS.md`
- Contracts between layers: `src/ngdesign/contracts/`
- Work queue: `specs/backend/`
- Reference data (ASME B36.10, B16.5, pipe classes, component constants): `data/`
- Demo target: `tests/e2e/test_slice.py`
