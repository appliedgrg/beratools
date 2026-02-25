# Canopy Footprint (Relative) — Algorithm Notes

Related user page: [Canopy Footprint (Relative)](../../user/canopy_footprint_rel.md)

## Purpose

Generate corridor polygons with thresholds adapted to local conditions for each centerline.

## Inputs and outputs

- Inputs: centerline vector, CHM/cost raster, relative-threshold controls
- Output: canopy footprint polygons

## Method summary

1. Build local corridor/cost representation per line.
2. Estimate line-specific threshold characteristics.
3. Apply relative/adaptive thresholding to extract candidate footprint.
4. Convert raster mask to polygons and clean outputs.
5. Write final footprint layer.

## Assumptions

- Local raster response contains enough signal to derive useful adaptive thresholds.
- Centerline quality is sufficient to anchor corridor extraction.

## Edge cases

- Noisy local windows can destabilize adaptive thresholds.
- Very short/atypical lines may need tuning to avoid overfit thresholds.
