# Check Seed Lines

> Algorithm details: [Technical Guide → Check Seed Lines](../technical/algorithms/check_seed_line.md)

## What does this tool do?

**Check Seed Lines** cleans and prepares seed lines before downstream processing. It can:

- normalize multipart lines to `LineString`
- remove invalid/empty/degenerate geometries
- optionally remove short lines
- optionally clip lines to CHM valid-data footprint (with inward shrink)
- optionally snap close endpoints (endpoint-only, directed snap)
- split lines at intersections
- optionally group lines
- optionally densify long lines by inserting internal vertices

## How do I use it?

### Quick Start

1. **Prepare your input files**: a seed line vector file and a CHM raster file.
2. **Run the tool** from the GUI:
   ![Check Seed Line](../screenshots/tool_check_line.png)

## What options can I set?

- **Seed Line**: Input seed line file
- **CHM Raster**: Input raster used to build a valid-data footprint for clipping
- **CHM footprint shrink (m)**: Inward buffer distance in meters applied before clipping (default `15`). Geographic CRS inputs are converted to a local meter-based projection for this step. See shrink-distance guide below.
- **Clip to CHM footprint**: Enable/disable footprint clipping step (default `true`). If enabled and CHM raster is missing, clipping is skipped with an error message.
- **Output Seed Line**: Output seed line file
- **Remove short lines**: Enable removal of short segments
- **Minimum line length (m)**: Threshold in meters for short-line removal (default `5`). Geographic CRS inputs are evaluated in a local meter-based projection for this step.
- **Snap close endpoints**: Enable endpoint-to-endpoint snapping only
- **Snap tolerance (m)**: Maximum endpoint snap distance in meters (default `5`). Geographic CRS inputs are evaluated in a local meter-based projection for this step. If both short-line removal and snapping are enabled, effective tolerance is `max(snap_tolerance, minimum_line_length)`.
- **Group lines**: Group nearby/intersecting lines and assign shared `BT_GROUP` values
- **Densify long lines**: Insert equalized internal vertices on long lines
- **Max segment length (m)**: Maximum segment length for densification (default `500`)

## Group lines methodology

- Builds endpoint nodes from each line and merges nearly coincident endpoints.
- Creates a connectivity graph linking lines that meet at merged endpoints.
- When angle grouping is enabled, uses endpoint direction to keep only angle-compatible links.
- Assigns one shared `BT_GROUP` ID to each connected component.
- This step assigns group IDs only; it does not dissolve/merge geometries.

## Tips

- Input vector and CHM raster should use the same CRS.
- Works with line data (not points or polygons).
- If clipping removes all lines, the output may be empty.
- CHM footprint is generated from raster valid-data cells at raster resolution, so edge boundaries are approximate and can be less accurate.
- After clipping, visually inspect edge segments and verify that clipped seed lines still match expected line extents.
- Optional numeric parameters remain visible in the GUI; toggle logic is enforced in backend processing.
- If CHM footprint shrink is too large, processing fails with guidance to reduce the shrink distance.

## CHM footprint shrink distance guide

- Start with a shrink distance near `1x` to `2x` CHM pixel size (for example, with `1 m` CHM use `1-2 m`; with `5 m` CHM use `5-10 m`).
- Increase shrink distance when noisy raster edges keep creating false edge segments.
- Decrease shrink distance when valid lines near canopy boundaries are being clipped too aggressively.
- For high-resolution CHM, prefer smaller values (`0.5-5 m`) and adjust gradually.
- For coarser CHM, larger values may be needed, but always verify edge areas visually in the output.
