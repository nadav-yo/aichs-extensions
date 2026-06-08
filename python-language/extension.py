"""Python language support for aichs.

This extension intentionally keeps all language features optional. It uses the
Python standard library as a baseline and adds Ruff diagnostics when the `ruff`
executable is available on PATH.
"""

from __future__ import annotations

import ast
import builtins
from collections import OrderedDict
import json
import keyword
import re
import subprocess


EXTENSION_DESCRIPTION = "Adds Python syntax diagnostics, symbols, and completion for the file editor."

_MAX_AST_CHARS = 500_000
_MAX_RUFF_CHARS = 500_000
_MAX_COMPLETION_SCAN_CHARS = 160_000
_MAX_COMPLETION_SYMBOL_CHARS = 400_000
_MAX_AST_CACHE_ENTRIES = 8
_RUFF_TIMEOUT_SECONDS = 2

_WORD_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
_SNIPPETS = {
    "class": "class Name:\n    pass",
    "def": "def name():\n    pass",
    "try": "try:\n    pass\nexcept Exception as exc:\n    pass",
    "with": "with expression as value:\n    pass",
}
_AST_CACHE = OrderedDict()


def register(registry):
    registry.metadata(description=EXTENSION_DESCRIPTION)
    registry.language(
        name="python",
        file_patterns=["*.py", "**/*.py"],
        diagnostics=diagnostics,
        symbols=symbols,
        completion=completion,
    )


def diagnostics(ctx):
    items = []
    _tree, syntax_error = _parse_ast(ctx)
    if syntax_error:
        items.append(_syntax_diagnostic(ctx, syntax_error))
    items.extend(_ruff_diagnostics(ctx))
    return _dedupe_diagnostics(items)


def symbols(ctx):
    tree, _syntax_error = _parse_ast(ctx)
    if tree is None:
        return []
    visitor = _SymbolVisitor(ctx.path)
    visitor.visit(tree)
    return visitor.items


def completion(ctx):
    prefix = str(getattr(ctx, "prefix", "") or "").strip()
    if not prefix:
        return []

    candidates = {}
    _add_prefixed(candidates, keyword.kwlist, prefix, "keyword")
    _add_prefixed(candidates, dir(builtins), prefix, "built-in")
    _add_prefixed(candidates, _document_words(_completion_scan_text(ctx)), prefix, "document")

    for label, insert_text in _SNIPPETS.items():
        if _matches_prefix(label, prefix):
            candidates[label] = {
                "label": label,
                "insert_text": insert_text,
                "detail": "snippet",
            }

    if len(ctx.content or "") <= _MAX_COMPLETION_SYMBOL_CHARS:
        for item in symbols(ctx):
            label = item["name"]
            if _matches_prefix(label, prefix):
                candidates.setdefault(label, {
                    "label": label,
                    "insert_text": label,
                    "detail": item["kind"],
                })

    return sorted(candidates.values(), key=lambda item: (item["label"].lower(), item["label"]))[:80]


class _SymbolVisitor(ast.NodeVisitor):
    def __init__(self, path: str):
        self.path = path
        self.items = []
        self._class_depth = 0

    def visit_ClassDef(self, node):
        self._add(node, node.name, "class")
        self._class_depth += 1
        self.generic_visit(node)
        self._class_depth -= 1

    def visit_FunctionDef(self, node):
        kind = "method" if self._class_depth else "function"
        self._add(node, node.name, kind)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node):
        kind = "async method" if self._class_depth else "async function"
        self._add(node, node.name, kind)
        self.generic_visit(node)

    def visit_Assign(self, node):
        if self._class_depth:
            return self.generic_visit(node)
        for target in node.targets:
            for name in _target_names(target):
                self._add(target, name, "variable")
        self.generic_visit(node)

    def visit_AnnAssign(self, node):
        if not self._class_depth:
            for name in _target_names(node.target):
                self._add(node.target, name, "variable")
        self.generic_visit(node)

    def _add(self, node, name: str, kind: str) -> None:
        if not name:
            return
        self.items.append({
            "path": self.path,
            "name": name,
            "kind": kind,
            "line": getattr(node, "lineno", 1),
            "column": getattr(node, "col_offset", 0),
            "end_line": getattr(node, "end_lineno", None),
            "end_column": getattr(node, "end_col_offset", None),
        })


def _target_names(node):
    if isinstance(node, ast.Name):
        yield node.id
        return
    if isinstance(node, (ast.Tuple, ast.List)):
        for item in node.elts:
            yield from _target_names(item)


def _document_words(content: str) -> set[str]:
    return set(_WORD_RE.findall(content or ""))


def _completion_scan_text(ctx) -> str:
    content = ctx.content or ""
    if len(content) <= _MAX_COMPLETION_SCAN_CHARS:
        return content
    position = _bounded_position(getattr(ctx, "position", len(content)), len(content))
    half_window = _MAX_COMPLETION_SCAN_CHARS // 2
    start = max(0, position - half_window)
    end = min(len(content), position + half_window)
    return content[start:end]


def _add_prefixed(candidates: dict, words, prefix: str, detail: str) -> None:
    for word in words:
        if _matches_prefix(word, prefix):
            candidates.setdefault(word, {
                "label": word,
                "insert_text": word,
                "detail": detail,
            })


def _matches_prefix(word: str, prefix: str) -> bool:
    return len(word) > len(prefix) and word.lower().startswith(prefix.lower())


def _parse_ast(ctx):
    content = ctx.content or ""
    if len(content) > _MAX_AST_CHARS:
        return None, None
    key = _cache_key(ctx.path or "", content)
    cached = _AST_CACHE.get(key)
    if cached is not None:
        _AST_CACHE.move_to_end(key)
        return cached
    try:
        parsed = (ast.parse(content, filename=ctx.path or "<buffer>"), None)
    except SyntaxError as exc:
        parsed = (None, exc)
    _AST_CACHE[key] = parsed
    while len(_AST_CACHE) > _MAX_AST_CACHE_ENTRIES:
        _AST_CACHE.popitem(last=False)
    return parsed


def _cache_key(path: str, content: str) -> tuple[str, int, int]:
    return (path, len(content), hash(content))


def _syntax_diagnostic(ctx, exc: SyntaxError) -> dict:
    line = exc.lineno or 1
    column = max(0, (exc.offset or 1) - 1)
    end_line = exc.end_lineno or line
    end_column = max(column + 1, (exc.end_offset or exc.offset or 1) - 1)
    return {
        "path": ctx.path,
        "line": line,
        "column": column,
        "end_line": end_line,
        "end_column": end_column,
        "severity": "error",
        "source": "python ast",
        "code": "syntax-error",
        "message": exc.msg or "Syntax error",
    }


def _ruff_diagnostics(ctx):
    if len(ctx.content or "") > _MAX_RUFF_CHARS:
        return []
    path = ctx.path or "buffer.py"
    try:
        result = subprocess.run(
            [
                "ruff",
                "check",
                "--output-format=json",
                "--stdin-filename",
                path,
                "-",
            ],
            input=ctx.content,
            text=True,
            capture_output=True,
            check=False,
            timeout=_RUFF_TIMEOUT_SECONDS,
        )
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return []
    if result.returncode not in (0, 1):
        return []
    try:
        raw_items = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(raw_items, list):
        return []
    return [
        _ruff_item_to_diagnostic(item, path)
        for item in raw_items
        if isinstance(item, dict)
    ]


def _ruff_item_to_diagnostic(item: dict, path: str) -> dict:
    location = item.get("location") if isinstance(item.get("location"), dict) else {}
    end_location = item.get("end_location") if isinstance(item.get("end_location"), dict) else {}
    return {
        "path": str(item.get("filename") or path),
        "line": _positive_int(location.get("row"), 1),
        "column": max(0, _positive_int(location.get("column"), 1) - 1),
        "end_line": _optional_positive_int(end_location.get("row")),
        "end_column": _optional_ruff_column(end_location.get("column")),
        "severity": "warning",
        "source": "ruff",
        "code": str(item.get("code") or ""),
        "message": str(item.get("message") or "Ruff diagnostic"),
    }


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


def _bounded_position(value, content_length: int) -> int:
    try:
        return max(0, min(int(value), content_length))
    except (TypeError, ValueError):
        return content_length


def _optional_positive_int(value):
    if value is None:
        return None
    return _positive_int(value, 1)


def _optional_ruff_column(value):
    if value is None:
        return None
    return max(0, _positive_int(value, 1) - 1)
