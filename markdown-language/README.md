# Markdown Language Support

Adds optional Markdown editor intelligence to `aichs`:

- structural diagnostics for common Markdown document issues
- optional lint diagnostics from `pymarkdown` when the executable is on PATH
- heading symbols for document outlines
- completions for common Markdown snippets

Install `pymarkdownlnt` separately to get full PyMarkdown diagnostics:

```bash
pip install pymarkdownlnt
```

Without PyMarkdown, the extension still provides headings, completions, and a
small set of built-in structural diagnostics.

For responsiveness, diagnostics and symbol parsing are skipped for very large
buffers.
