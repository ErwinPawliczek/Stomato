"""POST /api/agent (spec B-08): chat with the engineering agent over SSE.

The route owns only session identity and transport: conversations keyed by
``conversation_id`` live in the store's ConversationRow (spec P3-01 — a restart
keeps the transcripts; the engine is still the state, not the chat log), a
worker thread running :func:`run_conversation`, and a queue feeding the SSE
frames. The frontend contract (F-08) is: ``{message, conversation_id?}`` in,
then ``data: {json}`` frames — ``text_delta``, ``tool_call``, ``tool_result``,
``project_changed`` and a final ``done`` carrying the conversation id, or
``error``.

The model is injected: tests set a :class:`ScriptedModel` via
:func:`set_model` and no test ever touches the network. The project store
arrives as a dependency (the deps' :class:`DbProjectStore` implements the
agent's ProjectStore protocol).

Spec P3-01: :func:`agent_message_core` and friends take the store, so
routes_projects.py can register the project-scoped twins; the legacy unscoped
routes are deprecated aliases bound to the ``default`` project.
"""

from __future__ import annotations

import json
import os
import queue
import threading
import uuid
from collections.abc import Iterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
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
from ngdesign.api.deps import default_project_store
from ngdesign.store import DbProjectStore, delete_all_conversations

router = APIRouter()

#: The injected model client; lazily the real one when never set explicitly.
_model: ModelClient | None = None


def set_model(model: ModelClient) -> None:
    """Inject the model client (tests inject a ScriptedModel; production never calls this)."""
    global _model
    _model = model


def reset_sessions() -> None:
    """Drop every conversation of every project (test isolation)."""
    delete_all_conversations()


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
            tool_uses=(
                ToolUseRequest(id="demo-2", name="read_variable", input={"address": "K-101.power_W"}),
            ),
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


class AgentRequest(BaseModel):
    """POST /api/agent body (the F-08 frontend contract)."""

    message: str
    conversation_id: str | None = None


def _sse(event: dict[str, Any]) -> str:
    """One SSE frame: a single data line, blank-line terminated."""
    return f"data: {json.dumps(event)}\n\n"


def agent_message_core(store: DbProjectStore, req: AgentRequest) -> StreamingResponse:
    """Stream one agent turn on ``store``'s project as SSE frames (see module
    docstring for the contract; the legacy route and the project-scoped twin
    both call this)."""
    message = req.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="message must not be empty")
    conversations = store.conversations
    if req.conversation_id is not None and conversations.load(req.conversation_id) is None:
        raise HTTPException(
            status_code=404,
            detail="unknown conversation_id — the server does not remember it; start a new conversation",
        )
    conversation_id = req.conversation_id or uuid.uuid4().hex
    messages: list[dict[str, Any]] = []
    if req.conversation_id is not None:
        loaded = conversations.load(req.conversation_id)
        if loaded is not None:
            messages = loaded

    events: queue.Queue[dict[str, Any] | DoneInfo | None] = queue.Queue()

    def worker() -> None:
        try:
            done = run_conversation(get_model(), store, DEFAULT_ENGINE, message, messages, events.put)
            events.put(done)
        except ModelSetupError as exc:
            events.put({"type": "error", "message": str(exc)})
        except Exception as exc:  # noqa: BLE001 — the stream must end with an error event, never hang
            events.put({"type": "error", "message": f"agent failed: {exc}"})
        finally:
            # The loop mutates the history in place; persist whatever the turn
            # produced — a restart (or the next turn) picks up here.
            try:
                conversations.save(conversation_id, messages)
            except Exception as exc:  # noqa: BLE001 — persistence must not kill the stream
                events.put({"type": "error", "message": f"failed to persist conversation: {exc}"})
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


@router.post("/api/agent", deprecated=True)
def agent_message(
    req: AgentRequest, store: Annotated[DbProjectStore, Depends(default_project_store)]
) -> StreamingResponse:
    """Stream one agent turn on the default project as SSE frames."""
    return agent_message_core(store, req)


def agent_conversations_core(store: DbProjectStore) -> dict[str, list[str]]:
    """Conversation ids stored for this project (transcripts live in the store)."""
    return {"conversations": store.conversations.list_ids()}


@router.get("/api/agent", deprecated=True)
def list_conversations(
    store: Annotated[DbProjectStore, Depends(default_project_store)],
) -> dict[str, list[str]]:
    """Every conversation id of the default project."""
    return agent_conversations_core(store)


def agent_transcript_core(store: DbProjectStore, conversation_id: str) -> dict[str, Any]:
    """The conversation's message history in Anthropic API shape (tool calls and
    results included)."""
    messages = store.conversations.load(conversation_id)
    if messages is None:
        raise HTTPException(status_code=404, detail=f"unknown conversation {conversation_id!r}")
    return {"conversation_id": conversation_id, "messages": messages}


@router.get("/api/agent/{conversation_id}", deprecated=True)
def transcript(
    conversation_id: str, store: Annotated[DbProjectStore, Depends(default_project_store)]
) -> dict[str, Any]:
    """The default project's conversation history."""
    return agent_transcript_core(store, conversation_id)


def agent_conversation_delete_core(store: DbProjectStore, conversation_id: str) -> dict[str, str]:
    """Forget one conversation; the project state is untouched."""
    if not store.conversations.delete(conversation_id):
        raise HTTPException(status_code=404, detail=f"unknown conversation {conversation_id!r}")
    return {"deleted": conversation_id}


@router.delete("/api/agent/{conversation_id}", deprecated=True)
def delete_conversation(
    conversation_id: str, store: Annotated[DbProjectStore, Depends(default_project_store)]
) -> dict[str, str]:
    """Forget one conversation of the default project."""
    return agent_conversation_delete_core(store, conversation_id)
