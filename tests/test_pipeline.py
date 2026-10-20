"""P0-03 acceptance: ``pipeline.deliverables()`` on the solved slice equals,
stage by stage, what the CLI wrote — the byte-identical anchor for lifting the
deliverables chain out of ``ngdesign.cli``.
"""

from __future__ import annotations

from pathlib import Path

from ngdesign import cli, pipeline, registry


def test_deliverables_matches_cli_stage_by_stage(tmp_path: Path) -> None:
    """Run the CLI once, then recompute the chain through the pipeline and
    compare every stage: datasheets, P&ID, routing — bytes, not shapes."""
    assert cli.main(["slice", "--out", str(tmp_path)]) == 0

    solved = pipeline.run_sizers(cli._solve_slice())
    d = pipeline.deliverables(solved, {}, k_gas=pipeline.DEFAULT_K_GAS)

    # Stage: sizers — the datasheets the CLI attached before building.
    assert set(d.solved.datasheets) == set(solved.datasheets)
    assert d.solved.datasheets == solved.datasheets

    # Stage: P&ID — build_pid equals the explicit builder + rules + fixed point.
    rules = pipeline.rule_set(solved, k_gas=pipeline.DEFAULT_K_GAS)
    explicit = pipeline.apply_rules(registry.create("pid_builder", "default").build(solved), rules)
    assert d.pid == explicit

    # Stage: rendering — the CLI's pid.svg/pfd.svg are these models, byte for byte.
    assert registry.create("diagram", "pfd").render(d.solved) == (tmp_path / "pfd.svg").read_text(
        encoding="utf-8"
    )
    assert registry.create("diagram", "pid").render(d.pid) == (tmp_path / "pid.svg").read_text(
        encoding="utf-8"
    )

    # Stage: routing — one isometric per routed line, byte-identical to the CLI's.
    assert d.network == pipeline.route(explicit, {})
    assert len(d.network.lines) >= 5
    iso = registry.create("iso_renderer", "svg")
    for i, line in enumerate(d.network.lines, start=1):
        stem = cli._iso_stem(i, line.line_number)
        assert iso.render(line, d.pid).svg == (tmp_path / f"{stem}.svg").read_text(encoding="utf-8")
