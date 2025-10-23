# Overview

BERA Tools provide tools for enhanced delineation and attribution of
linear disturbances in forests.

![Main GUI](../screenshots/bt_gui.png)

## Key Features

- Line cleanup and quality control
- Vertex optimization using raster guidance
- Automatic centerline generation
- Multiple footprint methods: absolute, relative, fixed-width
- Small, scriptable command-line tools for batch processing

## Data Formats & Conventions

- Supported vector: GeoPackage, Shapefile
- Supported raster: GeoTIFF

## Support & Contributions

- See the repository README for detailed examples.
- Contributions welcome via issues and pull requests. Include tests and minimal reproducible examples.

## Tool Boxes

### Mapping

| Tool | Details |
|------|---------|
| [Check Seed Line](tools/check_seed_line.md) | Groups and splits input lines for seed line quality control. |
| [Vertex Optimization](tools/vertex_optimization.md) | Optimizes line vertices using raster data for improved delineation. |
| [Centerline](tools/centerline.md) | Generates centerlines from input lines and raster data. |
| [Line Footprint (Absolute)](tools/line_footprint_abs.md) | Generates line footprints based on absolute canopy thresholds. |
| [Line Footprint (Relative)](tools/line_footprint_rel.md) | Creates dynamic line footprints using least-cost corridor and relative thresholds. |
| [Line Footprint (Fixed Width)](tools/line_footprint_fixed.md) | Computes fixed-width line footprints and associated statistics. |
