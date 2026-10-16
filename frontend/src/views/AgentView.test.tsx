import { fireEvent, render, screen } from "@testing-library/react";
import { AgentView } from "./AgentView";

test("shows the conversation with tool calls and a large composer", () => {
  render(<AgentView />);
  expect(screen.getByRole("region", { name: "Conversation" })).toBeTruthy();
  expect(screen.getByText('add_unit(kind="scrubber", tag="V-102")')).toBeTruthy();
  expect(screen.queryByText("Tools")).toBeNull();

  const box = screen.getByRole("textbox", { name: "Message" }) as HTMLTextAreaElement;
  expect(box.rows).toBe(5);
  fireEvent.change(box, { target: { value: "Size V-101 for 60 MMSCFD" } });
  expect(box.value).toBe("Size V-101 for 60 MMSCFD");
  expect((screen.getByRole("button", { name: "Send" }) as HTMLButtonElement).disabled).toBe(true);
});
