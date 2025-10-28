# Canopy Footprint (Relative)

## What does this tool do?

**Canopy Footprint (Relative)** creates dynamic footprint polygons for each input line using a least-cost corridor method and thresholds that are calculated individually for each line. This is useful for mapping areas around lines (like roads or rivers) where the buffer adapts to local canopy or cost raster values.

## How do I use it?

### Quick Start

1. **Prepare your input files**: a line vector file (GeoPackage or Shapefile) with the attribute "OLnFID", and a canopy raster (e.g., CHM).
2. **Run the tool** from the command line:

   ```bash
   python -m beratools.tools.line_footprint_relative -i '{"in_line": "input.gpkg", "in_chm": "canopy.tif", ...}' -p -1 -v True
   ```

   *(Replace the JSON with your actual parameters. See below for options.)*

3. **Open the output file** in your GIS software to view the generated dynamic footprints.

### Using in Python

```python
from beratools.tools.line_footprint_functions import main_line_footprint_relative

main_line_footprint_relative(
    print,
    in_line="input.gpkg",
    in_chm="canopy.tif",
    # ...other parameters...
    processes=-1,
    verbose=True
)
```

## What options can I set?

- **in_line**: Path to your input line file (required, must have "OLnFID" field)
- **in_chm**: Path to your canopy raster file (required)
- **other parameters**: See [BERA Tools documentation](https://github.com/appliedgrg/beratools) for full list
- **processes**: Number of CPU cores to use (-1 = all)
- **verbose**: Show detailed progress (True/False)

## Example

```bash
python -m beratools.tools.line_footprint_relative -i '{"in_line": "roads.gpkg", "in_chm": "chm.tif"}' -p -1 -v True
```

## Tips

- Input lines must have the "OLnFID" attribute.
- Output can be loaded into QGIS, ArcGIS, or any GIS that supports GeoPackage or Shapefile.
- This tool adapts the buffer size for each line based on local raster values.

## Learn more

- [BERA Tools on GitHub](https://github.com/appliedgrg/beratools)
