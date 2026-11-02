"""Parse NASA CEA's thermo.inp (NASA 9-coefficient polynomials) as text.

Format: McBride, Zehe & Gordon, NASA Glenn Coefficients for Calculating Thermodynamic
Properties of Individual Species, NASA/TP-2002-211556 (2002), Appendix A. Per species:
a name line (name in columns 1-16, references after), a line with the interval count,
elemental formula, phase flag (0 gas), molar mass and ΔfH°298 (J/mol), then three lines
per temperature interval: the range and exponents, then seven coefficients a1..a7 and the
two integration constants b1, b2. Fortran ``D`` exponents are read as ``E``.

    Cp/R = a1/T² + a2/T + a3 + a4 T + a5 T² + a6 T³ + a7 T⁴
    H/RT = −a1/T² + a2 ln(T)/T + a3 + a4 T/2 + a5 T²/3 + a6 T³/4 + a7 T⁴/5 + b1/T
    S/R  = −a1/(2T²) − a2/T + a3 ln T + a4 T + a5 T²/2 + a6 T³/3 + a7 T⁴/4 + b2
"""

from __future__ import annotations

from typing import Any


def _floats(text: str, width: int = 16) -> list[float]:
    values: list[float] = []
    for start in range(0, len(text), width):
        chunk = text[start : start + width].strip()
        if chunk:
            values.append(float(chunk.replace("D", "E")))
    return values


def parse_thermo_inp(text: str) -> list[dict[str, Any]]:
    """Every species record with at least one temperature interval."""
    lines = [line.rstrip("\n") for line in text.splitlines()]
    records: list[dict[str, Any]] = []
    i = 0
    while i < len(lines) and not lines[i].startswith("thermo"):
        i += 1
    i += 2  # 'thermo' and the global temperature line
    while i + 1 < len(lines):
        head = lines[i]
        if head.startswith("END"):
            i += 1
            continue
        if head.startswith("!") or not head.strip():
            i += 1
            continue
        second = lines[i + 1]
        try:
            intervals = int(second[0:2])
            phase_flag = int(second[50:52])
            molar_mass = float(second[52:65])
            hf298 = float(second[65:80])
        except ValueError:
            i += 1
            continue
        name = head[:16].strip()
        reference = head[18:].strip()
        pieces = []
        cursor = i + 2
        for _ in range(intervals):
            window = lines[cursor]
            Tmin, Tmax = float(window[0:11]), float(window[11:22])
            first = _floats(lines[cursor + 1])
            last = lines[cursor + 2]
            a = first + _floats(last[:32])
            b = _floats(last[48:])
            pieces.append({"Tmin": Tmin, "Tmax": Tmax, "a": a[:7], "b": b[:2]})
            cursor += 3
        i = cursor if intervals else i + 3
        if pieces:
            records.append(
                {
                    "name": name,
                    "reference": reference,
                    "phase_flag": phase_flag,
                    "molar_mass": molar_mass,
                    "hf298": hf298,
                    "pieces": pieces,
                }
            )
    return records
