"""In-house virial vapour phases for the gamma-phi adapter (spec T-03b).

Two vapour options build real second-virial phases here:

- ``hoc`` - the Hayden-O'Connell (1975) correlation, transcribed from the
  open-source record: the Lehigh 1986 MSc thesis Appendix A (rendered-page
  read), the COBEQ-2014 proceedings paper, and - decisive for the ambiguous
  readings - the Prausnitz-1980 book's own Fortran (TDEP/BIJS2) embedded in
  the Maiorella LBL report (eScholarship 2d2148bx), which prints the
  parameter chain directly: RG-based pseudo-acentric factor,
  ``(2.4507-omega)^3*Tc/Pc_bar`` sigma cubed, the expanded epsilon dipole
  correction, and the B loop itself.
- ``nothnagel`` - the declared Tsonopoulos-extended fallback (the Nothnagel
  1973 b/K parameter table is in no open source; the catalogue row name
  says so).

Reading decisions and conflicts, each recorded (none silent):

- The book's Fortran computes A_ij (linear) and Delta-h_ij (squared) from
  the RAW reduced dipole mu_r, applying the piecewise correction afterwards;
  the LBL report's own equations 3-41/3-42 print the piecewise-corrected
  mu*.  Implementing the raw reading puts water B(373.15 K) at about
  -477 cm3/mol (5.1% off the Harvey-Lemmon -454 +-5 reference, outside the
  spec's 3% test); the mu* reading gives about -452.6 (0.3%).  We implement
  mu* in A/Delta-h and declare the conflict.
- The polar leading constant: 0.75 in the book's Fortran, 0.74 printed by
  the two secondary transcriptions.  Effect < 0.3% on the water anchor;
  the Fortran constant wins.
- The angle-averaging constant c: 2.882 (Lehigh visual read) vs 2.982 (LBL
  OCR).  2.882; the difference moves xi by ~4% and B by < 0.1%.
- Cross-pair dipole corrections (S1 A-24/25/29, shape agreed by both
  transcriptions; absent from the LBL demo because ethanol-water never
  triggers them) are implemented as printed: epsilon minus, sigma plus.
- The Prausnitz-1980 apparent-fugacity correction for strongly associating
  vapours is NOT implementable from open sources (documented literature
  gap); the second-virial fugacity treatment is invalid for acid-strength
  association, so slates with a pure eta >= 4.0 refuse (see
  ``refuse_acid_strength``) and the ``hoc_dimer`` special row remains the
  acid path.

Units: B in cm3/mol inside the correlation (b0 = 1.26184 sigma^3 with sigma
in Angstrom), converted to m3/mol at the model boundary.
"""

from __future__ import annotations

import math
from functools import cache
from pathlib import Path
from typing import Any

import yaml
from chemicals.molecular_geometry import CHEMSEP, RG
from thermo.phases.virial_phase import (
    VIRIAL_B_TSONOPOULOS_EXTENDED,
    VIRIAL_C_ZERO,
    VirialCSP,
    VirialGas,
)

HOC_MODEL = "Hayden-O'Connell (1975)"
NOTHNAGEL_MODEL = "Nothnagel (1973)"

#: vapour option value -> display name (gamma_phi wiring)
VIRIAL_VAPOURS = {"hoc": HOC_MODEL, "nothnagel": NOTHNAGEL_MODEL}

#: pure association parameter above which the second-virial fugacity
#: treatment is invalid (the ChemSep acid rows sit at 4.5; the next-highest
#: pair value in the table is 2.5)
PURE_ETA_ACID_LIMIT = 4.0

_ETA_YAML = Path(__file__).resolve().parents[3] / "data" / "thermo_params" / "virial" / "hoc_eta.yaml"


@cache
def _hoc_eta_pairs() -> dict[tuple[str, str], float]:
    """The ChemSep HAYDENO.IPD association/solvation table, loaded once."""
    with open(_ETA_YAML, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    pairs: dict[tuple[str, str], float] = {}
    for label, value in (raw.get("pairs") or {}).items():
        a, b = str(label).split("|")
        pairs[(a, b)] = float(value)
    return pairs


def eta_for_pair(cas_a: str, cas_b: str) -> float:
    """The HOC association parameter for one pair; 0.0 when the table is silent."""
    return _hoc_eta_pairs().get((cas_a, cas_b), 0.0)


def rg_of(cas: str) -> float:
    """The ChemSep mean radius of gyration (Angstrom) for one CAS.

    ``chemicals.molecular_geometry.RG`` reports metres; the correlation
    works in Angstroms.
    """
    return float(RG(cas, CHEMSEP)) * 1e10


def refuse_acid_strength(cas_list: list[str], etas: list[float]) -> None:
    """Refuse slates whose pure association strength breaks the B-truncation.

    With pure eta >= 4.0 (carboxylic acids) the chemical term dominates B so
    strongly that the truncated-virial fugacity phi = exp(BP/RT) goes
    unphysical (acetic acid at 400 K / 1 bar evaluates to Z = -1.3); the
    book's apparent-fugacity correction that handles this is not available
    in any open source.  Name the gap and point at the acid path.
    """
    offenders = [
        f"{cas} (eta={eta})" for cas, eta in zip(cas_list, etas, strict=True) if eta >= PURE_ETA_ACID_LIMIT
    ]
    if offenders:
        raise ValueError(
            "HOC virial vapour refuses association-strength pairs "
            f"(pure eta >= {PURE_ETA_ACID_LIMIT}): {', '.join(offenders)}. "
            "The second-virial fugacity truncation is invalid at this "
            "association strength and the Prausnitz-1980 apparent-fugacity "
            "correction is not available from open sources; use the "
            "hoc_dimer special row for acid vapours."
        )


def _poly_free(tsp: float) -> float:
    """The nonpolar free polynomial at TSP = 1/T*' (A-4)."""
    return 0.94 - 1.47 * tsp - 0.85 * tsp**2 + 1.015 * tsp**3


def _poly_polar(tsp: float) -> float:
    """The polar free polynomial at TSP = 1/T*' (A-5; Fortran constant 0.75)."""
    return 0.75 - 3.0 * tsp + 2.1 * tsp**2 + 2.1 * tsp**3


class HaydenOConnellModel:
    """Second-virial B model transcribed from Hayden-O'Connell (1975).

    Implements the ``VirialGas`` model protocol: ``to(T)``, ``B_pures``,
    ``B_interactions``, their first three temperature derivatives, and zero
    third-virial coefficients (``C_model = VIRIAL_C_ZERO``).

    Characteristic parameters are T-independent and precomputed once;
    ``to(T)`` carries them (and the CAS list, which the flash rebasing
    requires) into the new instance.
    """

    B_model = VIRIAL_B_TSONOPOULOS_EXTENDED
    C_model = VIRIAL_C_ZERO

    def __init__(
        self,
        T: float,
        Tcs: list[float],
        Pcs: list[float],
        dipoles: list[float],
        rgs: list[float],
        etas: list[float],
        cas_list: list[str],
    ) -> None:
        self.T = float(T)
        self.Tcs = list(Tcs)
        self.Pcs = list(Pcs)  # Pa
        self.dipoles = list(dipoles)  # Debye
        self.rgs = list(rgs)  # Angstrom
        self.etas = list(etas)
        self.cas_list = list(cas_list)
        self._params = self._characteristic_params()

    # -- characteristic (T-independent) parameter chain --------------------

    def _characteristic_params(self) -> list[dict[str, float]]:
        n = len(self.cas_list)
        pure: list[dict[str, float]] = []
        for i in range(n):
            pure.append(self._pure_params(i, self.etas[i]))
        params: list[dict[str, float]] = []
        for i in range(n):
            for j in range(n):
                if i == j:
                    params.append(pure[i])
                else:
                    params.append(self._cross_params(i, j, pure))
        return params

    def _pure_params(self, i: int, eta: float) -> dict[str, float]:
        """Pure characteristic parameters (A-16..A-23; Fortran 3-18..3-24)."""
        tc = self.Tcs[i]
        pc_bar = self.Pcs[i] / 1e5
        mu = self.dipoles[i]
        r_g = self.rgs[i]
        # (3-21) / A-18: pseudo-acentric factor from the radius of gyration
        omega = r_g * (r_g * (-0.001366 * r_g + 0.02096) + 0.006026)
        # (3-18) / A-19: standard form minus the association-removal term
        eps_p = tc * (0.748 + 0.91 * omega) - tc * 0.4 * eta / (2.0 + 20.0 * omega)
        # (A-20): sigma cubed, Pc in bar (Fortran constant 2.4507)
        sig_p3 = (2.4507 - omega) ** 3 * tc / pc_bar
        pn = 16.0 + 400.0 * omega  # A-22
        p1 = pn / (pn - 6.0)
        p2 = 3.0 / (pn - 6.0)
        cc = 2.882 - 1.882 * omega / (0.03 + omega)  # A-23
        if mu >= 1.45:  # A-21b: angle-averaging correction
            xi = 1.7941e7 * mu * mu / (cc * eps_p * sig_p3 * sig_p3 * tc)
            # Fortran's expanded second-order form of A-16
            eps = eps_p * (1.0 - xi * p1 + p1 * p1 * (1.0 + p1) * xi * xi / 2.0)
            sig3 = sig_p3 * (1.0 + xi * p2)  # A-17
        else:  # A-21a
            eps = eps_p
            sig3 = sig_p3
        return {"eps": eps, "sig3": sig3, "omega": omega, "eta": eta}

    def _cross_params(self, i: int, j: int, pure: list[dict[str, float]]) -> dict[str, float]:
        """Cross characteristic parameters (A-24..A-29)."""
        pi, pj = pure[i], pure[j]
        omega = 0.5 * (pi["omega"] + pj["omega"])  # A-26
        eps_p = 0.7 * math.sqrt(pi["eps"] * pj["eps"]) + 0.6 / (1.0 / pi["eps"] + 1.0 / pj["eps"])  # A-27
        sig3_p = math.sqrt(pi["sig3"] * pj["sig3"])  # A-28 (on sigma cubed)
        mu_i, mu_j = self.dipoles[i], self.dipoles[j]
        xi = 0.0
        if mu_i >= 2.0 and mu_j == 0.0:  # A-29a
            xi = mu_i * mu_i * pj["eps"] ** 2 * math.sqrt(pj["sig3"]) ** 4 / (pi["eps"] * pi["sig3"])
        elif mu_j >= 2.0 and mu_i == 0.0:  # A-29b
            xi = mu_j * mu_j * pi["eps"] ** 2 * math.sqrt(pi["sig3"]) ** 4 / (pj["eps"] * pj["sig3"])
        n = 16.0 + 400.0 * omega
        eps = eps_p * (1.0 - xi * n / (n - 6.0))  # A-24
        sig3 = sig3_p * (1.0 - 3.0 * xi / (n - 6.0))  # A-25
        return {
            "eps": eps,
            "sig3": sig3,
            "omega": omega,
            "eta": eta_for_pair(self.cas_list[i], self.cas_list[j]),
        }

    # -- per-pair static reduced quantities ---------------------------------

    def _pair_static(self, k: int) -> tuple[float, float, float, float, float]:
        """(b0, mu_star, A_ij, dh_ij, E_exponent) for pair slot k."""
        p = self._params[k]
        sig3 = p["sig3"]
        b0 = 1.26184 * sig3  # A-10
        i, j = divmod(k, len(self.cas_list))
        mu_i, mu_j = self.dipoles[i], self.dipoles[j]
        mu_r = 7243.8 * mu_i * mu_j / (p["eps"] * sig3)  # A-13
        if mu_r < 0.04:  # A-14a
            mu_star = mu_r
        elif mu_r < 0.25:  # A-14b
            mu_star = 0.0
        else:  # A-14c
            mu_star = mu_r - 0.25
        # The effective (piecewise-corrected) moment enters A/Delta-h: the
        # LBL report's equations 3-41/3-42 print the starred symbol, and the
        # water reference number confirms it (module docstring, conflict 1).
        a_ij = -0.3 - 0.05 * mu_star  # A-11
        dh_ij = 1.99 + 0.2 * mu_star * mu_star  # A-12
        eta = p["eta"]
        if eta < 4.5:  # A-15a
            e_exp = eta * (650.0 / (p["eps"] + 300.0) - 4.27)
        else:  # A-15b: carboxylic acids
            e_exp = eta * (42800.0 / (p["eps"] + 22400.0) - 4.27)
        return b0, mu_star, a_ij, dh_ij, e_exp

    # -- B evaluation --------------------------------------------------------

    def _B_at(self, T: float, k: int) -> float:
        """B for pair slot k (pure diagonal first) at T, in cm3/mol."""
        b0, mu_star, a_ij, dh_ij, e_exp = self._pair_static(k)
        p = self._params[k]
        t_star = T / p["eps"]  # A-8
        tsp = 1.0 / t_star - 1.6 * p["omega"]  # A-9: 1/T*'
        b = b0 * _poly_free(tsp)  # A-4
        if mu_star > 1e-19:  # Fortran threshold
            b -= b0 * mu_star * _poly_polar(tsp)  # A-5
        b += b0 * a_ij * math.exp(dh_ij / t_star)  # A-6
        eta = p["eta"]
        if eta > 0.0:  # A-7
            b += b0 * math.exp(e_exp) * (1.0 - math.exp(1500.0 * eta / T))
        return b

    # -- VirialGas protocol ---------------------------------------------------

    def to(self, T: float | None = None, **kwargs: Any) -> HaydenOConnellModel:
        if T is None:
            return self
        return HaydenOConnellModel(
            T=T,
            Tcs=self.Tcs,
            Pcs=self.Pcs,
            dipoles=self.dipoles,
            rgs=self.rgs,
            etas=self.etas,
            cas_list=self.cas_list,
        )

    def B_pures(self) -> list[float]:
        n = len(self.cas_list)
        return [self._B_at(self.T, i * (n + 1)) * 1e-6 for i in range(n)]  # cm3/mol -> m3/mol

    def B_interactions(self) -> list[list[float]]:
        n = len(self.cas_list)
        return [[self._B_at(self.T, i * n + j) * 1e-6 for j in range(n)] for i in range(n)]

    def _stencil(self, order: int, k: int, T: float) -> float:
        """Five-point central difference of order 1-3 for pair k at T."""
        h = max(0.01, 1e-4 * T)
        f_m2 = self._B_at(T - 2.0 * h, k)
        f_m1 = self._B_at(T - h, k)
        f_0 = self._B_at(T, k)
        f_p1 = self._B_at(T + h, k)
        f_p2 = self._B_at(T + 2.0 * h, k)
        if order == 1:
            return (-f_p2 + 8.0 * f_p1 - 8.0 * f_m1 + f_m2) / (12.0 * h)
        if order == 2:
            return (-f_p2 + 16.0 * f_p1 - 30.0 * f_0 + 16.0 * f_m1 - f_m2) / (12.0 * h * h)
        return (f_p2 - 2.0 * f_p1 + 2.0 * f_m1 - f_m2) / (2.0 * h**3)

    def _derivatives(self, order: int, diagonal: bool) -> list[Any]:
        n = len(self.cas_list)
        out: list[Any] = []
        for i in range(n):
            if diagonal:
                out.append(self._stencil(order, i * (n + 1), self.T) * 1e-6)
            else:
                out.append([self._stencil(order, i * n + j, self.T) * 1e-6 for j in range(n)])
        return out

    def dB_dT_pures(self) -> list[float]:
        return self._derivatives(1, True)

    def dB_dT_interactions(self) -> list[list[float]]:
        return self._derivatives(1, False)

    def d2B_dT2_pures(self) -> list[float]:
        return self._derivatives(2, True)

    def d2B_dT2_interactions(self) -> list[list[float]]:
        return self._derivatives(2, False)

    def d3B_dT3_pures(self) -> list[float]:
        return self._derivatives(3, True)

    def d3B_dT3_interactions(self) -> list[list[float]]:
        return self._derivatives(3, False)

    # zero third virial (C_model = VIRIAL_C_ZERO)
    def C_pures(self) -> list[float]:
        return [0.0] * len(self.cas_list)

    def C_interactions(self) -> list[list[float]]:
        n = len(self.cas_list)
        return [[0.0] * n for _ in range(n)]

    def dC_dT_pures(self) -> list[float]:
        return [0.0] * len(self.cas_list)

    def dC_dT_interactions(self) -> list[list[float]]:
        n = len(self.cas_list)
        return [[0.0] * n for _ in range(n)]

    def d2C_dT2_pures(self) -> list[float]:
        return [0.0] * len(self.cas_list)

    def d2C_dT2_interactions(self) -> list[list[float]]:
        n = len(self.cas_list)
        return [[0.0] * n for _ in range(n)]

    def d3C_dT3_pures(self) -> list[float]:
        return [0.0] * len(self.cas_list)

    def d3C_dT3_interactions(self) -> list[list[float]]:
        n = len(self.cas_list)
        return [[0.0] * n for _ in range(n)]


def hoc_vapour_phase(cas_list: list[str], constants: Any, correlations: Any) -> VirialGas:
    """The Hayden-O'Connell vapour phase over exactly this component set."""
    rgs = [rg_of(cas) for cas in cas_list]
    pure_etas = [eta_for_pair(cas, cas) for cas in cas_list]
    refuse_acid_strength(cas_list, pure_etas)
    model = HaydenOConnellModel(
        T=298.15,
        Tcs=list(constants.Tcs),
        Pcs=list(constants.Pcs),
        dipoles=list(constants.dipoles),
        rgs=rgs,
        etas=pure_etas,
        cas_list=cas_list,
    )
    # VirialGas requires composition at construction; the flasher rebases it.
    return VirialGas(
        model=model,
        HeatCapacityGases=correlations.HeatCapacityGases,
        zs=[1.0 / len(cas_list)] * len(cas_list),
    )


def model_params(cas_list: list[str], constants: Any, rgs: list[float]) -> list[dict[str, float]]:
    """Characteristic parameters per pair slot (exposed for tests)."""
    m = HaydenOConnellModel(
        T=298.15,
        Tcs=list(constants.Tcs),
        Pcs=list(constants.Pcs),
        dipoles=list(constants.dipoles),
        rgs=rgs,
        etas=[eta_for_pair(cas, cas) for cas in cas_list],
        cas_list=cas_list,
    )
    return m._params


def tsonopoulos_fallback_phase(constants: Any, correlations: Any) -> VirialGas:
    """The declared Tsonopoulos-extended fallback vapour phase.

    The Nothnagel (1973) b/K parameter table is not available from any open
    source, so the ``nothnagel`` rows build the installed Tsonopoulos-extended
    second-virial model instead; the catalogue row name identifies it.
    """
    n_components = len(constants.Tcs)
    model = VirialCSP(
        Tcs=list(constants.Tcs),
        Pcs=list(constants.Pcs),
        Vcs=list(constants.Vcs),
        omegas=list(constants.omegas),
        B_model="VIRIAL_B_TSONOPOULOS_EXTENDED",
        cross_B_model="Tarakad-Danner",
        C_model=VIRIAL_C_ZERO,
        cross_C_model="Zeros",
    )
    # VirialGas requires composition at construction; the flasher rebases it.
    return VirialGas(
        model=model,
        HeatCapacityGases=correlations.HeatCapacityGases,
        zs=[1.0 / n_components] * n_components,
    )


def refuse_not_implemented(vapour: str) -> None:
    """Refuse unknown virial vapour option values (kept for error paths)."""
    raise ValueError(f"virial vapour model {vapour!r} is not one of {sorted(VIRIAL_VAPOURS)}")
