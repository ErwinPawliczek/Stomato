"""Seed the 'Trace demo: gas processing' review project into a Stomato database.

    uv run python scripts/seed_trace_demo.py sqlite:///./stomato.db
    uv run python scripts/seed_trace_demo.py postgresql+psycopg://... --owner alice --replace

The flowsheet (``ngdesign.flowsheets.trace_demo``) is solved once with calculation
provenance recorded before it is stored: the script refuses to seed a project whose
solve fails or whose trace audit reports an error, and prints the audit summary. The
API traces the stored project on demand (GET /api/projects/{id}/trace); open the
Trace tab in the UI and pick the project in its project selector.

``--trace-out FILE`` also writes the full trace graph as JSON.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("database_url", help="SQLAlchemy URL of the database, e.g. sqlite:///./stomato.db")
    parser.add_argument("--owner", default="local", help="project owner (open-mode API owner is 'local')")
    parser.add_argument("--replace", action="store_true", help="replace an existing project of the same name")
    parser.add_argument("--trace-out", type=Path, help="also write the trace graph JSON here")
    args = parser.parse_args(argv)

    # The store reads its URL from the environment when the engine is first built.
    os.environ["STOMATO_DATABASE_URL"] = args.database_url

    from ngdesign.agent import engine
    from ngdesign.contracts import Project
    from ngdesign.flowsheets import trace_demo
    from ngdesign.provenance.audit import audit
    from ngdesign.store import ProjectExists, create_project, find_project, init_db, reset_engine
    from ngdesign.store.projects import DbProjectStore

    reset_engine()
    init_db()

    project = Project(name=trace_demo.NAME, flowsheet=trace_demo.build())
    solved, graph = engine.trace_project(project, cache={})
    if not solved.converged or solved.errors:
        print(f"refusing to seed: the solve did not converge cleanly: {solved.errors}", file=sys.stderr)
        return 1
    report = audit(graph)
    errors = [f for f in report.findings if f.severity == "error"]
    print(
        f"traced: {len(graph.values)} values, {len(graph.ops)} operations; "
        f"audit: {report.outputs} outputs, {report.clean} clean, "
        f"{len(errors)} errors, {len(report.findings) - len(errors)} warnings"
    )
    if errors:
        for f in errors[:10]:
            print(f"  {f.label}: {'; '.join(f.reasons)}", file=sys.stderr)
        print("refusing to seed a project whose trace has uncited outputs", file=sys.stderr)
        return 1
    if args.trace_out is not None:
        args.trace_out.write_text(graph.model_dump_json(indent=1), encoding="utf8")

    existing = find_project(name=trace_demo.NAME, owner=args.owner)
    if existing is not None:
        if not args.replace:
            print(f"project {trace_demo.NAME!r} already exists (id {existing.id}); use --replace")
            return 0
        DbProjectStore(existing.id).put(project)
        print(f"replaced {trace_demo.NAME!r} (id {existing.id})")
        return 0
    try:
        row = create_project(name=trace_demo.NAME, owner=args.owner, project=project)
    except ProjectExists:  # a concurrent seed won the race
        print(f"project {trace_demo.NAME!r} already exists")
        return 0
    print(f"seeded {trace_demo.NAME!r} (id {row.id}, owner {args.owner})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
