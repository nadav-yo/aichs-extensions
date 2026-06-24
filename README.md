# aichs extensions

Optional extensions for [aichs](https://github.com/nadav-yo/aichs).

Each extension lives in its own folder so it can grow into multiple files:

```text
extension-name/
  aichs-extension.json
  extension.py
```

To install an extension today, copy a folder into one of:

```text
~/.aichs/extensions/
.aichs/extensions/
```

The app loads both single-file extensions and folder extensions with an
`extension.py` entrypoint. Aichs itself does not ship these extensions by
default; they are opt-in examples and helpers.

In current aichs builds, you can also open the Extensions dialog, choose
**Add**, paste this repository URL, and select the extension folders to install.

## Extensions

| Extension | What it adds |
|---|---|
| `python-language` | Python syntax diagnostics, Ruff lint/fix/format support, symbols, and completion |
| `runtime-continue` | Runtime continuation and compaction helpers |
| `runtime-guard` | Retry-loop guardrails for runtime failures |
| `process-sessions` | Managed process session helpers |
| `context-resilience` | Compact handoff notes and large-output artifact spooling |
| `decision-memory` | Project decision memory helpers |
| `canvas-briefing` | Canvas context briefing example for graph chat and run agents |
| `canvas-notes` | Canvas-only note tools backed by extension storage |
| `web-fetch` | Web page fetch tool example |
| `ui-examples` | Status badge and panel examples |
| `workflow-examples` | Tool, command, context, and hook examples |


