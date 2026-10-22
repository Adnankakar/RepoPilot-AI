"""
Tests for app/services/file_type_filter.py

Covers all six SkipReason categories and verifies that normal source
files are not skipped.  No file I/O — all tests operate on path strings.
"""

import pytest

from app.services.file_type_filter import SkipReason, should_skip


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _reason(path: str) -> SkipReason | None:
    _, reason = should_skip(path)
    return reason


def _skipped(path: str) -> bool:
    skip, _ = should_skip(path)
    return skip


# ---------------------------------------------------------------------------
# Dependency directories
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", [
    "node_modules/lodash/index.js",
    "node_modules/.bin/webpack",
    "frontend/node_modules/react/index.js",
    ".venv/lib/python3.11/site.py",
    "venv/bin/activate",
    ".npm/cache/something",
    ".yarn/cache/package.zip",
    "vendor/autoload.php",
    "site-packages/requests/__init__.py",
    ".bundle/gems/rack.rb",
    ".gradle/caches/build.gradle",
    ".m2/repository/org/junit.jar",
    "bower_components/jquery/dist/jquery.js",
])
def test_dependency_directory_is_skipped(path):
    assert _skipped(path) is True
    assert _reason(path) == SkipReason.DEPENDENCY_DIRECTORY


# ---------------------------------------------------------------------------
# Build outputs
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", [
    "dist/bundle.js",
    "build/output.js",
    "out/Release/app",
    "__pycache__/main.cpython-311.pyc",
    "src/__pycache__/utils.cpython-311.pyc",
    ".pytest_cache/v/cache/lastfailed",
    ".mypy_cache/3.11/app.json",
    ".next/server/pages/index.js",
    ".nuxt/dist/client/app.js",
    "target/classes/Main.class",
    "htmlcov/index.html",
    ".tox/py311/bin/python",
    "tmp/scratch.txt",
    ".cache/babel-loader/data.json",
])
def test_build_output_is_skipped(path):
    assert _skipped(path) is True
    assert _reason(path) == SkipReason.BUILD_OUTPUT


# ---------------------------------------------------------------------------
# Lock files
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", [
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "Pipfile.lock",
    "poetry.lock",
    "pdm.lock",
    "uv.lock",
    "Gemfile.lock",
    "composer.lock",
    "Cargo.lock",
    "go.sum",
    "packages.lock.json",
    "Podfile.lock",
    "Package.resolved",
    "conda-lock.yml",
    # Case-insensitive
    "YARN.LOCK",
    "Poetry.Lock",
])
def test_lock_file_is_skipped(path):
    assert _skipped(path) is True
    assert _reason(path) == SkipReason.LOCK_FILE


# ---------------------------------------------------------------------------
# Generated files
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", [
    # Exact names
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
    ".gitkeep",
    ".keep",
    # Minified — use flat paths to avoid triggering build-output dir check
    "app.min.js",
    "style.min.css",
    # Bundled — *.bundle.js glob matches "app.bundle.js", not plain "bundle.js"
    "app.bundle.js",
    "vendor.chunk.js",
    # Protobuf generated
    "proto/user_pb2.py",
    "proto/user_pb2_grpc.py",
    "proto/user_pb.js",
    # Log files
    "logs/app.log",
    "error.log.1",
    # Coverage artefacts
    "coverage.xml",
    "coverage.json",
    # OpenAPI / GraphQL generated
    "generated_types.ts",
    "generated_queries.js",
    "api.gen.go",
    "types.gen.ts",
])
def test_generated_file_is_skipped(path):
    assert _skipped(path) is True
    assert _reason(path) == SkipReason.GENERATED_FILE


# ---------------------------------------------------------------------------
# Image files
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", [
    "assets/logo.png",
    "public/banner.jpg",
    "images/photo.jpeg",
    "icons/favicon.ico",
    "diagrams/arch.svg",
    "screenshots/demo.gif",
    "assets/thumb.webp",
    "design/mockup.psd",
    "raw/photo.raw",
    "assets/icon.icns",
    "photo.HEIC",
    "art/vector.AI",
])
def test_image_file_is_skipped(path):
    assert _skipped(path) is True
    assert _reason(path) == SkipReason.IMAGE_FILE


# ---------------------------------------------------------------------------
# Binary files
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", [
    # Compiled objects — use paths that don't trigger build-output dir checks
    "src/main.o",
    "lib/utils.obj",
    "lib/libfoo.a",
    "app.exe",           # bin/ is a build-output dir; test flat path instead
    "lib/native.so",
    "lib/native.dylib",
    "lib/native.dll",
    # Archives — flat paths (release/, dist/ are build-output dirs)
    "app.zip",
    "package.tar.gz",
    "package.tgz",
    "archive.rar",
    "data.7z",
    # Python bytecode — flat path (avoid __pycache__ build-output dir)
    "utils.pyc",
    "utils.pyo",
    # Java bytecode
    "Main.class",
    # Packages — flat path (dist/ is a build-output dir)
    "app-1.0.whl",
    "package.jar",
    "app.war",
    # Databases
    "data/app.db",
    "local.sqlite",
    "store.sqlite3",
    # Office / document
    "report.pdf",
    "doc.docx",
    "sheet.xlsx",
    # Fonts
    "fonts/Inter.ttf",
    "fonts/Inter.woff2",
    # ML data
    "model.pkl",
    "embeddings.npy",
    "data.parquet",
    "data.h5",
    # Misc binary
    "firmware.bin",
    "memory.dump",
])
def test_binary_file_is_skipped(path):
    assert _skipped(path) is True
    assert _reason(path) == SkipReason.BINARY_FILE


# ---------------------------------------------------------------------------
# Files that MUST NOT be skipped
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", [
    "src/main.py",
    "app/api/routes.py",
    "README.md",
    "LICENSE",
    "pyproject.toml",
    "setup.cfg",
    "requirements.txt",
    "Makefile",
    "Dockerfile",
    ".dockerignore",
    ".gitignore",
    "src/index.ts",
    "src/utils.js",
    "src/styles.css",
    "src/component.tsx",
    "tests/test_api.py",
    "docs/guide.md",
    "config/settings.yaml",
    "config/nginx.conf",
    ".github/workflows/ci.yml",
    "go.mod",              # go.mod is not go.sum
    "Cargo.toml",          # Cargo.toml is not Cargo.lock
    "package.json",        # package.json is not package-lock.json
])
def test_accepted_files_are_not_skipped(path):
    assert _skipped(path) is False
    assert _reason(path) is None


# ---------------------------------------------------------------------------
# Regression: "packages" directory must NOT cause false positives
#
# "packages" was previously in _DEPENDENCY_DIRS which incorrectly skipped
# any source file inside a directory named "packages" — a common monorepo
# workspace folder containing real application code.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", [
    # Monorepo workspace source files
    "packages/api/src/main.py",
    "packages/utils/index.ts",
    "packages/shared/lib/helpers.js",
    "packages/cli/README.md",
    # Nested inside packages
    "packages/auth/tests/test_login.py",
    "packages/core/pyproject.toml",
])
def test_packages_directory_source_files_are_not_skipped(path):
    """Source files under a 'packages' directory must not be filtered out."""
    assert _skipped(path) is False
    assert _reason(path) is None


# ---------------------------------------------------------------------------
# Regression: "env" directory must NOT cause false positives
#
# "env" was previously in _DEPENDENCY_DIRS which incorrectly skipped files
# inside any directory named "env" — a common application-level config or
# environment folder, not only a Python virtualenv.
# The actual virtualenv case is still covered by ".venv" and "venv".
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", [
    # Application environment/config directories
    "env/production/config.yaml",
    "env/staging/settings.py",
    "env/development/docker-compose.yml",
    "config/env/base.py",
    "src/env/constants.ts",
])
def test_env_directory_source_files_are_not_skipped(path):
    """Source files under an 'env' directory must not be filtered out."""
    assert _skipped(path) is False
    assert _reason(path) is None


# ---------------------------------------------------------------------------
# True positives still covered after the fix
#
# Verify that removing "packages" and "env" from _DEPENDENCY_DIRS did NOT
# break filtering for the cases those entries were originally meant to handle.
# The real dependency cases are covered by other entries in the set.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", [
    # Real Python virtualenvs — covered by ".venv" and "venv"
    ".venv/lib/python3.11/site.py",
    "venv/bin/activate",
    # PEP 582 local packages — covered by "__pypackages__"
    "__pypackages__/3.11/lib/requests/__init__.py",
    # Installed packages — covered by "site-packages"
    "site-packages/flask/__init__.py",
    ".venv/lib/python3.12/site-packages/django/db/models.py",
])
def test_real_dependency_dirs_are_still_skipped(path):
    """Dependency directories not affected by the fix must still be skipped."""
    assert _skipped(path) is True
    assert _reason(path) == SkipReason.DEPENDENCY_DIRECTORY
