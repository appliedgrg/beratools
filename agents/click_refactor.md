The CLI tool should expose only explicit user-facing arguments, with -p and -v always required.
A hidden JSON input (-i) is supported for internal automation, not shown in help output.
If -i is provided, parse it as JSON; otherwise, compile individual args into a dict for downstream logic.
The click library is preferred for its clear help output and ability to hide internal options.
The goal is a clean, user-friendly CLI with internal flexibility for automation.
