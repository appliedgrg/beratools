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
3. Solve the least-cost path with the selected method.
4. Build the corridor raster and corridor polygon with the selected method.
5. Extract the centerline from the corridor polygon using the least-cost path as guidance.
6. Apply endpoint/trim post-processing.
7. Optionally run `geo-simplify reduce-bend` on extracted centerlines.
8. Write centerline and supporting outputs.

## Least-cost and corridor methods

- `bera` is the default and preserves the existing BERA Tools workflow: BERA Dijkstra/skimage least-cost path, BERA corridor raster, corridor polygon, then polygon-centerline extraction.
- `astar` uses an 8-neighbor grid A* least-cost path with stable tie-breaking toward the seed-line direction.
- The A* least-cost path can be simplified with `geo-simplify reduce-bend --smooth-line` and smoothed before corridor generation.
- The A* corridor raster is built from forward/reverse A* accumulation. It uses BERA's corridor convention: `0` inside the corridor and `1` outside.
- The A* corridor supports a line-bias weight and a distance-from-path penalty weight.
- The A* corridor polygon can be simplified and smoothed before final centerline extraction.
- The A* final centerline is derived from the A* corridor polygon using the processed A* least-cost path as the guide line.

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
