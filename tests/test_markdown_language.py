from __future__ import annotations

import importlib.util
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Context:
    cwd: str | None = None
    path: str = "demo.md"
    content: str = ""
    prefix: str = ""
    position: int = 0


def _load_extension():
    path = Path(__file__).resolve().parents[1] / "markdown-language" / "extension.py"
    spec = importlib.util.spec_from_file_location("markdown_language_extension", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_markdown_diagnostics_include_pymarkdown_when_available(monkeypatch):
    extension = _load_extension()

    def fake_run(*args, **kwargs):
        assert args[0][:2] == ["pymarkdown", "scan"]
        temp_path = args[0][2]
        assert temp_path.endswith(".md")
        assert Path(temp_path).read_text(encoding="utf-8") == "# Title\n# Other\n"
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=1,
            stdout=f"{temp_path}:2:1: MD025: Multiple top-level headings in the same document (single-title,single-h1)\n",
            stderr="",
        )

    monkeypatch.setattr(extension.subprocess, "run", fake_run)

    items = extension.diagnostics(Context(content="# Title\n# Other\n"))

    assert items == [{
        "path": "demo.md",
        "line": 2,
        "column": 0,
        "severity": "warning",
        "source": "pymarkdown",
        "code": "MD025",
        "message": "Multiple top-level headings in the same document (single-title,single-h1)",
    }]


def test_markdown_diagnostics_falls_back_when_pymarkdown_is_missing(monkeypatch):
    extension = _load_extension()

    def missing_pymarkdown(*_args, **_kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(extension.subprocess, "run", missing_pymarkdown)

    items = extension.diagnostics(Context(content="# Title\n# Other\n```python\nx = 1\n"))

    by_code = {item["code"]: item for item in items}
    assert by_code["multiple-h1"]["line"] == 2
    assert by_code["unclosed-fence"]["line"] == 3


def test_markdown_diagnostics_skips_pymarkdown_for_large_files(monkeypatch):
    extension = _load_extension()

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("pymarkdown should be skipped for large buffers")

    monkeypatch.setattr(extension.subprocess, "run", fail_if_called)
    content = "# Title\n" * 80_000

    assert extension.diagnostics(Context(content=content)) == []


def test_markdown_symbols_include_headings_and_skip_fenced_code():
    extension = _load_extension()
    content = "# Title\n\n```markdown\n# Not a heading\n```\n\n## Section\n"

    items = extension.symbols(Context(content=content))

    assert items == [
        {
            "path": "demo.md",
            "name": "Title",
            "kind": "heading 1",
            "line": 1,
            "column": 0,
            "end_line": 1,
            "end_column": 7,
        },
        {
            "path": "demo.md",
            "name": "Section",
            "kind": "heading 2",
            "line": 7,
            "column": 0,
            "end_line": 7,
            "end_column": 10,
        },
    ]


def test_markdown_completion_uses_prefix():
    extension = _load_extension()

    items = extension.completion(Context(prefix="ta"))

    assert {
        "label": "table",
        "insert_text": "| Column | Column |\n| --- | --- |\n| Value | Value |",
        "detail": "markdown snippet",
    } in items


def test_markdown_local_diagnostics_find_structural_issues(monkeypatch):
    extension = _load_extension()

    def missing_pymarkdown(*_args, **_kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(extension.subprocess, "run", missing_pymarkdown)
    content = "# Title\n\n### Jump\n\n##Missing Space\n\n[ref]: /one\n[REF]: /two\n"

    items = extension.diagnostics(Context(content=content))
    codes = {item["code"] for item in items}

    assert "heading-level-jump" in codes
    assert "heading-space" in codes
    assert "duplicate-reference" in codes


def test_register_contributes_markdown_language():
    extension = _load_extension()
    captured = {}

    class Registry:
        def metadata(self, **kwargs):
            captured["metadata"] = kwargs

        def language(self, **kwargs):
            captured["language"] = kwargs

    extension.register(Registry())

    language = captured["language"]
    assert language["name"] == "markdown"
    assert "*.md" in language["file_patterns"]
    assert "*.markdown" in language["file_patterns"]
    assert callable(language["diagnostics"])
    assert callable(language["symbols"])
    assert callable(language["completion"])
    assert "code_actions" not in language
    assert "format_document" not in language
