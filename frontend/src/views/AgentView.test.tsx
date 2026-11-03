import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { AgentView, foldEvent, transcriptToMsgs } from "./AgentView";
import { followProjectChanges, onProjectChanged } from "../api/refresh";
import { ApiError, api, TAB_ACTOR, type ChangeSource } from "../api/client";

test("empty state shows the composer hint and a disabled Send", () => {
  render(<AgentView />);
  expect(screen.getByRole("region", { name: "Conversation" })).toBeTruthy();
  expect(screen.getByText(/Start the conversation/)).toBeTruthy();
  const box = screen.getByRole("textbox", { name: "Message" }) as HTMLTextAreaElement;
  expect(box.rows).toBe(5);
  expect((screen.getByRole("button", { name: "Send" }) as HTMLButtonElement).disabled).toBe(true);
});

test("a streamed mock session shows text deltas, collapsible tool calls with results, and enables Send only with text", async () => {
  render(<AgentView />);

  // Send is disabled without text, enabled with it.
  const box = screen.getByRole("textbox", { name: "Message" });
  const send = screen.getByRole("button", { name: "Send" }) as HTMLButtonElement;
  expect(send.disabled).toBe(true);
  fireEvent.change(box, { target: { value: "Add the sour-gas treating train" } });
  expect(send.disabled).toBe(false);

  // Enter sends (Shift+Enter would newline) — fire the keydown directly.
  fireEvent.keyDown(box, { key: "Enter", shiftKey: false });

  // The user's message appears, Send turns into Streaming…, then the mock
  // events stream in: tool calls render as collapsible rows with results.
  expect(screen.getByText("Add the sour-gas treating train")).toBeTruthy();
  expect(await screen.findByText(/✓ C-201 added/)).toBeTruthy();
  expect(await screen.findByText(/✓ converged, 4 passes/)).toBeTruthy();
  await waitFor(() => expect((screen.getByRole("button", { name: "Send" }) as HTMLButtonElement).disabled).toBe(true));

  // Full input and result are available on expand (details/summary).
  const chat = within(screen.getByRole("region", { name: "Conversation" }));
  const row = chat.getAllByText(/C-201/)[0].closest("details") as HTMLDetailsElement;
  row.open = true;
  expect(row.textContent).toContain('"kind": "mdea_absorber"');
  expect(row.textContent).toContain('"tag": "C-201"');
  // The collapsed row shows the call label in call syntax.
  expect(row.textContent).toContain('add_unit(kind="mdea_absorber", tag="C-201")');

  // Final assistant text arrived as deltas.
  expect(screen.getByText(/The treating train is in place/)).toBeTruthy();
});

test("a project_changed event raises the shared refresh signal exactly once per send", async () => {
  let changes = 0;
  const off = onProjectChanged(() => {
    changes += 1;
  });
  try {
    render(<AgentView />);
    fireEvent.change(screen.getByRole("textbox", { name: "Message" }), { target: { value: "go" } });
    fireEvent.keyDown(screen.getByRole("textbox", { name: "Message" }), { key: "Enter", shiftKey: false });
    await screen.findByText(/The treating train is in place/);
    await waitFor(() => expect(changes).toBe(1)); // the mock stream emits project_changed once
  } finally {
    off();
  }
});

test("a mutating tool row shows the change it made as diff lines with summary and seq", async () => {
  render(<AgentView />);
  fireEvent.change(screen.getByRole("textbox", { name: "Message" }), { target: { value: "go" } });
  fireEvent.keyDown(screen.getByRole("textbox", { name: "Message" }), { key: "Enter", shiftKey: false });
  const chat = within(screen.getByRole("region", { name: "Conversation" }));
  const diff = await chat.findByLabelText("Change 1: Placed C-201 (mdea_absorber)");
  expect(diff.textContent).toContain("#1");
  const line = within(diff).getByText("+ unit C-201 (mdea_absorber)");
  expect(line.className).toContain("add");
  expect(await chat.findByText("+ stream S-201")).toBeTruthy();
  // A read-only tool (solve) carries no change block.
  const solveRow = (await chat.findByText(/✓ converged, 4 passes/)).closest(".call-wrap") as HTMLElement;
  expect(solveRow.querySelector(".diff")).toBeNull();
});

test("history lists recent changes; Undo calls the API, records the change and raises the refresh signal", async () => {
  api._resetMock();
  let refreshes = 0;
  const off = onProjectChanged(() => {
    refreshes += 1;
  });
  const undo = vi.spyOn(api.history, "undo");
  try {
    render(<AgentView />);
    const history = within(screen.getByRole("region", { name: "History" }));
    expect(await history.findByText("Set K-101.params.P_out = 65 bar")).toBeTruthy();
    expect(history.getByText("mcp")).toBeTruthy();
    fireEvent.click(history.getByRole("button", { name: "Undo" }));
    await waitFor(() => expect(refreshes).toBe(1));
    expect(undo).toHaveBeenCalledTimes(1);
    expect(await history.findByText("Undo: last change")).toBeTruthy();
  } finally {
    undo.mockRestore();
    off();
  }
});

test("followProjectChanges raises the refresh signal for other actors' changes, skipping this tab's own", async () => {
  api._resetMock();
  const sources: { url: string; src: ChangeSource }[] = [];
  api.history._setSource((url) => {
    const src: ChangeSource = { onmessage: null, close: vi.fn() };
    sources.push({ url, src });
    return src;
  });
  let refreshes = 0;
  const off = onProjectChanged(() => {
    refreshes += 1;
  });
  const seen: number[] = [];
  const stop = followProjectChanges((c) => seen.push(c.seq ?? -1));
  try {
    await waitFor(() => expect(sources).toHaveLength(1));
    expect(sources[0].url).not.toContain("after="); // the server starts live: no backlog replay
    const change = { seq: 3, kind: "edit", op: "move_unit", actor: "mcp", summary: "Moved V-101", args: {}, diff: {}, lines: [] };
    const own = { ...change, seq: 4, actor: TAB_ACTOR };
    sources[0].src.onmessage?.({ data: JSON.stringify({ type: "change", change }) });
    sources[0].src.onmessage?.({ data: JSON.stringify({ type: "change", change: own }) }); // own edit: skipped
    sources[0].src.onmessage?.({ data: "not json" }); // ignored
    expect(seen).toEqual([3]);
    expect(refreshes).toBe(1);
  } finally {
    stop();
    off();
    api.history._setSource(null);
  }
  expect(sources[0].src.close).toHaveBeenCalled();
});

test("text written between tool calls stays between them, in order", () => {
  let parts = foldEvent([], { type: "text_delta", text: "Solving " });
  parts = foldEvent(parts, { type: "text_delta", text: "first." });
  parts = foldEvent(parts, { type: "tool_call", id: "t1", name: "solve", input: {} });
  parts = foldEvent(parts, { type: "tool_result", id: "t1", ok: true, summary: "converged" });
  parts = foldEvent(parts, { type: "text_delta", text: "Now reading." });
  expect(parts.map((p) => (p.kind === "text" ? p.text : `${p.call.label}:${p.call.summary}`))).toEqual([
    "Solving first.",
    "solve():converged",
    "Now reading.",
  ]);
});

test("a stored transcript becomes the same chat, tool results on their calls", () => {
  const msgs = transcriptToMsgs([
    { role: "user", content: "What is in the flowsheet?" },
    { role: "assistant", content: [{ type: "text", text: "Solving." }, { type: "tool_use", id: "d1", name: "solve", input: {} }] },
    { role: "user", content: [{ type: "tool_result", tool_use_id: "d1", content: '{"converged": true}' }] },
    { role: "assistant", content: [{ type: "text", text: "Done." }] },
  ]);
  expect(msgs.map((m) => m.who)).toEqual(["You", "Agent"]);
  const parts = msgs[1].parts;
  expect(parts[0]).toEqual({ kind: "text", text: "Solving." });
  expect(parts[1].kind === "call" && parts[1].call.result).toEqual({ converged: true });
  expect(parts[1].kind === "call" && parts[1].call.ok).toBe(true);
  expect(parts[2]).toEqual({ kind: "text", text: "Done." });
});

test("with no project open the Agent page offers the projects and opens the chosen one", async () => {
  api._resetMock();
  const onOpen = vi.fn();
  render(<AgentView projectName={null} onOpenProject={onOpen} />);
  expect(screen.queryByRole("textbox", { name: "Message" })).toBeNull();
  fireEvent.click(await screen.findByRole("button", { name: "Open slice" }));
  expect(onOpen).toHaveBeenCalledWith("p-1");
});

test("the project's last conversation reopens; another can be picked; New clears", async () => {
  api._resetMock();
  api.agent._setMockConversations({
    c1: [{ role: "user", content: "older question" }, { role: "assistant", content: [{ type: "text", text: "older answer" }] }],
    c2: [{ role: "user", content: "latest question" }, { role: "assistant", content: [{ type: "text", text: "latest answer" }] }],
  });
  render(<AgentView projectName="slice" />);
  expect(await screen.findByText("latest answer")).toBeTruthy();
  const picker = screen.getByRole("combobox", { name: "Conversation" }) as HTMLSelectElement;
  expect(picker.value).toBe("c2");
  fireEvent.change(picker, { target: { value: "c1" } });
  expect(await screen.findByText("older answer")).toBeTruthy();
  fireEvent.change(picker, { target: { value: "" } });
  await waitFor(() => expect(screen.getByText(/Start the conversation/)).toBeTruthy());
  // Delete is only for an open conversation.
  expect((screen.getByRole("button", { name: "Delete conversation" }) as HTMLButtonElement).disabled).toBe(true);
});

test("a 404 for a stale conversation starts a new one instead of failing every send", async () => {
  api._resetMock();
  api.agent._setMockConversations({ gone: [{ role: "user", content: "hi" }] });
  const sent: (string | undefined)[] = [];
  const spy = vi.spyOn(api.agent, "send").mockImplementation(async (_text, id, onEvent) => {
    sent.push(id);
    if (id === "gone") throw new ApiError('POST /api/agent: 404 {"detail":"unknown conversation"}', 404);
    onEvent({ type: "text_delta", text: "fresh reply" });
    onEvent({ type: "done", conversation_id: "new-1", stop_reason: "end_turn" });
  });
  render(<AgentView projectName="slice" />);
  await waitFor(() => expect((screen.getByRole("combobox", { name: "Conversation" }) as HTMLSelectElement).value).toBe("gone"));
  fireEvent.change(screen.getByRole("textbox", { name: "Message" }), { target: { value: "again" } });
  fireEvent.keyDown(screen.getByRole("textbox", { name: "Message" }), { key: "Enter", shiftKey: false });
  expect(await screen.findByText("fresh reply")).toBeTruthy();
  expect(screen.getByText(/no longer exists on the server/)).toBeTruthy();
  expect(sent).toEqual(["gone", undefined]);
  expect(screen.queryByRole("alert")).toBeNull();
  spy.mockRestore();
});
