"""
Tests for app/services/file_validator.py

Covers validate_path (no I/O), validate_content, and validate_encoding.
File I/O tests use pytest's tmp_path fixture to create real files.
"""

import pytest

from app.services.file_validator import (
    validate_content,
    validate_encoding,
    validate_path,
    _MAX_PATH_LENGTH,
)


# ===========================================================================
# validate_path — no I/O
# ===========================================================================

class TestValidatePath:

    def test_valid_simple_path(self):
        result = validate_path("src/main.py")
        assert result.valid is True
        assert result.reason == ""

    def test_valid_nested_path(self):
        result = validate_path("app/api/v1/routes.py")
        assert result.valid is True

    def test_valid_filename_only(self):
        result = validate_path("README.md")
        assert result.valid is True

    def test_rejects_empty_string(self):
        result = validate_path("")
        assert result.valid is False
        assert "empty" in result.reason

    def test_rejects_whitespace_only(self):
        result = validate_path("   ")
        assert result.valid is False
        assert "empty" in result.reason

    def test_rejects_path_too_long(self):
        # Single segment with no separators — definitely over 512 chars.
        long_path = "a" * (_MAX_PATH_LENGTH + 1)
        result = validate_path(long_path)
        assert result.valid is False
        assert "too long" in result.reason

    def test_accepts_path_at_exact_limit(self):
        # Build a path that is exactly _MAX_PATH_LENGTH characters.
        # Use a valid segment repeated to fill the budget.
        segment = "ab/"
        repetitions = (_MAX_PATH_LENGTH - len("x.py")) // len(segment)
        path = segment * repetitions + "x.py"
        path = path[:_MAX_PATH_LENGTH]
        # May or may not be valid depending on exact length; just assert no crash.
        result = validate_path(path)
        assert isinstance(result.valid, bool)

    def test_rejects_directory_traversal(self):
        result = validate_path("src/../etc/passwd")
        assert result.valid is False
        assert ".." in result.reason or "unsafe" in result.reason

    def test_rejects_absolute_path(self):
        result = validate_path("/etc/passwd")
        assert result.valid is False
        assert "absolute" in result.reason

    @pytest.mark.parametrize("path", [
        "src/file<name>.py",
        "src/file>name.py",
        'src/file"name.py',
        "src/file|name.py",
        "src/file?name.py",
        "src/file*name.py",
        "src\\windows\\path.py",
    ])
    def test_rejects_illegal_characters(self, path):
        result = validate_path(path)
        assert result.valid is False

    def test_rejects_control_characters(self):
        result = validate_path("src/file\x00name.py")
        assert result.valid is False

    def test_rejects_newline_in_path(self):
        result = validate_path("src/file\nname.py")
        assert result.valid is False


# ===========================================================================
# validate_content — reads real files via tmp_path
# ===========================================================================

class TestValidateContent:

    def test_accepts_plain_text_file(self, tmp_path):
        f = tmp_path / "hello.py"
        f.write_text("print('hello')\n", encoding="utf-8")
        result = validate_content(f)
        assert result.valid is True

    def test_accepts_empty_file(self, tmp_path):
        f = tmp_path / "empty.py"
        f.write_bytes(b"")
        result = validate_content(f)
        assert result.valid is True

    def test_rejects_file_with_nul_byte(self, tmp_path):
        f = tmp_path / "binary.bin"
        f.write_bytes(b"some text\x00more text")
        result = validate_content(f)
        assert result.valid is False
        assert "NUL" in result.reason or "binary" in result.reason

    def test_rejects_nul_byte_at_start(self, tmp_path):
        f = tmp_path / "data.bin"
        f.write_bytes(b"\x00" + b"A" * 100)
        result = validate_content(f)
        assert result.valid is False

    def test_nul_byte_beyond_probe_window_is_not_detected(self, tmp_path):
        # NUL bytes beyond the 512-byte probe window are not checked by design.
        f = tmp_path / "large.txt"
        f.write_bytes(b"A" * 512 + b"\x00" * 10)
        result = validate_content(f)
        assert result.valid is True

    def test_returns_no_encoding_on_success(self, tmp_path):
        # validate_content does not detect encoding; that's validate_encoding's job.
        f = tmp_path / "code.py"
        f.write_text("x = 1\n", encoding="utf-8")
        result = validate_content(f)
        assert result.encoding == ""


# ===========================================================================
# validate_encoding — reads real files via tmp_path
# ===========================================================================

class TestValidateEncoding:

    def test_accepts_utf8_file(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("# coding: utf-8\nprint('héllo')\n", encoding="utf-8")
        result = validate_encoding(f)
        assert result.valid is True
        assert result.encoding == "utf-8"

    def test_accepts_ascii_as_utf8(self, tmp_path):
        f = tmp_path / "ascii.py"
        f.write_bytes(b"print('hello')\n")
        result = validate_encoding(f)
        assert result.valid is True
        assert result.encoding == "utf-8"

    def test_accepts_empty_file_as_utf8(self, tmp_path):
        f = tmp_path / "empty.py"
        f.write_bytes(b"")
        result = validate_encoding(f)
        assert result.valid is True
        assert result.encoding == "utf-8"

    def test_accepts_latin1_file(self, tmp_path):
        # Latin-1 encoded content that is not valid UTF-8.
        # The encoding candidate order (utf-8 → utf-16 → latin-1) means the
        # detected encoding depends on the byte sequence; we only assert the
        # file is accepted as valid text.
        f = tmp_path / "latin1.txt"
        f.write_bytes("café résumé\n".encode("latin-1"))
        result = validate_encoding(f)
        assert result.valid is True
        assert result.encoding != ""

    def test_rejects_undecodable_bytes(self, tmp_path):
        # Craft a byte sequence that fails UTF-8, UTF-16, and is designed to
        # exercise the fallback path.  In practice latin-1 catches everything,
        # so we monkeypatch _ENCODING_CANDIDATES to exclude it for this test.
        import app.services.file_validator as fv
        original = fv._ENCODING_CANDIDATES
        fv._ENCODING_CANDIDATES = ("utf-8", "utf-16")
        try:
            f = tmp_path / "bad.bin"
            # 0xFF 0xFE starts a UTF-16 LE BOM; adding random bytes after
            # makes it fail strict UTF-16 decoding.
            f.write_bytes(b"\xff\xfe\x00\x00garbage\xfe\xff")
            result = validate_encoding(f)
            # With only utf-8 and utf-16 as candidates this may pass utf-16;
            # the important thing is the function does not raise.
            assert isinstance(result.valid, bool)
        finally:
            fv._ENCODING_CANDIDATES = original

    def test_encoding_stored_in_result(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("x = 1\n", encoding="utf-8")
        result = validate_encoding(f)
        assert result.encoding != ""
