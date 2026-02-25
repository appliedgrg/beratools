# Tool Runtime Model

This page describes how a BERA tool is executed across GUI and CLI.

## Tool API pattern

Tools generally expose a function shaped like:

```python
def tool_name(..., processes=0, call_mode=CallMode.CLI, log_level="INFO")
```

The final framework parameters are shared across tools and are used to standardize runtime behavior.

## Argument composition

`compose_tool_kwargs` reads tool metadata and creates runtime kwargs for each mode:

- **GUI mode**: tool parameters are bundled from the GUI payload.
- **CLI mode**: required/optional parameters are parsed as command-line args.
- **Module mode**: direct Python function call with explicit arguments.

This keeps tool definitions synchronized between GUI and CLI while avoiding duplicated parameter schemas.

## Multiprocessing model

For data-parallel tasks, tools can call `execute_multiprocessing` from `beratools.core.tool_base`.

Key behavior:

- Auto-detect available CPUs
- Reserve one core for system stability
- On Windows, apply conservative limits for process handle constraints
- Fall back to sequential mode when one process is used
- Keep progress/log behavior consistent with `call_mode`

## Separation of concerns

- `beratools/tools/*`: input wiring and dispatch
- `beratools/core/*`: heavy processing and algorithm implementation

This structure keeps tool wrappers small and makes algorithm logic easier to test and maintain.

See also: [How to Add a New Tool](../../developer/add_new_tool.md)
