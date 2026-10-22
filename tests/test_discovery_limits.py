"""
Tests for the three hard limits in file_discovery_service.discover_files():
  - MAX_FILE_COUNT
  - MAX_REPO_SIZE_BYTES
  - MAX_DISCOVERY_SECONDS

Also covers elapsed_seconds and total_size_bytes population.
Uses tmp_path for real files and monkeypatch for settings — no git.
"""

import time

import pytest

from app.services.file_discovery_service import discover_files


def _write(tmp_path, rel: str, content: bytes = b"x = 1\n") -> None:
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)


# ---------------------------------------------------------------------------
# MAX_FILE_COUNT
# ---------------------------------------------------------------------------

def test_file_count_limit_sets_stop_reason(tmp_path, monkeypatch):
    import app.core.config as cfg
    monkeypatch.setattr(cfg.settings, "max_file_count", 2)

    _write(tmp_path, "a.py")
    _write(tmp_path, "b.py")
    _write(tmp_path, "c.py")

    result = discover_files(tmp_path)

    assert result.stop_reason is not None
    assert "file count limit" in result.stop_reason
    assert "2" in result.stop_reason


def test_file_count_limit_does_not_exceed_limit(tmp_path, monkeypatch):
    import app.core.config as cfg
    monkeypatch.setattr(cfg.settings, "max_file_count", 2)

    for i in range(5):
        _write(tmp_path, f"file{i}.py")

    result = discover_files(tmp_path)

    assert len(result.files) <= 2


def test_file_count_limit_exact_count_is_accepted(tmp_path, monkeypatch):
    """Files up to the limit must all be accepted before stopping."""
    import app.core.config as cfg
    monkeypatch.setattr(cfg.settings, "max_file_count", 3)

    for i in range(5):
        _write(tmp_path, f"file{i}.py")

    result = discover_files(tmp_path)

    assert len(result.files) == 3


def test_below_file_count_limit_no_stop_reason(tmp_path, monkeypatch):
    import app.core.config as cfg
    monkeypatch.setattr(cfg.settings, "max_file_count", 10)

    for i in range(3):
        _write(tmp_path, f"file{i}.py")

    result = discover_files(tmp_path)

    assert result.stop_reason is None
    assert len(result.files) == 3


# ---------------------------------------------------------------------------
# MAX_REPO_SIZE_BYTES
# ---------------------------------------------------------------------------

def test_repo_size_limit_sets_stop_reason(tmp_path, monkeypatch):
    import app.core.config as cfg
    # Allow 2 files of 6 bytes each (12 bytes total), limit to 10 bytes
    monkeypatch.setattr(cfg.settings, "max_repo_size_bytes", 10)

    _write(tmp_path, "a.py", b"x = 1\n")   # 6 bytes
    _write(tmp_path, "b.py", b"y = 2\n")   # 6 bytes — cumulative 12 > 10

    result = discover_files(tmp_path)

    assert result.stop_reason is not None
    assert "repository size limit" in result.stop_reason


def test_repo_size_limit_total_bytes_does_not_exceed_limit(tmp_path, monkeypatch):
    import app.core.config as cfg
    monkeypatch.setattr(cfg.settings, "max_repo_size_bytes", 10)

    _write(tmp_path, "a.py", b"x = 1\n")   # 6 bytes
    _write(tmp_path, "b.py", b"y = 2\n")   # would push total to 12

    result = discover_files(tmp_path)

    assert result.total_size_bytes <= 10


def test_repo_size_limit_single_large_file_not_accepted(tmp_path, monkeypatch):
    """A single file whose size would exceed the running total stops discovery."""
    import app.core.config as cfg
    monkeypatch.setattr(cfg.settings, "max_repo_size_bytes", 5)

    _write(tmp_path, "small.py", b"x\n")    # 2 bytes — accepted
    _write(tmp_path, "big.py",   b"y" * 10) # 10 bytes — cumulative 12 > 5

    result = discover_files(tmp_path)

    paths = {f.relative_path for f in result.files}
    assert "big.py" not in paths


# ---------------------------------------------------------------------------
# MAX_DISCOVERY_SECONDS
# ---------------------------------------------------------------------------

def test_time_limit_sets_stop_reason(tmp_path, monkeypatch):
    import app.core.config as cfg
    # Negative value guarantees the deadline is already in the past when
    # the first loop iteration runs the time check.
    monkeypatch.setattr(cfg.settings, "max_discovery_seconds", -1.0)

    for i in range(3):
        _write(tmp_path, f"file{i}.py")

    result = discover_files(tmp_path)

    assert result.stop_reason is not None
    assert "processing time limit" in result.stop_reason


def test_time_limit_stop_reason_includes_limit_value(tmp_path, monkeypatch):
    import app.core.config as cfg
    monkeypatch.setattr(cfg.settings, "max_discovery_seconds", -1.0)

    for i in range(3):
        _write(tmp_path, f"file{i}.py")

    result = discover_files(tmp_path)

    assert result.stop_reason is not None
    assert "-1s" in result.stop_reason


# ---------------------------------------------------------------------------
# elapsed_seconds and total_size_bytes population
# ---------------------------------------------------------------------------

def test_elapsed_seconds_is_positive_after_discovery(tmp_path):
    _write(tmp_path, "src/main.py", b"x = 1\n")
    result = discover_files(tmp_path)
    assert result.elapsed_seconds >= 0.0
    assert isinstance(result.elapsed_seconds, float)


def test_total_size_bytes_matches_sum_of_accepted_files(tmp_path):
    _write(tmp_path, "a.py", b"abc")    # 3 bytes
    _write(tmp_path, "b.py", b"defg")   # 4 bytes

    result = discover_files(tmp_path)

    expected = sum(f.size_bytes for f in result.files)
    assert result.total_size_bytes == expected
    assert result.total_size_bytes == 7


def test_total_size_bytes_zero_for_empty_directory(tmp_path):
    result = discover_files(tmp_path)
    assert result.total_size_bytes == 0
    assert result.elapsed_seconds >= 0.0
