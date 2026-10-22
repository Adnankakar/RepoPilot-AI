"""
file_discovery_service.py

Walks a cloned repository directory and collects metadata for every
accepted regular file: relative path, extension, size, and encoding.

Exclusion filters (applied in order, cheapest first):
  1. .git directory                    — path segment check
  2. Secrets / credentials             — secret_filter
  3. Binary / generated / build / deps — file_type_filter
  4. File too large                    — per-file size limit
  5. Invalid path                      — validate_path
  6. Unsupported content               — validate_content (NUL-byte sniff)
  7. Undecodable encoding              — validate_encoding

Hard limits (discovery stops cleanly when any is reached):
  - MAX_FILE_COUNT       — total accepted files
  - MAX_REPO_SIZE_BYTES  — total accepted bytes
  - MAX_DISCOVERY_SECONDS — wall-clock time for the entire run

All filters operate on path strings or a small byte sample only.
File contents beyond the 512-byte probe are never read here.
Every exclusion and every limit-stop is logged with a clear reason.
"""

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from app.services.secret_filter import is_secret_file
from app.services.file_type_filter import should_skip
from app.services.file_validator import validate_path, validate_content, validate_encoding
from app.core.config import settings

logger = logging.getLogger(__name__)

# Directories that are never walked into.
_EXCLUDED_DIRS = {".git"}


@dataclass(frozen=True)
class DiscoveredFile:
    relative_path: str  # forward-slash path from repo root, e.g. "src/main.py"
    extension: str      # includes dot, e.g. ".py"; empty string if none
    size_bytes: int
    encoding: str       # detected text encoding, e.g. "utf-8"


@dataclass(frozen=True)
class SkippedFile:
    relative_path: str  # forward-slash path from repo root
    reason: str         # human-readable skip reason, e.g. "dependency directory"


@dataclass
class DiscoveryResult:
    files: list[DiscoveredFile] = field(default_factory=list)
    skipped: list[SkippedFile] = field(default_factory=list)
    # None means the run completed normally; a string means it was cut short.
    stop_reason: str | None = None
    elapsed_seconds: float = 0.0
    total_size_bytes: int = 0


def discover_files(clone_path: Path) -> DiscoveryResult:
    """
    Recursively walk *clone_path*, apply all filters, enforce all limits,
    and return a DiscoveryResult.

    The caller should inspect ``result.stop_reason`` to know whether
    discovery completed normally or was halted by a limit.
    """
    result = DiscoveryResult()

    if not clone_path.is_dir():
        logger.warning(
            "discover_files: path does not exist or is not a directory: %s",
            clone_path,
        )
        return result

    deadline = time.monotonic() + settings.max_discovery_seconds
    start = time.monotonic()

    for entry in clone_path.rglob("*"):

        # -----------------------------------------------------------------
        # Hard limit: processing time
        # -----------------------------------------------------------------
        if time.monotonic() > deadline:
            result.stop_reason = (
                f"processing time limit reached "
                f"({settings.max_discovery_seconds:.0f}s)"
            )
            logger.warning("Discovery stopped: %s — %s", result.stop_reason, clone_path)
            break

        # -----------------------------------------------------------------
        # Structural skip: excluded directories
        # -----------------------------------------------------------------
        if any(part in _EXCLUDED_DIRS for part in entry.parts):
            continue

        if not entry.is_file():
            continue

        try:
            size = entry.stat().st_size
        except OSError as exc:
            logger.warning("Could not stat %s: %s", entry, exc)
            continue

        rel = entry.relative_to(clone_path)
        relative_path = rel.as_posix()

        # -----------------------------------------------------------------
        # Per-file exclusion filters
        # -----------------------------------------------------------------
        if is_secret_file(relative_path):
            reason = "secret file"
            logger.info("Excluded (%s): %s", reason, relative_path)
            result.skipped.append(SkippedFile(relative_path, reason))
            continue

        skip, skip_reason = should_skip(relative_path)
        if skip:
            reason = skip_reason.value
            logger.info("Excluded (%s): %s", reason, relative_path)
            result.skipped.append(SkippedFile(relative_path, reason))
            continue

        if size > settings.max_file_size_bytes:
            reason = f"file too large ({size} bytes, limit {settings.max_file_size_bytes} bytes)"
            logger.info("Excluded (%s): %s", reason, relative_path)
            result.skipped.append(SkippedFile(relative_path, reason))
            continue

        path_result = validate_path(relative_path)
        if not path_result.valid:
            reason = f"invalid path — {path_result.reason}"
            logger.info("Excluded (%s): %s", reason, relative_path)
            result.skipped.append(SkippedFile(relative_path, reason))
            continue

        content_result = validate_content(entry)
        if not content_result.valid:
            reason = f"unsupported content — {content_result.reason}"
            logger.info("Excluded (%s): %s", reason, relative_path)
            result.skipped.append(SkippedFile(relative_path, reason))
            continue

        encoding_result = validate_encoding(entry)
        if not encoding_result.valid:
            reason = f"encoding error — {encoding_result.reason}"
            logger.info("Excluded (%s): %s", reason, relative_path)
            result.skipped.append(SkippedFile(relative_path, reason))
            continue

        # -----------------------------------------------------------------
        # Hard limit: total repository size
        # -----------------------------------------------------------------
        if result.total_size_bytes + size > settings.max_repo_size_bytes:
            result.stop_reason = (
                f"repository size limit reached "
                f"({settings.max_repo_size_bytes / 1_048_576:.0f} MB)"
            )
            logger.warning("Discovery stopped: %s — %s", result.stop_reason, clone_path)
            break

        # -----------------------------------------------------------------
        # Accept the file
        # -----------------------------------------------------------------
        result.files.append(
            DiscoveredFile(
                relative_path=relative_path,
                extension=entry.suffix,
                size_bytes=size,
                encoding=encoding_result.encoding,
            )
        )
        result.total_size_bytes += size

        # -----------------------------------------------------------------
        # Hard limit: file count  (checked after append so the count is exact)
        # -----------------------------------------------------------------
        if len(result.files) >= settings.max_file_count:
            result.stop_reason = (
                f"file count limit reached ({settings.max_file_count} files)"
            )
            logger.warning("Discovery stopped: %s — %s", result.stop_reason, clone_path)
            break

    result.elapsed_seconds = round(time.monotonic() - start, 3)

    if result.stop_reason:
        logger.info(
            "Discovery halted after %d files / %d skipped / %d bytes / %.3fs — reason: %s",
            len(result.files),
            len(result.skipped),
            result.total_size_bytes,
            result.elapsed_seconds,
            result.stop_reason,
        )
    else:
        logger.info(
            "Discovery complete: %d files / %d skipped / %d bytes / %.3fs — %s",
            len(result.files),
            len(result.skipped),
            result.total_size_bytes,
            result.elapsed_seconds,
            clone_path,
        )

    return result
