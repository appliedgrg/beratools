# Vertex Optimization — Algorithm Notes

Related user page: [Vertex Optimization](../../user/vertex_optimization.md)

## Purpose

Adjust vertex positions so input lines better align with raster-derived signals (for example CHM/cost patterns).

## Inputs and outputs

- Inputs: line vector, CHM/cost raster, search distance
- Output: optimized line vector

## Method summary

1. Iterate vertices/segments from input lines.
2. Search nearby candidate positions within configured distance.
3. Evaluate candidate quality against raster-derived objective.
4. Replace vertex positions with improved candidates.
5. Rebuild and write optimized geometries.

## Assumptions

- Raster and vector share compatible CRS.
- Search distance is appropriate for local corridor width.

## Edge cases

- Large search radius can over-smooth or drift geometry.
- Sparse/noisy raster patterns can reduce optimization reliability.
