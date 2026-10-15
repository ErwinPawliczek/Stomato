"""Electrolyte-NRTL speciation for CO2 + MDEA/MEA + H2O (CO2-only service).

Second amine chemistry, per the wave-3 spec: a from-scratch Long-Li-Chen
electrolyte-NRTL (e-NRTL) speciation module, opt-in through the amine units'
``equilibrium_model`` parameter. Like the Kent-Eisenberg module
(``ngdesign.units.mdea_equilibrium``), chemistry lives at unit level: the
thermodynamic package never sees the ionic species, the unit owns the
equilibrium solve, and the stream ``z`` stays molecular -- ions never leave
this module. H2S is deliberately unsupported (see ``_reject_h2s``): no
citable e-NRTL parameter set covers it, so sour-gas loading stays
Kent-Eisenberg.

Model
-----
True liquid species: H2O, amine (MDEA or MEA), molecular CO2, AmineH+,
H+, OH-, HCO3-, CO3--, and MEACOO- for MEA (carbamate). Excess Gibbs energy
in the Long-Li-Chen / Chen e-NRTL form:

    g*ex/RT = g*ex_PDH/RT + g*ex_lc/RT

1. Long range (electrostatics among ions), Pitzer-Debye-Hueckel on the
   molality base -- the standard closed form (Pitzer, 1973, J. Phys. Chem.
   77:268; the molality-base DH term used across the electrolyte-NRTL
   literature):

       ln gamma_i = -A_phi z_i^2 [ sqrt(I_m)/(1 + b sqrt(I_m))
                                   + (2/b) ln(1 + b sqrt(I_m)) ]

   with I_m the molality ionic strength (mol/kg water) and b = 1.2 the
   published Pitzer coefficient. The molality base is chosen deliberately:
   the chemical equilibria below (Edwards et al. / NeqSim constants, shared
   with mdea_equilibrium.py) live on the molal-1 standard state, so the
   activity coefficients must live there too -- one consistent scale, no
   standard-state conversion chain. (The wave-3 open-access reference,
   Vivier, Kamalpour & Mehablia, "Thermodynamics of CO2-MDEA using eNRTL
   with Differential Evolution Algorithm", J. Thermodyn. Catal. 3:114
   (2012), doi:10.4172/2157-7544.1000114, writes the same electrostatic
   term on the mole-fraction base; its standard-state conversions belong
   to the paywalled journal convention chain, so the molality-base form is
   the citable assembly here.) A_phi comes from its published definition
   (reference eq. 30), evaluated from CODATA constants and thermo-databank
   water data; the 298.15 K value is pinned to the published 0.392 by a
   test.

2. Local (short range), the e-NRTL local-composition term with like-ion
   repulsion: each molecule centers a shell over all species; each ion
   centers a shell over molecules + counter-ions. With
   G_ij = exp(-alpha tau_ij):

       g_lc/RT = sum_m X_m (sum_i X_i G_mi tau_mi) / (sum_k X_k G_km)
               + sum_c X_c (sum_m X_m G_cm tau_cm + sum_a X_a G_ac tau_ac)
                         / (sum_m X_m G_cm + sum_a X_a G_ac)
               + sum_a X_a (sum_m X_m G_am tau_am + sum_c X_c G_ca tau_ca)
                         / (sum_m X_m G_am + sum_c X_c G_ca)

   X_j are true species mole fractions, m molecules, c cations, a anions.
   Source: the reference's eq. 32 structure with its G_jm = exp(-alpha
   tau_jm) definitions, like-ion repulsion, and the anti-symmetric
   molecule-electrolyte relation tau_mc,ca = -tau_cm,ca; same form in
   Chen, Britt, Boston & Evans, 1982, AIChE J. 28(4) 588-596 and Chen &
   Evans, 1986, AIChE J. 32(3) 444-454 (the reference's eqs. [5-7]).
   Each ion's centered term carries that ion's own mole fraction, so the
   local contribution to ln gamma vanishes as the species dilutes to
   infinity -- the unsymmetric normalization the reference's standard
   states require; activity coefficients are therefore used raw (no
   separate reference-state evaluation).

   The Born ion-reference-state-transfer term (the third e-NRTL
   contribution in mixed solvents) is omitted: its parameters (solvent
   dielectric-constant databank entries for MDEA/MEA) are not openly
   available, and water is the only reference solvent in this treatment.
   Both references above state the Born term drops out for a single
   reference solvent; the residual effect is folded into the apparent
   constants below -- the same apparent-constant epistemology the
   Kent-Eisenberg module documents.

Parameter provenance (per constant)
-----------------------------------
- alpha_ij = 0.2 for every pair, and the Pitzer b = 1.2: published
  structural constants. alpha = 0.2 is the standard e-NRTL non-randomness
  factor ("The non randomness factor (alpha) is fixed at 0.2", reference
  above; also the DWSIM electrolyte-activity documentation retrieved in
  the wave-3 findings, art_tEPEk6C1). b = 1.2 is Pitzer's published
  coefficient for the molality-base form (Pitzer 1973).
- Unfitted molecule-electrolyte pairs tau_m,ca = 8, tau_ca,m = -4; all
  molecule-molecule and electrolyte-electrolyte taus 0: the published e-NRTL
  defaults ("we set all molecule-molecule and electrolyte-electrolyte binary
  parameters to zero, unless specified otherwise, and molecule-electrolyte
  binary parameters to 8 and -4 as reported in NRTL model", reference
  above; the Chen & Evans 1986 convention).
- A_phi: computed from its definition (reference eq. 30) from CODATA
  constants and water density/permittivity (IAPWS) banked in the thermo
  library; pinned to the published 0.392 at 298.15 K by a test.
- Chemical equilibria (thermodynamic constants on the molal-1 standard
  state, mol/kg): K1/K2/Kw from Edwards, Maurer, Newman & Prausnitz, 1978,
  AIChE J. 24(6) 966-976 (identical expressions to mdea_equilibrium.py);
  amine protonation Kam and (MEA) carbamate reversion Kc from NeqSim's
  AmineKentEisenberg model -- the same repo-citable constant set
  mdea_equilibrium.py carries (MDEA Kam = exp(-6.40 - 4210/T), MEA
  Kam = exp(-3.10 - 5630/T), MEA Kc = exp(3.90 - 1800/T)). The
  Kent-Eisenberg module applies these constants to mol/L concentrations
  (its documented apparent convention); this module applies them to
  molalities, their native standard state -- with gamma = 1 the two
  coincide at the dilute end and the property tests pin the cross-check.
- Henry CO2 (water-referenced, Pa.m3/mol): Versteeg & van Swaaij, 1988,
  J. Chem. Eng. Data 33, 29-34: H = 2.82e6 exp(-2044/T) -- identical to
  mdea_equilibrium.py. p_CO2 = H * c_CO2 * gamma*_CO2 with c_CO2 the
  molecular-CO2 molarity and gamma*_CO2 the unsymmetric activity
  coefficient (-> 1 at infinite dilution in water, where Henry's law is
  defined).

Honest parameter-status note (read before extending)
----------------------------------------------------
The pinned journal parameter tables -- Zhang & Chen 2011, I&EC Res. 50:163,
doi:10.1021/ie1006855 (CO2-MDEA-H2O) and Zhang, Que & Chen 2011, Fluid
Phase Equilib. 311, doi:10.1016/j.fluid.2011.08.025 (CO2-MEA-H2O) -- are
publisher-paywalled; this session's retrieval pass (five rounds, recorded
in the PR) could not obtain their row-by-row tau tables, and the open
access reference's own regressed tables do not extract unambiguously from
its PDF text layer. This module therefore ships the fully public model
STRUCTURE with the published structural constants and defaults above, and
its accuracy is asserted -- not claimed -- against published CO2 loading
anchors (tests): the NeqSim CO2 regression anchors for 50 wt% MDEA at
313.15 K (p_CO2 ~ 0.0093 bara at loading 0.10, ~0.229 bara at 0.40, the
anchors mdea_equilibrium.py carries) and NeqSim's documented MEA
engineering band (30 wt%, 313.15 K, loading 0.5: p_CO2 within 5-30 kPa).
When publisher access to the two journal tables exists, swapping their
tau values into ``_PAIR_TAU_OVERRIDES`` is a data change, not a model
change.

Solve method
------------
With activity coefficients fixed, the speciation algebra is the
Kent-Eisenberg module's, evaluated on molalities (mol/kg water): closed-form
carbon distribution for the tertiary amine (MDEA), a nested bracketed carbon
root for the secondary amine (MEA, carbamate sink), and a bracketed Brent
root on ln([H+]) for the charge balance. Electroneutrality counts charges on
concentrations (molalities), not activities. A damped outer fixed point
iterates (gamma <-> speciation) to convergence; gamma comes from numerical
differentiation of n g_ex/RT for the local term plus the closed-form PDH
term, which keeps one Gibbs-energy implementation as the single source of
truth for the local part.

With every gamma forced to 1 the module reproduces the Kent-Eisenberg
module's speciation (same constants, same algebra, molality-vs-molarity
scaling aside) -- a tested cross-check against the merged, CI-green
implementation.

All public quantities are SI: T in K, molarity in mol/m3, pressures in Pa
absolute. Internally the chemistry runs on molalities (mol/kg water) and
converts at the API boundary. Pure functions; deterministic; no I/O.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial

from ngdesign.units.mdea_equilibrium import _brent_root

__all__ = [
    "AMINES",
    "EnrtlChemistry",
    "EnrtlSpeciation",
    "equilibrium_loadings",
    "equilibrium_partial_pressures",
]

#: Max supported CO2 loading, mol/mol amine (the KE module's window).
_MAX_LOADING = 1.5

#: Bracket for the charge-balance root find on ln([H+]) (KE module's bracket,
#: molalities span the same decades).
_LN_H_LO = -34.0
_LN_H_HI = 16.0

#: e-NRTL non-randomness factor, all pairs. Published constant (see
#: "Parameter provenance" in the module docstring): alpha = 0.2.
_ALPHA = 0.2

#: Published e-NRTL closest-approach parameter for the long-range term
#: (report nomenclature, "closest approach parameter, 14.9"; the same 14.9
#: the wave-3 findings attribute to DWSIM's public model documentation).
_RHO = 14.9

#: Published e-NRTL molecule-electrolyte default pair: tau(molecule, ion
#: pair) = 8, tau(ion pair, molecule) = -4, with the anti-symmetry
#: tau_mc,ca = -tau_cm,ca. Molecule-molecule and electrolyte-electrolyte
#: pairs default to 0. Provenance: module docstring, "Parameter provenance".
_DEFAULT_TAU_M_CA = 8.0
_DEFAULT_TAU_CA_M = -4.0

#: Water molar mass, kg/mol (thermo/chemicals databank value for H2O; used
#: to convert the flashed water molarity to kg water per litre).
_M_WATER_KG_MOL = 0.01801528

#: CODATA 2018 constants for the A_phi definition (reference eq. 30).
_N_AVOGADRO = 6.02214076e23  # 1/mol
_E_CHARGE = 1.602176634e-19  # C
_K_BOLTZMANN = 1.380649e-23  # J/K
_EPS_0 = 8.8541878128e-12  # F/m, vacuum permittivity

#: Damped outer fixed point (gamma <-> speciation) controls.
_GAMMA_DAMP = 0.5
_GAMMA_MAX_ITER = 120
_GAMMA_TOL = 1e-9

#: Validity window (absorber/regenerator service, mirroring the KE module).
_T_MIN_K = 290.0
_T_MAX_K = 400.0

#: True species indices. Molecules 0-2, cations 3-4, anions 5+.
_H2O, _AMINE, _CO2 = 0, 1, 2
_AMINEH, _H, _OH, _HCO3, _CO3, _CARB = 3, 4, 5, 6, 7, 8

_MOLECULE_NAMES = {_H2O: "H2O", _AMINE: "Amine", _CO2: "CO2"}


@dataclass(frozen=True)
class EnrtlChemistry:
    """Per-amine chemistry and e-NRTL pair structure.

    ``carbamate`` carries the (a, b) pair of the apparent carbamate
    reversion constant Kc = exp(a + b/T) for MEA (secondary amine); MDEA
    (tertiary) forms no carbamate. Provenance for every constant is in the
    module docstring; the values equal the Kent-Eisenberg module's
    repo-citable set so the two models share chemistry and differ only in
    the activity treatment.
    """

    name: str
    molar_mass_kg_mol: float
    liquid_density_kg_m3: float
    kam_a: float
    kam_b: float
    carbamate: tuple[float, float] | None

    def kam(self, T: float) -> float:
        """Apparent amine dissociation (protonation) constant, mol/kg."""
        return math.exp(self.kam_a - self.kam_b / T)

    def kc(self, T: float) -> float | None:
        """Apparent carbamate reversion constant, mol/kg (tertiary amines: None)."""
        if self.carbamate is None:
            return None
        a, b = self.carbamate
        return math.exp(a + b / T)


MDEA_CHEMISTRY = EnrtlChemistry(
    name="MDEA",
    molar_mass_kg_mol=0.10514,
    liquid_density_kg_m3=1090.0,
    kam_a=-6.40,
    kam_b=4210.0,
    carbamate=None,
)
MEA_CHEMISTRY = EnrtlChemistry(
    name="MEA",
    molar_mass_kg_mol=0.06108,
    liquid_density_kg_m3=1018.0,
    kam_a=-3.10,
    kam_b=5630.0,
    carbamate=(3.90, -1800.0),
)

#: Supported e-NRTL amine chemistries, by component name. CO2-only service:
#: no H2S parameter set exists (module docstring, "Honest parameter-status").
#: Molar masses and liquid densities at 298.15 K are the thermo/chemicals
#: databank values for the pure components (used only for the ideal-mixing
#: water-content estimate at the API boundary).
AMINES: dict[str, EnrtlChemistry] = {
    MDEA_CHEMISTRY.name: MDEA_CHEMISTRY,
    MEA_CHEMISTRY.name: MEA_CHEMISTRY,
}


def _chemistry(amine: str) -> EnrtlChemistry:
    """Look up a supported e-NRTL amine chemistry by component name."""
    chem = AMINES.get(amine)
    if chem is None:
        supported = ", ".join(sorted(AMINES))
        raise ValueError(f"unsupported amine {amine!r}; supported amines: {supported}")
    return chem


def _reject_h2s(h2s_loading: float, p_h2s: float) -> None:
    """Refuse H2S service with the evidence-based scope error.

    No citable e-NRTL parameter set covers CO2+H2S amine service: the
    molecule-electrolyte interactions for HS-/S-- are absent from the
    published open sets (wave-3 findings art_tEPEk6C1: "no citable set
    exists"), so any H2S number this module produced would be fabricated.
    Sour-gas loading stays on the Kent-Eisenberg model.
    """
    if h2s_loading > 0.0 or p_h2s > 0.0:
        raise ValueError(
            "equilibrium_model='enrtl' supports CO2-only service: no citable "
            "electrolyte-NRTL parameter set exists for H2S amine chemistry "
            "(Zhang-Chen 2011 and Zhang-Que-Chen 2011 cover CO2 only), so H2S "
            f"loading (got {h2s_loading} mol/mol) or p_H2S (got {p_h2s} Pa) is "
            "rejected rather than estimated. Use equilibrium_model="
            "'kent_eisenberg' (the default) for sour-gas service."
        )


# --- Equilibrium constants (identical expressions to mdea_equilibrium.py) ---


def _co2_k1(T: float) -> float:
    """CO2 + H2O <=> H+ + HCO3-, mol/kg (Edwards et al. 1978)."""
    return math.exp(-12092.1 / T - 36.7816 * math.log(T) + 235.482)


def _co2_k2(T: float) -> float:
    """HCO3- <=> H+ + CO3--, mol/kg (Edwards et al. 1978)."""
    return math.exp(-12431.7 / T - 35.4819 * math.log(T) + 220.067)


def _water_kw(T: float) -> float:
    """H2O <=> H+ + OH-, (mol/kg)^2 (Edwards et al. 1978)."""
    return math.exp(-13445.9 / T - 22.4773 * math.log(T) + 140.932)


def _henry_co2(T: float) -> float:
    """CO2 Henry constant in water, Pa.m3/mol (Versteeg & van Swaaij 1988)."""
    return 2.82e6 * math.exp(-2044.0 / T)


# --- Water data for A_phi (thermo databank; pure functions at the API edge) ---


def _a_phi(T: float) -> float:
    """Pitzer-Debye-Hueckel A_phi for water at T, from its definition.

    Published form (reference eq. 30, cgs): A_phi = (1/3) (2 pi N0 d_w /
    1000)^(1/2) (e^2/(D_w k T))^(3/2) with d_w in g/cm3 and e in esu. SI
    translation used here: the Bjerrum length l_B = e^2/(4 pi eps0 D_w k T)
    in cm replaces the esu e^2/(D k T), and the density prefactor runs on
    d_w in g/cm3 / 1000 -- reproducing the published 298.15 K value 0.392
    (pinned by a test). Water density and dielectric constant (IAPWS
    permittivity) come from the thermo library databank, the repo's banked
    reference data.
    """
    from thermo import Chemical  # late import: databank access at the edge

    water = Chemical("water", T=T, P=101325.0)
    d_w_g_cm3 = float(water.rho) / 1000.0  # kg/m3 -> g/cm3
    eps_w = float(water.permittivity)  # relative dielectric constant (IAPWS)
    l_b_cm = (_E_CHARGE**2) / (4.0 * math.pi * _EPS_0 * eps_w * _K_BOLTZMANN * T) * 100.0
    return float((1.0 / 3.0) * math.sqrt(2.0 * math.pi * _N_AVOGADRO * d_w_g_cm3 / 1000.0) * l_b_cm**1.5)


# --- Species layout ---


@dataclass(frozen=True)
class _Species:
    """True-species layout for one amine system."""

    charges: tuple[float, ...]
    n_species: int
    molecules: tuple[int, ...]
    cations: tuple[int, ...]
    anions: tuple[int, ...]


def _species(chem: EnrtlChemistry) -> _Species:
    """Species layout: H2O, amine, CO2, AmineH+, H+, OH-, HCO3-, CO3--, [carbamate]."""
    if chem.carbamate is None:
        charges: tuple[float, ...] = (0.0, 0.0, 0.0, 1.0, 1.0, -1.0, -1.0, -2.0)
        anions: tuple[int, ...] = (_OH, _HCO3, _CO3)
    else:
        charges = (0.0, 0.0, 0.0, 1.0, 1.0, -1.0, -1.0, -2.0, -1.0)
        anions = (_OH, _HCO3, _CO3, _CARB)
    molecules = (_H2O, _AMINE, _CO2)
    cations = (_AMINEH, _H)
    return _Species(
        charges=charges, n_species=len(charges), molecules=molecules, cations=cations, anions=anions
    )


# --- Activity coefficients ---
#
# Assembled per the open NETL report (Akula, Eslick, Bhattacharyya & Miller,
# "A Modified Electrolyte NRTL Model with Analytical Excess Enthalpy:
# Application to the MEA-H2O-CO2 System", OSTI 1963954, open full text) and
# the Song-Chen symmetric e-NRTL structure it implements:
#
#   ln gamma_i = ln gamma_i^PDH (mole-fraction base, closed form)
#              + ln gamma_i^lc - ln gamma_i^lc(infinite dilution)
#
# The local-term infinite-dilution subtraction is the report's eq. (A2)/(B3)
# unsymmetric device: it cancels the constant molecule-ion interaction
# carried by every ion's local chemical potential, so gamma* -> 1 for every
# solute at infinite dilution in the solvent. The PDH term vanishes at
# dilution on its own and needs no subtraction.
#
# Basis note (the one scale decision that must not drift): the PDH runs on
# the MOLE-FRACTION base with A_x -- NOT the molality-base A_phi. The exact
# basis relation at the Debye-Hueckel limiting law, A_x sqrt(I_x) =
# A_phi sqrt(I_m), fixes A_x = A_phi(T) * sqrt(n_solution per kg water);
# at pure water this reproduces the published mole-fraction A_x (the
# report's eq. A6 evaluates to the same number, A_phi*sqrt(1000/M_w) =
# 2.92 at 298.15 K). Using the molality A_phi inside the mole-fraction
# form under-counts ln gamma by sqrt(55.5) and was the numerical root
# cause of the carbonate over-stabilization in the first draft.


def _mole_fraction_ionic_strength(mole_fractions: tuple[float, ...], sp: _Species) -> float:
    """Mole-fraction ionic strength I_x = 1/2 sum z_i^2 x_i over ions (eq A5)."""
    acc = 0.0
    for i, z in enumerate(sp.charges):
        if z != 0.0:
            acc += z * z * mole_fractions[i]
    return 0.5 * acc


def _effective_mole_fractions(mole_fractions: tuple[float, ...], sp: _Species) -> tuple[float, ...]:
    """Effective mole fractions X_i = x_i for molecules, x_i |z_i| for ions (eq B5)."""
    return tuple(x * abs(z) if z != 0.0 else x for x, z in zip(mole_fractions, sp.charges, strict=True))


def _pair_tau(chem: EnrtlChemistry, c: int, a: int, m: int, T: float) -> tuple[float, float]:
    """(tau(molecule -> pair), tau(pair -> molecule)) for pair (c, a), shell molecule m.

    Fitted pair (report Table 6, parameters E1-E4, tau = C + D/T per the
    report's Table 1 rows 3-4): H2O <-> (MEAH+, MEACOO-) for MEA:

        tau(H2O -> pair) = 18.588 - 1533.6 / T     (E1 = 18.588, E3 = -1533.6)
        tau(pair -> H2O) = -7.056 + 1224.1 / T     (E2 = -7.056, E4 = 1224.1)

    Every other molecule-ion pair runs the published structural defaults
    tau(m -> ca) = 8, tau(ca -> m) = -4 (C only, D = 0), the e-NRTL
    unfitted-pair convention of the report's Table 2 / Aspen defaults.
    """
    if chem.carbamate is not None and c == _AMINEH and a == _CARB and m == _H2O:
        return (18.588 - 1533.6 / T, -7.056 + 1224.1 / T)
    return (_DEFAULT_TAU_M_CA, _DEFAULT_TAU_CA_M)


def _molecule_pair_tau(chem: EnrtlChemistry, i: int, j: int, T: float) -> float:
    """tau(i-centered, j-shell) for molecule-molecule pairs (report Table 1 rows 1-2).

    Fitted pair (per-constant provenance in the module docstring): the
    MEA(1) + H2O(2) binary NRTL parameters of Zhang, Que & Chen 2011 as
    tabulated in the report's Table 4 (row W4), tau = A + B/T:

        tau(MEA-center, H2O-shell) = 1.5201 - 910.3 / T   (A12, B12)
        tau(H2O-center, MEA-shell) = 0.1559 + 110.8 / T   (A21, B21)

    All other molecule-molecule pairs (H2O-CO2, amine-CO2, MDEA-H2O) carry
    the published default 0.
    """
    if chem.carbamate is not None and i == _AMINE and j == _H2O:
        return 1.5201 - 910.3 / T
    if chem.carbamate is not None and i == _H2O and j == _AMINE:
        return 0.1559 + 110.8 / T
    return 0.0


def _g_ex_lc(mole_fractions: tuple[float, ...], sp: _Species, chem: EnrtlChemistry, T: float) -> float:
    """g*ex_lc/RT: the symmetric e-NRTL local-composition term (report eq. A3).

    Three cell types over effective mole fractions X_i (eq B5): a molecule
    center (shell over molecules + cations + anions), a cation center
    (molecules + anions, no like ions), an anion center (molecules +
    cations). The ion-molecule Boltzmann factors are the charge-fraction-
    mixed ION-PAIR interactions of the report's Table 1 rows 7-12: a
    molecule sees the pair (c, a) through G = exp(-alpha tau(m -> ca)); a
    cation center sees molecule m through the anion-mixed pair factor
    G_cm = sum_a Y_a G_(ca,m) with the log-mixing rule
    tau_cm = -sum_a Y_a ln(G_(ca,m))/alpha; anion centers mirror with the
    cation mixing (row 8). Like-ion slots carry the published
    electrolyte-electrolyte default tau = 0 (G = 1).
    """
    total = sum(mole_fractions)
    if total <= 0.0:
        return 0.0
    x = tuple(n / total for n in mole_fractions)
    eff = _effective_mole_fractions(x, sp)

    pair_total = sum(eff[c] for c in sp.cations)
    acc = 0.0
    if pair_total <= 0.0:
        # Ion-free solvent: plain NRTL on the molecules (fitted MEA-H2O pair
        # only, everything else 0).
        for m in sp.molecules:
            num = den = 0.0
            for m2 in sp.molecules:
                t = _molecule_pair_tau(chem, m, m2, T)
                g = math.exp(-_ALPHA * t)
                num += eff[m2] * g * t
                den += eff[m2] * g
            if den > 0.0:
                acc += eff[m] * num / den
        return acc

    y_c = {c: eff[c] / pair_total for c in sp.cations}
    y_a = {a: eff[a] / pair_total for a in sp.anions}

    def mixed_from_molecule(m: int) -> tuple[float, float]:
        """(G_mc, tau_mc): molecule m's slot over cations/anions (rows 9-10).

        G_mc = sum_a Y_a G_(m,ca); tau_mc = -ln(G_mc)/alpha. The anion-slot
        mirror (row 10) mixes the same pair factors over cations.
        """
        g_mix = 0.0
        ln_mix = 0.0
        for a in sp.anions:
            if y_a[a] <= 0.0:
                continue
            t = _pair_tau(chem, sp.cations[0], a, m, T)[0]
            g = math.exp(-_ALPHA * t)
            g_mix += y_a[a] * g
            ln_mix += y_a[a] * math.log(g)
        return g_mix, -ln_mix / _ALPHA

    def mixed_to_molecule(c: int, m: int) -> tuple[float, float]:
        """(G_cm, tau_cm): cation c's slot over molecule m (row 7).

        G_cm = sum_a Y_a G_((c,a),m); tau_cm = -ln(G_cm)/alpha.
        """
        g_mix = 0.0
        ln_mix = 0.0
        for a in sp.anions:
            if y_a[a] <= 0.0:
                continue
            t = _pair_tau(chem, c, a, m, T)[1]
            g = math.exp(-_ALPHA * t)
            g_mix += y_a[a] * g
            ln_mix += y_a[a] * math.log(g)
        return g_mix, -ln_mix / _ALPHA

    # Molecule-centered cells.
    for m in sp.molecules:
        num = den = 0.0
        for m2 in sp.molecules:
            t = _molecule_pair_tau(chem, m, m2, T)
            g = math.exp(-_ALPHA * t)
            num += eff[m2] * g * t
            den += eff[m2] * g
        g_mc, tau_mc = mixed_from_molecule(m)
        num += sum(eff[c] for c in sp.cations) * g_mc * tau_mc
        den += sum(eff[c] for c in sp.cations) * g_mc
        g_ma, tau_ma = g_mc, tau_mc  # rows 9-10 share the mixed pair factor
        num += sum(eff[a] for a in sp.anions) * g_ma * tau_ma
        den += sum(eff[a] for a in sp.anions) * g_ma
        if den > 0.0:
            acc += eff[m] * num / den

    # Cation-centered cells: molecules (mixed pair factors) + anions (G = 1).
    for c in sp.cations:
        num = den = 0.0
        for m in sp.molecules:
            g_cm, tau_cm = mixed_to_molecule(c, m)
            num += eff[m] * g_cm * tau_cm
            den += eff[m] * g_cm
        num += sum(eff[a] for a in sp.anions) * 1.0 * 0.0
        den += sum(eff[a] for a in sp.anions)
        if den > 0.0:
            acc += eff[c] * num / den

    # Anion-centered cells: molecules (mixed pair factors) + cations (G = 1).
    for a in sp.anions:
        num = den = 0.0
        for m in sp.molecules:
            # Row 8 mirror: mix the pair factors over cations.
            g_mix = ln_mix = 0.0
            for c in sp.cations:
                if y_c[c] <= 0.0:
                    continue
                t = _pair_tau(chem, c, a, m, T)[1]
                g = math.exp(-_ALPHA * t)
                g_mix += y_c[c] * g
                ln_mix += y_c[c] * math.log(g)
            g_am = g_mix
            tau_am = -ln_mix / _ALPHA
            num += eff[m] * g_am * tau_am
            den += eff[m] * g_am
        num += sum(eff[c] for c in sp.cations) * 1.0 * 0.0
        den += sum(eff[c] for c in sp.cations)
        if den > 0.0:
            acc += eff[a] * num / den

    return acc


def _ln_gamma_from_energy(
    energy: Callable[[tuple[float, ...]], float],
    mole_fractions: tuple[float, ...],
    n_species: int,
) -> tuple[float, ...]:
    """Symmetric-convention ln gamma_i of an intensive g(X) per mole.

    Chain rule under n_i -> n_tot scaling: ln gamma_i = g + D_i - sum_j
    X_j D_j, with D_j the directional derivative of g along the j-th
    simplex vertex (x_j scaled by 1+-h, renormalized). Multiplicative
    perturbations keep every ratio-type mixing weight invariant, so no
    1/total trace singularity can appear; absent species get a one-sided
    additive probe (finitely perturbs the mixing weights).
    """
    h = 1e-6

    def directional(j: int) -> float:
        x_j = mole_fractions[j]
        if x_j > 0.0:
            up = tuple(v * (1.0 + h if k == j else 1.0) for k, v in enumerate(mole_fractions))
            down = tuple(v * (1.0 - h if k == j else 1.0) for k, v in enumerate(mole_fractions))
            up = tuple(v / sum(up) for v in up)
            down = tuple(v / sum(down) for v in down)
            return (energy(up) - energy(down)) / (2.0 * h)
        add = 1e-7
        up = tuple(
            v / (1.0 + add) if k != j else (v + add) / (1.0 + add) for k, v in enumerate(mole_fractions)
        )
        return (energy(up) - energy(mole_fractions)) / add

    g0 = energy(mole_fractions)
    dirs = [directional(j) for j in range(n_species)]
    weighted = sum(x * d for x, d in zip(mole_fractions, dirs, strict=True))
    return tuple(g0 + d - weighted for d in dirs)


def _pdh_g_energy(mole_fractions: tuple[float, ...], sp: _Species, a_x: float) -> float:
    """g*ex,LR/RT: the Pitzer-Debye-Hueckel long-range energy (report eq. A4).

    g = -(4 A_x I_x / rho) ln(1 + rho sqrt(I_x)) with the mole-fraction
    ionic strength I_x (eq A5) and the published closest-approach parameter
    rho = 14.9. A_x enters as an argument so its solvent-composition
    dependence is handled by the caller.
    """
    i_x = _mole_fraction_ionic_strength(mole_fractions, sp)
    if i_x <= 0.0:
        return 0.0
    return -(4.0 * a_x * i_x / _RHO) * math.log(1.0 + _RHO * math.sqrt(i_x))


def _reference_local_gamma(
    sp: _Species, chem: EnrtlChemistry, T: float, solvent_like: tuple[float, ...]
) -> tuple[float, ...]:
    """Local ln gamma at infinite dilution (the report's eq. A2/B9 subtraction).

    ``solvent_like`` is the reference solvent mole vector (pure water for
    the ionic aqueous reference, eq B9; the current water+amine solvent mix
    for the CO2 Henry component, eq B10). Solutes enter at a trace mole
    fraction each; the local ln gamma is evaluated there and later
    subtracted species-wise, cancelling the constant molecule-ion
    interaction so gamma* -> 1 at dilution.
    """
    trace = 1e-9
    moles = [0.0] * sp.n_species
    for i, base in enumerate(solvent_like):
        moles[i] = base
    for i in range(sp.n_species):
        if sp.charges[i] != 0.0 or i == _CO2:
            moles[i] += trace
    total = sum(moles)
    x_ref = tuple(m / total for m in moles)
    return _ln_gamma_from_energy(lambda x: _g_ex_lc(x, sp, chem, T), x_ref, sp.n_species)


def _gamma_star(
    mole_fractions: tuple[float, ...],
    sp: _Species,
    chem: EnrtlChemistry,
    T: float,
) -> tuple[float, ...]:
    """Unsymmetric activity coefficients gamma*_i (report eq. 3, Born omitted).

    Solutes (ions, molecular CO2): ln gamma* = ln gamma^PDH(mole-fraction
    base, A_x) + ln gamma^lc - ln gamma^lc(infinite dilution in the
    reference solvent). Solvents (water, amine): symmetric convention, the
    raw local term. The PDH vanishes at dilution and needs no subtraction;
    the local subtraction is the report's eq. A2/B3/B9 device. The Born
    ion-reference-transfer term is omitted (module docstring, "Honest
    parameter-status note").
    """
    x_water = max(mole_fractions[_H2O], 1e-9)
    n_total_per_kg_water = 1.0 / (x_water * _M_WATER_KG_MOL)
    a_x = _a_phi(T) * math.sqrt(n_total_per_kg_water)
    pdh = _ln_gamma_from_energy(lambda x: _pdh_g_energy(x, sp, a_x), mole_fractions, sp.n_species)
    lc = _ln_gamma_from_energy(lambda x: _g_ex_lc(x, sp, chem, T), mole_fractions, sp.n_species)

    # Ionic aqueous reference: trace ions in pure water (eq B9).
    water_ref = [0.0] * sp.n_species
    water_ref[_H2O] = 1.0
    ref_aq = _reference_local_gamma(sp, chem, T, tuple(water_ref))
    # CO2 Henry-component reference: trace CO2 in the current solvent mix
    # (eq B10) -- water + amine only.
    solvent_mix = [0.0] * sp.n_species
    solvent_mix[_H2O] = mole_fractions[_H2O]
    solvent_mix[_AMINE] = mole_fractions[_AMINE]
    ref_mix = _reference_local_gamma(sp, chem, T, tuple(solvent_mix))

    star: list[float] = []
    for i in range(sp.n_species):
        if sp.charges[i] != 0.0:
            star.append(math.exp(pdh[i] + lc[i] - ref_aq[i]))
        elif i == _CO2:
            star.append(math.exp(pdh[i] + lc[i] - ref_mix[i]))
        else:
            star.append(math.exp(lc[i]))
    return tuple(star)


# --- Speciation (activity-corrected Kent-Eisenberg algebra, molality base) ---


@dataclass(frozen=True)
class EnrtlSpeciation:
    """Liquid true-speciation in mol/kg water plus the equilibrium CO2 pressure."""

    h: float
    amine: float
    amineh: float
    carbamate: float
    co2_free: float
    hco3: float
    co3: float
    oh: float
    gamma_co2: float
    p_co2: float


def _activity_factors(
    gamma: tuple[float, ...], T: float, chem: EnrtlChemistry
) -> tuple[float, float, float, float]:
    """Activity-corrected equilibrium factors at fixed gamma* (molality base).

    Returns (K1e, K2e, Kwe, Kame) so the KE algebra forms hold verbatim on
    molalities; water activity is the apparent-convention 1 (module
    docstring, the KE module's documented convention).
    """
    k1e = _co2_k1(T) * gamma[_CO2] / (gamma[_H] * gamma[_HCO3])
    k2e = _co2_k2(T) * gamma[_HCO3] / (gamma[_H] * gamma[_CO3])
    kwe = _water_kw(T) / (gamma[_H] * gamma[_OH])
    kame = chem.kam(T) * gamma[_AMINEH] / (gamma[_AMINE] * gamma[_H])
    return k1e, k2e, kwe, kame


def _kc_activity(gamma: tuple[float, ...], T: float, chem: EnrtlChemistry) -> float | None:
    """Activity-corrected carbamate reversion constant (MEA)."""
    kc = chem.kc(T)
    if kc is None:
        return None
    # AmineCOO- + H2O <=> Amine + HCO3- : water activity is the apparent 1.
    return kc * gamma[_CARB] / (gamma[_AMINE] * gamma[_HCO3])


def _carbon_balance_at_h(
    h: float, M_co2: float, M_A: float, k1e: float, k2e: float, kame: float, kce: float | None
) -> tuple[float, float, float, float, float]:
    """Carbon balance at fixed [H+]: free CO2 given the carbamate sink.

    Same strictly-increasing structure as the Kent-Eisenberg module's
    ``_carbon_balance_at_h`` (all quantities molalities, mol/kg water);
    bracketed Brent on hco3 in [0, M_co2]. Returns
    (co2_free, hco3, co3, amine, carbamate).
    """
    h_over_k1e = h / k1e
    k2e_over_h = k2e / h

    def carbon_residual(hco3: float) -> float:
        amine = M_A / (1.0 + h / kame + hco3 / kce) if kce is not None else M_A / (1.0 + h / kame)
        carbamate = amine * hco3 / kce if kce is not None else 0.0
        return hco3 * h_over_k1e + hco3 + hco3 * k2e_over_h + carbamate - M_co2

    if kce is None:
        # Tertiary amine: closed form (no carbamate sink).
        denom = 1.0 + k1e / h + k1e * k2e / (h * h)
        co2 = M_co2 / denom
        hco3 = k1e * co2 / h
        co3 = k2e * hco3 / h
        amine = M_A / (1.0 + h / kame)
        return co2, hco3, co3, amine, 0.0
    hco3 = _brent_root(carbon_residual, 0.0, M_co2)
    co2 = hco3 * h_over_k1e
    co3 = hco3 * k2e_over_h
    amine = M_A / (1.0 + h / kame + hco3 / kce)
    carbamate = amine * hco3 / kce
    return co2, hco3, co3, amine, carbamate


def _charge_residual_ln_h(
    ln_h: float,
    T: float,
    M_A: float,
    M_co2: float,
    gamma: tuple[float, ...],
    chem: EnrtlChemistry,
) -> float:
    """Forward residual (loading fixed): cations - anions, mol/kg water.

    Strictly increasing in [H+] (the KE module's monotonicity argument
    carries over: every anion sink decreases with [H+]).
    """
    h = math.exp(ln_h)
    k1e, k2e, kwe, kame = _activity_factors(gamma, T, chem)
    kce = _kc_activity(gamma, T, chem)
    oh = kwe / h
    co2_free, hco3, co3, amine, carbamate = _carbon_balance_at_h(h, M_co2, M_A, k1e, k2e, kame, kce)
    amineh = amine * h / kame
    return amineh + h - (oh + hco3 + 2.0 * co3 + carbamate)


def _speciate_from_loading(
    T: float, M_A: float, M_co2: float, gamma: tuple[float, ...], chem: EnrtlChemistry
) -> EnrtlSpeciation:
    """One speciation solve at fixed activity coefficients (molality base)."""
    fn: Callable[[float], float] = partial(
        _charge_residual_ln_h, T=T, M_A=M_A, M_co2=M_co2, gamma=gamma, chem=chem
    )
    ln_h = _brent_root(fn, _LN_H_LO, _LN_H_HI)
    h = math.exp(ln_h)
    k1e, k2e, kwe, kame = _activity_factors(gamma, T, chem)
    kce = _kc_activity(gamma, T, chem)
    oh = kwe / h
    co2_free, hco3, co3, amine, carbamate = _carbon_balance_at_h(h, M_co2, M_A, k1e, k2e, kame, kce)
    amineh = amine * h / kame
    return EnrtlSpeciation(
        h=h,
        amine=amine,
        amineh=amineh,
        carbamate=carbamate,
        co2_free=co2_free,
        hco3=hco3,
        co3=co3,
        oh=oh,
        gamma_co2=gamma[_CO2],
        p_co2=0.0,  # filled by the caller, which owns the water-content basis
    )


def _moles_from_speciation(
    spec: EnrtlSpeciation, chem: EnrtlChemistry
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """(molalities, mole fractions) of the true species from a speciation.

    Molalities are mol/kg water -- water enters at its pure-water molality
    1/M_w; they drive the PDH term. Mole fractions over all true species
    feed the local term.
    """
    molal: tuple[float, ...] = (
        1.0 / _M_WATER_KG_MOL,  # water: 55.5 mol per kg water
        spec.amine,
        spec.co2_free,
        spec.amineh,
        spec.h,
        spec.oh,
        spec.hco3,
        spec.co3,
    )
    if chem.carbamate is not None:
        # MEA/DEA (carbamate-forming amines) add the 9th species slot.
        molal = (*molal, spec.carbamate)
    total = sum(molal)
    return molal, tuple(m / total for m in molal)


def _solve_speciation(
    T: float,
    M_A: float,
    co2_loading: float,
    kg_water_per_l: float,
    chem: EnrtlChemistry,
) -> EnrtlSpeciation:
    """Damped outer fixed point: (gamma <-> speciation) to convergence.

    Starts from the ideal (gamma* = 1) solution -- which is the
    Kent-Eisenberg speciation on the molality base -- and iterates the
    activity coefficients. Deterministic: no randomness, fixed damping,
    fixed iteration cap.
    """
    sp_layout = _species(chem)
    gamma: tuple[float, ...] = tuple(1.0 for _ in range(sp_layout.n_species))
    spec = _speciate_from_loading(T, M_A, co2_loading * M_A, gamma, chem)
    for _ in range(_GAMMA_MAX_ITER):
        _molal, mole_fractions = _moles_from_speciation(spec, chem)
        gamma_next = _gamma_star(mole_fractions, sp_layout, chem, T)
        delta = max(abs(math.log(g) - math.log(g0)) for g, g0 in zip(gamma_next, gamma, strict=True))
        gamma = tuple(
            math.exp(_GAMMA_DAMP * math.log(g) + (1.0 - _GAMMA_DAMP) * math.log(g0))
            for g, g0 in zip(gamma_next, gamma, strict=True)
        )
        spec = _speciate_from_loading(T, M_A, co2_loading * M_A, gamma, chem)
        if delta < _GAMMA_TOL:
            break
    else:
        raise ValueError(
            f"e-NRTL speciation did not converge in {_GAMMA_MAX_ITER} iterations "
            f"(T={T} K, amine={chem.name}, loading={co2_loading} mol/mol)"
        )
    p_co2 = _henry_co2(T) * (spec.co2_free * kg_water_per_l) * 1000.0 * spec.gamma_co2
    return EnrtlSpeciation(
        h=spec.h,
        amine=spec.amine,
        amineh=spec.amineh,
        carbamate=spec.carbamate,
        co2_free=spec.co2_free,
        hco3=spec.hco3,
        co3=spec.co3,
        oh=spec.oh,
        gamma_co2=spec.gamma_co2,
        p_co2=p_co2,
    )


# --- Water content at the API boundary (ideal-mixing apparent basis) ---


def _water_molarity_from_amine(chem: EnrtlChemistry, amine_molarity_mol_m3: float) -> float:
    """Water molarity, mol/m3, from the amine molarity by ideal mixing.

    The unit flashes the liquid amine molarity (the KE module's basis);
    the molality scale additionally needs the water amount. With no solution
    density correlation in the locked data, the binary amine/water solution
    is volume-additive (documented apparent assumption, the same class of
    assumption as the KE module's constant-water basis): 1 m3 = amine
    volume + water volume, each from the pure-component databank densities.
    """
    amine_volume = amine_molarity_mol_m3 * chem.molar_mass_kg_mol / chem.liquid_density_kg_m3
    water_volume = max(1.0 - amine_volume, 0.05)
    return water_volume * 997.0 / _M_WATER_KG_MOL  # rho_water ~ 997 kg/m3 (databank, 298 K)


# --- Public API (mirrors mdea_equilibrium so units swap models cleanly) ---


def equilibrium_partial_pressures(
    T: float,
    amine_molarity_mol_m3: float,
    co2_loading: float,
    h2s_loading: float = 0.0,
    amine: str = "MDEA",
) -> tuple[float, float]:
    """Equilibrium (p_CO2, p_H2S) in Pa over amine solution at fixed loadings.

    Args:
        T: temperature in K.
        amine_molarity_mol_m3: total amine molarity of the liquid phase, mol/m3.
        co2_loading: total CO2 loading (mol CO2 per mol amine, free + bound).
        h2s_loading: must be 0 -- H2S is rejected (module docstring).
        amine: solvent amine, one of ``AMINES`` (default MDEA).
    """
    _reject_h2s(h2s_loading, 0.0)
    chem = _chemistry(amine)
    _validate_common(T, amine_molarity_mol_m3)
    if co2_loading < 0.0:
        raise ValueError(f"co2_loading must be non-negative, got {co2_loading}")
    if co2_loading > _MAX_LOADING:
        raise ValueError(f"co2_loading={co2_loading} exceeds the model window (max {_MAX_LOADING} mol/mol)")
    kg_water_per_l = _water_molarity_from_amine(chem, amine_molarity_mol_m3) * _M_WATER_KG_MOL / 1000.0
    M_A = amine_molarity_mol_m3 / 1000.0 / kg_water_per_l
    spec = _solve_speciation(T, M_A, co2_loading, kg_water_per_l, chem)
    return spec.p_co2, 0.0


def equilibrium_loadings(
    T: float,
    amine_molarity_mol_m3: float,
    p_co2: float,
    p_h2s: float = 0.0,
    amine: str = "MDEA",
) -> tuple[float, float]:
    """Equilibrium (CO2, H2S) loadings (mol/mol amine) at fixed partial pressures.

    Args:
        T: temperature in K.
        amine_molarity_mol_m3: total amine molarity of the liquid phase, mol/m3.
        p_co2: CO2 partial pressure over the solution, Pa absolute.
        p_h2s: must be 0 -- H2S is rejected (module docstring).
        amine: solvent amine, one of ``AMINES`` (default MDEA).
    """
    _reject_h2s(0.0, p_h2s)
    chem = _chemistry(amine)
    _validate_common(T, amine_molarity_mol_m3)
    if p_co2 < 0.0:
        raise ValueError(f"p_co2 must be non-negative, got {p_co2}")
    if p_co2 == 0.0:
        return 0.0, 0.0
    kg_water_per_l = _water_molarity_from_amine(chem, amine_molarity_mol_m3) * _M_WATER_KG_MOL / 1000.0
    M_A = amine_molarity_mol_m3 / 1000.0 / kg_water_per_l

    def residual(co2_loading: float) -> float:
        spec = _solve_speciation(T, M_A, co2_loading, kg_water_per_l, chem)
        return spec.p_co2 - p_co2

    loading = _brent_root(residual, 0.0, _MAX_LOADING)
    return loading, 0.0


def _validate_common(T: float, amine_molarity_mol_m3: float) -> None:
    if T <= 0.0:
        raise ValueError(f"temperature must be positive, got {T} K")
    if not _T_MIN_K <= T <= _T_MAX_K:
        raise ValueError(
            f"temperature {T} K outside the model window ({_T_MIN_K}-{_T_MAX_K} K, "
            "absorber/regenerator service)"
        )
    if amine_molarity_mol_m3 <= 0.0:
        raise ValueError(f"amine molarity must be positive, got {amine_molarity_mol_m3} mol/m3")
