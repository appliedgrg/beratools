# Centerline — Algorithm Notes

Related user page: [Centerline](../../user/centerline.md)

## Purpose

Extract a centerline path guided by a raster cost surface and seed-line endpoints.

## Inputs and outputs

- Inputs: seed line vector, CHM/cost raster, centerline mode, segment-processing options
- Outputs: centerline vector and auxiliary corridor/path artifacts

## Method summary

1. Build/prepare local cost representation from input raster.
2. Derive graph/candidate route structures for each line context.
3. Solve least-cost path(s) according to mode.
4. Apply endpoint/trim post-processing.
5. Write centerline and supporting outputs.

## Centerline modes

- `main_route`: derives principal route from corridor graph.
- `pairwise`: scores source/destination node pairs and selects best path.
- `virtual_nodes`: injects temporary virtual source/destination nodes and solves shortest path.

## Assumptions

- Inputs are in compatible projected CRS for stable distance/cost interpretation.
- Seed lines provide meaningful endpoint guidance.

## Edge cases

- Weak corridor contrast can create ambiguous routes.
- Endpoint geometry issues in seed lines can degrade mode behavior.
