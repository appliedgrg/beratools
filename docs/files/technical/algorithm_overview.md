# Algorithm Overview

BERA Tools processes line mapping in a staged pipeline:

1. **Seed line quality control** (`Check Seed Lines`)
2. **Optional geometry refinement** (`Vertex Optimization`)
3. **Centerline extraction** (`Centerline`)
4. **Canopy corridor delineation** (`Canopy Footprint Absolute/Relative`)
5. **Ground footprint derivation** (`Ground Footprint`)

## Shared technical assumptions

- Vector and raster inputs should use compatible CRS.
- Distance-based operations assume projected units (meters).
- Tool scripts act as thin interfaces; core logic lives in `beratools/core`.

## Where to go next

- Architecture:
  - [System Overview](architecture/system_overview.md)
  - [Execution Pipeline](architecture/execution_pipeline.md)
  - [Tool Runtime Model](architecture/tool_runtime_model.md)
- Algorithms:
  - [Check Seed Lines](algorithms/check_seed_line.md)
  - [Vertex Optimization](algorithms/vertex_optimization.md)
  - [Centerline](algorithms/centerline.md)
  - [Canopy Footprint (Absolute)](algorithms/canopy_footprint_absolute.md)
  - [Canopy Footprint (Relative)](algorithms/canopy_footprint_relative.md)
  - [Ground Footprint](algorithms/ground_footprint.md)
