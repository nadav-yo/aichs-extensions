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

