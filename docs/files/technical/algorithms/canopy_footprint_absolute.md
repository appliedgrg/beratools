# Canopy Footprint (Absolute) — Algorithm Notes

Related user page: [Canopy Footprint (Absolute)](../../user/canopy_footprint_abs.md)

## Purpose

Generate corridor polygons using an absolute threshold strategy for each centerline context.

## Inputs and outputs

- Inputs: centerline vector, CHM/cost raster, threshold controls
- Output: canopy footprint polygons

## Method summary

1. Build local analysis window around each centerline.
2. Compute corridor/cost surface response.
3. Apply absolute threshold(s) to extract footprint mask.
4. Convert mask to vector polygons and clean geometry.
5. Write output footprint layer.

## Assumptions

- Absolute thresholds are meaningful across the target dataset.
- Input centerlines reasonably represent corridor center paths.

## Edge cases

- Single global threshold may under/over-segment in heterogeneous canopy conditions.
- Raster artifacts/noise can create fragmented polygons without post-cleaning.
