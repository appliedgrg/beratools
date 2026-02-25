# How to Add a New Tool

This page focuses on the **practical contributor workflow** for adding a new tool.

For runtime internals (CLI/GUI call modes, argument composition, multiprocessing), see:
- [Tool Runtime Model](../technical/architecture/tool_runtime_model.md)

## 1) Create the tool script

Add a new script in `beratools/tools` (you can start from `tool_template.py`).

Typical API pattern:

```python
def my_tool(..., processes=0, call_mode=CallMode.CLI, log_level="INFO"):
    ...
```

Add `__main__` entrypoint:

```python
if __name__ == "__main__":
    from beratools.utility.tool_args import compose_tool_kwargs
    kwargs = compose_tool_kwargs("my_tool")
    my_tool(**kwargs)
```

## 2) Register in GUI metadata

Update `beratools/gui/assets/beratools.json` and add your tool definition in the proper category.

At minimum, define:

- `name`, `info`, `tool_type`, `tool_api`, `icon`, `tech_link`
- parameter list (`variable`, `label`, `description`, `type`, `subtype`, `default`, `output`, `optional`)

## 3) Keep tools thin; move heavy logic to core

- Put high-level tool wiring in `beratools/tools/*`
- Put algorithm-heavy logic in `beratools/core/*`

This keeps code easier to test and maintain.

## 4) Test from CLI first

Run help and a sample execution before validating in GUI:

```bash
python beratools/tools/my_tool.py --help
```

Then test via GUI once CLI behavior is stable.

## 5) Add docs and tests

- Add/update user docs if end-user behavior changed
- Add/update technical docs for algorithm/runtime internals
- Add tests in `tests/` for new behavior and edge cases

## 6) Submit PR

- Follow branching and contribution guidance in [Development](development.md)
- Request review and ensure CI passes
