# Reference data (read-only; loaded through `ngdesign.data`)

## Component registry (`components.yaml` + `ngdesign.data.component_record`, spec P1-02)

The curated slate `components.yaml` carries **identity only**: `id`, `name`, `CAS`,
and provenance notes on deliberate overrides. Physical properties are resolved at
runtime, per id, through the resolution order in
`ngdesign.data.component_record(id_or_cas_or_name)`:

1. **Curated** — a `components.yaml` id. `name` and `cas` come from the yaml;
   every physical property comes from the `chemicals` databank *by that CAS*
   (the same `ChemicalConstantsPackage.from_IDs` path the EOS flashers use, so a
   resolved record and its flasher constants can never drift apart). Deliberate
   overrides stay: `C6+` is modelled as n-hexane (the yaml note records this).
2. **Databank** — any other CAS number or chemical name known to the `chemicals`
   library (`chemicals.identifiers.CAS_from_any`, the universal resolver), e.g.
   `"n-heptane"` or `"142-82-5"`.
3. **Pseudo-component** — an id registered through
   `ngdesign.data.register_pseudo(id, name, Tb, sg)` (normal boiling point in K
   plus specific gravity, water = 1). Its constants are derived and
   provenance-graded:
   - `Tc`, `Pc` — Kesler & Lee (1976), *Hydrocarbon Processing* 55(3), 153;
   - `omega` — Lee & Kesler (1975) acentric-factor correlation
     (`chemicals.acentric.LK_omega`);
   - `mw` — Riazi & Daubert (1980), *Hydrocarbon Processing* 59(3);
   - `cas` is `None`; `formula` is unknown for pseudos.

An id no source resolves raises `ValueError` naming the key.

## Provenance format

Every resolved record carries `provenance: {property: source-string}`, one entry
per physical property (`mw`, `Tc`, `Pc`, `omega`, `Tb`, `name`, `cas`). Curated
entries use `curated` for identity and `chemicals (by curated CAS)` for
properties; databank entries use `chemicals`; pseudos cite the correlation
named above, with `user` for the supplied `Tb`/`sg`. Downstream consumers
(`ngdesign.contracts.components.Component`) must not overwrite these strings.

## Legacy shape

`ngdesign.data.components()` keeps its old contract for existing callers: the
18 curated ids keyed to `name/cas/mw/tc_K/pc_Pa/omega` (+ additive `tb_K`,
`sg`, `kind`, `provenance`), with values now resolved from the databank.
