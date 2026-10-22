"""
chunking_service.py

Code-aware and text-based chunking for Python, JavaScript, documentation files,
and plain text.

Key Features:
- Code-aware chunking: preserves functions and classes as contiguous units whenever possible.
- Oversized structure splitting: safely subdivides oversized classes (by member methods)
  and oversized functions or blocks (at blank lines or line limits) without line loss.
- Documentation chunking: text-based chunking by Markdown/RST headings and paragraph breaks.
- Strict line accuracy: every chunk records 1-based start_line and end_line, and its
  content exactly matches the source slice.
- Safe fallbacks: handles empty files, whitespace-only files, syntax errors, and
  unsupported languages cleanly.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from app.services.code_parser import (
    CodeSymbol,
    SymbolType,
    detect_language,
    parse_code,
)

logger = logging.getLogger(__name__)

# Default chunking parameters
DEFAULT_MAX_LINES: int = 100
DEFAULT_MAX_CHARS: int = 4000

# Extensions recognized as documentation / prose
_DOC_EXTENSIONS = frozenset(
    {
        ".md",
        ".markdown",
        ".mdown",
        ".mkdn",
        ".rst",
        ".txt",
        ".adoc",
        ".asciidoc",
    }
)

_DOC_LANGUAGES = frozenset(
    {
        "markdown",
        "md",
        "rst",
        "restructuredtext",
        "text",
        "txt",
        "documentation",
        "doc",
    }
)

# Markdown heading pattern: e.g. "# Heading", "### Subheading"
_MD_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$")


@dataclass(frozen=True)
class Chunk:
    chunk_index: int
    start_line: int  # 1-indexed
    end_line: int  # 1-indexed
    content: str
    file_path: str | None = None
    chunk_type: str = "code"  # "function", "class", "method", "code", "documentation", "text"
    symbol_name: str | None = None
    language: str | None = None

    @property
    def line_count(self) -> int:
        return self.end_line - self.start_line + 1


def is_documentation_file(
    file_path: str | Path | None = None,
    language_hint: str | None = None,
) -> bool:
    """
    Check if a file or language hint represents a documentation file (e.g. Markdown, RST, text).
    """
    if language_hint:
        hint_clean = language_hint.strip().lower()
        if hint_clean in _DOC_LANGUAGES:
            return True

    if file_path is not None:
        suffix = Path(file_path).suffix.lower()
        if suffix in _DOC_EXTENSIONS:
            return True

    return False


# ---------------------------------------------------------------------------
# Low-level Line-splitting Helpers
# ---------------------------------------------------------------------------

def _measure_chars(lines: Sequence[str], start_1based: int, end_1based: int) -> int:
    """Calculate character count (including newlines) for lines in [start_1based, end_1based]."""
    return sum(len(lines[i - 1]) + 1 for i in range(start_1based, end_1based + 1))


def _split_line_range(
    lines: Sequence[str],
    start_line: int,
    end_line: int,
    max_lines: int,
    max_chars: int,
) -> list[tuple[int, int]]:
    """
    Safely split a 1-based line range [start_line, end_line] into smaller
    non-overlapping contiguous sub-ranges [sub_start, sub_end], each not exceeding
    max_lines (and preferring not to exceed max_chars).

    Prefers breaking at blank lines where possible. Every line in the original
    range is included exactly once.
    """
    if start_line > end_line or not lines:
        return []

    ranges: list[tuple[int, int]] = []
    sub_start = start_line

    while sub_start <= end_line:
        # Determine maximum candidate end line based on max_lines
        hard_limit = min(sub_start + max_lines - 1, end_line)

        # Shrink candidate end if char count exceeds max_chars
        candidate_end = hard_limit
        while candidate_end > sub_start and _measure_chars(lines, sub_start, candidate_end) > max_chars:
            candidate_end -= 1

        # If we have a span greater than 2 lines, try to find a natural break (empty line)
        # in the latter half of the window
        if candidate_end < end_line and (candidate_end - sub_start) >= 3:
            search_start = sub_start + (candidate_end - sub_start) // 2
            for split_pt in range(candidate_end, search_start - 1, -1):
                if not lines[split_pt - 1].strip():
                    candidate_end = split_pt
                    break

        ranges.append((sub_start, candidate_end))
        sub_start = candidate_end + 1

    return ranges


def _build_chunk(
    lines: Sequence[str],
    start_line: int,
    end_line: int,
    chunk_index: int,
    file_path: str | None = None,
    chunk_type: str = "code",
    symbol_name: str | None = None,
    language: str | None = None,
) -> Chunk:
    content = "\n".join(lines[start_line - 1 : end_line])
    return Chunk(
        chunk_index=chunk_index,
        start_line=start_line,
        end_line=end_line,
        content=content,
        file_path=file_path,
        chunk_type=chunk_type,
        symbol_name=symbol_name,
        language=language,
    )


# ---------------------------------------------------------------------------
# Code-aware Chunking (Python & JavaScript)
# ---------------------------------------------------------------------------

def _chunk_code_symbols(
    lines: list[str],
    symbols: list[CodeSymbol],
    language: str,
    file_path: str | None,
    max_lines: int,
    max_chars: int,
) -> list[Chunk]:
    """
    Chunk code using extracted AST symbols, preserving top-level functions and
    classes when they fit, splitting oversized structures safely.
    """
    total_lines = len(lines)
    if total_lines == 0:
        return []

    # Map children symbols by parent name (e.g. methods in a class)
    children_by_parent: dict[str, list[CodeSymbol]] = {}
    top_level_symbols: list[CodeSymbol] = []

    for sym in symbols:
        if sym.parent_name is None:
            top_level_symbols.append(sym)
        else:
            children_by_parent.setdefault(sym.parent_name, []).append(sym)

    # Sort top-level symbols by start_line
    top_level_symbols.sort(key=lambda s: s.start_line)

    raw_chunks: list[tuple[int, int, str, str | None]] = []  # (start, end, type, name)
    current_line = 1

    for sym in top_level_symbols:
        # Ignore symbol if out of bounds or invalid
        if sym.start_line > total_lines:
            continue
        sym_end = min(sym.end_line, total_lines)

        # 1. Handle gap before this symbol (e.g. imports, comments, globals)
        if sym.start_line > current_line:
            gap_start = current_line
            gap_end = sym.start_line - 1
            while gap_start <= gap_end and not lines[gap_start - 1].strip():
                gap_start += 1
            while gap_end >= gap_start and not lines[gap_end - 1].strip():
                gap_end -= 1

            if gap_start <= gap_end:
                for sub_s, sub_e in _split_line_range(lines, gap_start, gap_end, max_lines, max_chars):
                    raw_chunks.append((sub_s, sub_e, "code", None))

        # 2. Handle symbol itself
        sym_start = sym.start_line
        sym_lines = sym_end - sym_start + 1
        sym_chars = _measure_chars(lines, sym_start, sym_end)

        if sym_lines <= max_lines and sym_chars <= max_chars:
            # Fits in a single chunk: keep together!
            raw_chunks.append((sym_start, sym_end, sym.symbol_type.value, sym.name))
        else:
            # Oversized structure: split safely
            if sym.symbol_type == SymbolType.CLASS:
                methods = children_by_parent.get(sym.name, [])
                if methods:
                    methods.sort(key=lambda m: m.start_line)
                    inner_line = sym_start

                    for method in methods:
                        m_start = method.start_line
                        m_end = min(method.end_line, sym_end)

                        # Class body gap before method (e.g. class docstring, class attributes)
                        if m_start > inner_line:
                            c_gap_start = inner_line
                            c_gap_end = m_start - 1
                            while c_gap_start <= c_gap_end and not lines[c_gap_start - 1].strip():
                                c_gap_start += 1
                            while c_gap_end >= c_gap_start and not lines[c_gap_end - 1].strip():
                                c_gap_end -= 1
                            if c_gap_start <= c_gap_end:
                                for s_s, s_e in _split_line_range(lines, c_gap_start, c_gap_end, max_lines, max_chars):
                                    raw_chunks.append((s_s, s_e, "class", f"{sym.name}__prelude"))

                        # Method itself
                        m_lines = m_end - m_start + 1
                        m_chars = _measure_chars(lines, m_start, m_end)
                        if m_lines <= max_lines and m_chars <= max_chars:
                            raw_chunks.append((m_start, m_end, "method", f"{sym.name}.{method.name}"))
                        else:
                            for s_s, s_e in _split_line_range(lines, m_start, m_end, max_lines, max_chars):
                                raw_chunks.append((s_s, s_e, "method", f"{sym.name}.{method.name}"))

                        inner_line = m_end + 1

                    # Class body after last method (if any)
                    if inner_line <= sym_end:
                        c_post_start = inner_line
                        c_post_end = sym_end
                        while c_post_start <= c_post_end and not lines[c_post_start - 1].strip():
                            c_post_start += 1
                        while c_post_end >= c_post_start and not lines[c_post_end - 1].strip():
                            c_post_end -= 1
                        if c_post_start <= c_post_end:
                            for s_s, s_e in _split_line_range(lines, c_post_start, c_post_end, max_lines, max_chars):
                                raw_chunks.append((s_s, s_e, "class", f"{sym.name}__postlude"))
                else:
                    # Class without parsed child methods: split lines
                    for sub_s, sub_e in _split_line_range(lines, sym_start, sym_end, max_lines, max_chars):
                        raw_chunks.append((sub_s, sub_e, "class", sym.name))
            else:
                # Oversized function: split lines
                for sub_s, sub_e in _split_line_range(lines, sym_start, sym_end, max_lines, max_chars):
                    raw_chunks.append((sub_s, sub_e, sym.symbol_type.value, sym.name))

        current_line = sym_end + 1

    # 3. Handle trailing code after the last symbol (if any)
    if current_line <= total_lines:
        gap_start = current_line
        gap_end = total_lines
        while gap_start <= gap_end and not lines[gap_start - 1].strip():
            gap_start += 1
        while gap_end >= gap_start and not lines[gap_end - 1].strip():
            gap_end -= 1

        if gap_start <= gap_end:
            for sub_s, sub_e in _split_line_range(lines, gap_start, gap_end, max_lines, max_chars):
                raw_chunks.append((sub_s, sub_e, "code", None))

    # Convert raw chunk descriptors to Chunk instances with sequential indices
    chunks: list[Chunk] = []
    for idx, (s_line, e_line, c_type, s_name) in enumerate(raw_chunks):
        chunks.append(
            _build_chunk(
                lines=lines,
                start_line=s_line,
                end_line=e_line,
                chunk_index=idx,
                file_path=file_path,
                chunk_type=c_type,
                symbol_name=s_name,
                language=language,
            )
        )

    return chunks


# ---------------------------------------------------------------------------
# Documentation Chunking (Markdown / RST / Plain Text)
# ---------------------------------------------------------------------------

def _chunk_documentation(
    lines: list[str],
    file_path: str | None,
    max_lines: int,
    max_chars: int,
) -> list[Chunk]:
    """
    Chunk documentation files using Markdown/RST section headings and
    paragraph boundaries.
    """
    total_lines = len(lines)
    if total_lines == 0:
        return []

    # Find heading lines: 1-indexed line numbers where sections start
    heading_lines: list[int] = []
    for idx, line in enumerate(lines):
        line_num = idx + 1
        # Check Markdown heading # ...
        if _MD_HEADING_PATTERN.match(line):
            heading_lines.append(line_num)
        # Check RST underline: line idx+1 made of === or ---
        elif (
            idx + 1 < total_lines
            and len(lines[idx + 1].strip()) >= 3
            and all(ch in "=-~^`" for ch in lines[idx + 1].strip())
            and line.strip()
        ):
            heading_lines.append(line_num)

    # If headings exist, divide into sections by heading
    sections: list[tuple[int, int]] = []
    if heading_lines:
        # Preamble before first heading
        if heading_lines[0] > 1:
            sections.append((1, heading_lines[0] - 1))

        for i, h_line in enumerate(heading_lines):
            next_h = heading_lines[i + 1] if i + 1 < len(heading_lines) else total_lines + 1
            sec_start = h_line
            sec_end = next_h - 1
            sections.append((sec_start, sec_end))
    else:
        # No headings: single section covering entire document
        sections.append((1, total_lines))

    raw_chunks: list[tuple[int, int]] = []

    for sec_start, sec_end in sections:
        # Trim leading and trailing blank lines
        s_start = sec_start
        s_end = sec_end
        while s_start <= s_end and not lines[s_start - 1].strip():
            s_start += 1
        while s_end >= s_start and not lines[s_end - 1].strip():
            s_end -= 1

        if s_start > s_end:
            continue

        sec_lines = s_end - s_start + 1
        sec_chars = _measure_chars(lines, s_start, s_end)

        if sec_lines <= max_lines and sec_chars <= max_chars:
            raw_chunks.append((s_start, s_end))
        else:
            # Oversized section: split by paragraphs (empty lines)
            p_start = s_start
            while p_start <= s_end:
                while p_start <= s_end and not lines[p_start - 1].strip():
                    p_start += 1
                if p_start > s_end:
                    break

                limit = min(p_start + max_lines - 1, s_end)
                candidate_end = limit

                while candidate_end > p_start and _measure_chars(lines, p_start, candidate_end) > max_chars:
                    candidate_end -= 1

                # Look for paragraph separator (blank line)
                if candidate_end < s_end and (candidate_end - p_start) >= 2:
                    for split_pt in range(candidate_end, p_start, -1):
                        if not lines[split_pt - 1].strip():
                            candidate_end = split_pt
                            break

                c_end = candidate_end
                while c_end >= p_start and not lines[c_end - 1].strip():
                    c_end -= 1

                if c_end >= p_start:
                    raw_chunks.append((p_start, c_end))

                p_start = candidate_end + 1

    chunks: list[Chunk] = []
    for idx, (s_line, e_line) in enumerate(raw_chunks):
        chunks.append(
            _build_chunk(
                lines=lines,
                start_line=s_line,
                end_line=e_line,
                chunk_index=idx,
                file_path=file_path,
                chunk_type="documentation",
                symbol_name=None,
                language="markdown",
            )
        )

    return chunks


# ---------------------------------------------------------------------------
# General Text Fallback Chunking
# ---------------------------------------------------------------------------

def _chunk_general_text(
    lines: list[str],
    file_path: str | None,
    language: str | None,
    max_lines: int,
    max_chars: int,
) -> list[Chunk]:
    """
    Fallback chunking for plaintext or unsupported languages.
    Groups lines up to max_lines/max_chars, splitting at blank lines where possible.
    """
    total_lines = len(lines)
    if total_lines == 0:
        return []

    line_ranges = _split_line_range(lines, 1, total_lines, max_lines, max_chars)
    chunks: list[Chunk] = []
    idx = 0

    for s_line, e_line in line_ranges:
        # Skip pure whitespace chunks
        if not any(lines[i - 1].strip() for i in range(s_line, e_line + 1)):
            continue

        chunks.append(
            _build_chunk(
                lines=lines,
                start_line=s_line,
                end_line=e_line,
                chunk_index=idx,
                file_path=file_path,
                chunk_type="text",
                symbol_name=None,
                language=language,
            )
        )
        idx += 1

    return chunks


# ---------------------------------------------------------------------------
# Public APIs
# ---------------------------------------------------------------------------

def chunk_content(
    content: str,
    language: str | None = None,
    file_path: str | Path | None = None,
    max_lines: int = DEFAULT_MAX_LINES,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> list[Chunk]:
    """
    Chunk source code or document text into structured chunks.

    Parameters:
        content: The text content to chunk.
        language: Optional language hint ("python", "javascript", "markdown", etc.).
        file_path: Optional file path for language/type inference.
        max_lines: Maximum lines per chunk (default: 100).
        max_chars: Target maximum characters per chunk (default: 4000).

    Returns:
        A list of Chunk objects with 1-based start_line, end_line, and exact content.
    """
    if not content or not content.strip():
        return []

    lines = content.splitlines()
    if not lines:
        return []

    path_str = str(file_path) if file_path is not None else None

    # 1. Check if this is a documentation file
    if is_documentation_file(file_path=file_path, language_hint=language):
        return _chunk_documentation(
            lines=lines,
            file_path=path_str,
            max_lines=max_lines,
            max_chars=max_chars,
        )

    # 2. Check for supported code language (Python / JavaScript)
    resolved_lang = detect_language(file_path=file_path, language_hint=language)

    if resolved_lang in ("python", "javascript"):
        parse_result = parse_code(content, language=resolved_lang, file_path=file_path)
        if parse_result.symbols:
            return _chunk_code_symbols(
                lines=lines,
                symbols=parse_result.symbols,
                language=resolved_lang,
                file_path=path_str,
                max_lines=max_lines,
                max_chars=max_chars,
            )

    # 3. Fallback for files without extracted symbols or unsupported languages
    return _chunk_general_text(
        lines=lines,
        file_path=path_str,
        language=resolved_lang or language,
        max_lines=max_lines,
        max_chars=max_chars,
    )


def chunk_file(
    file_path: str | Path,
    language: str | None = None,
    max_lines: int = DEFAULT_MAX_LINES,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> list[Chunk]:
    """
    Read a file from disk and chunk it.
    Returns an empty list safely if the file is missing or unreadable.
    """
    path = Path(file_path)
    if not path.is_file():
        logger.warning("chunk_file: file not found: %s", file_path)
        return []

    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        logger.error("chunk_file: failed to read file %s: %s", file_path, exc)
        return []

    return chunk_content(
        content=content,
        language=language,
        file_path=file_path,
        max_lines=max_lines,
        max_chars=max_chars,
    )
