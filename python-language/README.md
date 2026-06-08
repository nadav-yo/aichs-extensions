# Python Language Support

Adds optional Python editor intelligence to `aichs`:

- syntax diagnostics using `ast.parse`
- symbols for classes, functions, async functions, methods, and top-level variables
- completions for keywords, built-ins, document words, symbols, and a few snippets

This extension has no required dependencies. The manifest lists `tree-sitter`
and `tree-sitter-python` as optional future dependencies so the parser can grow
without changing the `registry.language(...)` API.

Install it from the aichs Extensions dialog by fetching this repository and
selecting **Python Language Support**.
