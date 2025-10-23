# Line Footprint Fixed

## What does this tool do?

**Line Footprint Fixed** creates footprint polygons for each input line using a fixed-width buffer, based on the measured width of the line features. This is useful for mapping corridors or buffered areas around lines (like roads or rivers) using a consistent width or percentile-based width.

## How do I use it?

### Quick Start

1. **Prepare your input files**: a line vector file (GeoPackage or Shapefile) and a polygon footprint file.
2. **Run the tool** from the command line:

   ```bash
   python -m beratools.tools.line_footprint_fixed --in_line path/to/input.gpkg --in_footprint path/to/footprint.gpkg --n_samples 10 --offset 0.0 --max_width False --out_footprint path/to/output.gpkg --verbose
   ```

3. **Open the output file** in your GIS software to view the generated fixed-width footprints.

### Using in Python

```python
from beratools.tools.line_footprint_fixed import line_footprint_fixed

line_footprint_fixed(
    in_line="input.gpkg",
    in_footprint="footprint.gpkg",
    n_samples=10,
    offset=0.0,
    max_width=False,
    out_footprint="output.gpkg",
    processes=-1,
    verbose=True
)
```

## What options can I set?

- **in_line**: Path to your input line file (required)
- **in_footprint**: Path to your input footprint polygon file (required)
- **n_samples**: Number of sample points along each line (default: 10)
- **offset**: Offset distance for width measurement (default: 0.0)
- **max_width**: Use maximum width (True) or percentile width (False, default)
- **out_footprint**: Path for the output footprint file (required)
- **processes**: Number of CPU cores to use (-1 = all)
- **verbose**: Show detailed progress (True/False)
- **in_layer**: Layer name in input file (optional)
- **out_layer**: Layer name for output (optional)
- **width_percentile**: Percentile for width calculation (default: 75)

## Example

```bash
python -m beratools.tools.line_footprint_fixed --in_line roads.gpkg --in_footprint footprints.gpkg --n_samples 10 --offset 0.0 --max_width False --out_footprint fixed_footprints.gpkg --verbose
```

## Tips

- Use `max_width=True` to buffer using the maximum measured width (plus 20%).
- Default is to use the 75th percentile width for more robust results.
- Output can be loaded into QGIS, ArcGIS, or any GIS that supports GeoPackage or Shapefile.

## Learn more

- [BERA Tools on GitHub](https://github.com/appliedgrg/beratools)
