import { api } from "./client";

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
