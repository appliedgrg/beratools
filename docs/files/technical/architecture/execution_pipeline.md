# Execution Pipeline

This page describes the high-level runtime flow from user input to final outputs.

## Pipeline stages

1. **Input collection**
   - GUI mode: parameters are collected from form widgets.
   - CLI mode: parameters are parsed from command-line arguments.

2. **Argument normalization**
   - Tool metadata defines required/optional parameters.
   - Framework options (`processes`, `call_mode`, `log_level`) are applied consistently.

3. **Preprocessing and validation**
   - Read vector/raster inputs.
   - Validate geometry types, CRS compatibility, and required values.

4. **Core algorithm execution**
   - Tool wrapper dispatches to core modules in `beratools/core`.
   - Optional multiprocessing is used for suitable workloads.

5. **Post-processing and output writing**
   - Build output geometries/attributes.
   - Write result files.
   - Emit logs/progress information.

## Typical workflow chain

`Check Seed Lines` → `Vertex Optimization` (optional) → `Centerline` → `Canopy Footprint` → `Ground Footprint`

## Failure points to monitor

- Invalid or empty geometries in seed inputs
- CRS mismatch or geographic CRS used for meter-based operations
- Over-aggressive thresholds that remove most features
- Missing raster coverage where clipping/corridor operations are expected

See also: [Tool Runtime Model](tool_runtime_model.md)
