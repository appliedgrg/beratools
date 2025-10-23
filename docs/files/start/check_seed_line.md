# Check Seed Line

## What does this tool do?

**Check Seed Line** helps you group and clean up line features (like road or river centerlines) in a GIS file. It reads your input file, merges and splits lines as needed, and saves a new file with grouped lines—making your data easier to use for mapping and analysis.

## How do I use it?

### Quick Start

1. **Prepare your input file** (GeoPackage, Shapefile, etc.) with line features.
2. **Run the tool** from the command line:

   ```bash
   python -m beratools.tools.check_seed_line --in_line path/to/input.gpkg --out_line path/to/output.gpkg --verbose
   ```

3. **Open the output file** in your GIS software to see the grouped lines.

### Using in Python

```python
from beratools.tools.check_seed_line import check_seed_line

check_seed_line(
    in_line="input.gpkg",
    out_line="output.gpkg",
    verbose=True
)
```

## What options can I set?

- **in_line**: Path to your input file (required)
- **out_line**: Path for the output file (required)
- **verbose**: Show detailed progress (True/False)
- **processes**: Number of CPU cores to use (-1 = all)
- **in_layer**: Layer name in input file (optional)
- **out_layer**: Layer name for output (optional)
- **use_angle_grouping**: Use angle-based grouping (default: True)

## Example

```bash
python -m beratools.tools.check_seed_line --in_line seed_lines.gpkg --out_line grouped_lines.gpkg --verbose
```

## Tips

- Works best with line data (not points or polygons).
- Output can be loaded into QGIS, ArcGIS, or any GIS that supports GeoPackage or Shapefile.

## Learn more

- [BERA Tools on GitHub](https://github.com/appliedgrg/beratools)
