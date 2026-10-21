"""POST /api/agent (spec B-08): chat with the engineering agent over SSE.

The route owns only session identity and transport: in-memory conversations
keyed by ``conversation_id`` (a restart starts fresh — the engine is the state,
not the chat log), a worker thread running :func:`run_conversation`, and a
queue feeding the SSE frames. The frontend contract (F-08) is:
``{message, conversation_id?}`` in, then ``data: {json}`` frames —
``text_delta``, ``tool_call``, ``tool_result``, ``project_changed`` and a final
``done`` carrying the conversation id, or ``error``.

The model and the project store are injected: tests set a :class:`ScriptedModel`
via :func:`set_model` and no test ever touches the network.
"""

from __future__ import annotations

import json
import os
import queue
import threading
import uuid
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ngdesign.agent.engine import DEFAULT_ENGINE
from ngdesign.agent.loop import DoneInfo, run_conversation
from ngdesign.agent.model import (
    AnthropicModel,
    ModelClient,
    ModelResponse,
    ModelSetupError,
    ScriptedModel,
    ToolUseRequest,
)

router = APIRouter()

#: conversation_id -> message history in Anthropic API shape. In-memory by
#: design (spec B-08): the project is the durable state, the chat is not.
_sessions: dict[str, list[dict[str, Any]]] = {}

#: The injected model client; lazily the real one when never set explicitly.
_model: ModelClient | None = None


def set_model(model: ModelClient) -> None:
    """Inject the model client (tests inject a ScriptedModel; production never calls this)."""
    global _model
    _model = model


def reset_sessions() -> None:
    """Drop every conversation (test isolation)."""
    _sessions.clear()


def scripted_demo_script() -> list[ModelResponse]:
    """The deterministic scripted turn behind ``STOMATO_AGENT_MODE=scripted``.

    Used by tests and ``VITE_MOCK`` demos (spec B-08): one fixed plan against
    whatever project the app currently holds — solve, read the compressor's
    power, render — ending in a final answer. A fresh script per turn keeps
    repeated demo turns identical and independent.
    """
    return [
        ModelResponse(
            text="Solving the current flowsheet first.",
            tool_uses=(ToolUseRequest(id="demo-1", name="solve", input={}),),
            stop_reason="tool_use",
            input_tokens=10,
            output_tokens=5,
        ),
        ModelResponse(
            text="Now reading the compressor's power draw.",
            tool_uses=(ToolUseRequest(id="demo-2", name="read_variable", input={"addr": "K-101.power_W"}),),
            stop_reason="tool_use",
            input_tokens=15,
            output_tokens=6,
        ),
        ModelResponse(
            text="And the drawing that matches the solved project.",
            tool_uses=(ToolUseRequest(id="demo-3", name="render", input={"view": "pfd"}),),
            stop_reason="tool_use",
            input_tokens=20,
            output_tokens=7,
        ),
        ModelResponse(
            text="Done: the solve, compressor power read and PFD render above all ran "
            "against the current project through the same tools the live model uses.",
            tool_uses=(),
            stop_reason="end_turn",
            input_tokens=25,
            output_tokens=30,
        ),
    ]


def get_model() -> ModelClient:
    """The model for one conversation turn (spec B-08: ``ScriptedModel`` when env
    ``STOMATO_AGENT_MODE=scripted`` — deterministic, no network — else the real
    ``AnthropicModel``, built once per process)."""
    global _model
    if os.environ.get("STOMATO_AGENT_MODE") == "scripted":
        return ScriptedModel(script=scripted_demo_script())
    if _model is None:
        _model = AnthropicModel()
    return _model


class _AppStateStore:
    """ProjectStore over app.py's single-project state (the API owns the project)."""

    def get(self) -> Any:
        from ngdesign.api.app import _project

        return _project()

    def put(self, project: Any) -> Any:
        from ngdesign.api.app import _state

        _state["p"] = project
        return project


class AgentRequest(BaseModel):
    """POST /api/agent body (the F-08 frontend contract)."""

    message: str
    conversation_id: str | None = None


def _sse(event: dict[str, Any]) -> str:
    """One SSE frame: a single data line, blank-line terminated."""
    return f"data: {json.dumps(event)}\n\n"


@router.post("/api/agent")
def agent_message(req: AgentRequest) -> StreamingResponse:
    """Stream one agent turn as SSE frames (see module docstring for the contract)."""
    message = req.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="message must not be empty")
    if req.conversation_id is not None and req.conversation_id not in _sessions:
        raise HTTPException(
            status_code=404,
            detail="unknown conversation_id — the server does not remember it; start a new conversation",
        )
    conversation_id = req.conversation_id or uuid.uuid4().hex
    messages = _sessions.setdefault(conversation_id, [])

    events: queue.Queue[dict[str, Any] | DoneInfo | None] = queue.Queue()

    def worker() -> None:
        try:
            done = run_conversation(
                get_model(), _AppStateStore(), DEFAULT_ENGINE, message, messages, events.put
            )
            events.put(done)
        except ModelSetupError as exc:
            events.put({"type": "error", "message": str(exc)})
        except Exception as exc:  # noqa: BLE001 — the stream must end with an error event, never hang
            events.put({"type": "error", "message": f"agent failed: {exc}"})
        finally:
            events.put(None)

    threading.Thread(target=worker, daemon=True, name="agent-conversation").start()

    def frames() -> Iterator[str]:
        while True:
            event = events.get()
            if event is None:
                break
            if isinstance(event, DoneInfo):
                yield _sse(
                    {
                        "type": "done",
                        "conversation_id": conversation_id,
                        "stop_reason": event.stop_reason,
                        "usage": event.usage,
                    }
                )
                continue
            yield _sse(event)

    return StreamingResponse(
        frames(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/api/agent")
def list_conversations() -> dict[str, list[str]]:
    """Every known conversation id (transcripts live in memory, spec B-08)."""
    return {"conversations": sorted(_sessions)}


@router.get("/api/agent/{conversation_id}")
def transcript(conversation_id: str) -> dict[str, Any]:
    """The conversation's message history in Anthropic API shape (tool calls and results included)."""
    if conversation_id not in _sessions:
        raise HTTPException(status_code=404, detail=f"unknown conversation {conversation_id!r}")
    return {"conversation_id": conversation_id, "messages": _sessions[conversation_id]}


@router.delete("/api/agent/{conversation_id}")
def delete_conversation(conversation_id: str) -> dict[str, str]:
    """Forget one conversation; the project state is untouched."""
    if conversation_id not in _sessions:
        raise HTTPException(status_code=404, detail=f"unknown conversation {conversation_id!r}")
    del _sessions[conversation_id]
    return {"deleted": conversation_id}
