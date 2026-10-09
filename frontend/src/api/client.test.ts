import { api } from "./client";

test("placement round-trips through the client", async () => {
  api._resetMock();
  const layout = await api.place("pfd", "V-101", { x: 10, y: 20 });
  expect(layout.pfd?.["V-101"]).toEqual({ x: 10, y: 20 });
  const p = await api.getProject();
  expect(p.layout?.pfd?.["V-101"]).toEqual({ x: 10, y: 20 });
});
