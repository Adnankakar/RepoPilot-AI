"""
file_type_filter.py

Decides whether a file should be excluded from discovery based on its
type, purpose, or location — not its contents.

Rules are applied to the relative path string only.
No file I/O is performed.

Categories handled
------------------
- Binary files         (compiled objects, executables, archives, media)
- Image files          (raster and vector formats)
- Lock files           (package manager lock files)
- Generated files      (compiled output, proto-generated, auto-formatters)
- Build outputs        (dist/, build/, __pycache__/, *.pyc, …)
- Dependency trees     (node_modules/, vendor/, .venv/, …)

Each excluded file carries a SkipReason so callers can log or surface a
clear explanation without inspecting internals.
"""

import fnmatch
import logging
from enum import Enum
from pathlib import PurePosixPath

logger = logging.getLogger(__name__)


class SkipReason(str, Enum):
    BINARY_FILE = "binary file"
    IMAGE_FILE = "image file"
    LOCK_FILE = "lock file"
    GENERATED_FILE = "generated file"
    BUILD_OUTPUT = "build output"
    DEPENDENCY_DIRECTORY = "dependency directory"


# ---------------------------------------------------------------------------
# Dependency / vendor directories
# Any file whose path contains one of these directory names is skipped.
# ---------------------------------------------------------------------------
_DEPENDENCY_DIRS: frozenset[str] = frozenset(
    {
        # JavaScript / Node
        "node_modules",
        ".npm",
        ".yarn",
        ".pnp",
        # Python
        ".venv",
        "venv",
        ".env",         # virtualenv named .env (not the dotenv file)
        "__pypackages__",
        "site-packages",
        # Ruby
        "vendor",
        ".bundle",
        # Go
        "vendor",
        # PHP
        "vendor",
        # Java / Kotlin
        ".gradle",
        ".m2",
        # Rust
        # (target/ handled under build outputs)
        # Generic
        "bower_components",
        "jspm_packages",
    }
)

# ---------------------------------------------------------------------------
# Build output directories
# ---------------------------------------------------------------------------
_BUILD_OUTPUT_DIRS: frozenset[str] = frozenset(
    {
        # Generic
        "dist",
        "build",
        "out",
        "output",
        "release",
        "bin",
        "obj",
        # Python
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        "htmlcov",
        ".coverage",
        # JavaScript / TypeScript
        ".next",
        ".nuxt",
        ".svelte-kit",
        ".turbo",
        ".parcel-cache",
        # Java
        "target",
        "classes",
        # iOS / macOS
        "DerivedData",
        "xcuserdata",
        # .NET
        "artifacts",
        # Rust
        "target",
        # Misc
        "tmp",
        "temp",
        ".cache",
        ".sass-cache",
    }
)

# ---------------------------------------------------------------------------
# Lock file exact names (case-insensitive)
# ---------------------------------------------------------------------------
_LOCK_FILE_EXACT: frozenset[str] = frozenset(
    {
        # JavaScript / Node
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "npm-shrinkwrap.json",
        "bun.lockb",
        # Python
        "pipfile.lock",
        "poetry.lock",
        "pdm.lock",
        "uv.lock",
        # Ruby
        "gemfile.lock",
        # PHP
        "composer.lock",
        # Rust
        "cargo.lock",
        # Go
        "go.sum",
        # .NET
        "packages.lock.json",
        "project.assets.json",
        # Cocoapods / Swift
        "podfile.lock",
        "package.resolved",
        # Gradle
        "gradle.lockfile",
        "buildscript-gradle.lockfile",
        # Conda
        "conda-lock.yml",
    }
)

# ---------------------------------------------------------------------------
# Generated file exact names (case-insensitive)
# ---------------------------------------------------------------------------
_GENERATED_FILE_EXACT: frozenset[str] = frozenset(
    {
        ".ds_store",
        "thumbs.db",
        "desktop.ini",
        ".gitkeep",
        ".keep",
        ".editorconfig",    # editor meta, not source
    }
)

# ---------------------------------------------------------------------------
# Glob patterns — matched against the filename only (case-insensitive)
# ---------------------------------------------------------------------------

# Binary / compiled
_BINARY_GLOBS: tuple[str, ...] = (
    # Compiled objects and executables
    "*.o",
    "*.obj",
    "*.a",
    "*.lib",
    "*.so",
    "*.so.*",
    "*.dylib",
    "*.dll",
    "*.exe",
    "*.out",
    "*.elf",
    # Archives / packages
    "*.zip",
    "*.tar",
    "*.tar.gz",
    "*.tgz",
    "*.tar.bz2",
    "*.tar.xz",
    "*.rar",
    "*.7z",
    "*.gz",
    "*.bz2",
    "*.xz",
    "*.lz4",
    "*.zst",
    "*.cab",
    "*.iso",
    "*.dmg",
    "*.pkg",
    "*.deb",
    "*.rpm",
    "*.apk",
    "*.ipa",
    "*.jar",
    "*.war",
    "*.ear",
    "*.whl",
    "*.egg",
    "*.nupkg",
    # Python bytecode
    "*.pyc",
    "*.pyo",
    "*.pyd",
    # Java bytecode
    "*.class",
    # .NET / Mono
    "*.pdb",
    "*.ilk",
    # LLVM / WebAssembly
    "*.bc",
    "*.wasm",
    # Databases / binary data
    "*.db",
    "*.sqlite",
    "*.sqlite3",
    "*.mdb",
    "*.accdb",
    # Office / document formats (binary)
    "*.pdf",
    "*.doc",
    "*.docx",
    "*.xls",
    "*.xlsx",
    "*.ppt",
    "*.pptx",
    "*.odt",
    "*.ods",
    "*.odp",
    # Fonts
    "*.ttf",
    "*.otf",
    "*.woff",
    "*.woff2",
    "*.eot",
    # Audio
    "*.mp3",
    "*.mp4",
    "*.wav",
    "*.ogg",
    "*.flac",
    "*.aac",
    "*.m4a",
    "*.webm",
    "*.avi",
    "*.mov",
    "*.mkv",
    "*.wmv",
    # Misc binary
    "*.bin",
    "*.dat",
    "*.dump",
    "*.swap",
    "*.snap",
    "*.pkl",
    "*.pickle",
    "*.npy",
    "*.npz",
    "*.h5",
    "*.hdf5",
    "*.parquet",
    "*.arrow",
    "*.feather",
    # Map / debug info files
    "*.map",
    "*.dSYM",
)

# Image formats
_IMAGE_GLOBS: tuple[str, ...] = (
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.bmp",
    "*.tiff",
    "*.tif",
    "*.webp",
    "*.ico",
    "*.icns",
    "*.svg",
    "*.eps",
    "*.ai",
    "*.psd",
    "*.xcf",
    "*.heic",
    "*.heif",
    "*.avif",
    "*.raw",
    "*.cr2",
    "*.nef",
)

# Generated code / tooling artefact patterns
_GENERATED_GLOBS: tuple[str, ...] = (
    # Compiled CSS / JS
    "*.min.js",
    "*.min.css",
    "*.bundle.js",
    "*.chunk.js",
    "*.map",            # source maps
    # Proto-generated
    "*_pb2.py",
    "*_pb2_grpc.py",
    "*_pb.js",
    "*_grpc_web_pb.js",
    "*.pb.go",
    "*.pb.swift",
    # GraphQL generated
    "*generated*.ts",
    "*generated*.js",
    # OpenAPI generated
    "*.gen.go",
    "*.gen.ts",
    # Misc generated
    "*.generated.*",
    "*.auto.*",
    # Coverage / test artefacts
    "*.lcov",
    "coverage.xml",
    "coverage.json",
    # Log files
    "*.log",
    "*.log.*",
)


def should_skip(relative_path: str) -> tuple[bool, SkipReason | None]:
    """
    Return (True, reason) if the file should be excluded from discovery,
    or (False, None) if it should be included.

    Parameters
    ----------
    relative_path:
        Forward-slash relative path from the repository root,
        e.g. "node_modules/lodash/index.js".

    No file I/O is performed — only the path string is inspected.
    """
    path = PurePosixPath(relative_path)
    filename_lower = path.name.lower()
    # All directory segments (excluding the filename)
    dir_parts_lower = [p.lower() for p in path.parts[:-1]]

    # ------------------------------------------------------------------
    # 1. Dependency directories — check first, cheapest path out
    # ------------------------------------------------------------------
    for segment in dir_parts_lower:
        if segment in _DEPENDENCY_DIRS:
            logger.debug("Skip [%s] dir=%s: %s", SkipReason.DEPENDENCY_DIRECTORY, segment, relative_path)
            return True, SkipReason.DEPENDENCY_DIRECTORY

    # ------------------------------------------------------------------
    # 2. Build output directories
    # ------------------------------------------------------------------
    for segment in dir_parts_lower:
        if segment in _BUILD_OUTPUT_DIRS:
            logger.debug("Skip [%s] dir=%s: %s", SkipReason.BUILD_OUTPUT, segment, relative_path)
            return True, SkipReason.BUILD_OUTPUT

    # ------------------------------------------------------------------
    # 3. Lock files (exact filename)
    # ------------------------------------------------------------------
    if filename_lower in _LOCK_FILE_EXACT:
        logger.debug("Skip [%s]: %s", SkipReason.LOCK_FILE, relative_path)
        return True, SkipReason.LOCK_FILE

    # ------------------------------------------------------------------
    # 4. Generated files (exact filename)
    # ------------------------------------------------------------------
    if filename_lower in _GENERATED_FILE_EXACT:
        logger.debug("Skip [%s]: %s", SkipReason.GENERATED_FILE, relative_path)
        return True, SkipReason.GENERATED_FILE

    # ------------------------------------------------------------------
    # 5. Generated file globs
    # ------------------------------------------------------------------
    for pattern in _GENERATED_GLOBS:
        if fnmatch.fnmatch(filename_lower, pattern.lower()):
            logger.debug("Skip [%s] glob=%s: %s", SkipReason.GENERATED_FILE, pattern, relative_path)
            return True, SkipReason.GENERATED_FILE

    # ------------------------------------------------------------------
    # 6. Image globs
    # ------------------------------------------------------------------
    for pattern in _IMAGE_GLOBS:
        if fnmatch.fnmatch(filename_lower, pattern.lower()):
            logger.debug("Skip [%s] glob=%s: %s", SkipReason.IMAGE_FILE, pattern, relative_path)
            return True, SkipReason.IMAGE_FILE

    # ------------------------------------------------------------------
    # 7. Binary globs  (checked last — broadest set)
    # ------------------------------------------------------------------
    for pattern in _BINARY_GLOBS:
        if fnmatch.fnmatch(filename_lower, pattern.lower()):
            logger.debug("Skip [%s] glob=%s: %s", SkipReason.BINARY_FILE, pattern, relative_path)
            return True, SkipReason.BINARY_FILE

    return False, None
