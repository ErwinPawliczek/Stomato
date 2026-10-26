# Column internals (trays/packing) (`column_internals`)

Family: **column** · P&ID symbol: `INT`

Rigour ladder: R1 provisional

## Ports

| direction | port | required | description |
|---|---|---|---|
| inlet | `inlet` | yes | solved column result (hydraulics input) |
| outlet | `outlet` | yes | hydraulics report |

## Levels

| level | status | adapter | basis |
|---|---|---|---|
| R1 | provisional | `ngdesign.units.column_shortcut.column_internals_r1:ColumnInternalsR1` | sieve-tray flooding/diameter/pressure drop (Fair capacity via the Lygeros-Magoulas 1986 fit, Seader-Henley-Roper 3rd ed. §6.6) and packed-section Stichlmair dry/wet/flood plus optional Robbins dP via fluids 1.3.1; pass-through outlet, all hydraulics in info; every result carries flooded = 1.0 when flood_fraction > 1, else 0.0 (the info contract carries floats), and dP_wet_Pa is reported only at or below the flood point (the irrigated correlation is undefined above it); HETP is not computed, hetp_m·n_stages is reported when both are given |

### R1 parameters

```yaml
additionalProperties: false
properties:
  Fpd_per_ft:
    description: packing factor, 1/ft (packing; Robbins dP is reported when given)
    type: number
  aeration_factor:
    description: aeration factor, in (0, 1] (tray, required)
    type: number
  column_diameter_m:
    description: packed-section diameter, m, > 0 (packing, required)
    type: number
  design_flood_fraction:
    description: design fraction of flood, in (0, 1) (tray design mode; give exactly
      one of diameter_m / design_flood_fraction)
    type: number
  diameter_m:
    description: column diameter, m, > 0 (tray rating mode; give exactly one of diameter_m
      / design_flood_fraction)
    type: number
  downcomer_area_frac:
    description: total area fraction taken by each downcomer, in (0, 0.5) (tray, required)
    type: number
  foaming_factor:
    description: foaming system factor, > 1 foaming, default 1 (tray)
    type: number
  hetp_m:
    description: HETP, m (packing; give both of hetp_m / n_stages or neither)
    type: number
  hole_area_frac:
    description: hole area as a fraction of the ACTIVE area, in [0.06, 0.20] (tray,
      required)
    type: number
  internals:
    description: sieve_tray | packing
    type: string
  n_stages:
    description: theoretical stages (packing; give both of hetp_m / n_stages or neither)
    type: integer
  orifice_coefficient:
    description: orifice discharge coefficient, > 0 (tray, required)
    type: number
  packed_height_m:
    description: packed height, m, > 0 (packing, required)
    type: number
  specific_area_m2_m3:
    description: packing specific area, m2/m3, > 0 (packing, required)
    type: number
  stichlmair_C1:
    description: Stichlmair constant C1, > 0 (packing, required)
    type: number
  stichlmair_C2:
    description: Stichlmair constant C2, > 0 (packing, required)
    type: number
  stichlmair_C3:
    description: Stichlmair constant C3, > 0 (packing, required)
    type: number
  surface_tension_N_m:
    description: liquid surface tension, N/m, > 0 (tray, required)
    type: number
  tray_spacing_m:
    description: tray spacing, m, > 0; the Fair fit takes mm internally (tray, required)
    type: number
  voidage:
    description: packing void fraction, in (0, 1) (packing, required)
    type: number
  weir_height_m:
    description: weir height, m, > 0 (tray, required)
    type: number
  weir_length_m:
    description: weir length, m, > 0 (tray, required)
    type: number
required:
- internals
type: object
```

## References

- docs/unit-catalogue-plan.md §2 U-E 11

> R1 sieve-tray hydraulics (Seader-Henley-Roper 3rd ed. §6.6; the C_SB fit is Lygeros-Magoulas 1986 — 0.0105 + 8.127e-4·TS_mm^0.755·exp(−1.463·F_LV^0.842), verified against the Perry 8th ed. eq. 14-90 form and Souza et al., I&EC Res. 64(4), 2256, 2025) and packed-section Stichlmair dry/wet/flood plus optional Robbins dP through fluids 1.3.1, all anchored to closed-form tests. The hole-area correction is applied (plan eq. 3 — F_HA = 1 at Ah/Aa ≥ 0.10, else 5·(Ah/Aa) + 0.5, refusal below 0.06) and reported in info as F_HA; params reject unknown keys (strict params schema). V1 gap — the spec's candidate (Seader-Henley-Roper §6.6 worked sieve-tray example) is not transcribed — no accessible printed page, and the book reads C_F from the Fair chart, where a fit-based reading would be an assessed value, so the case is withdrawn rather than tuned; the level ships provisional. dP_wet_Pa above the flood point is omitted (fluids.Stichlmair_wet does not converge there; dry dP, flood velocity and flood fraction are still reported — SPEC ISSUE on PR
