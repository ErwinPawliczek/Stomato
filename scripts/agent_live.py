"""Run the B-08 showcase sentence against a live server with the real model.

    ANTHROPIC_API_KEY=... uvicorn ngdesign.api.app:app --port 8000
    uv run python scripts/agent_live.py --base-url http://localhost:8000

Sends the showcase sentence to ``POST /api/agent`` and prints the SSE event
stream as it arrives: the model's narration, every tool call and result, the
project-change notifications, and the final ``done`` summary. This is a manual
showcase, not a test — it is skipped unless ``ANTHROPIC_API_KEY`` is set, and
it never mocks the model. The scripted counterpart of this sentence lives in
``tests/agent/test_loop.py`` (``_showcase_script``).
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import httpx

#: The sentence the hackathon showcase performs (spec B-08 test 5): TEG
#: dehydration feeding an MDEA absorber and a compressor on the sour gas, with
#: amine Kent–Eisenberg chemistry, a converged solve and both drawings.
SHOWCASE_SENTENCE = (
    "Showcase: build a natural-gas dehydration and sweetening train. Feed the "
    "water-saturated sour gas into a TEG contactor, route the dried gas into an "
    "MDEA amine absorber, and compress the sales gas with a compressor. Pick "
    "suitable stream services, use the amine Kent-Eisenberg thermo package, "
    "solve the flowsheet, read the compressor power, and render the PFD and the "
    "P&ID."
)


def _parse_sse_frames(lines: list[str]) -> list[str]:
    """Group SSE lines into ``data:`` payloads (frames end at a blank line)."""
    payloads: list[str] = []
    current: list[str] = []
    for line in lines:
        if line.strip() == "":
            if current:
                payloads.append("\n".join(current))
                current = []
            continue
        if line.startswith("data: "):
            current.append(line[len("data: ") :])
    if current:
        payloads.append("\n".join(current))
    return payloads


def run(base_url: str, sentence: str, timeout: float) -> int:
    """Stream one agent turn; 0 on a clean end_turn, 1 on any failure."""
    with httpx.Client(timeout=timeout) as client:
        with client.stream(
            "POST",
            f"{base_url}/api/agent",
            json={"message": sentence},
        ) as response:
            if response.status_code != 200:
                print(f"HTTP {response.status_code} from {base_url}/api/agent", file=sys.stderr)
                return 1
            lines: list[str] = []
            for chunk in response.iter_lines():
                lines.append(chunk)

    conversation_id = None
    stop_reason = None
    for payload in _parse_sse_frames(lines):
        event = json.loads(payload)
        kind = event.get("type")
        if kind == "text_delta":
            print(event["text"], end="", flush=True)
        elif kind == "tool_call":
            print(
                f"\n→ tool {event['name']}  {json.dumps(event['input'], sort_keys=True)}",
                flush=True,
            )
        elif kind == "tool_result":
            mark = "✓" if event["ok"] else "✗"
            print(f"\n{mark} {event['summary']}", flush=True)
        elif kind == "project_changed":
            print("\n● project changed", flush=True)
        elif kind == "error":
            print(f"\nERROR: {event['message']}", file=sys.stderr, flush=True)
            return 1
        elif kind == "done":
            conversation_id = event["conversation_id"]
            stop_reason = event["stop_reason"]
            usage = event["usage"]
            print(
                f"\n\ndone: stop_reason={stop_reason} usage={usage} conversation={conversation_id}",
                flush=True,
            )
    return 0 if stop_reason == "end_turn" else 1


def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set — skipping the live agent showcase.")
        return 0

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://localhost:8000", help="running ngdesign API")
    parser.add_argument("--sentence", default=SHOWCASE_SENTENCE, help="user message to send")
    parser.add_argument("--timeout", type=float, default=600.0, help="seconds before giving up")
    args = parser.parse_args()

    return run(args.base_url, args.sentence, args.timeout)


if __name__ == "__main__":
    raise SystemExit(main())
