"""Python language support for aichs.

This extension intentionally starts with the Python standard library so it can
be installed without native dependencies. Optional Tree-sitter support can be
added beside this file later without changing the public registry contract.
"""

from __future__ import annotations

import ast
import builtins
import keyword
import re


EXTENSION_DESCRIPTION = "Adds Python syntax diagnostics, symbols, and completion for the file editor."

_WORD_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
_SNIPPETS = {
    "class": "class Name:\n    pass",
    "def": "def name():\n    pass",
    "try": "try:\n    pass\nexcept Exception as exc:\n    pass",
    "with": "with expression as value:\n    pass",
}


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
    try:
        ast.parse(ctx.content, filename=ctx.path or "<buffer>")
    except SyntaxError as exc:
        line = exc.lineno or 1
        column = max(0, (exc.offset or 1) - 1)
        end_line = exc.end_lineno or line
        end_column = max(column + 1, (exc.end_offset or exc.offset or 1) - 1)
        return [{
            "path": ctx.path,
            "line": line,
            "column": column,
            "end_line": end_line,
            "end_column": end_column,
            "severity": "error",
            "source": "python ast",
            "code": "syntax-error",
            "message": exc.msg or "Syntax error",
        }]
    return []


def symbols(ctx):
    try:
        tree = ast.parse(ctx.content, filename=ctx.path or "<buffer>")
    except SyntaxError:
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
    _add_prefixed(candidates, _document_words(ctx.content), prefix, "document")

    for label, insert_text in _SNIPPETS.items():
        if _matches_prefix(label, prefix):
            candidates[label] = {
                "label": label,
                "insert_text": insert_text,
                "detail": "snippet",
            }

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
