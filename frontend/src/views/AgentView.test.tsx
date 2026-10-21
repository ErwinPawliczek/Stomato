import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { AgentView } from "./AgentView";
import { onProjectChanged } from "../api/refresh";

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
  const row = screen.getAllByText(/C-201/)[0].closest("details") as HTMLDetailsElement;
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
