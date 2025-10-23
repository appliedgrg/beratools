# Vertex Optimization

## What does this tool do?

**Vertex Optimization** improves the geometry of line features by optimizing the position of their vertices based on a reference raster (such as a canopy height model or cost surface). This helps to align lines more accurately with features in the raster.

## How do I use it?

### Quick Start

1. **Prepare your input files**: a line vector file (GeoPackage or Shapefile) and a raster file (e.g., CHM).
2. **Run the tool** from the command line:

   ```bash
   python -m beratools.tools.vertex_optimization --in_line path/to/input.gpkg --in_raster path/to/input.tif --search_distance 5 --line_radius 35 --out_line path/to/output.gpkg --verbose
   ```

3. **Open the output file** in your GIS software to see the optimized lines.

### Using in Python

```python
from beratools.tools.vertex_optimization import vertex_optimization

vertex_optimization(
    in_line="input.gpkg",
    in_raster="input.tif",
    search_distance=5,
    line_radius=35,
    out_line="output.gpkg",
    processes=-1,
    verbose=True
)
```

## What options can I set?

- **in_line**: Path to your input line file (required)
- **in_raster**: Path to your input raster file (required)
- **search_distance**: Maximum distance to search for optimal vertex placement (required)
- **line_radius**: Processing distance from input lines (required)
- **out_line**: Path for the output file (required)
- **processes**: Number of CPU cores to use (-1 = all)
- **verbose**: Show detailed progress (True/False)
- **in_layer**: Layer name in input file (optional)
- **out_layer**: Layer name for output (optional)

## Example

```bash
python -m beratools.tools.vertex_optimization --in_line roads.gpkg --in_raster chm.tif --search_distance 5 --line_radius 35 --out_line optimized_lines.gpkg --verbose
```

## Tips

- Input lines and raster must have the same spatial reference (CRS).
- Useful for refining digitized lines to better match raster features.
- Output can be loaded into QGIS, ArcGIS, or any GIS that supports GeoPackage or Shapefile.

## Learn more

- [BERA Tools on GitHub](https://github.com/appliedgrg/beratools)
