# System Overview

BERA Tools is organized into clear layers:

- `beratools/tools`: thin tool entry points (CLI/GUI-facing)
- `beratools/core`: core algorithms and processing logic
- `beratools/gui`: desktop GUI and parameter widgets
- `beratools/utility`: shared helpers (arguments, environment checks, spatial helpers)

## Design principles

- **Separation of concerns**: tool wrappers stay lightweight; heavy logic remains in core modules.
- **Single source of tool metadata**: GUI and CLI parameter behavior derives from tool configuration.
- **Consistent execution model**: tools support CLI and GUI call modes with shared runtime behaviors.

## Module responsibilities

- `tools/*`: validate/collect inputs, call corresponding core logic, write outputs.
- `core/*`: geometric/raster algorithms, optimization, line processing.
- `gui/*`: exposes tools and parameters for interactive use.

See also: [Execution Pipeline](execution_pipeline.md)
