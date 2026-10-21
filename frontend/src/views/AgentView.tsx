import { useEffect, useRef, useState } from "react";
import { api, type AgentEvent } from "../api/client";
import { notifyProjectChanged } from "../api/refresh";

type ToolRow = {
  id: string;
  label: string;
  input?: unknown;
  ok?: boolean;
  summary?: string;
  result?: unknown;
};
type Msg = { id?: string; who: "You" | "Agent"; text?: string; calls?: ToolRow[]; error?: string };

/** Compact one-line label for a tool call, e.g. add_unit(kind="scrubber", tag="V-102"). */
function callLabel(name: string, input: unknown): string {
  if (input === undefined || input === null || (typeof input === "object" && Object.keys(input as object).length === 0)) {
    return `${name}()`;
  }
  if (typeof input !== "object") return `${name}(${String(input)})`;
  const args = Object.entries(input as Record<string, unknown>)
    .map(([k, v]) => `${k}=${typeof v === "string" ? JSON.stringify(v) : JSON.stringify(v)}`)
    .join(", ");
  return `${name}(${args})`;
}

/** Chat with the engine agent: full-width conversation with a large composer.
 * Streams POST /api/agent (SSE) through api.agent.send; tool calls render as
 * collapsible rows; a `project_changed` event raises the shared refresh signal. */
export function AgentView() {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [conversationId, setConversationId] = useState<string | undefined>(undefined);
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    // jsdom (tests) has no scrollIntoView; optional call keeps it safe there.
    endRef.current?.scrollIntoView?.({ block: "end" });
  }, [msgs]);

  const canSend = draft.trim().length > 0 && !streaming;

  const send = async () => {
    const text = draft.trim();
    if (!text || streaming) return;
    setDraft("");
    setStreaming(true);

    const userMsg: Msg = { who: "You", text };
    const replyId = `agent-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    setMsgs((m) => [...m, userMsg, { id: replyId, who: "Agent", calls: [] }]);

    // Local accumulators: the onEvent callback fires synchronously per chunk,
    // so we fold each event into the reply message in one state write.
    let reply: Msg = { id: replyId, who: "Agent", calls: [] };
    let changed = false;
    let convId: string | undefined;
    const flush = () => setMsgs((m) => m.map((x) => (x.id === replyId ? reply : x)));

    try {
      await api.agent.send(text, conversationId, (ev: AgentEvent) => {
        if (ev.type === "text_delta") {
          reply = { ...reply, text: (reply.text ?? "") + ev.text };
          flush();
        } else if (ev.type === "tool_call") {
          reply = {
            ...reply,
            calls: [...(reply.calls ?? []), { id: ev.id, label: callLabel(ev.name, ev.input), input: ev.input }],
          };
          flush();
        } else if (ev.type === "tool_result") {
          reply = {
            ...reply,
            calls: (reply.calls ?? []).map((c) =>
              c.id === ev.id ? { ...c, ok: ev.ok, summary: ev.summary, result: ev.result } : c,
            ),
          };
          flush();
        } else if (ev.type === "project_changed") {
          changed = true;
        } else if (ev.type === "done") {
          convId = ev.conversation_id;
        } else if (ev.type === "error") {
          reply = { ...reply, error: ev.message };
          flush();
        }
      });
      if (convId) setConversationId(convId);
      if (changed) notifyProjectChanged();
    } catch (e) {
      reply = { ...reply, error: e instanceof Error ? e.message : String(e) };
      flush();
    } finally {
      setStreaming(false);
    }
  };

  return (
    <section className="page">
      <div className="pagehead">
        <div>
          <h1>Agent</h1>
          <p>Ask for changes in plain language. The agent works through the same API as the screens, and every tool call is shown.</p>
        </div>
      </div>
      <section className="chat ob" aria-label="Conversation">
        {msgs.length === 0 && <p className="small muted note">Start the conversation — ask about the flowsheet or request a change.</p>}
        {msgs.map((m, i) => (
          <div key={i} className={"msg " + (m.who === "You" ? "user" : "bot")}>
            <span className="who">{m.who}</span>
            {m.calls && m.calls.length > 0 && (
              <div className="calls">
                {m.calls.map((c) => (
                  <details key={c.id || c.label} className="call">
                    <summary>
                      <span>{c.label}</span>
                      {c.ok === undefined ? (
                        <span className="okc">…</span>
                      ) : c.ok ? (
                        <span className="okc">✓ {c.summary ?? "done"}</span>
                      ) : (
                        <span className="badc">✗ {c.summary ?? "failed"}</span>
                      )}
                    </summary>
                    {c.input !== undefined && <pre className="call-io">input: {JSON.stringify(c.input, null, 2)}</pre>}
                    {c.result !== undefined && <pre className="call-io">result: {JSON.stringify(c.result, null, 2)}</pre>}
                  </details>
                ))}
              </div>
            )}
            {m.error && (
              <p role="alert" className="chip bad">
                {m.error}
              </p>
            )}
            {m.text && <span>{m.text}</span>}
          </div>
        ))}
        <div ref={endRef} />
        <form
          className="composer"
          onSubmit={(e) => {
            e.preventDefault();
            void send();
          }}
        >
          <div className="inp ob">
            <textarea
              name="ask"
              aria-label="Message"
              placeholder="Ask about the flowsheet or request a change"
              rows={5}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void send();
                }
              }}
            />
          </div>
          <button type="submit" className="btn ob primary" disabled={!canSend} title={streaming ? "Streaming…" : undefined}>
            {streaming ? "Streaming…" : "Send"}
          </button>
        </form>
      </section>
    </section>
  );
}
