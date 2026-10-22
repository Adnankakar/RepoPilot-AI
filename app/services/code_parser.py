"""
code_parser.py

Extracts top-level and nested functions, classes, and methods from Python
and JavaScript source files using tree-sitter.

Capabilities:
- Python parsing (functions, async functions, classes, methods, decorated definitions)
- JavaScript parsing (function declarations, generator functions, arrow functions,
  function expressions, class declarations, class expressions, methods, exported symbols)
- Accurate 1-indexed start and end lines
- Safe handling of empty and whitespace-only files
- Fault-tolerant parsing of files containing syntax errors
- Safe handling of unsupported languages and missing files without unhandled crashes
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from tree_sitter import Language, Node, Parser, Tree
import tree_sitter_javascript
import tree_sitter_python

logger = logging.getLogger(__name__)


class SymbolType(str, Enum):
    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"


@dataclass(frozen=True)
class CodeSymbol:
    name: str
    symbol_type: SymbolType
    start_line: int  # 1-indexed
    end_line: int  # 1-indexed
    start_column: int = 0  # 0-indexed column
    end_column: int = 0  # 0-indexed column
    parent_name: str | None = None
    is_async: bool = False
    is_method: bool = False

    @property
    def is_function(self) -> bool:
        return self.symbol_type in (SymbolType.FUNCTION, SymbolType.METHOD)

    @property
    def is_class(self) -> bool:
        return self.symbol_type == SymbolType.CLASS


@dataclass
class ParseResult:
    symbols: list[CodeSymbol] = field(default_factory=list)
    language: str | None = None
    is_supported: bool = True
    has_syntax_errors: bool = False
    error_message: str | None = None

    @property
    def functions(self) -> list[CodeSymbol]:
        return [s for s in self.symbols if s.is_function]

    @property
    def classes(self) -> list[CodeSymbol]:
        return [s for s in self.symbols if s.is_class]


# ---------------------------------------------------------------------------
# Supported Languages & Extension Mappings
# ---------------------------------------------------------------------------

_PYTHON_ALIASES = frozenset({"python", "py"})
_PYTHON_EXTENSIONS = frozenset({".py", ".pyi", ".pyw"})

_JAVASCRIPT_ALIASES = frozenset({"javascript", "js"})
_JAVASCRIPT_EXTENSIONS = frozenset({".js", ".jsx", ".mjs", ".cjs"})

_LANGUAGES: dict[str, Language] = {
    "python": Language(tree_sitter_python.language()),
    "javascript": Language(tree_sitter_javascript.language()),
}


def detect_language(
    file_path: str | Path | None = None,
    language_hint: str | None = None,
) -> str | None:
    """
    Resolve the canonical language name ("python", "javascript") from an explicit
    hint or a file path extension. Returns None if unsupported or indeterminate.
    """
    if language_hint:
        hint_clean = language_hint.strip().lower()
        if hint_clean in _PYTHON_ALIASES:
            return "python"
        if hint_clean in _JAVASCRIPT_ALIASES:
            return "javascript"
        return hint_clean

    if file_path is not None:
        path = Path(file_path)
        suffix = path.suffix.lower()
        if suffix in _PYTHON_EXTENSIONS:
            return "python"
        if suffix in _JAVASCRIPT_EXTENSIONS:
            return "javascript"

    return None


def _get_parser(language: str) -> Parser | None:
    lang_obj = _LANGUAGES.get(language)
    if lang_obj is None:
        return None
    return Parser(lang_obj)


def _node_text(node: Node, source_bytes: bytes) -> str:
    return source_bytes[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _calc_start_line(node: Node) -> int:
    # 0-indexed row -> 1-indexed line
    return node.start_point[0] + 1


def _calc_end_line(node: Node) -> int:
    # If end_point column is 0 and it spans past start row, it ends at previous line
    if node.end_point[1] == 0 and node.end_point[0] > node.start_point[0]:
        return node.end_point[0]
    return node.end_point[0] + 1


# ---------------------------------------------------------------------------
# Python AST Extraction
# ---------------------------------------------------------------------------

def _extract_python_symbols(
    node: Node,
    source_bytes: bytes,
    symbols: list[CodeSymbol],
    parent_class: str | None = None,
    parent_func: str | None = None,
) -> None:
    for child in node.children:
        # 1. Decorated functions / classes
        if child.type == "decorated_definition":
            definition_node = None
            for sub in child.children:
                if sub.type in ("function_definition", "class_definition"):
                    definition_node = sub
                    break

            if definition_node is not None:
                _process_python_def(
                    def_node=definition_node,
                    span_node=child,
                    source_bytes=source_bytes,
                    symbols=symbols,
                    parent_class=parent_class,
                    parent_func=parent_func,
                )
            else:
                _extract_python_symbols(
                    child,
                    source_bytes,
                    symbols,
                    parent_class=parent_class,
                    parent_func=parent_func,
                )

        # 2. Undecorated function or class definitions
        elif child.type in ("function_definition", "class_definition"):
            # Avoid re-processing if directly wrapped in decorated_definition
            if node.type != "decorated_definition":
                _process_python_def(
                    def_node=child,
                    span_node=child,
                    source_bytes=source_bytes,
                    symbols=symbols,
                    parent_class=parent_class,
                    parent_func=parent_func,
                )

        else:
            _extract_python_symbols(
                child,
                source_bytes,
                symbols,
                parent_class=parent_class,
                parent_func=parent_func,
            )


def _process_python_def(
    def_node: Node,
    span_node: Node,
    source_bytes: bytes,
    symbols: list[CodeSymbol],
    parent_class: str | None,
    parent_func: str | None,
) -> None:
    name_node = def_node.child_by_field_name("name")
    name = _node_text(name_node, source_bytes) if name_node else "(anonymous)"

    start_line = _calc_start_line(span_node)
    end_line = _calc_end_line(span_node)
    start_column = span_node.start_point[1]
    end_column = span_node.end_point[1]

    if def_node.type == "function_definition":
        is_async = any(c.type == "async" for c in def_node.children) or (
            span_node.type == "decorated_definition"
            and any(c.type == "async" for c in span_node.children)
        )
        is_method = parent_class is not None
        parent_name = parent_class if is_method else parent_func

        symbols.append(
            CodeSymbol(
                name=name,
                symbol_type=SymbolType.FUNCTION,
                start_line=start_line,
                end_line=end_line,
                start_column=start_column,
                end_column=end_column,
                parent_name=parent_name,
                is_async=is_async,
                is_method=is_method,
            )
        )

        body_node = def_node.child_by_field_name("body")
        if body_node:
            _extract_python_symbols(
                body_node,
                source_bytes,
                symbols,
                parent_class=parent_class,
                parent_func=name,
            )

    elif def_node.type == "class_definition":
        symbols.append(
            CodeSymbol(
                name=name,
                symbol_type=SymbolType.CLASS,
                start_line=start_line,
                end_line=end_line,
                start_column=start_column,
                end_column=end_column,
                parent_name=parent_class,
                is_async=False,
                is_method=False,
            )
        )

        body_node = def_node.child_by_field_name("body")
        if body_node:
            _extract_python_symbols(
                body_node,
                source_bytes,
                symbols,
                parent_class=name,
                parent_func=None,
            )


# ---------------------------------------------------------------------------
# JavaScript AST Extraction
# ---------------------------------------------------------------------------

def _extract_javascript_symbols(
    node: Node,
    source_bytes: bytes,
    symbols: list[CodeSymbol],
    parent_class: str | None = None,
    parent_func: str | None = None,
) -> None:
    for child in node.children:
        node_type = child.type

        # 1. Standard function declaration, generator, or named/exported function expression
        if node_type in ("function_declaration", "generator_function_declaration") or (
            node_type == "function_expression"
            and (child.child_by_field_name("name") is not None or node.type == "export_statement")
        ):
            name_node = child.child_by_field_name("name")
            if name_node:
                name = _node_text(name_node, source_bytes)
            elif node.type == "export_statement":
                name = "default"
            else:
                name = "(anonymous)"

            is_async = any(c.type == "async" for c in child.children)

            symbols.append(
                CodeSymbol(
                    name=name,
                    symbol_type=SymbolType.FUNCTION,
                    start_line=_calc_start_line(child),
                    end_line=_calc_end_line(child),
                    start_column=child.start_point[1],
                    end_column=child.end_point[1],
                    parent_name=parent_class or parent_func,
                    is_async=is_async,
                    is_method=parent_class is not None,
                )
            )

            body_node = child.child_by_field_name("body")
            if body_node:
                _extract_javascript_symbols(
                    body_node,
                    source_bytes,
                    symbols,
                    parent_class=parent_class,
                    parent_func=name,
                )

        # 2. Class declaration: class Foo {}
        elif node_type == "class_declaration":
            name_node = child.child_by_field_name("name")
            name = _node_text(name_node, source_bytes) if name_node else "(anonymous)"

            symbols.append(
                CodeSymbol(
                    name=name,
                    symbol_type=SymbolType.CLASS,
                    start_line=_calc_start_line(child),
                    end_line=_calc_end_line(child),
                    start_column=child.start_point[1],
                    end_column=child.end_point[1],
                    parent_name=parent_class,
                    is_async=False,
                    is_method=False,
                )
            )

            body_node = child.child_by_field_name("body")
            if body_node:
                _extract_javascript_symbols(
                    body_node,
                    source_bytes,
                    symbols,
                    parent_class=name,
                    parent_func=None,
                )

        # 3. Method definition inside class or object: myMethod() {}, get x() {}, set x() {}
        elif node_type == "method_definition":
            name_node = child.child_by_field_name("name")
            name = _node_text(name_node, source_bytes) if name_node else "(anonymous)"
            is_async = any(c.type == "async" for c in child.children)

            symbols.append(
                CodeSymbol(
                    name=name,
                    symbol_type=SymbolType.FUNCTION,
                    start_line=_calc_start_line(child),
                    end_line=_calc_end_line(child),
                    start_column=child.start_point[1],
                    end_column=child.end_point[1],
                    parent_name=parent_class,
                    is_async=is_async,
                    is_method=True,
                )
            )

            body_node = child.child_by_field_name("body")
            if body_node:
                _extract_javascript_symbols(
                    body_node,
                    source_bytes,
                    symbols,
                    parent_class=parent_class,
                    parent_func=name,
                )

        # 4. Variable declarations with arrow functions, function expressions, or class expressions
        # e.g.: const foo = () => {}, let bar = function() {}, const Baz = class {}
        elif node_type == "variable_declarator":
            name_node = child.child_by_field_name("name")
            value_node = child.child_by_field_name("value")

            if name_node and value_node:
                var_name = _node_text(name_node, source_bytes)

                if value_node.type in ("arrow_function", "function_expression"):
                    is_async = any(c.type == "async" for c in value_node.children)
                    symbols.append(
                        CodeSymbol(
                            name=var_name,
                            symbol_type=SymbolType.FUNCTION,
                            start_line=_calc_start_line(child),
                            end_line=_calc_end_line(child),
                            start_column=child.start_point[1],
                            end_column=child.end_point[1],
                            parent_name=parent_class or parent_func,
                            is_async=is_async,
                            is_method=parent_class is not None,
                        )
                    )
                    body_node = value_node.child_by_field_name("body")
                    if body_node:
                        _extract_javascript_symbols(
                            body_node,
                            source_bytes,
                            symbols,
                            parent_class=parent_class,
                            parent_func=var_name,
                        )

                elif value_node.type == "class":
                    symbols.append(
                        CodeSymbol(
                            name=var_name,
                            symbol_type=SymbolType.CLASS,
                            start_line=_calc_start_line(child),
                            end_line=_calc_end_line(child),
                            start_column=child.start_point[1],
                            end_column=child.end_point[1],
                            parent_name=parent_class,
                            is_async=False,
                            is_method=False,
                        )
                    )
                    body_node = value_node.child_by_field_name("body")
                    if body_node:
                        _extract_javascript_symbols(
                            body_node,
                            source_bytes,
                            symbols,
                            parent_class=var_name,
                            parent_func=None,
                        )
                else:
                    _extract_javascript_symbols(
                        child,
                        source_bytes,
                        symbols,
                        parent_class=parent_class,
                        parent_func=parent_func,
                    )
            else:
                _extract_javascript_symbols(
                    child,
                    source_bytes,
                    symbols,
                    parent_class=parent_class,
                    parent_func=parent_func,
                )

        # 5. Export default function / class without declaration
        elif node_type == "export_statement":
            # Recurse through export children (declarations, variable_declarations, etc.)
            _extract_javascript_symbols(
                child,
                source_bytes,
                symbols,
                parent_class=parent_class,
                parent_func=parent_func,
            )

        else:
            _extract_javascript_symbols(
                child,
                source_bytes,
                symbols,
                parent_class=parent_class,
                parent_func=parent_func,
            )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_code(
    code: str | bytes,
    language: str | None = None,
    file_path: str | Path | None = None,
) -> ParseResult:
    """
    Parse Python or JavaScript code and extract functions and classes with their
    exact start and end lines.

    Parameters:
        code: Source code as string or bytes.
        language: Explicit language hint ("python", "javascript", etc.).
        file_path: Optional file path or filename to infer language from extension.

    Returns:
        ParseResult containing extracted symbols, language, support status, and syntax error flags.
    """
    resolved_lang = detect_language(file_path=file_path, language_hint=language)

    if resolved_lang is None or resolved_lang not in _LANGUAGES:
        unsupported_name = resolved_lang or (
            Path(file_path).suffix if file_path else (language or "unknown")
        )
        return ParseResult(
            symbols=[],
            language=resolved_lang,
            is_supported=False,
            has_syntax_errors=False,
            error_message=f"Unsupported language: '{unsupported_name}'",
        )

    # Convert code to bytes safely
    if isinstance(code, str):
        source_bytes = code.encode("utf-8")
    elif isinstance(code, (bytes, bytearray)):
        source_bytes = bytes(code)
    else:
        return ParseResult(
            symbols=[],
            language=resolved_lang,
            is_supported=True,
            has_syntax_errors=False,
            error_message="Invalid code input type: expected str or bytes",
        )

    # Empty or whitespace-only check
    if not source_bytes.strip():
        return ParseResult(
            symbols=[],
            language=resolved_lang,
            is_supported=True,
            has_syntax_errors=False,
        )

    parser = _get_parser(resolved_lang)
    if parser is None:
        return ParseResult(
            symbols=[],
            language=resolved_lang,
            is_supported=False,
            error_message=f"Parser could not be initialized for: '{resolved_lang}'",
        )

    try:
        tree: Tree = parser.parse(source_bytes)
    except Exception as exc:
        logger.error("Error parsing code with tree-sitter: %s", exc, exc_info=True)
        return ParseResult(
            symbols=[],
            language=resolved_lang,
            is_supported=True,
            has_syntax_errors=True,
            error_message=str(exc),
        )

    has_syntax_errors = tree.root_node.has_error
    symbols: list[CodeSymbol] = []

    try:
        if resolved_lang == "python":
            _extract_python_symbols(tree.root_node, source_bytes, symbols)
        elif resolved_lang == "javascript":
            _extract_javascript_symbols(tree.root_node, source_bytes, symbols)
    except Exception as exc:
        logger.error("Unexpected error traversing AST: %s", exc, exc_info=True)
        return ParseResult(
            symbols=symbols,
            language=resolved_lang,
            is_supported=True,
            has_syntax_errors=True,
            error_message=str(exc),
        )

    return ParseResult(
        symbols=symbols,
        language=resolved_lang,
        is_supported=True,
        has_syntax_errors=has_syntax_errors,
        error_message="Syntax errors encountered during parsing" if has_syntax_errors else None,
    )


def parse_file(
    file_path: str | Path,
    language: str | None = None,
) -> ParseResult:
    """
    Read a file from disk and parse it. Safe against missing files, unreadable files,
    and unsupported languages.
    """
    path = Path(file_path)
    if not path.is_file():
        logger.warning("parse_file: file does not exist or is not a file: %s", file_path)
        resolved_lang = detect_language(file_path=file_path, language_hint=language)
        return ParseResult(
            symbols=[],
            language=resolved_lang,
            is_supported=resolved_lang in _LANGUAGES if resolved_lang else False,
            has_syntax_errors=False,
            error_message=f"File not found: {file_path}",
        )

    try:
        content_bytes = path.read_bytes()
    except Exception as exc:
        logger.error("parse_file: failed to read file %s: %s", file_path, exc)
        resolved_lang = detect_language(file_path=file_path, language_hint=language)
        return ParseResult(
            symbols=[],
            language=resolved_lang,
            is_supported=resolved_lang in _LANGUAGES if resolved_lang else False,
            has_syntax_errors=False,
            error_message=f"Could not read file: {exc}",
        )

    return parse_code(code=content_bytes, language=language, file_path=file_path)
