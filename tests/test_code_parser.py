"""
Unit tests for app/services/code_parser.py

Tests cover:
- Python parsing (functions, async functions, classes, methods, decorators, nested functions)
- JavaScript parsing (function declarations, generator functions, arrow functions,
  function expressions, class declarations, class expressions, methods, exports)
- Exact start and end line calculations
- Empty files and whitespace-only content
- Syntax error resilience and partial AST extraction
- Unsupported languages and unknown file extensions
- File-based parsing with parse_file (existing files and non-existent files)
- Helper properties and data structures
"""

from pathlib import Path
import pytest

from app.services.code_parser import (
    CodeSymbol,
    ParseResult,
    SymbolType,
    detect_language,
    parse_code,
    parse_file,
)


# ===========================================================================
# 1. Language Detection Tests
# ===========================================================================

def test_detect_language_by_hint():
    assert detect_language(language_hint="python") == "python"
    assert detect_language(language_hint="Python") == "python"
    assert detect_language(language_hint="py") == "python"
    assert detect_language(language_hint="javascript") == "javascript"
    assert detect_language(language_hint="JS") == "javascript"
    assert detect_language(language_hint="js") == "javascript"
    assert detect_language(language_hint="ruby") == "ruby"


def test_detect_language_by_path():
    assert detect_language(file_path="app/main.py") == "python"
    assert detect_language(file_path="types.pyi") == "python"
    assert detect_language(file_path="src/index.js") == "javascript"
    assert detect_language(file_path="component.jsx") == "javascript"
    assert detect_language(file_path="server.mjs") == "javascript"
    assert detect_language(file_path="config.cjs") == "javascript"
    assert detect_language(file_path="README.md") is None
    assert detect_language(file_path="binary.dat") is None


def test_detect_language_precedence():
    # Explicit hint takes precedence over file extension
    assert detect_language(file_path="script.js", language_hint="python") == "python"
    assert detect_language(file_path="script.py", language_hint="javascript") == "javascript"


# ===========================================================================
# 2. Python Extraction Tests
# ===========================================================================

def test_parse_python_simple_function():
    code = (
        "def add(a: int, b: int) -> int:\n"
        "    return a + b\n"
    )
    result = parse_code(code, language="python")

    assert result.is_supported is True
    assert result.has_syntax_errors is False
    assert len(result.symbols) == 1

    sym = result.symbols[0]
    assert sym.name == "add"
    assert sym.symbol_type == SymbolType.FUNCTION
    assert sym.is_function is True
    assert sym.is_class is False
    assert sym.is_async is False
    assert sym.is_method is False
    assert sym.parent_name is None
    assert sym.start_line == 1
    assert sym.end_line == 2


def test_parse_python_async_function():
    code = (
        "async def fetch_data(url: str):\n"
        "    pass\n"
    )
    result = parse_code(code, language="python")

    assert len(result.symbols) == 1
    sym = result.symbols[0]
    assert sym.name == "fetch_data"
    assert sym.symbol_type == SymbolType.FUNCTION
    assert sym.is_async is True
    assert sym.start_line == 1
    assert sym.end_line == 2


def test_parse_python_class_with_methods():
    code = (
        "class Calculator:\n"
        "    def __init__(self):\n"
        "        self.total = 0\n"
        "\n"
        "    def add(self, n: int) -> int:\n"
        "        self.total += n\n"
        "        return self.total\n"
    )
    result = parse_code(code, language="python")

    assert result.is_supported is True
    assert len(result.symbols) == 3

    cls_sym = result.classes[0]
    assert cls_sym.name == "Calculator"
    assert cls_sym.symbol_type == SymbolType.CLASS
    assert cls_sym.is_class is True
    assert cls_sym.start_line == 1
    assert cls_sym.end_line == 7

    methods = [s for s in result.symbols if s.is_method]
    assert len(methods) == 2

    init_method = methods[0]
    assert init_method.name == "__init__"
    assert init_method.parent_name == "Calculator"
    assert init_method.is_method is True
    assert init_method.start_line == 2
    assert init_method.end_line == 3

    add_method = methods[1]
    assert add_method.name == "add"
    assert add_method.parent_name == "Calculator"
    assert add_method.is_method is True
    assert add_method.start_line == 5
    assert add_method.end_line == 7


def test_parse_python_decorated_function_and_class():
    code = (
        "@router.get('/items')\n"
        "@auth_required\n"
        "def get_items():\n"
        "    return []\n"
        "\n"
        "@dataclass\n"
        "class Item:\n"
        "    id: int\n"
    )
    result = parse_code(code, language="python")

    assert len(result.symbols) == 2
    func_sym = result.symbols[0]
    assert func_sym.name == "get_items"
    assert func_sym.start_line == 1  # Includes decorator
    assert func_sym.end_line == 4

    cls_sym = result.symbols[1]
    assert cls_sym.name == "Item"
    assert cls_sym.start_line == 6  # Includes @dataclass
    assert cls_sym.end_line == 8


def test_parse_python_nested_functions_and_classes():
    code = (
        "def outer():\n"
        "    def inner():\n"
        "        return 42\n"
        "    return inner()\n"
        "\n"
        "class OuterClass:\n"
        "    class InnerClass:\n"
        "        def inner_method(self):\n"
        "            pass\n"
    )
    result = parse_code(code, language="python")

    names = [s.name for s in result.symbols]
    assert names == ["outer", "inner", "OuterClass", "InnerClass", "inner_method"]

    inner_func = [s for s in result.symbols if s.name == "inner"][0]
    assert inner_func.parent_name == "outer"
    assert inner_func.start_line == 2
    assert inner_func.end_line == 3

    inner_cls = [s for s in result.symbols if s.name == "InnerClass"][0]
    assert inner_cls.parent_name == "OuterClass"
    assert inner_cls.start_line == 7
    assert inner_cls.end_line == 9

    inner_meth = [s for s in result.symbols if s.name == "inner_method"][0]
    assert inner_meth.parent_name == "InnerClass"
    assert inner_meth.is_method is True
    assert inner_meth.start_line == 8
    assert inner_meth.end_line == 9


# ===========================================================================
# 3. JavaScript Extraction Tests
# ===========================================================================

def test_parse_javascript_functions():
    code = (
        "function regular(a, b) {\n"
        "    return a + b;\n"
        "}\n"
        "\n"
        "async function fetchUser(id) {\n"
        "    return { id };\n"
        "}\n"
        "\n"
        "function* idGenerator() {\n"
        "    yield 1;\n"
        "}\n"
    )
    result = parse_code(code, language="javascript")

    assert result.is_supported is True
    assert len(result.symbols) == 3

    reg = result.symbols[0]
    assert reg.name == "regular"
    assert reg.symbol_type == SymbolType.FUNCTION
    assert reg.start_line == 1
    assert reg.end_line == 3
    assert reg.is_async is False

    async_fn = result.symbols[1]
    assert async_fn.name == "fetchUser"
    assert async_fn.is_async is True
    assert async_fn.start_line == 5
    assert async_fn.end_line == 7

    gen_fn = result.symbols[2]
    assert gen_fn.name == "idGenerator"
    assert gen_fn.start_line == 9
    assert gen_fn.end_line == 11


def test_parse_javascript_arrow_and_expression_functions():
    code = (
        "const multiply = (x, y) => {\n"
        "    return x * y;\n"
        "};\n"
        "\n"
        "let doAsync = async (val) => val * 2;\n"
        "\n"
        "var legacyFunc = function(z) {\n"
        "    return z;\n"
        "};\n"
    )
    result = parse_code(code, language="javascript")

    assert len(result.symbols) == 3

    arrow = result.symbols[0]
    assert arrow.name == "multiply"
    assert arrow.is_function is True
    assert arrow.is_async is False
    assert arrow.start_line == 1
    assert arrow.end_line == 3

    async_arrow = result.symbols[1]
    assert async_arrow.name == "doAsync"
    assert async_arrow.is_async is True
    assert async_arrow.start_line == 5
    assert async_arrow.end_line == 5

    func_expr = result.symbols[2]
    assert func_expr.name == "legacyFunc"
    assert func_expr.start_line == 7
    assert func_expr.end_line == 9


def test_parse_javascript_class_and_methods():
    code = (
        "class UserService {\n"
        "    constructor(db) {\n"
        "        this.db = db;\n"
        "    }\n"
        "\n"
        "    async getUser(id) {\n"
        "        return this.db.find(id);\n"
        "    }\n"
        "\n"
        "    static create() {\n"
        "        return new UserService();\n"
        "    }\n"
        "}\n"
    )
    result = parse_code(code, language="javascript")

    assert len(result.classes) == 1
    cls = result.classes[0]
    assert cls.name == "UserService"
    assert cls.start_line == 1
    assert cls.end_line == 13

    methods = [s for s in result.symbols if s.is_method]
    assert len(methods) == 3

    ctor = methods[0]
    assert ctor.name == "constructor"
    assert ctor.parent_name == "UserService"
    assert ctor.start_line == 2
    assert ctor.end_line == 4

    get_user = methods[1]
    assert get_user.name == "getUser"
    assert get_user.parent_name == "UserService"
    assert get_user.is_async is True
    assert get_user.start_line == 6
    assert get_user.end_line == 8

    create_fn = methods[2]
    assert create_fn.name == "create"
    assert create_fn.parent_name == "UserService"
    assert create_fn.start_line == 10
    assert create_fn.end_line == 12


def test_parse_javascript_exports_and_class_expression():
    code = (
        "export function exportedFn() {\n"
        "    return 1;\n"
        "}\n"
        "\n"
        "export default class ExportedClass {\n"
        "    greet() {}\n"
        "}\n"
        "\n"
        "const AnonymousClass = class {\n"
        "    run() {}\n"
        "};\n"
    )
    result = parse_code(code, language="javascript")

    names = [s.name for s in result.symbols]
    assert "exportedFn" in names
    assert "ExportedClass" in names
    assert "greet" in names
    assert "AnonymousClass" in names
    assert "run" in names


# ===========================================================================
# 4. Empty Files and Whitespace
# ===========================================================================

@pytest.mark.parametrize("empty_content", [
    "",
    b"",
    "   ",
    "\n\n\r\n\t\t   \n",
    b"   \n  \t  ",
])
def test_parse_empty_content(empty_content):
    result_py = parse_code(empty_content, language="python")
    assert result_py.symbols == []
    assert result_py.is_supported is True
    assert result_py.has_syntax_errors is False

    result_js = parse_code(empty_content, language="javascript")
    assert result_js.symbols == []
    assert result_js.is_supported is True
    assert result_js.has_syntax_errors is False


# ===========================================================================
# 5. Syntax Errors Resilience
# ===========================================================================

def test_parse_python_with_syntax_errors():
    code = (
        "def valid_first():\n"
        "    return 1\n"
        "\n"
        "def broken_func(\n"
        "    something missing closing paren\n"
        "\n"
        "def valid_second():\n"
        "    return 2\n"
    )
    result = parse_code(code, language="python")

    assert result.is_supported is True
    assert result.has_syntax_errors is True
    assert result.error_message is not None

    # Valid functions surrounding the syntax error are preserved
    names = [s.name for s in result.symbols]
    assert "valid_first" in names
    assert "valid_second" in names


def test_parse_javascript_with_syntax_errors():
    code = (
        "function validFirst() {\n"
        "    return 1;\n"
        "}\n"
        "\n"
        "function badSyntax( {\n"
        "    ???;\n"
        "\n"
        "function validSecond() {\n"
        "    return 2;\n"
        "}\n"
    )
    result = parse_code(code, language="javascript")

    assert result.is_supported is True
    assert result.has_syntax_errors is True

    names = [s.name for s in result.symbols]
    assert "validFirst" in names
    assert "validSecond" in names


# ===========================================================================
# 6. Unsupported Languages & Safety
# ===========================================================================

@pytest.mark.parametrize("unsupported_lang", [
    "rust",
    "golang",
    "ruby",
    "csharp",
    "unknown_lang",
])
def test_parse_unsupported_language_by_name(unsupported_lang):
    result = parse_code("fn main() {}", language=unsupported_lang)
    assert result.is_supported is False
    assert result.symbols == []
    assert "Unsupported language" in result.error_message


def test_parse_unsupported_language_by_path():
    result = parse_code("fn main() {}", file_path="main.rs")
    assert result.is_supported is False
    assert result.symbols == []
    assert "Unsupported language" in result.error_message


def test_parse_without_language_or_path():
    result = parse_code("hello world")
    assert result.is_supported is False
    assert result.symbols == []
    assert "Unsupported language" in result.error_message


def test_parse_invalid_input_type():
    result = parse_code(12345, language="python")  # type: ignore[arg-type]
    assert result.symbols == []
    assert result.error_message is not None


# ===========================================================================
# 7. File-Based Parsing (parse_file)
# ===========================================================================

def test_parse_file_python(tmp_path: Path):
    file_path = tmp_path / "sample.py"
    file_path.write_text(
        "def greet(name: str) -> str:\n"
        "    return f'Hello, {name}'\n",
        encoding="utf-8",
    )

    result = parse_file(file_path)
    assert result.is_supported is True
    assert result.language == "python"
    assert len(result.symbols) == 1
    assert result.symbols[0].name == "greet"
    assert result.symbols[0].start_line == 1
    assert result.symbols[0].end_line == 2


def test_parse_file_javascript(tmp_path: Path):
    file_path = tmp_path / "sample.js"
    file_path.write_text(
        "class App {\n"
        "    render() {}\n"
        "}\n",
        encoding="utf-8",
    )

    result = parse_file(file_path)
    assert result.is_supported is True
    assert result.language == "javascript"
    assert len(result.classes) == 1
    assert len(result.functions) == 1
    assert result.classes[0].name == "App"
    assert result.functions[0].name == "render"


def test_parse_file_non_existent():
    result = parse_file("non_existent_file_path.py")
    assert result.symbols == []
    assert result.error_message is not None
    assert "File not found" in result.error_message


def test_parse_file_unsupported_extension(tmp_path: Path):
    file_path = tmp_path / "notes.txt"
    file_path.write_text("Just some text", encoding="utf-8")

    result = parse_file(file_path)
    assert result.is_supported is False
    assert result.symbols == []
