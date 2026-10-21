import { api } from "./client";
import type { AgentEvent } from "./client";

test("mock agent.send streams the canned event sequence in order and ends with done", async () => {
  const events: AgentEvent[] = [];
  await api.agent.send("Build the treating train", undefined, (e) => events.push(e));
  expect(events.length).toBeGreaterThan(5);
  expect(events[0].type).toBe("text_delta");
  // every tool_call gets a matching tool_result
  for (const call of events.filter((e): e is Extract<AgentEvent, { type: "tool_call" }> => e.type === "tool_call")) {
    const result = events.find((e) => e.type === "tool_result" && e.id === call.id);
    expect(result).toBeTruthy();
  }
  const done = events[events.length - 1];
  expect(done.type).toBe("done");
  if (done.type === "done") expect(done.conversation_id).toBe("c_mock_1");
});

test("placement round-trips through the client", async () => {
  api._resetMock();
  const layout = await api.place("pfd", "V-101", { x: 10, y: 20 });
  expect(layout.pfd?.["V-101"]).toEqual({ x: 10, y: 20 });
  const p = await api.getProject();
  expect(p.layout?.pfd?.["V-101"]).toEqual({ x: 10, y: 20 });
});

test("mock pfd.svg honours saved placement, as GET /api/views/pfd.svg does", async () => {
  api._resetMock();
  const before = await api.pfdSvg();
  expect(before).toContain('<g data-tag="V-101"');
  await api.place("pfd", "V-101", { x: 300, y: 200 });
  const after = await api.pfdSvg();
  // The stored centre wins: the box is re-centred on (300, 200).
  expect(after).toContain('x="245" y="155"');
});


test("getMeta mirrors GET /api/meta's registry inventory", async () => {
  const meta = await api.getMeta();
  expect(meta.thermo).toEqual(expect.arrayContaining(["pr", "nrtl", "srk", "pr78"]));
  expect(meta.unit).toEqual(
    expect.arrayContaining([
      "compressor",
      "expander",
      "compression_train",
      "mdea_absorber",
      "mdea_regenerator",
      "teg_contactor",
    ]),
  );
});
