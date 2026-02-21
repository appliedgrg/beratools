# Full Workflow Example (Hydra)

This folder contains a Hydra-driven example that runs a full processing workflow using BERA tools:

1. `check_seed_line`
2. `centerline`
3. `footprint_abs`
4. `footprint_ground`

## Files

- `full_workflow.py`: workflow entrypoint.
- `config.yaml`: Hydra config for inputs, outputs, and step selection.

## Requirements

- Python environment with BERA Tools dependencies installed.
- `hydra-core` and `omegaconf` available in the environment.
- Input data available at the paths configured in `config.yaml`.

## Configure Input Data

Edit `config.yaml` and set at least:

- `DATA_DIR`
- `CHM`
- `SEEDLINE_ORIGINAL`
- `SEEDLINE_ORIGINAL_LAYER`

The workflow uses `file|layer` syntax for vector layer references.

Example:

```yaml
in_line: ${DATA_DIR}/${SEEDLINE_ORIGINAL}|${SEEDLINE_ORIGINAL_LAYER}
```

## Run

From the repository root:

```bash
python examples/full_workflow.py
```

Run with Hydra overrides:

```bash
python examples/full_workflow.py processes=8
python examples/full_workflow.py steps_to_run=[centerline,footprint_abs]
python examples/full_workflow.py DATA_DIR="D:/my_data"
```

## Common Overrides

- `processes=<int>`: number of worker processes; defaults to all CPU cores when `null`.
- `steps_to_run=[...]`: run only selected steps in order.
- Any nested argument, for example:

```bash
python examples/full_workflow.py args_centerline.line_radius=20
python examples/full_workflow.py args_footprint_ground.width_percentile=75
```

## Output

Outputs are written to paths defined in `config.yaml`, including:

- `centerline.gpkg|centerline`
- `footprint_abs.gpkg|footprint_abs`
- `footprint_ground.gpkg|footprint_ground`
