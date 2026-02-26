# Check Seed Lines — Algorithm Notes

Related user page: [Check Seed Lines](../../user/check_seed_line.md)

## Purpose

Prepare and normalize input seed lines so downstream centerline/corridor tools receive clean, consistent geometry.

## Inputs and outputs

- Inputs: seed line vector, optional CHM raster
- Output: cleaned seed line vector

## Main processing stages

1. Normalize line geometries (multipart handling)
2. Remove invalid/empty/degenerate features
3. Optional short-line filtering
4. Optional CHM footprint clipping (with inward shrink)
5. Optional endpoint-only snapping
6. Split at intersections
7. Optional grouping and merge
8. Optional densification of long segments

## Assumptions

- Input is line geometry.
- Distance thresholds are interpreted in meter-like projected units.
- Raster footprint approximates valid-data extent.

## Edge cases

- Excessive shrink distance can remove all line coverage.
- Aggressive minimum length can over-prune short valid segments.
- Snapping tolerance larger than intended can over-connect nearby lines.

## Notes for maintainers

- Keep QC stages deterministic and independent where possible.
- Preserve clear logs for each pruning/cleanup stage.
