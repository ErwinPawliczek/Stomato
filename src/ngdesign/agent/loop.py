"""The agent conversation loop (spec B-08).

One call to :func:`run_conversation` is one user message: append it, then
alternate model turns and tool rounds until the model answers without tool use
(or a stop condition fires). Events stream out through the ``emit`` callback —
``text_delta`` while the model streams, ``tool_call``/``tool_result`` per tool
round, ``project_changed`` after a successful mutating tool — so the API layer
can forward them as SSE frames unchanged. The loop owns no state: the caller
keeps the message history (the session) and the project lives behind the
injected store.

Tool failures are results, not exceptions: the model sees the error text and
fixes its own mistake. The loop raises nothing for model stop conditions or
capped rounds — it reports them through the returned :class:`DoneInfo` and an
``error`` event; only caller-level failures (model setup, a buggy client)
raise, and the route turns those into the SSE error event.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ngdesign.agent.engine import Engine
from ngdesign.agent.model import ModelClient
from ngdesign.agent.tools import TOOLS_BY_NAME, ProjectStore, ToolOutcome, run_tool, tool_definitions

#: Hard cap on model/tool alternations per user message (spec B-08): a runaway
#: loop ends with an SSE error event, never an infinite stream.
MAX_TOOL_ROUNDS = 25

#: SSE-ready event dicts flow to the API layer through this callback.
Emit = Callable[[dict[str, Any]], None]

SYSTEM_PROMPT = """\
You are the ngdesign engineering agent: you build, inspect and study gas-processing \
flowsheets in SI units through the typed tools — the same operations the web app's \
routes perform, nothing more.

Working rules:
- Build flowsheets by adding units (list_unit_kinds shows every registered kind with \
its port names and params), then connect them with feed and product streams. Component \
ids come from list_components; mole fractions sum to 1. Set each stream's service code \
(PG process gas, PL process liquid, W water, GL glycol) — line sizing and the P&ID need it.
- Call solve after every topology or parameter change before reading results or \
rendering: read_variable reads solved values by address — '<stream>.T', '<stream>.P', \
'<stream>.molar_flow', '<stream>.mass_flow', '<stream>.vapor_fraction', \
'<stream>.x.<component_id>', '<unit>.duty_W', '<unit>.power_W', '<unit>.info.<key>'.
- case_study sweeps a writable address ('<unit>.params.<key>' or \
'<feed>.feed.<T|P|molar_flow>') over values and reports each requested output; the \
stored project is left unchanged.
- Tool errors tell you what went wrong and what the nearest valid input is — read \
them, fix the call, retry. Do not invent units, components, ports or params. \
Call recommend_thermo before changing the property package (set_thermo): it ranks \
the registered methods for the current slate and feed conditions with reasons and warnings.
- render returns the URL of the requested drawing plus P&ID counts; the UI fetches it.
- Report engineering results with units (K, Pa, mol/s, W). Be concise; let the tool \
rows carry the detail.
"""


@dataclass(frozen=True)
class DoneInfo:
    """How one conversation turn ended (the SSE ``done`` event's payload)."""

    stop_reason: str
    usage: dict[str, int]


def _tool_input(raw: Any) -> dict[str, Any]:
    """Tool inputs arrive from the model as JSON strings or dicts — normalize to dict."""
    if isinstance(raw, str):
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("tool input must be a JSON object")
        return parsed
    if isinstance(raw, dict):
        return dict(raw)
    raise ValueError("tool input must be a JSON object")


def _summarize(outcome: ToolOutcome) -> str:
    """One-line summary for the frontend's tool row (full JSON stays available)."""
    if not outcome.ok:
        return f"failed: {(outcome.error or 'unknown error')[:120]}"
    body = json.dumps(outcome.result or {})
    return body[:120] if body else "ok"


def run_conversation(
    model: ModelClient,
    store: ProjectStore,
    engine: Engine,
    user_text: str,
    messages: list[dict[str, Any]],
    emit: Emit,
) -> DoneInfo:
    """One user message through model/tool rounds until the model stops asking.

    ``messages`` is the session history in Anthropic API shape, mutated in place
    (the caller owns the session). ``emit`` receives SSE-ready event dicts;
    text deltas stream exactly when the model streams them. Returns the done
    info; the caller appends ``conversation_id`` to the final event.
    """
    tools = tool_definitions()
    messages.append({"role": "user", "content": user_text})
    usage = {"input_tokens": 0, "output_tokens": 0}
    for _ in range(MAX_TOOL_ROUNDS):
        streamed_text = False

        def on_text(delta: str) -> None:
            nonlocal streamed_text
            streamed_text = True
            emit({"type": "text_delta", "text": delta})

        response = model.stream(SYSTEM_PROMPT, messages, tools, on_text)
        usage["input_tokens"] += response.input_tokens
        usage["output_tokens"] += response.output_tokens
        if response.text and not streamed_text:
            # The client delivered no deltas (scripted model or silent stream):
            # emit the finished text once so the UI still shows it.
            emit({"type": "text_delta", "text": response.text})

        stop = response.stop_reason
        if stop == "max_tokens":
            emit(
                {"type": "error", "message": "the model hit its output limit mid-answer; try a smaller step"}
            )
            return DoneInfo(stop_reason="max_tokens", usage=usage)
        if stop == "refusal":
            emit({"type": "error", "message": "the model declined this request"})
            return DoneInfo(stop_reason="refusal", usage=usage)

        if not response.tool_uses:
            # The final answer still belongs to the session history: the next
            # turn's context must contain this assistant message.
            if response.text:
                messages.append({"role": "assistant", "content": [{"type": "text", "text": response.text}]})
            return DoneInfo(stop_reason=stop or "end_turn", usage=usage)

        content: list[dict[str, Any]] = []
        if response.text:
            content.append({"type": "text", "text": response.text})
        parsed: list[tuple[Any, dict[str, Any]]] = []
        for use in response.tool_uses:
            tool_input = _tool_input(use.input)
            parsed.append((use, tool_input))
            content.append({"type": "tool_use", "id": use.id, "name": use.name, "input": tool_input})
            emit({"type": "tool_call", "id": use.id, "name": use.name, "input": tool_input})
        messages.append({"role": "assistant", "content": content})

        result_blocks: list[dict[str, Any]] = []
        changed = False
        for use, tool_input in parsed:
            outcome = run_tool(use.name, tool_input, store, engine)
            if outcome.ok and use.name in TOOLS_BY_NAME and TOOLS_BY_NAME[use.name].mutates:
                changed = True
            event: dict[str, Any] = {
                "type": "tool_result",
                "id": use.id,
                "ok": outcome.ok,
                "summary": _summarize(outcome),
            }
            if outcome.ok:
                event["result"] = outcome.result
                result_content: str | dict[str, Any] = outcome.result or {}
            else:
                result_content = {"error": outcome.error or "unknown error"}
            result_blocks.append(
                {"type": "tool_result", "tool_use_id": use.id, "content": json.dumps(result_content)}
            )
            emit(event)

        messages.append({"role": "user", "content": result_blocks})
        if changed:
            emit({"type": "project_changed"})

    emit(
        {
            "type": "error",
            "message": f"the agent exceeded {MAX_TOOL_ROUNDS} tool rounds; ask again to continue",
        }
    )
    return DoneInfo(stop_reason="max_tool_rounds", usage=usage)


__all__ = ["MAX_TOOL_ROUNDS", "DoneInfo", "Emit", "SYSTEM_PROMPT", "run_conversation"]
