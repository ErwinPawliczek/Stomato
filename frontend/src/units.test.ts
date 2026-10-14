import { toDegC, toKPaG, toKmolH, toKw } from "./units";

test("converts backend SI base units to user units", () => {
  expect(toDegC(293.15)).toBe(20);
  expect(toDegC(0)).toBe(-273.1);
  expect(toKPaG(3447000)).toBe(3345.7);
  expect(toKPaG(101325)).toBe(0);
  expect(toKmolH(691.7062)).toBe(2490.142);
  expect(toKmolH(0)).toBe(0);
  expect(toKw(1505837)).toBe(1505.84);
  expect(toKw(0)).toBe(0);
});
