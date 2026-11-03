import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, errorReason, type AgentEvent, type Change, type ProjectInfo, type TranscriptMessage } from "../api/client";
import { notifyProjectChanged } from "../api/refresh";

type ToolRow = {
  id: string;
  label: string;
  input?: unknown;
  ok?: boolean;
  summary?: string;
  result?: unknown;
  change?: Change;
};
/** A reply is text and tool calls in the order the agent produced them. */
type Part = { kind: "text"; text: string } | { kind: "call"; call: ToolRow };
type Msg = { id?: string; who: "You" | "Agent"; parts: Part[]; error?: string; note?: string };

/** Pure: fold one streamed event into a reply's parts (text deltas extend the
 * current text part; a call after text starts a new part, so text written
 * between tool calls stays between them instead of running together). */
export function foldEvent(parts: Part[], ev: AgentEvent): Part[] {
  if (ev.type === "text_delta") {
    const last = parts.at(-1);
    if (last?.kind === "text") return [...parts.slice(0, -1), { kind: "text", text: last.text + ev.text }];
    return [...parts, { kind: "text", text: ev.text }];
  }
  if (ev.type === "tool_call")
    return [...parts, { kind: "call", call: { id: ev.id, label: callLabel(ev.name, ev.input), input: ev.input } }];
  if (ev.type === "tool_result")
    return parts.map((p) =>
      p.kind === "call" && p.call.id === ev.id
        ? { kind: "call", call: { ...p.call, ok: ev.ok, summary: ev.summary, result: ev.result, change: ev.change } }
        : p,
    );
  return parts;
}

/** Pure: a stored transcript (Anthropic messages) as chat messages. Tool results
 * attach to their calls; one user turn's assistant messages form one reply. */
export function transcriptToMsgs(messages: TranscriptMessage[]): Msg[] {
  const out: Msg[] = [];
  let reply: Msg | null = null;
  const parseResult = (content: unknown): unknown => {
    if (typeof content !== "string") return content;
    try {
      return JSON.parse(content) as unknown;
    } catch {
      return content;
    }
  };
  for (const m of messages) {
    if (m.role === "user" && typeof m.content === "string") {
      out.push({ who: "You", parts: [{ kind: "text", text: m.content }] });
      reply = null;
      continue;
    }
    const blocks = typeof m.content === "string" ? [{ type: "text" as const, text: m.content }] : m.content;
    if (m.role === "user") {
      for (const b of blocks) {
        if (b.type !== "tool_result" || !reply) continue;
        const result = parseResult(b.content);
        reply.parts = reply.parts.map((p) =>
          p.kind === "call" && p.call.id === b.tool_use_id
            ? { kind: "call", call: { ...p.call, ok: !b.is_error, summary: b.is_error ? "failed" : "done", result } }
            : p,
        );
      }
      continue;
    }
    if (!reply) {
      reply = { who: "Agent", parts: [] };
      out.push(reply);
    }
    for (const b of blocks) {
      if (b.type === "text") reply.parts = foldEvent(reply.parts, { type: "text_delta", text: b.text });
      else if (b.type === "tool_use") reply.parts = foldEvent(reply.parts, { type: "tool_call", id: b.id, name: b.name, input: b.input });
    }
  }
  return out;
}

/** First line of a conversation's first user message: its label in the picker. */
function titleOf(messages: TranscriptMessage[]): string {
  const first = messages.find((m) => m.role === "user" && typeof m.content === "string");
  const text = typeof first?.content === "string" ? first.content.trim().split("\n")[0] : "";
  return text.length > 60 ? `${text.slice(0, 59)}…` : text || "(empty conversation)";
}

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

/** CSS class of one diff line by its leading marker (+ added, - removed, ~ changed). */
function diffClass(line: string): string {
  if (line.startsWith("+")) return "diff-line add";
  if (line.startsWith("-")) return "diff-line del";
  return "diff-line mod";
}

/** The change a tool call committed: summary, seq and one line per diff entry. */
export function ChangeDiff({ change }: { change: Change }) {
  return (
    <div className="diff" aria-label={`Change ${change.seq ?? ""}: ${change.summary}`}>
      <div className="diff-head small">
        {change.seq !== null && change.seq !== undefined && <span className="muted">#{change.seq} </span>}
        {change.summary}
      </div>
      {change.lines.length > 0 && (
        <ul className="diff-lines">
          {change.lines.map((line, i) => (
            <li key={i} className={diffClass(line)}>
              {line}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Recent changes from any actor, with Undo / Redo (API v1 change history). */
function History({ changes, busy, onMove }: { changes: Change[]; busy: boolean; onMove: (kind: "undo" | "redo") => void }) {
  const recent = changes.slice(-8).reverse();
  return (
    <section className="history ob" aria-label="History">
      <div className="history-head">
        <h2>History</h2>
        <span className="grow" />
        <button type="button" className="btn ob" disabled={busy} onClick={() => onMove("undo")}>
          Undo
        </button>
        <button type="button" className="btn ob" disabled={busy} onClick={() => onMove("redo")}>
          Redo
        </button>
      </div>
      {recent.length === 0 ? (
        <p className="small muted">No changes yet.</p>
      ) : (
        <ol className="history-list">
          {recent.map((c) => (
            <li key={c.seq ?? c.summary} className="small">
              <span className="muted">#{c.seq}</span> <span className="chip">{c.actor}</span> {c.summary}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

/** Chat with the engine agent about the open project: full-width conversation
 * with a large composer. Streams POST .../agent (SSE) through api.agent.send;
 * text and tool calls render in the order they came, each tool call with the
 * change it made; a `project_changed` event raises the shared refresh signal.
 * Past conversations of the project can be reopened or deleted. With no project
 * open (`projectName === null`) it offers the projects to open instead. */
export function AgentView({
  projectName,
  onOpenProject,
}: {
  projectName?: string | null;
  onOpenProject?: (id: string) => void;
} = {}) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [conversationId, setConversationId] = useState<string | undefined>(undefined);
  const [conversations, setConversations] = useState<{ id: string; title: string }[]>([]);
  const endRef = useRef<HTMLDivElement | null>(null);
  const [changes, setChanges] = useState<Change[]>([]);
  const [historyBusy, setHistoryBusy] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const noProject = projectName === null;

  const reloadHistory = () =>
    api.history
      .list()
      .then(setChanges)
      .catch((e: unknown) => setHistoryError(`Could not load history: ${errorReason(e)}`));

  /** The project's conversations (newest last), each titled by its first message. */
  const reloadConversations = useCallback(async (): Promise<{ id: string; title: string; messages: TranscriptMessage[] }[]> => {
    const ids = await api.agent.conversations();
    const rows = await Promise.all(
      ids.slice(-20).map(async (id) => {
        const messages = await api.agent.transcript(id).catch(() => null);
        return messages ? { id, title: titleOf(messages), messages } : null;
      }),
    );
    const found = rows.filter((r): r is NonNullable<typeof r> => r !== null);
    setConversations(found.map(({ id, title }) => ({ id, title })));
    return found;
  }, []);

  useEffect(() => {
    if (noProject) return;
    void reloadHistory();
    // Pick up where this project's last conversation left off.
    reloadConversations()
      .then((found) => {
        const last = found.at(-1);
        if (last) {
          setConversationId(last.id);
          setMsgs(transcriptToMsgs(last.messages));
        }
      })
      .catch(() => undefined);
    // Live: changes from any actor (this tab, the agent, MCP, the REST API)
    // append here. App.tsx's own follower raises the project-changed signal.
    return api.history.subscribe((c) => setChanges((cs) => (cs.some((x) => x.seq === c.seq) ? cs : [...cs, c])));
  }, [noProject, reloadConversations]);

  const move = async (kind: "undo" | "redo") => {
    setHistoryBusy(true);
    setHistoryError(null);
    try {
      const m = kind === "undo" ? await api.history.undo() : await api.history.redo();
      const change = m.change;
      if (change) setChanges((cs) => (cs.some((x) => x.seq === change.seq) ? cs : [...cs, change]));
      notifyProjectChanged();
    } catch (e) {
      setHistoryError(errorReason(e));
    } finally {
      setHistoryBusy(false);
    }
  };

  const openConversation = async (id: string) => {
    if (!id) {
      setConversationId(undefined);
      setMsgs([]);
      return;
    }
    try {
      setMsgs(transcriptToMsgs(await api.agent.transcript(id)));
      setConversationId(id);
    } catch (e) {
      setMsgs([{ who: "Agent", parts: [], error: `Could not open the conversation: ${errorReason(e)}` }]);
      setConversationId(undefined);
      void reloadConversations();
    }
  };

  const deleteConversation = async () => {
    if (!conversationId) return;
    try {
      await api.agent.deleteConversation(conversationId);
    } catch (e) {
      setHistoryError(errorReason(e));
    }
    setConversationId(undefined);
    setMsgs([]);
    void reloadConversations();
  };

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

    const userMsg: Msg = { who: "You", parts: [{ kind: "text", text }] };
    const replyId = `agent-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    setMsgs((m) => [...m, userMsg, { id: replyId, who: "Agent", parts: [] }]);

    // Local accumulators: the onEvent callback fires synchronously per chunk,
    // so we fold each event into the reply message in one state write.
    let reply: Msg = { id: replyId, who: "Agent", parts: [] };
    let changed = false;
    let convId: string | undefined;
    const flush = () => setMsgs((m) => m.map((x) => (x.id === replyId ? reply : x)));
    const onEvent = (ev: AgentEvent) => {
      if (ev.type === "project_changed") changed = true;
      else if (ev.type === "done") convId = ev.conversation_id;
      else if (ev.type === "error") {
        reply = { ...reply, error: ev.message };
        flush();
      } else {
        reply = { ...reply, parts: foldEvent(reply.parts, ev) };
        flush();
      }
    };

    try {
      try {
        await api.agent.send(text, conversationId, onEvent);
      } catch (e) {
        // The conversation is gone (deleted elsewhere, server restarted with a
        // fresh store): start a new one instead of failing every later send.
        if (!(e instanceof ApiError && e.status === 404 && conversationId)) throw e;
        reply = { ...reply, note: "That conversation no longer exists on the server; this message started a new one." };
        flush();
        setConversationId(undefined);
        await api.agent.send(text, undefined, onEvent);
      }
      if (convId) {
        setConversationId(convId);
        if (!conversations.some((c) => c.id === convId)) void reloadConversations();
      }
      if (changed) {
        notifyProjectChanged();
        void reloadHistory();
      }
    } catch (e) {
      reply = { ...reply, error: errorReason(e) };
      flush();
    } finally {
      setStreaming(false);
    }
  };

  if (noProject) return <PickProject onOpen={onOpenProject} />;

  return (
    <section className="page">
      <div className="pagehead">
        <div>
          <h1>Agent{projectName ? ` · ${projectName}` : ""}</h1>
          <p>Ask for changes in plain language. The agent works through the same API as the screens; every tool call is shown with the change it made, and every change can be undone.</p>
        </div>
        <div className="row">
          <label className="field">
            <span>Conversation</span>
            <select aria-label="Conversation" value={conversationId ?? ""} disabled={streaming} onChange={(e) => void openConversation(e.target.value)}>
              <option value="">New conversation</option>
              {conversations.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.title}
                </option>
              ))}
            </select>
          </label>
          <button type="button" className="btn ob" disabled={!conversationId || streaming} onClick={() => void deleteConversation()}>
            Delete conversation
          </button>
        </div>
      </div>
      <History changes={changes} busy={historyBusy} onMove={(k) => void move(k)} />
      {historyError && (
        <p role="alert" className="chip bad">
          {historyError}
        </p>
      )}
      <section className="chat ob" aria-label="Conversation">
        {msgs.length === 0 && <p className="small muted note">Start the conversation — ask about the flowsheet or request a change.</p>}
        {msgs.map((m, i) => (
          <div key={i} className={"msg " + (m.who === "You" ? "user" : "bot")}>
            <span className="who">{m.who}</span>
            {m.note && <p className="small muted">{m.note}</p>}
            {m.parts.map((part, j) =>
              part.kind === "text" ? (
                <p key={j} className="msg-text">
                  {part.text}
                </p>
              ) : (
                <ToolCall key={part.call.id || j} c={part.call} />
              ),
            )}
            {m.error && (
              <p role="alert" className="chip bad">
                {m.error}
              </p>
            )}
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

/** One tool call: collapsible input/result, plus the change it committed. */
function ToolCall({ c }: { c: ToolRow }) {
  return (
    <div className="calls">
      <div className="call-wrap">
        <details className="call">
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
        {c.change && <ChangeDiff change={c.change} />}
      </div>
    </div>
  );
}

/** No project open: the agent edits one project, so pick it first. */
function PickProject({ onOpen }: { onOpen?: (id: string) => void }) {
  const [projects, setProjects] = useState<ProjectInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api
      .listProjects()
      .then(setProjects)
      .catch((e: unknown) => setError(errorReason(e)));
  }, []);
  return (
    <section className="page">
      <div className="pagehead">
        <div>
          <h1>Agent</h1>
          <p>The agent reads and edits one project. Open the project to work on.</p>
        </div>
      </div>
      {error && (
        <p role="alert" className="chip bad">
          Could not load projects: {error}
        </p>
      )}
      {projects?.length === 0 && <p className="muted">No projects yet. Create one on Home first.</p>}
      <ul className="pick-projects" aria-label="Projects">
        {(projects ?? []).map((p) => (
          <li key={p.id}>
            <button type="button" className="btn ob" onClick={() => onOpen?.(p.id)}>
              Open {p.name}
            </button>{" "}
            <span className="small muted">
              {p.project.flowsheet.units.length} units · {p.project.flowsheet.streams.length} streams
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
