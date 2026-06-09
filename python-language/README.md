# Python Language Support

Adds optional Python editor intelligence to `aichs`:

- syntax diagnostics using `ast.parse`
- optional lint diagnostics from `ruff` when the executable is on PATH
- safe Ruff quick fixes
- Ruff formatting through the generic language formatting API
- symbols for classes, functions, async functions, methods, and top-level variables
- completions for keywords, built-ins, document words, symbols, and a few snippets

Install `ruff` separately to get lint diagnostics, safe fixes, and formatting.
Without Ruff, the extension still provides syntax diagnostics, symbols, and
completion from the Python standard library.

For responsiveness, heavyweight diagnostics and symbol parsing are skipped for
very large buffers. Completion scans a bounded window around the cursor instead
of the entire file.

Install it from the aichs Extensions dialog by fetching this repository and
selecting **Python Language Support**.
