# Centerline — Algorithm Notes

Related user page: [Centerline](../../user/centerline.md)

## Purpose

Extract a centerline path guided by a raster cost surface and seed-line endpoints.

## Inputs and outputs

- Inputs: seed line vector, CHM/cost raster, guided strategy (`pairwise` default), segment-processing options
- Outputs: centerline vector and auxiliary corridor/path artifacts

## Method summary

1. Build/prepare local cost representation from input raster.
2. Derive graph/candidate route structures for each line context.
3. Solve least-cost path(s) according to mode.
4. Apply endpoint/trim post-processing.
5. Optionally run `geo-simplify reduce-bend` on extracted centerlines.
6. Write centerline and supporting outputs.

## Centerline modes

- Default mode is `pairwise`.
- `main_route`: unguided extraction from the corridor graph; requires post clipping/snapping (trim/snap) to align terminals.
- `pairwise`: endpoint-guided extraction by scoring source/destination node pairs and selecting the best path.
- `virtual_nodes`: endpoint-guided extraction by adding temporary source/destination graph nodes before shortest-path solve.
- `direct_insert`: endpoint-guided extraction by inserting endpoints directly into the Voronoi graph before shortest-path solve.

## Mode distinctions (summary)

- `main_route`: most tolerant when endpoint guidance is weak or unavailable; unlike guided modes, it depends on post clipping/snapping to recover line terminals.
- `pairwise` (default): explicit endpoint control with direct pair scoring; favored for general production workflows.
- `virtual_nodes`: graph-augmentation approach that can navigate complex shapes where strict pair matching is limiting.
- `direct_insert`: strongest geometric endpoint anchoring by direct graph insertion; favored when exact terminal placement is critical.

## Direction of travel

- `pairwise` and `main_route` are the primary supported modes, exposed through the GUI; all four modes remain available via CLI/API.
- `virtual_nodes` and `direct_insert` are not exposed in the GUI at this time and may be phased out in a future release.
- `direct_insert` includes a clearance-weight control (`snap_clearance_weight`) in the implementation; this parameter may be exposed in CLI/API or GUI later.

## Assumptions

- Inputs are in compatible projected CRS for stable distance/cost interpretation.
- Seed lines provide meaningful endpoint guidance.

## Edge cases

- Weak corridor contrast can create ambiguous routes.
- Endpoint geometry issues in seed lines can degrade mode behavior.
