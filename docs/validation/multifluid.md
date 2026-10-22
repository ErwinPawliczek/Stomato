# multifluid — Multi-fluid Helmholtz (teqp CoolProp library)

family `saft` · status **experimental** · adapter `ngdesign.thermo.teqp_bridge:MultifluidThermo`.

## Applicability (Carlson 1996)

- component classes: hydrocarbon, light_gas, inert, acid_gas
- polar: False · electrolyte: False
- T window: 60–800 K · P window: 100–1e+08 Pa
- phases: V, L

## Parameters

- source: teqp multifluid over the CoolProp fluid library (data/thermo_params/saft/pure.yaml alias table)
- provenance: fluid names resolve to teqp's bundled CoolProp-32 fluid library (IAPWS, NIST REFPROP-derived and GERG Helmholtz formulations as shipped by teqp 0.23.2); binary pairs and departure functions from teqp's bundled mixture files. Water-bearing feeds are refused — teqp's bundled pair file has no water interaction data (bare Lorentz-Berthelot), which puts the slice dew 2x above the CoolProp with-water value

## L0 self-consistency

| check | result | worst | measured |
| --- | --- | --- | --- |

## L1/L2 reference-case outcomes

None yet — validation case ids arrive with the data tasks (T-11..T-13).

## References

- teqp 0.23 (Thol & Bell), https://teqp.readthedocs.io, MIT licence
- Huber, Lemmon, Diky, Smith & Brunner, "ThermoData Engine (TDE103b)", J. Chem. Eng. Data 61 (2016) 3382-3395 (CoolProp fluid data lineage)
