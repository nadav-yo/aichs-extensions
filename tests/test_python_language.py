from __future__ import annotations

import importlib.util
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Context:
    path: str = "demo.py"
    content: str = ""
    prefix: str = ""
    position: int = 0


def _load_extension():
    path = Path(__file__).resolve().parents[1] / "python-language" / "extension.py"
    spec = importlib.util.spec_from_file_location("python_language_extension", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_python_diagnostics_reports_syntax_error():
    extension = _load_extension()

    items = extension.diagnostics(Context(content="def bad(:\n    pass\n"))

    assert len(items) == 1
    assert items[0]["severity"] == "error"
    assert items[0]["source"] == "python ast"
    assert items[0]["line"] == 1


def test_python_diagnostics_includes_ruff_when_available(monkeypatch):
    extension = _load_extension()

    def fake_run(*args, **kwargs):
        assert args[0][:3] == ["ruff", "check", "--output-format=json"]
        assert "--stdin-filename" in args[0]
        assert kwargs["input"] == "import os\n"
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=1,
            stdout=json.dumps([{
                "filename": "demo.py",
                "code": "F401",
                "message": "`os` imported but unused",
                "location": {"row": 1, "column": 8},
                "end_location": {"row": 1, "column": 10},
            }]),
            stderr="",
        )

    monkeypatch.setattr(extension.subprocess, "run", fake_run)

    items = extension.diagnostics(Context(content="import os\n"))

    assert items == [{
        "path": "demo.py",
        "line": 1,
        "column": 7,
        "end_line": 1,
        "end_column": 9,
        "severity": "warning",
        "source": "ruff",
        "code": "F401",
        "message": "`os` imported but unused",
    }]


def test_python_diagnostics_falls_back_when_ruff_is_missing(monkeypatch):
    extension = _load_extension()

    def missing_ruff(*_args, **_kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(extension.subprocess, "run", missing_ruff)

    assert extension.diagnostics(Context(content="x = 1\n")) == []


def test_python_diagnostics_skips_ruff_for_large_files(monkeypatch):
    extension = _load_extension()

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("ruff should be skipped for large buffers")

    monkeypatch.setattr(extension.subprocess, "run", fail_if_called)
    content = "x = 1\n" * 90_000

    assert extension.diagnostics(Context(content=content)) == []


def test_python_completion_scans_bounded_window_and_skips_large_ast(monkeypatch):
    extension = _load_extension()

    def fail_if_parse_called(*_args, **_kwargs):
        raise AssertionError("AST parsing should be skipped for large completion buffers")

    monkeypatch.setattr(extension.ast, "parse", fail_if_parse_called)
    content = ("alpha_name = 1\n" * 30_000) + "target_value = 2\n"

    items = extension.completion(Context(
        content=content,
        prefix="tar",
        position=len(content),
    ))

    assert {"label": "target_value", "insert_text": "target_value", "detail": "document"} in items
    assert all(item["label"] != "alpha_name" for item in items)


def test_python_symbols_reuses_cached_ast(monkeypatch):
    extension = _load_extension()
    calls = []
    real_parse = extension.ast.parse

    def counted_parse(*args, **kwargs):
        calls.append(args[0])
        return real_parse(*args, **kwargs)

    monkeypatch.setattr(extension.ast, "parse", counted_parse)
    ctx = Context(content="class App:\n    pass\n")

    assert extension.symbols(ctx)
    assert extension.symbols(ctx)
    assert len(calls) == 1


def test_python_symbols_include_classes_methods_and_variables():
    extension = _load_extension()
    content = """
VALUE = 1

class App:
    async def start(self):
        pass

def build():
    return App()
""".strip()

    items = extension.symbols(Context(content=content))

    by_name = {item["name"]: item["kind"] for item in items}
    assert by_name["VALUE"] == "variable"
    assert by_name["App"] == "class"
    assert by_name["start"] == "async method"
    assert by_name["build"] == "function"


def test_python_completion_uses_prefix():
    extension = _load_extension()

    items = extension.completion(Context(content="class Renderer:\n    pass\n", prefix="Ren"))

    assert {"label": "Renderer", "insert_text": "Renderer", "detail": "document"} in items


def test_register_contributes_python_language():
    extension = _load_extension()
    captured = {}

    class Registry:
        def metadata(self, **kwargs):
            captured["metadata"] = kwargs

        def language(self, **kwargs):
            captured["language"] = kwargs

    extension.register(Registry())

    language = captured["language"]
    assert language["name"] == "python"
    assert "*.py" in language["file_patterns"]
    assert callable(language["diagnostics"])
    assert callable(language["symbols"])
    assert callable(language["completion"])
