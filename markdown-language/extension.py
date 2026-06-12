"""Markdown language support for aichs.

This extension keeps Markdown support useful without external dependencies and
adds PyMarkdown diagnostics when the `pymarkdown` executable is available.
"""

from __future__ import annotations

from pathlib import Path
import re
import subprocess
import tempfile


EXTENSION_DESCRIPTION = "Adds Markdown diagnostics, headings, and completion for the file editor."

_MAX_DIAGNOSTIC_CHARS = 500_000
_MAX_SYMBOL_CHARS = 500_000
_PYMARKDOWN_TIMEOUT_SECONDS = 2

_ATX_HEADING_RE = re.compile(r"^(?P<indent>[ \t]{0,3})(?P<marks>#{1,6})(?P<space>[ \t]+|$)(?P<title>.*)$")
_BAD_ATX_HEADING_RE = re.compile(r"^(?P<indent>[ \t]{0,3})(?P<marks>#{1,6})(?P<title>[^#\s].*)$")
_FENCE_RE = re.compile(r"^[ \t]{0,3}(?P<marks>`{3,}|~{3,})")
_REFERENCE_RE = re.compile(r"^[ \t]{0,3}\[(?P<label>[^\]\n]+)\]:", re.IGNORECASE)
_PYMARKDOWN_RE = re.compile(
    r"^(?P<path>.+):(?P<line>\d+):(?P<column>\d+):\s+"
    r"(?P<code>MD\d+):\s+(?P<message>.+)$"
)

_SNIPPETS = {
    "fence": "```text\n\n```",
    "frontmatter": "---\n\n---",
    "image": "![alt text](url)",
    "link": "[link text](url)",
    "table": "| Column | Column |\n| --- | --- |\n| Value | Value |",
    "task": "- [ ] Task",
}


def register(registry):
    registry.metadata(description=EXTENSION_DESCRIPTION)
    registry.language(
        name="markdown",
        file_patterns=["*.md", "**/*.md", "*.markdown", "**/*.markdown"],
        diagnostics=diagnostics,
        symbols=symbols,
        completion=completion,
    )


def diagnostics(ctx):
    content = ctx.content or ""
    if len(content) > _MAX_DIAGNOSTIC_CHARS:
        return []
    pymarkdown_items = _pymarkdown_diagnostics(ctx)
    if pymarkdown_items is not None:
        return _dedupe_diagnostics(pymarkdown_items)
    return _dedupe_diagnostics(_local_diagnostics(ctx))


def symbols(ctx):
    content = ctx.content or ""
    if len(content) > _MAX_SYMBOL_CHARS:
        return []

    items = []
    fence = None
    for line_number, line in enumerate(content.splitlines(), start=1):
        fence = _next_fence_state(fence, line)
        if fence and not _is_fence_line(line, fence):
            continue
        if fence:
            continue

        match = _ATX_HEADING_RE.match(line)
        if not match:
            continue
        title = _heading_text(match.group("title"))
        if not title:
            continue
        level = len(match.group("marks"))
        items.append({
            "path": ctx.path,
            "name": title,
            "kind": f"heading {level}",
            "line": line_number,
            "column": len(match.group("indent")),
            "end_line": line_number,
            "end_column": len(line),
        })
    return items


def completion(ctx):
    prefix = str(getattr(ctx, "prefix", "") or "").strip()
    if not prefix:
        return []
    items = []
    for label, insert_text in _SNIPPETS.items():
        if _matches_prefix(label, prefix):
            items.append({
                "label": label,
                "insert_text": insert_text,
                "detail": "markdown snippet",
            })
    return sorted(items, key=lambda item: item["label"])[:80]


def _pymarkdown_diagnostics(ctx):
    content = ctx.content or ""
    suffix = Path(ctx.path or "buffer.md").suffix.lower()
    if suffix not in (".md", ".markdown"):
        suffix = ".md"

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            suffix=suffix,
            prefix=".aichs-pymarkdown-",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(content)

        result = subprocess.run(
            ["pymarkdown", "scan", str(temp_path)],
            text=True,
            capture_output=True,
            check=False,
            timeout=_PYMARKDOWN_TIMEOUT_SECONDS,
            cwd=ctx.cwd or None,
        )
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return None
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink()
            except OSError:
                pass

    output = "\n".join(part for part in (result.stdout, result.stderr) if part)
    items = _parse_pymarkdown_output(output, ctx.path or "buffer.md")
    if result.returncode == 0:
        return items
    return items if items else None


def _parse_pymarkdown_output(output: str, path: str) -> list[dict]:
    items = []
    for raw_line in (output or "").splitlines():
        match = _PYMARKDOWN_RE.match(raw_line.strip())
        if not match:
            continue
        line = _positive_int(match.group("line"), 1)
        column = max(0, _positive_int(match.group("column"), 1) - 1)
        items.append({
            "path": path,
            "line": line,
            "column": column,
            "severity": "warning",
            "source": "pymarkdown",
            "code": match.group("code"),
            "message": match.group("message").strip(),
        })
    return items


def _local_diagnostics(ctx):
    items = []
    fence = None
    h1_line = None
    previous_heading_level = 0
    references = {}

    for line_number, line in enumerate((ctx.content or "").splitlines(), start=1):
        if fence:
            if _closes_fence(line, fence):
                fence = None
            continue

        opening = _opening_fence(line)
        if opening:
            fence = {
                "marker": opening["marker"],
                "length": opening["length"],
                "line": line_number,
                "column": opening["column"],
            }
            continue

        bad_heading = _BAD_ATX_HEADING_RE.match(line)
        if bad_heading:
            items.append(_diagnostic(
                ctx,
                line_number,
                len(bad_heading.group("indent")) + len(bad_heading.group("marks")),
                "Heading marker should be followed by a space.",
                code="heading-space",
            ))
            continue

        heading = _ATX_HEADING_RE.match(line)
        if heading:
            level = len(heading.group("marks"))
            title = _heading_text(heading.group("title"))
            if title:
                if level == 1:
                    if h1_line is not None:
                        items.append(_diagnostic(
                            ctx,
                            line_number,
                            len(heading.group("indent")),
                            "Multiple top-level headings in the same document.",
                            code="multiple-h1",
                        ))
                    else:
                        h1_line = line_number
                if previous_heading_level and level > previous_heading_level + 1:
                    items.append(_diagnostic(
                        ctx,
                        line_number,
                        len(heading.group("indent")),
                        f"Heading level jumps from {previous_heading_level} to {level}.",
                        code="heading-level-jump",
                    ))
                previous_heading_level = level

        reference = _REFERENCE_RE.match(line)
        if reference:
            label = _normalize_reference_label(reference.group("label"))
            if label in references:
                items.append(_diagnostic(
                    ctx,
                    line_number,
                    reference.start("label"),
                    f"Duplicate reference definition for [{reference.group('label')}].",
                    code="duplicate-reference",
                ))
            else:
                references[label] = line_number

    if fence:
        items.append(_diagnostic(
            ctx,
            fence["line"],
            fence["column"],
            "Unclosed fenced code block.",
            code="unclosed-fence",
        ))

    return items


def _diagnostic(ctx, line: int, column: int, message: str, *, code: str) -> dict:
    return {
        "path": ctx.path,
        "line": line,
        "column": max(0, column),
        "severity": "warning",
        "source": "markdown",
        "code": code,
        "message": message,
    }


def _opening_fence(line: str):
    match = _FENCE_RE.match(line)
    if not match:
        return None
    marks = match.group("marks")
    return {
        "marker": marks[0],
        "length": len(marks),
        "column": match.start("marks"),
    }


def _closes_fence(line: str, fence: dict) -> bool:
    match = _FENCE_RE.match(line)
    if not match:
        return False
    marks = match.group("marks")
    return marks[0] == fence["marker"] and len(marks) >= fence["length"]


def _next_fence_state(fence, line: str):
    if fence:
        return None if _closes_fence(line, fence) else fence
    return _opening_fence(line)


def _is_fence_line(line: str, fence: dict) -> bool:
    opening = _opening_fence(line)
    if not opening:
        return False
    return opening["marker"] == fence["marker"] and opening["length"] >= fence["length"]


def _heading_text(value: str) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[ \t]+#+[ \t]*$", "", text).strip()
    return text


def _normalize_reference_label(value: str) -> str:
    return " ".join(str(value or "").split()).casefold()


def _matches_prefix(word: str, prefix: str) -> bool:
    return len(word) > len(prefix) and word.lower().startswith(prefix.lower())


def _dedupe_diagnostics(items):
    seen = set()
    deduped = []
    for item in items:
        key = (
            item.get("source"),
            item.get("code"),
            item.get("line"),
            item.get("column"),
            item.get("message"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _positive_int(value, default: int) -> int:
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return default
