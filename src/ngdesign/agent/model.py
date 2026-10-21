"""Model client seam (spec B-08).

``ModelClient`` is the one seam between the conversation loop and the LLM: the
loop drives the protocol, never the SDK. :class:`AnthropicModel` is the real
client (official anthropic SDK, streaming); :class:`ScriptedModel` replays
preloaded responses — every test runs on it, none touch the network. The real
client is itself covered by a stub that yields SDK-shaped stream events
(tests/agent/test_model.py).

The SDK shapes the conversation here and nowhere else: strict tool definitions
from ``ngdesign.agent.tools`` go in, a :class:`ModelResponse` (text, tool-use
requests, stop reason, usage) comes out.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol, cast

#: The default agent model (orchestrator-locked: claude-opus-5-5).
DEFAULT_MODEL = "claude-opus-5-5"

#: Reasoning effort sent as ``output_config={"effort": ...}`` (no thinking
#: parameter, no budget tokens — the locked call shape).
DEFAULT_EFFORT = "medium"

#: Response cap for the agent's messages call (SI-scale tool sessions are small).
MAX_TOKENS = 16000

#: Text deltas flow from the model to the loop through this callback.
TextSink = Callable[[str], None]


class ModelSetupError(Exception):
    """The agent cannot run: no ANTHROPIC_API_KEY in the environment.

    Raised eagerly at client construction — the API maps it to a clear SSE error
    instead of a traceback mid-conversation (the SDK itself does not raise when
    the variable is absent).
    """


@dataclass(frozen=True)
class ToolUseRequest:
    """One tool-use block the model asked for."""

    id: str
    name: str
    input: dict[str, Any]


@dataclass(frozen=True)
class ModelResponse:
    """One completed assistant turn, parsed from the stream's final message."""

    text: str
    tool_uses: tuple[ToolUseRequest, ...]
    stop_reason: str | None
    input_tokens: int
    output_tokens: int
    raw: Any = None  # the SDK final message; tests assert on it


class ModelClient(Protocol):
    """The loop's view of the LLM: one streaming call per assistant turn."""

    def stream(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        on_text: TextSink,
    ) -> ModelResponse: ...


def _stop_reason(message: Any) -> str | None:
    reason = getattr(message, "stop_reason", None)
    return None if reason is None else str(reason)


def _usage_tokens(message: Any) -> tuple[int, int]:
    usage = getattr(message, "usage", None)
    if usage is None:
        return 0, 0
    return int(getattr(usage, "input_tokens", 0)), int(getattr(usage, "output_tokens", 0))


def _from_message(message: Any) -> ModelResponse:
    """Parse an SDK final Message into a ModelResponse (attribute access works
    for both real SDK models and test stubs shaped like them)."""
    text_parts: list[str] = []
    tool_uses: list[ToolUseRequest] = []
    for block in getattr(message, "content", None) or []:
        block_type = getattr(block, "type", None)
        if block_type == "text":
            text_parts.append(getattr(block, "text", ""))
        elif block_type == "tool_use":
            tool_uses.append(
                ToolUseRequest(
                    id=str(getattr(block, "id", "")),
                    name=str(getattr(block, "name", "")),
                    input=dict(getattr(block, "input", None) or {}),
                )
            )
    input_tokens, output_tokens = _usage_tokens(message)
    return ModelResponse(
        text="".join(text_parts),
        tool_uses=tuple(tool_uses),
        stop_reason=_stop_reason(message),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        raw=message,
    )


class AnthropicModel:
    """The real client: anthropic SDK streaming with the locked call shape.

    ``messages.stream(...)`` + ``get_final_message()``; ``output_config`` for
    effort; no thinking parameter, no budget tokens, no forced tool_choice, no
    assistant prefill. Tools arrive strict from :func:`ngdesign.agent.tools.tool_definitions`.
    """

    def __init__(
        self,
        model: str | None = None,
        effort: str | None = None,
        client: Any | None = None,
    ) -> None:
        # Spec B-08: model and effort come from the environment when not given
        # (STOMATO_AGENT_MODEL / STOMATO_AGENT_EFFORT), defaulting to the locked values.
        model = model or os.environ.get("STOMATO_AGENT_MODEL") or DEFAULT_MODEL
        effort = effort or os.environ.get("STOMATO_AGENT_EFFORT") or DEFAULT_EFFORT
        if client is None:
            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise ModelSetupError(
                    "ANTHROPIC_API_KEY is not set — the agent cannot run. Set the "
                    "variable in the API process environment to enable the Agent view."
                )
            import anthropic

            client = anthropic.Anthropic()
        self._client = client
        self._model = model
        self._effort = effort

    def stream(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        on_text: TextSink,
    ) -> ModelResponse:
        with self._client.messages.stream(
            model=self._model,
            max_tokens=MAX_TOKENS,
            # Prompt caching (spec B-08): the system prompt is byte-stable per
            # process, so it carries a cache breakpoint like the last tool does.
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            # SDK boundary: the loop's message/tool dicts are JSON wire shapes and
            # match the SDK's TypedDict params at runtime; the SDK's static types
            # are nominal, so pass them through as Any rather than rebuild dicts.
            messages=cast(Any, messages),
            tools=cast(Any, tools),
            output_config=cast(Any, {"effort": self._effort}),
        ) as stream:
            for delta in stream.text_stream:
                if delta:
                    on_text(delta)
            message = stream.get_final_message()
        return _from_message(message)


@dataclass
class ScriptedModel:
    """Replays preloaded ModelResponses in order — the model every test uses.

    Each :meth:`stream` call records its arguments in ``calls`` (system,
    messages copy, tools) so tests assert what the loop actually sent, and
    pops the next scripted response, forwarding its text through ``on_text``.
    An empty script raises AssertionError — a test that runs out of script has
    a bug in its expectations, not a silent stop.
    """

    script: list[ModelResponse] = field(default_factory=list)
    calls: list[tuple[str, list[dict[str, Any]], list[dict[str, Any]]]] = field(default_factory=list)

    def stream(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        on_text: TextSink,
    ) -> ModelResponse:
        if not self.script:
            raise AssertionError("ScriptedModel script exhausted — add a response for this turn")
        self.calls.append((system, [dict(m) for m in messages], tools))
        response = self.script.pop(0)
        if response.text:
            on_text(response.text)
        return response


class StubStream:
    """SDK-shaped stream event source for the real client's tests (no network).

    Context manager with ``text_stream`` and ``get_final_message()`` — the only
    surface :meth:`AnthropicModel.stream` touches.
    """

    def __init__(self, text_deltas: Iterable[str], final_message: Any) -> None:
        self._deltas = list(text_deltas)
        self._final = final_message
        self.kwargs: dict[str, Any] | None = None  # what the client was called with

    def __enter__(self) -> StubStream:
        return self

    def __exit__(self, *exc: object) -> None: ...

    @property
    def text_stream(self) -> Iterable[str]:
        return iter(self._deltas)

    def get_final_message(self) -> Any:
        return self._final


class StubAnthropicClient:
    """A stand-in for ``anthropic.Anthropic`` yielding one StubStream per call."""

    def __init__(self, streams: list[StubStream]) -> None:
        self._streams = list(streams)
        self.requests: list[dict[str, Any]] = []

    @property
    def messages(self) -> StubAnthropicClient:
        return self

    def stream(self, **kwargs: Any) -> StubStream:
        self.requests.append(kwargs)
        if not self._streams:
            raise AssertionError("StubAnthropicClient has no stream left")
        stub = self._streams.pop(0)
        stub.kwargs = kwargs
        return stub


__all__ = [
    "DEFAULT_EFFORT",
    "DEFAULT_MODEL",
    "MAX_TOKENS",
    "AnthropicModel",
    "ModelClient",
    "ModelResponse",
    "ModelSetupError",
    "ScriptedModel",
    "StubAnthropicClient",
    "StubStream",
    "TextSink",
    "ToolUseRequest",
]
