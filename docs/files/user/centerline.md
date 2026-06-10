# Centerline

> Algorithm details: [Technical Guide → Centerline](../technical/algorithms/centerline.md)

## What does this tool do?

**Centerline** finds the least-cost path between vertices of your input lines, helping you extract centerlines (such as for rivers or roads) based on a cost raster (e.g., a canopy height model or other surface).

## How do I use it?

### Quick Start

1. **Prepare your input files**: a line vector file (e.g., GeoPackage or Shapefile) and a raster file (e.g., canopy height model).
2. **Run the tool** from GUI:

   ![Centerline](../screenshots/tool_centerline.png)

3. **Open the output file** in your GIS software to see the extracted centerlines.

## What options can I set?

- **Seed Line**: Path to your input line file
- **CHM Raster**: Path to your input raster file
- **Process Segments**: Process each segment between vertices (True/False, default: True)
- **Centerline Method**: Choose `bera` for the existing BERA Tools least-cost/corridor workflow or `astar` for the A* least-cost path and A* accumulation corridor workflow
- **Guided Strategy**: Centerline extraction strategy (`pairwise` or `main_route`, default: `pairwise`)
- **Simplify A* LCP**: Optionally run `geo-simplify reduce-bend` on the A* least-cost path before corridor generation
- **Smooth A* LCP**: Optionally smooth the A* least-cost path before corridor generation
- **A* Corridor Line Bias**: Biases A* accumulation toward the endpoint direction when resolving ties
- **A* Corridor Distance Penalty**: Narrows the A* corridor by penalizing cells farther from the A* path
- **Simplify/Smooth A* Corridor Polygon**: Optionally simplify and smooth the A* corridor polygon before final centerline extraction
- **Simplify Centerline**: Optionally run `geo-simplify reduce-bend` after centerline extraction
- **Simplify Diameter (m)**: Reduce-bend diameter (default: `10.0`, `0` skips simplify)
- **Output Centerline**: Path for the output file

## Tips

- Input lines and raster must have the same spatial reference (CRS).
- Output includes centerlines and auxiliary layers (least cost path, corridor polygons).
- In A* mode, the final centerline is extracted from the A* corridor polygon using the simplified/smoothed A* least-cost path as guidance.
- Works with GeoPackage or Shapefile formats.

## Guided mode details

- **pairwise** (default): endpoint-guided extraction by scoring source/destination node pairs. Recommended for most workflows.
- **main_route**: unguided extraction from the corridor graph. Useful when endpoint guidance is weak or unavailable.
