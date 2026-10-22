"""
Unit tests for app/services/chunking_service.py

Validates:
- Code-aware chunking for Python (functions, classes, methods, imports)
- Code-aware chunking for JavaScript (functions, arrow functions, classes, methods)
- Keeping functions and classes together whenever possible
- Splitting oversized functions and classes safely
- Documentation files chunking (Markdown headings, paragraph breaks)
- Exact 1-based start_line and end_line preservation
- Exact source content match for every chunk
- Edge cases: empty files, whitespace, syntax errors, unsupported languages
- File-based chunking with chunk_file
"""

from pathlib import Path
import pytest

from app.services.chunking_service import (
    Chunk,
    chunk_content,
    chunk_file,
    is_documentation_file,
)


def _assert_chunk_invariants(chunks: list[Chunk], original_source: str):
    """
    Verify fundamental chunking invariants:
    1. 1-based indexing: start_line >= 1, end_line >= start_line.
    2. Exact content match: chunk.content must match lines[start-1 : end].
    3. line_count property equals end_line - start_line + 1.
    4. Sequential chunk_index starting from 0.
    """
    lines = original_source.splitlines()
    for idx, chunk in enumerate(chunks):
        assert chunk.chunk_index == idx
        assert chunk.start_line >= 1
        assert chunk.end_line >= chunk.start_line
        assert chunk.end_line <= len(lines)
        assert chunk.line_count == chunk.end_line - chunk.start_line + 1

        expected_slice = "\n".join(lines[chunk.start_line - 1 : chunk.end_line])
        assert chunk.content == expected_slice


# ===========================================================================
# 1. Documentation File Detection
# ===========================================================================

def test_is_documentation_file():
    assert is_documentation_file("docs/index.md") is True
    assert is_documentation_file("README.markdown") is True
    assert is_documentation_file("api.rst") is True
    assert is_documentation_file("notes.txt") is True
    assert is_documentation_file(language_hint="markdown") is True
    assert is_documentation_file(language_hint="rst") is True
    assert is_documentation_file("app/main.py") is False
    assert is_documentation_file("src/index.js") is False
    assert is_documentation_file(language_hint="python") is False


# ===========================================================================
# 2. Python Code-Aware Chunking (Functions & Classes Kept Together)
# ===========================================================================

def test_python_keep_functions_together():
    code = (
        "import os\n"
        "import sys\n"
        "\n"
        "def first_function(x: int) -> int:\n"
        "    y = x * 2\n"
        "    return y + 1\n"
        "\n"
        "def second_function(name: str) -> str:\n"
        "    return f'Hello, {name}'\n"
    )

    chunks = chunk_content(code, language="python", max_lines=50)

    _assert_chunk_invariants(chunks, code)
    assert len(chunks) == 3

    # Chunk 0: Imports / prelude
    assert chunks[0].chunk_type == "code"
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 2

    # Chunk 1: first_function
    assert chunks[1].chunk_type == "function"
    assert chunks[1].symbol_name == "first_function"
    assert chunks[1].start_line == 4
    assert chunks[1].end_line == 6

    # Chunk 2: second_function
    assert chunks[2].chunk_type == "function"
    assert chunks[2].symbol_name == "second_function"
    assert chunks[2].start_line == 8
    assert chunks[2].end_line == 9


def test_python_keep_class_together():
    code = (
        "class Calculator:\n"
        "    def __init__(self):\n"
        "        self.val = 0\n"
        "\n"
        "    def add(self, n):\n"
        "        self.val += n\n"
        "        return self.val\n"
    )

    chunks = chunk_content(code, language="python", max_lines=50)

    _assert_chunk_invariants(chunks, code)
    assert len(chunks) == 1

    cls_chunk = chunks[0]
    assert cls_chunk.chunk_type == "class"
    assert cls_chunk.symbol_name == "Calculator"
    assert cls_chunk.start_line == 1
    assert cls_chunk.end_line == 7


# ===========================================================================
# 3. Oversized Code Structures Splitting
# ===========================================================================

def test_python_split_oversized_function():
    # A function with 25 lines, with max_lines=10
    lines = ["def huge_function():"] + [f"    step_{i} = {i}" for i in range(1, 25)]
    code = "\n".join(lines)

    chunks = chunk_content(code, language="python", max_lines=10)

    _assert_chunk_invariants(chunks, code)
    assert len(chunks) >= 3

    # All lines must be accounted for without gaps
    for idx in range(len(chunks) - 1):
        assert chunks[idx + 1].start_line == chunks[idx].end_line + 1

    assert chunks[0].start_line == 1
    assert chunks[-1].end_line == 25
    for c in chunks:
        assert c.line_count <= 10


def test_python_split_oversized_class_by_methods():
    # A class with 3 methods. Total lines = 24. Setting max_lines=10 forces class split,
    # but each individual method (< 10 lines) should stay intact.
    code = (
        "class BigService:\n"
        "    version = 1\n"
        "\n"
        "    def method_alpha(self):\n"
        "        a = 1\n"
        "        b = 2\n"
        "        return a + b\n"
        "\n"
        "    def method_beta(self):\n"
        "        x = 'hello'\n"
        "        y = 'world'\n"
        "        return f'{x} {y}'\n"
        "\n"
        "    def method_gamma(self):\n"
        "        total = 0\n"
        "        for i in range(5):\n"
        "            total += i\n"
        "        return total\n"
    )

    chunks = chunk_content(code, language="python", max_lines=10)

    _assert_chunk_invariants(chunks, code)
    # The class should be split into header and its methods
    chunk_types = [c.chunk_type for c in chunks]
    assert "class" in chunk_types  # Prelude header
    assert "method" in chunk_types

    method_symbols = [c.symbol_name for c in chunks if c.chunk_type == "method"]
    assert "BigService.method_alpha" in method_symbols
    assert "BigService.method_beta" in method_symbols
    assert "BigService.method_gamma" in method_symbols


# ===========================================================================
# 4. JavaScript Code-Aware Chunking
# ===========================================================================

def test_javascript_chunking():
    code = (
        "import express from 'express';\n"
        "\n"
        "function handleRequest(req, res) {\n"
        "    res.json({ ok: true });\n"
        "}\n"
        "\n"
        "const calculateSum = (a, b) => {\n"
        "    return a + b;\n"
        "};\n"
        "\n"
        "class AppServer {\n"
        "    start() {\n"
        "        console.log('Listening');\n"
        "    }\n"
        "}\n"
    )

    chunks = chunk_content(code, language="javascript", max_lines=50)

    _assert_chunk_invariants(chunks, code)
    assert len(chunks) == 4

    # Imports
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 1

    # handleRequest function
    assert chunks[1].chunk_type == "function"
    assert chunks[1].symbol_name == "handleRequest"
    assert chunks[1].start_line == 3
    assert chunks[1].end_line == 5

    # calculateSum arrow function
    assert chunks[2].chunk_type == "function"
    assert chunks[2].symbol_name == "calculateSum"
    assert chunks[2].start_line == 7
    assert chunks[2].end_line == 9

    # AppServer class
    assert chunks[3].chunk_type == "class"
    assert chunks[3].symbol_name == "AppServer"
    assert chunks[3].start_line == 11
    assert chunks[3].end_line == 15


# ===========================================================================
# 5. Documentation Chunking (Markdown / RST / Plain Text)
# ===========================================================================

def test_markdown_heading_chunking():
    doc = (
        "# Project Overview\n"
        "This project is a code indexing and analysis tool.\n"
        "It supports Python and JavaScript.\n"
        "\n"
        "## Installation\n"
        "Run `pip install -r requirements.txt` to install.\n"
        "\n"
        "## Quick Start\n"
        "Import the service and call chunk_content.\n"
    )

    chunks = chunk_content(doc, language="markdown", max_lines=50)

    _assert_chunk_invariants(chunks, doc)
    assert len(chunks) == 3

    # Section 1: Overview
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 3
    assert "# Project Overview" in chunks[0].content

    # Section 2: Installation
    assert chunks[1].start_line == 5
    assert chunks[1].end_line == 6
    assert "## Installation" in chunks[1].content

    # Section 3: Quick Start
    assert chunks[2].start_line == 8
    assert chunks[2].end_line == 9
    assert "## Quick Start" in chunks[2].content


def test_markdown_oversized_section_split_by_paragraphs():
    # A single section with multiple paragraphs spanning 20 lines, max_lines=8
    doc = (
        "# Architecture Guide\n"
        "Paragraph 1 line A.\n"
        "Paragraph 1 line B.\n"
        "\n"
        "Paragraph 2 line A.\n"
        "Paragraph 2 line B.\n"
        "Paragraph 2 line C.\n"
        "\n"
        "Paragraph 3 line A.\n"
        "Paragraph 3 line B.\n"
    )

    chunks = chunk_content(doc, file_path="docs/arch.md", max_lines=6)

    _assert_chunk_invariants(chunks, doc)
    assert len(chunks) >= 2
    for c in chunks:
        assert c.line_count <= 6


def test_plain_text_chunking():
    text = (
        "First block of text.\n"
        "Still first block.\n"
        "\n"
        "Second block of text.\n"
        "Still second block.\n"
    )

    chunks = chunk_content(text, language="text", max_lines=50)

    _assert_chunk_invariants(chunks, text)
    assert len(chunks) >= 1


# ===========================================================================
# 6. Edge Cases & Resilience
# ===========================================================================

@pytest.mark.parametrize("empty_input", [
    "",
    "   ",
    "\n\n\r\n\t\t\n",
])
def test_empty_content(empty_input):
    assert chunk_content(empty_input, language="python") == []
    assert chunk_content(empty_input, language="markdown") == []
    assert chunk_content(empty_input) == []


def test_syntax_error_resilience():
    code = (
        "def valid_func():\n"
        "    return 42\n"
        "\n"
        "def broken():\n"
        "    x = \n"
        "\n"
        "def another_valid():\n"
        "    return 100\n"
    )

    chunks = chunk_content(code, language="python", max_lines=50)

    _assert_chunk_invariants(chunks, code)
    # Valid functions are preserved in chunks
    symbol_names = [c.symbol_name for c in chunks if c.symbol_name]
    assert "valid_func" in symbol_names
    assert "another_valid" in symbol_names


def test_unsupported_language_fallback():
    # Unsupported language safely falls back to line-based chunking without raising error
    code = (
        "fn main() {\n"
        "    println!(\"Hello Rust\");\n"
        "}\n"
    )
    chunks = chunk_content(code, language="rust", max_lines=10)

    _assert_chunk_invariants(chunks, code)
    assert len(chunks) == 1
    assert "println!" in chunks[0].content


# ===========================================================================
# 7. File-Based Chunking (chunk_file)
# ===========================================================================

def test_chunk_file_python(tmp_path: Path):
    py_file = tmp_path / "sample.py"
    content = (
        "def calculate(n: int) -> int:\n"
        "    return n * n\n"
    )
    py_file.write_text(content, encoding="utf-8")

    chunks = chunk_file(py_file)
    _assert_chunk_invariants(chunks, content)
    assert len(chunks) == 1
    assert chunks[0].symbol_name == "calculate"
    assert chunks[0].file_path == str(py_file)


def test_chunk_file_non_existent():
    chunks = chunk_file("non_existent_file.py")
    assert chunks == []
