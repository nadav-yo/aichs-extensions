# Python Language Support

Adds optional Python editor intelligence to `aichs`:

- syntax diagnostics using `ast.parse`
- optional lint diagnostics from `ruff` when the executable is on PATH
- symbols for classes, functions, async functions, methods, and top-level variables
- completions for keywords, built-ins, document words, symbols, and a few snippets

This extension has no required dependencies. Install `ruff` separately to get
lint diagnostics in addition to syntax errors. The manifest also lists
`tree-sitter` and `tree-sitter-python` as optional future dependencies so the
parser can grow without changing the `registry.language(...)` API.

For responsiveness, heavyweight diagnostics and symbol parsing are skipped for
very large buffers. Completion scans a bounded window around the cursor instead
of the entire file.

Install it from the aichs Extensions dialog by fetching this repository and
selecting **Python Language Support**.
