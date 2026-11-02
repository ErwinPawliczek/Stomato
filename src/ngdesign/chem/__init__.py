"""Chemistry engine: stoichiometry, thermochemistry, equilibrium, kinetics, phases.

Sits directly above ``ngdesign.units`` so it can reuse the reaction physics in
``units/_physics`` and evaluate any registered thermo package, and it reads
species data from the cited database in ``ngdesign.data.chemdb``.
"""
