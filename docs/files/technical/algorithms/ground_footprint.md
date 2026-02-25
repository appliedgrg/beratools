# Ground Footprint — Algorithm Notes

Related user page: [Ground Footprint](../../user/ground_footprint.md)

## Purpose

Derive ground-level footprint polygons from centerline geometry and canopy footprint width cues.

## Inputs and outputs

- Inputs: centerline vector, canopy footprint polygons, width-selection settings
- Output: ground footprint polygons

## Method summary

1. Measure/aggregate canopy-derived width characteristics near each line.
2. Select operational width policy (e.g., percentile or max-based).
3. Buffer centerlines using selected width model.
4. Post-process and clean resulting polygons.
5. Write output footprint layer.

## Assumptions

- Canopy footprint quality is sufficient to estimate representative widths.
- Width policy is chosen according to mapping objective (conservative vs inclusive).

## Edge cases

- Outlier widths can inflate buffers under max-width strategy.
- Poor upstream canopy footprints propagate to ground footprint quality.
