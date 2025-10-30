# Overview

## BERA Tools

BERA Tools is a suite of utilities for mapping, analyzing, and processing forest linear disturbances. It provides both command-line and GUI interfaces, along with a set of modular tools for various workflows.
![BERA logo](screenshots/bt_gui.png)

BERA Tools provide tools for enhanced delineation and attribution of
linear disturbances in forests.

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
| [Check Seed Line](user/check_seed_line.md) | Groups and splits input lines for seed line quality control. |
| [Vertex Optimization](user/vertex_optimization.md) | Optimizes line vertices using raster data for improved delineation. |
| [Centerline](user/centerline.md) | Generates centerlines from input lines and raster data. |
| [Line Footprint (Absolute)](user/canopy_footprint_abs.md) | Generates line footprints based on absolute canopy thresholds. |
| [Line Footprint (Relative)](user/line_footprint_rel.md) | Creates dynamic line footprints using least-cost corridor and relative thresholds. |
| [Line Footprint (Fixed Width)](user/ground_footprint.md) | Computes fixed-width line footprints and associated statistics. |