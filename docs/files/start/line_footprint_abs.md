# Line Footprint (Absolute)

## What does this tool do?

**Line Footprint (Absolute)** generates footprint polygons for each input line using an absolute threshold method. This is useful for mapping the area around lines (like roads or rivers) based on a canopy or cost raster, with user-defined thresholds.

## How do I use it?

### Quick Start

1. **Prepare your input files**: a line vector file (GeoPackage or Shapefile) and a canopy raster file (e.g., CHM).
2. **Run the tool** from the command line:

   ```bash
   python -m beratools.tools.line_footprint_absolute --in_line path/to/input.gpkg --in_chm path/to/canopy.tif --corridor_thresh 3.0 --max_ln_width 10 --exp_shk_cell 0 --out_footprint path/to/output.gpkg --verbose
   ```

3. **Open the output file** in your GIS software to view the generated footprints.

### Using in Python

```python
from beratools.tools.line_footprint_absolute import line_footprint_abs

line_footprint_abs(
    in_line="input.gpkg",
    in_chm="canopy.tif",
    corridor_thresh=3.0,
    max_ln_width=10,
    exp_shk_cell=0,
    out_footprint="output.gpkg",
    processes=-1,
    verbose=True
)
```

## What options can I set?

- **in_line**: Path to your input line file (required)
- **in_chm**: Path to your canopy raster file (required)
- **corridor_thresh**: Absolute threshold for corridor extraction (default: 3.0)
- **max_ln_width**: Maximum processing width for input lines (default: 10)
- **exp_shk_cell**: Expand/shrink cell range for cleaning polygons (default: 0)
- **out_footprint**: Path for the output footprint file (required)
- **processes**: Number of CPU cores to use (-1 = all)
- **verbose**: Show detailed progress (True/False)
- **in_layer**: Layer name in input file (optional)
- **out_layer**: Layer name for output (optional)

## Example

```bash
python -m beratools.tools.line_footprint_absolute --in_line roads.gpkg --in_chm chm.tif --corridor_thresh 3.0 --max_ln_width 10 --exp_shk_cell 0 --out_footprint footprints.gpkg --verbose
```

## Tips

- Works best with line data and a canopy or cost raster.
- Adjust `corridor_thresh` and `max_ln_width` for your data and mapping needs.
- Output can be loaded into QGIS, ArcGIS, or any GIS that supports GeoPackage or Shapefile.

## Learn more

- [BERA Tools on GitHub](https://github.com/appliedgrg/beratools)
