# Benchmark appendix — Python reference engine

Feeds OQ-1 (stomato-core parity/speed): a reproducible timing and profile
baseline for the Python reference engine over the golden thermo surfaces and
the sequential modular slice solve.

**Load-bearing assumption.** This appendix assumes Python-reference timings
are the right baseline for judging stomato-core kernel speedups. That holds
only if the Python hot spots below (flash iteration, PR package construction)
are the same work stomato-core will take over — confirm the kernel boundary
against `art_BK3G24zf` before quoting speedup targets. Numbers below are
machine-specific; compare case-to-case ratios, not absolute times, and
re-run on target hardware before publishing claims.

## How to run

```bash
uv run python scripts/bench_harness.py --mode pyperf   # statistical timing (.json + table)
uv run python scripts/bench_harness.py --mode cprofile # deterministic .prof per case
uv run python scripts/bench_harness.py --mode pyspy    # sampled flamegraphs (.svg)
uv run python scripts/bench_harness.py --mode all      # everything, one artifact dir
uv run python scripts/bench_harness.py --mode pyperf --case thermo.flash_pt_pure_c1
```

Artifacts land in `out/bench/` (override with `--out`): one
`<case>.json` (pyperf, re-comparable with `pyperf compare_to`), one
`<case>.prof` (cProfile), one `<case>.flame.svg` (py-spy) per case.

pyperf and py-spy are fetched ephemerally through
`uv run --with pyperf|py-spy` at invocation time; `pyproject.toml` is not
touched and no dependency is added. py-spy needs `ptrace` permissions —
run inside the same container/user that owns the benchmarked process.

## What is timed

| Case | Surface | Exercises |
|---|---|---|
| `thermo.flash_pt_pure_c1` | golden PT flash, pure methane | single-phase branch, PR root solve |
| `thermo.flash_pt_pure_co2` | golden PT flash, pure CO2 | near-critical root stability |
| `thermo.flash_pt_gas_mix` | golden PT flash, gas mix | full composition path |
| `thermo.flash_ph_roundtrip_gas` | golden PH round-trip | nested flash iteration |
| `thermo.flash_ps_roundtrip_gas` | golden PS round-trip | nested flash iteration |
| `thermo.flash_two_phase_c1_c3_nc5` | golden two-phase VLE | Rachford–Rice, lnphi evaluation |
| `thermo.flash_free_water_c1_h2o` | golden free-water flash | three-phase split |
| `thermo.flash_slice_inlet_three_phase` | slice inlet stream | three-phase inlet conditioning |
| `solver.slice_sequential_modular` | locked sample slice | end-to-end sequential modular solve |

Cases mirror `data/golden/*.yaml` oracle surfaces — the harness benchmarks
exactly the code the oracle tests validate, so a parity regression in stomato-core
shows up as both a golden-test failure and a timing change in the same case.

## Methodology

- **pyperf**: 3 worker processes × 20 values per case (60 values total),
  calibrated loops (min-time 0.1 s), warmups excluded. Worker processes
  re-execute the harness script; results return through pyperf's pipe.
- **cProfile**: one warmup run (discarded — lazy imports otherwise dominate),
  then one profiled run dumped to `.prof`.
- **py-spy**: nonblocking sampling attach at 100 Hz over one warm run;
  flamegraph written as SVG.

## Baseline (2026-10-14, CPython 3.13, Linux container, shared sandbox)

Mean ± std dev from pyperf, 60 values per case:

| Case | Mean ± std dev |
|---|---|
| `thermo.flash_pt_pure_c1` | 404.7 µs ± 55.0 µs |
| `thermo.flash_pt_pure_co2` | 439.5 µs ± 59.2 µs |
| `thermo.flash_two_phase_c1_c3_nc5` | 3.695 ms ± 502 µs |
| `thermo.flash_free_water_c1_h2o` | 865.4 µs ± 120.1 µs |
| `thermo.flash_pt_gas_mix` | 10.37 ms ± 1.24 ms |
| `thermo.flash_slice_inlet_three_phase` | 8.933 ms ± 1.15 ms |
| `thermo.flash_ph_roundtrip_gas` | 57.71 ms ± 7.03 ms |
| `thermo.flash_ps_roundtrip_gas` | 60.20 ms ± 8.28 ms |
| `solver.slice_sequential_modular` | 758.8 ms ± 65.8 ms |

pyperf flagged the slice-solve case as possibly unstable (sub-1% variation
unlikely at this sample count on shared infrastructure) — treat the slice
number as order-of-magnitude and re-run on dedicated hardware for OQ-1 claims.

## Where the time goes (slice solve, cProfile hot spots)

The 759 ms slice solve is dominated by thermo work inside unit-op `solve`
calls: the compressor solve (`src/ngdesign/units/compressor.py:58`, 0.70 s
cumulative on a single call) drives a `thermo` PH-flash
(`solve_PT_HSGUA_NP_guess_bisect` → secant iteration), and Peng–Robinson
`lnphis_at_zs` evaluation (9,115 calls, ~0.68 s cumulative). These are the
natural stomato-core kernel targets: PR evaluation, cubic-root solving,
multiphase flash, and the nested PH/PS iteration.

## Caveats

- Shared sandbox: numbers include neighbor noise; the ± values above are the
  honest variance, not a tuning target.
- py-spy flamegraphs sample a single run — use them to find *where* time goes,
  never to quantify change; use pyperf JSONs for that.
- Re-baseline after any engine change that alters case semantics; the golden
  suite remains the behavioral gate.
