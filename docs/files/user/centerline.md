# Centerline

## What does this tool do?

**Centerline** finds the least-cost path between vertices of your input lines, helping you extract centerlines (such as for rivers or roads) based on a cost raster (e.g., a canopy height model or other surface).

## How do I use it?

### Quick Start

1. **Prepare your input files**: a line vector file (e.g., GeoPackage or Shapefile) and a raster file (e.g., canopy height model).
2. **Run the tool** from the command line:

   ```bash
   python -m beratools.tools.centerline --in_line path/to/input.gpkg --in_raster path/to/input.tif --out_line path/to/output.gpkg --line_radius 35 --proc_segments True --verbose
   ```

3. **Open the output file** in your GIS software to see the extracted centerlines.

### Using in Python

```python
from beratools.tools.centerline import centerline

centerline(
    in_line="input.gpkg",
    in_raster="input.tif",
    line_radius=35,
    proc_segments=True,
    out_line="output.gpkg",
    processes=-1,
    verbose=True
)
```

## What options can I set?

- **in_line**: Path to your input line file (required)
- **in_raster**: Path to your input raster file (required)
- **line_radius**: Maximum processing distance from input lines (default: 35)
- **proc_segments**: Process each segment between vertices (True/False, default: True)
- **out_line**: Path for the output file (required)
- **processes**: Number of CPU cores to use (-1 = all)
- **verbose**: Show detailed progress (True/False)
- **in_layer**: Layer name in input file (optional)
- **out_layer**: Layer name for output (optional)

## Example

```bash
python -m beratools.tools.centerline --in_line river_lines.gpkg --in_raster chm.tif --out_line centerlines.gpkg --line_radius 35 --proc_segments True --verbose
```

## Tips

- Input lines and raster must have the same spatial reference (CRS).
- Output includes centerlines and auxiliary layers (least cost path, corridor polygons).
- Works with GeoPackage or Shapefile formats.

## Learn more

- [BERA Tools on GitHub](https://github.com/appliedgrg/beratools)
