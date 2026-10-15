"""CLI for the B-08 scripted agent session: drive a live server end to end.

    uv run python -m scripts.agent_session --base-url http://localhost:8000 --out out/session/
    # add --check-determinism to run the recipe twice and byte-compare the outputs

Writes every artifact the session produces — the final project.json, the routed
network JSON (route.json), a step log (session.json) and all three view SVGs —
then exits 0. Any failed call or assertion aborts non-zero, naming the step.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from ngdesign.agent.session import (
    HttpResult,
    SessionReport,
    StepError,
    Transport,
    determinism_problems,
    run_session,
)


class UrllibTransport:
    """stdlib-urllib transport: the CLI adds no third-party dependency."""

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")

    def request(self, method: str, path: str, json_body: Any | None = None) -> HttpResult:
        data = None if json_body is None else json.dumps(json_body).encode("utf-8")
        request = urllib.request.Request(self._base_url + path, data=data, method=method)
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request) as response:
                return HttpResult(response.status, response.headers.get_content_type(), response.read())
        except urllib.error.HTTPError as exc:  # 4xx/5xx: return the body; the runner aborts on it
            with exc:
                headers = exc.headers
                content_type = headers.get_content_type() if headers is not None else ""
                return HttpResult(exc.code, content_type, exc.read())


def write_artifacts(report: SessionReport, out_dir: Path) -> list[Path]:
    """Write project.json, route.json, session.json and the three SVGs; no timestamps."""
    out_dir.mkdir(parents=True, exist_ok=True)
    payloads: dict[str, Any] = {
        "project.json": report.project,
        "route.json": report.routed,
        "session.json": {"steps": list(report.steps)},
    }
    written = []
    for name, payload in sorted(payloads.items()):
        path = out_dir / name
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written.append(path)
    for name, svg in sorted(report.svgs.items()):
        path = out_dir / name
        path.write_bytes(svg)
        written.append(path)
    return written


def main(argv: list[str] | None = None, transport: Transport | None = None) -> int:
    """Run the session against --base-url; exit 0 clean, 1 on the first failure."""
    parser = argparse.ArgumentParser(description="Run the B-08 scripted agent session over HTTP.")
    parser.add_argument("--base-url", default="http://localhost:8000", help="ngdesign server base URL")
    parser.add_argument("--out", default="out/session/", help="directory for the session artifacts")
    parser.add_argument(
        "--check-determinism",
        action="store_true",
        help="run the recipe twice and byte-compare the SVGs and the route result",
    )
    args = parser.parse_args(argv)

    client = transport if transport is not None else UrllibTransport(args.base_url)
    try:
        report = run_session(client)
        written = write_artifacts(report, Path(args.out))
        problems = determinism_problems(report, run_session(client)) if args.check_determinism else []
    except StepError as exc:
        print(f"session aborted: {exc}", file=sys.stderr)
        return 1
    for path in written:
        print(f"wrote {path}")
    for problem in problems:
        print(f"non-deterministic: {problem}", file=sys.stderr)
    if problems:
        return 1
    print(f"session ok: {len(report.steps)} steps (create -> edit -> solve -> place -> route -> export)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
