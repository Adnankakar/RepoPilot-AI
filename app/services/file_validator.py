"""
file_validator.py

Three-stage validation for files that have already passed the path-based
filters (secret_filter, file_type_filter, size check).

Stages
------
1. validate_path     — pure string checks on the relative path, no I/O
2. validate_content  — reads a small byte sample to detect binary content
3. validate_encoding — probes the same sample for a decodable text encoding

Each stage returns a ValidationResult so the caller always has a
human-readable reason when a file is rejected.

No stage reads more than CONTENT_PROBE_BYTES (512 B) from disk.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

logger = logging.getLogger(__name__)

# Number of bytes read for content-type and encoding probes.
CONTENT_PROBE_BYTES: int = 512

# Encodings attempted in order during encoding validation.
# UTF-8 covers the vast majority of modern source code.
# Latin-1 is a fallback because it never raises a decode error
# (every byte is valid), so it acts as a "probably text but not UTF-8" signal.
_ENCODING_CANDIDATES: tuple[str, ...] = ("utf-8", "utf-16", "latin-1")

# Relative path segments that are unsafe regardless of content.
_UNSAFE_PATH_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\.\."),          # directory traversal
    re.compile(r"[\x00-\x1f]"),   # control characters
    re.compile(r"[<>:\"|?*\\]"),  # characters illegal on Windows
)

# Hard limit on relative path length (characters).
_MAX_PATH_LENGTH: int = 512


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    reason: str        # always populated; empty string only when valid=True
    encoding: str      # detected encoding, e.g. "utf-8"; empty when not text


# ---------------------------------------------------------------------------
# Stage 1 — path validation (no I/O)
# ---------------------------------------------------------------------------

def validate_path(relative_path: str) -> ValidationResult:
    """
    Validate *relative_path* as a safe, well-formed relative file path.

    Checks performed
    ----------------
    - Not empty
    - Does not exceed _MAX_PATH_LENGTH characters
    - No directory-traversal sequences (..)
    - No control characters
    - No characters that are illegal on Windows file systems
    - Each path component is non-empty (no double slashes)
    - Path does not start with a forward slash (must be relative)
    """
    if not relative_path or not relative_path.strip():
        return ValidationResult(valid=False, reason="empty path", encoding="")

    if len(relative_path) > _MAX_PATH_LENGTH:
        return ValidationResult(
            valid=False,
            reason=f"path too long ({len(relative_path)} chars, limit {_MAX_PATH_LENGTH})",
            encoding="",
        )

    for pattern in _UNSAFE_PATH_PATTERNS:
        if pattern.search(relative_path):
            return ValidationResult(
                valid=False,
                reason=f"unsafe path characters matched pattern {pattern.pattern!r}",
                encoding="",
            )

    if relative_path.startswith("/"):
        return ValidationResult(
            valid=False,
            reason="path must be relative, not absolute",
            encoding="",
        )

    parts = PurePosixPath(relative_path).parts
    if any(part == "" for part in parts):
        return ValidationResult(
            valid=False,
            reason="path contains empty component (double slash)",
            encoding="",
        )

    return ValidationResult(valid=True, reason="", encoding="")


# ---------------------------------------------------------------------------
# Stage 2 — content-type validation (minimal I/O)
# ---------------------------------------------------------------------------

def validate_content(absolute_path: Path) -> ValidationResult:
    """
    Read up to CONTENT_PROBE_BYTES from *absolute_path* and reject the
    file if it appears to be binary (contains a NUL byte).

    A NUL byte (0x00) is the most reliable single indicator of binary
    content and requires no external library.
    """
    try:
        with absolute_path.open("rb") as fh:
            sample = fh.read(CONTENT_PROBE_BYTES)
    except OSError as exc:
        return ValidationResult(
            valid=False,
            reason=f"could not read file for content check: {exc}",
            encoding="",
        )

    if b"\x00" in sample:
        return ValidationResult(
            valid=False,
            reason="binary content detected (NUL byte in first 512 bytes)",
            encoding="",
        )

    return ValidationResult(valid=True, reason="", encoding="")


# ---------------------------------------------------------------------------
# Stage 3 — encoding validation (same byte sample, no extra I/O)
# ---------------------------------------------------------------------------

def validate_encoding(absolute_path: Path) -> ValidationResult:
    """
    Read up to CONTENT_PROBE_BYTES from *absolute_path* and attempt to
    decode the sample with each encoding in _ENCODING_CANDIDATES.

    Returns the first encoding that succeeds, or an invalid result when
    no candidate can decode the sample (e.g. corrupt or exotic binary).

    Latin-1 never raises UnicodeDecodeError, so it serves as the final
    fallback; a file that only passes Latin-1 is still considered valid
    text — downstream processors can decide how to handle it.
    """
    try:
        with absolute_path.open("rb") as fh:
            sample = fh.read(CONTENT_PROBE_BYTES)
    except OSError as exc:
        return ValidationResult(
            valid=False,
            reason=f"could not read file for encoding check: {exc}",
            encoding="",
        )

    # Empty file — valid, treat as UTF-8.
    if not sample:
        return ValidationResult(valid=True, reason="", encoding="utf-8")

    for encoding in _ENCODING_CANDIDATES:
        try:
            sample.decode(encoding)
            return ValidationResult(valid=True, reason="", encoding=encoding)
        except (UnicodeDecodeError, LookupError):
            continue

    return ValidationResult(
        valid=False,
        reason=(
            f"could not decode file with any supported encoding "
            f"({', '.join(_ENCODING_CANDIDATES)})"
        ),
        encoding="",
    )
