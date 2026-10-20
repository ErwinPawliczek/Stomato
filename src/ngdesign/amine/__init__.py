"""Amine-treatment chemistry modules (electrolyte models).

Chemistry lives in plain modules here; the registered amine unit plugins
(``mdea_absorber`` / ``mdea_regenerator``) import from it.
Ionic species never leave these modules: stream ``z`` stays molecular.
"""
