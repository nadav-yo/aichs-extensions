from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Context:
    path: str = "demo.py"
    content: str = ""
    prefix: str = ""


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
