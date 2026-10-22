"""
Tests for app/services/file_discovery_service.py

Uses tmp_path to build real directory trees and verifies that
discover_files() correctly accepts, skips, and records reasons for
every category of file.
"""

import pytest

from app.services.file_discovery_service import DiscoveryResult, discover_files


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _accepted_paths(result: DiscoveryResult) -> set[str]:
    return {f.relative_path for f in result.files}


def _skipped_paths(result: DiscoveryResult) -> set[str]:
    return {s.relative_path for s in result.skipped}


def _skip_reason(result: DiscoveryResult, path: str) -> str | None:
    for s in result.skipped:
        if s.relative_path == path:
            return s.reason
    return None


def _write(tmp_path, rel: str, content: bytes = b"print('hello')\n") -> None:
    """Write *content* to *tmp_path/rel*, creating intermediate directories."""
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)


# ---------------------------------------------------------------------------
# Basic acceptance
# ---------------------------------------------------------------------------

def test_accepts_plain_python_file(tmp_path):
    _write(tmp_path, "src/main.py")
    result = discover_files(tmp_path)
    assert "src/main.py" in _accepted_paths(result)
    assert result.stop_reason is None


def test_accepted_file_has_correct_metadata(tmp_path):
    content = b"x = 1\n"
    _write(tmp_path, "app/utils.py", content)
    result = discover_files(tmp_path)
    files = {f.relative_path: f for f in result.files}
    assert "app/utils.py" in files
    f = files["app/utils.py"]
    assert f.extension == ".py"
    assert f.size_bytes == len(content)
    assert f.encoding == "utf-8"


def test_empty_directory_returns_no_files(tmp_path):
    result = discover_files(tmp_path)
    assert result.files == []
    assert result.skipped == []
    assert result.stop_reason is None


def test_nonexistent_path_returns_empty_result(tmp_path):
    result = discover_files(tmp_path / "does_not_exist")
    assert result.files == []
    assert result.skipped == []


# ---------------------------------------------------------------------------
# Secret files
# ---------------------------------------------------------------------------

def test_skips_dotenv_file(tmp_path):
    _write(tmp_path, ".env", b"DB_PASSWORD=secret\n")
    result = discover_files(tmp_path)
    assert ".env" not in _accepted_paths(result)
    assert ".env" in _skipped_paths(result)
    assert _skip_reason(result, ".env") == "secret file"


def test_skips_env_in_subdirectory(tmp_path):
    _write(tmp_path, "config/.env.production", b"KEY=val\n")
    result = discover_files(tmp_path)
    assert "config/.env.production" in _skipped_paths(result)
    assert _skip_reason(result, "config/.env.production") == "secret file"


def test_skips_pem_certificate(tmp_path):
    _write(tmp_path, "certs/server.pem", b"-----BEGIN CERTIFICATE-----\n")
    result = discover_files(tmp_path)
    assert "certs/server.pem" in _skipped_paths(result)
    assert _skip_reason(result, "certs/server.pem") == "secret file"


def test_skips_private_key_file(tmp_path):
    _write(tmp_path, "keys/id_rsa", b"-----BEGIN RSA PRIVATE KEY-----\n")
    result = discover_files(tmp_path)
    assert "keys/id_rsa" in _skipped_paths(result)


def test_skips_file_inside_ssh_directory(tmp_path):
    _write(tmp_path, ".ssh/config", b"Host github.com\n")
    result = discover_files(tmp_path)
    assert ".ssh/config" in _skipped_paths(result)
    assert _skip_reason(result, ".ssh/config") == "secret file"


# ---------------------------------------------------------------------------
# Binary files
# ---------------------------------------------------------------------------

def test_skips_compiled_python_bytecode(tmp_path):
    _write(tmp_path, "app/__pycache__/main.pyc", b"\x00bytecode")
    result = discover_files(tmp_path)
    assert "app/__pycache__/main.pyc" not in _accepted_paths(result)


def test_skips_zip_archive(tmp_path):
    # Use a flat path so the binary-file glob fires, not the build-output dir check.
    _write(tmp_path, "app.zip", b"PK\x03\x04binary")
    result = discover_files(tmp_path)
    assert "app.zip" in _skipped_paths(result)
    assert _skip_reason(result, "app.zip") == "binary file"


def test_skips_file_with_nul_byte_content(tmp_path):
    # A .txt file that happens to contain a NUL byte — binary content check.
    _write(tmp_path, "data/output.txt", b"hello\x00world")
    result = discover_files(tmp_path)
    assert "data/output.txt" not in _accepted_paths(result)
    reason = _skip_reason(result, "data/output.txt")
    assert reason is not None
    assert "unsupported content" in reason or "binary" in reason


# ---------------------------------------------------------------------------
# Generated files
# ---------------------------------------------------------------------------

def test_skips_minified_js(tmp_path):
    _write(tmp_path, "static/app.min.js", b"!function(){}")
    result = discover_files(tmp_path)
    assert "static/app.min.js" in _skipped_paths(result)
    assert _skip_reason(result, "static/app.min.js") == "generated file"


def test_skips_log_file(tmp_path):
    _write(tmp_path, "logs/app.log", b"2026-01-01 INFO started\n")
    result = discover_files(tmp_path)
    assert "logs/app.log" in _skipped_paths(result)
    assert _skip_reason(result, "logs/app.log") == "generated file"


def test_skips_ds_store(tmp_path):
    _write(tmp_path, ".DS_Store", b"\x00\x00bplist")
    result = discover_files(tmp_path)
    assert ".DS_Store" not in _accepted_paths(result)


# ---------------------------------------------------------------------------
# Lock files
# ---------------------------------------------------------------------------

def test_skips_package_lock(tmp_path):
    _write(tmp_path, "package-lock.json", b'{"lockfileVersion":3}')
    result = discover_files(tmp_path)
    assert "package-lock.json" in _skipped_paths(result)
    assert _skip_reason(result, "package-lock.json") == "lock file"


def test_skips_poetry_lock(tmp_path):
    _write(tmp_path, "poetry.lock", b"[[package]]\n")
    result = discover_files(tmp_path)
    assert "poetry.lock" in _skipped_paths(result)
    assert _skip_reason(result, "poetry.lock") == "lock file"


# ---------------------------------------------------------------------------
# Dependency directories
# ---------------------------------------------------------------------------

def test_skips_node_modules(tmp_path):
    _write(tmp_path, "node_modules/lodash/index.js", b"module.exports={}")
    result = discover_files(tmp_path)
    assert "node_modules/lodash/index.js" in _skipped_paths(result)
    assert _skip_reason(result, "node_modules/lodash/index.js") == "dependency directory"


def test_skips_venv_directory(tmp_path):
    _write(tmp_path, ".venv/lib/python3.11/site.py", b"# site\n")
    result = discover_files(tmp_path)
    assert ".venv/lib/python3.11/site.py" in _skipped_paths(result)
    assert _skip_reason(result, ".venv/lib/python3.11/site.py") == "dependency directory"


# ---------------------------------------------------------------------------
# Build outputs
# ---------------------------------------------------------------------------

def test_skips_dist_directory(tmp_path):
    _write(tmp_path, "dist/bundle.js", b"(function(){})()")
    result = discover_files(tmp_path)
    assert "dist/bundle.js" in _skipped_paths(result)
    assert _skip_reason(result, "dist/bundle.js") == "build output"


def test_skips_pycache_directory(tmp_path):
    _write(tmp_path, "src/__pycache__/utils.cpython-311.pyc", b"\x00bytecode")
    result = discover_files(tmp_path)
    assert "src/__pycache__/utils.cpython-311.pyc" not in _accepted_paths(result)


# ---------------------------------------------------------------------------
# Oversized files
# ---------------------------------------------------------------------------

def test_skips_oversized_file(tmp_path, monkeypatch):
    import app.core.config as cfg
    monkeypatch.setattr(cfg.settings, "max_file_size_bytes", 10)
    _write(tmp_path, "big.py", b"x = 1\n" * 10)  # 60 bytes > 10
    result = discover_files(tmp_path)
    assert "big.py" in _skipped_paths(result)
    reason = _skip_reason(result, "big.py")
    assert "too large" in reason
    assert "10" in reason  # limit appears in reason


def test_accepts_file_exactly_at_size_limit(tmp_path, monkeypatch):
    import app.core.config as cfg
    content = b"x = 1\n"  # 6 bytes
    monkeypatch.setattr(cfg.settings, "max_file_size_bytes", len(content))
    _write(tmp_path, "exact.py", content)
    result = discover_files(tmp_path)
    assert "exact.py" in _accepted_paths(result)


# ---------------------------------------------------------------------------
# Encoding
# ---------------------------------------------------------------------------

def test_accepted_file_encoding_is_recorded(tmp_path):
    _write(tmp_path, "src/code.py", "# utf-8\nprint('héllo')\n".encode("utf-8"))
    result = discover_files(tmp_path)
    files = {f.relative_path: f for f in result.files}
    assert "src/code.py" in files
    assert files["src/code.py"].encoding == "utf-8"


# ---------------------------------------------------------------------------
# Skip records integrity
# ---------------------------------------------------------------------------

def test_skip_records_have_path_and_reason(tmp_path):
    _write(tmp_path, ".env", b"SECRET=x\n")
    _write(tmp_path, "dist/app.js", b"!function(){}")
    result = discover_files(tmp_path)
    for skip in result.skipped:
        assert skip.relative_path
        assert skip.reason


def test_accepted_files_not_in_skipped(tmp_path):
    _write(tmp_path, "src/main.py", b"x = 1\n")
    _write(tmp_path, ".env", b"KEY=val\n")
    result = discover_files(tmp_path)
    accepted = _accepted_paths(result)
    skipped = _skipped_paths(result)
    assert accepted.isdisjoint(skipped)


def test_mixed_repo_counts(tmp_path):
    _write(tmp_path, "src/main.py", b"x = 1\n")
    _write(tmp_path, "src/utils.py", b"def f(): pass\n")
    _write(tmp_path, ".env", b"KEY=val\n")
    _write(tmp_path, "node_modules/dep/index.js", b"module.exports={}")
    _write(tmp_path, "dist/bundle.js", b"!function(){}")
    result = discover_files(tmp_path)
    assert len(result.files) == 2
    assert len(result.skipped) == 3
