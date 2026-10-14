import {
  celsiusToKelvin,
  formatNumber,
  kelvinToCelsius,
  kmolPerHToMolS,
  kpaGaugeToPa,
  molPerSToKmolPerH,
  paToKpaGauge,
  parseFiniteNumber,
  toDegC,
  toKmolH,
  toKPaG,
  toKw,
} from "./units";

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

test("temperature conversions round-trip", () => {
  expect(kelvinToCelsius(322.15)).toBeCloseTo(49, 9);
  expect(celsiusToKelvin(kelvinToCelsius(322.15))).toBeCloseTo(322.15, 9);
  expect(celsiusToKelvin(0)).toBeCloseTo(273.15, 9);
});

test("gauge pressure conversions round-trip", () => {
  expect(paToKpaGauge(3447000)).toBeCloseTo(3345.675, 6);
  expect(kpaGaugeToPa(paToKpaGauge(3447000))).toBeCloseTo(3447000, 6);
});

test("molar flow conversions round-trip", () => {
  expect(molPerSToKmolPerH(100)).toBeCloseTo(360, 9);
  expect(kmolPerHToMolS(360)).toBeCloseTo(100, 9);
  expect(molPerSToKmolPerH(691.7062)).toBeCloseTo(2490.14232, 4);
});

test("parseFiniteNumber rejects blank and non-numeric text", () => {
  expect(parseFiniteNumber("3.5")).toBe(3.5);
  expect(parseFiniteNumber("1e3")).toBe(1000);
  expect(parseFiniteNumber("")).toBeNull();
  expect(parseFiniteNumber("  ")).toBeNull();
  expect(parseFiniteNumber("abc")).toBeNull();
  expect(parseFiniteNumber("NaN")).toBeNull();
  expect(parseFiniteNumber("Infinity")).toBeNull();
});

test("formatNumber strips float noise", () => {
  expect(formatNumber(293.15 - 273.15)).toBe("20");
  expect(formatNumber(7000000)).toBe("7000000");
  expect(formatNumber(0.1 + 0.2)).toBe("0.3");
});
