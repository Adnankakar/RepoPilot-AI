"""
secret_filter.py

Decides whether a file path should be excluded from discovery because
it may contain secrets, credentials, or other sensitive data.

Rules are applied to the *relative path only* — file contents are never
read or inspected.

Matching order
--------------
1. Exact filename match  (e.g. ".env", "id_rsa")
2. Filename glob pattern (e.g. "*.pem", ".env.*")
3. Path segment match    (e.g. any component named ".ssh")

All comparisons are case-insensitive so ".ENV" and ".Env" are both caught.
"""

import fnmatch
import logging
from pathlib import PurePosixPath

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exact filenames (case-insensitive)
# ---------------------------------------------------------------------------
_EXACT_FILENAMES: frozenset[str] = frozenset(
    {
        # Environment / dotenv
        ".env",
        ".env.local",
        ".env.development",
        ".env.development.local",
        ".env.test",
        ".env.test.local",
        ".env.production",
        ".env.production.local",
        ".env.staging",
        # SSH private keys
        "id_rsa",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        "id_rsa.pub",       # public keys can leak usernames / hosts
        "id_dsa.pub",
        "id_ecdsa.pub",
        "id_ed25519.pub",
        # Generic key/credential filenames
        "private_key",
        "private-key",
        "secret_key",
        "secret-key",
        "credentials",
        "credentials.json",  # Google service-account / AWS credential files
        "service_account.json",
        "service-account.json",
        # Cloud / infrastructure credentials
        "terraform.tfvars",
        "terraform.tfvars.json",
        ".terraformrc",
        "backend.tfvars",
        # Password / vault files
        ".htpasswd",
        ".netrc",
        ".pgpass",
        "pass.txt",
        "passwords.txt",
        # Database dump files that may contain auth details
        "dump.sql",
        "database.sql",
        # Auth / token files
        ".npmrc",           # may contain registry auth tokens
        ".pypirc",          # may contain PyPI credentials
        ".docker/config.json",
        "auth.json",
        "token",
        "token.json",
        "access_token",
        "refresh_token",
        # Certificate / keystore files (exact names)
        "keystore.jks",
        "truststore.jks",
        "cacerts",
        # Generic secrets files
        "secrets.yml",
        "secrets.yaml",
        "secrets.json",
        "secrets.toml",
        "secret.yml",
        "secret.yaml",
        "secret.json",
        "secret.toml",
    }
)

# ---------------------------------------------------------------------------
# Glob patterns matched against the filename only (case-insensitive)
# ---------------------------------------------------------------------------
_FILENAME_GLOBS: tuple[str, ...] = (
    ".env.*",           # .env.local, .env.production, etc.
    "*.pem",            # PEM-encoded private keys / certs
    "*.key",            # generic private key files
    "*.p12",            # PKCS#12 keystores
    "*.pfx",            # same format, different extension
    "*.jks",            # Java keystores
    "*.keystore",
    "*.truststore",
    "*.cer",            # certificate files (may bundle private key)
    "*.crt",            # same
    "*.der",            # DER-encoded cert / key
    "*.ppk",            # PuTTY private key
    "*.kdbx",           # KeePass database
    "*.kdb",
    "*_rsa",            # id_rsa variants
    "*_dsa",
    "*_ecdsa",
    "*_ed25519",
    "*.secrets",        # *.secrets files
    "*secret*",         # anything with "secret" in the name
    "*credential*",     # anything with "credential" in the name
    "*password*",       # anything with "password" in the name
    "*passwd*",
    "*apikey*",         # anything with "apikey" in the name
    "*api_key*",
    "*api-key*",
    "*token*",          # anything with "token" in the name — broad but safe
    "*.tfvars",         # all Terraform variable files
    "*.vault",          # Ansible vault encrypted files
)

# ---------------------------------------------------------------------------
# Path *segment* names that indicate a secrets directory
# ---------------------------------------------------------------------------
_SENSITIVE_DIR_SEGMENTS: frozenset[str] = frozenset(
    {
        ".ssh",
        ".gnupg",
        ".gpg",
        "secrets",
        "secret",
        "credentials",
        "private",
        ".aws",
        ".azure",
        ".gcloud",
        ".kube",        # Kubernetes config directory
    }
)


def is_secret_file(relative_path: str) -> bool:
    """
    Return True if *relative_path* looks like a sensitive / secret file
    that must be excluded from discovery and never stored or processed.

    Parameters
    ----------
    relative_path:
        Forward-slash relative path from the repository root,
        e.g. "config/.env.production".

    No file I/O is performed — only the path string is inspected.
    """
    path = PurePosixPath(relative_path)
    filename_lower = path.name.lower()

    # 1. Exact filename match
    if filename_lower in _EXACT_FILENAMES:
        logger.debug("Secret filter [exact]: %s", relative_path)
        return True

    # 2. Glob pattern match against filename
    for pattern in _FILENAME_GLOBS:
        if fnmatch.fnmatch(filename_lower, pattern.lower()):
            logger.debug("Secret filter [glob %s]: %s", pattern, relative_path)
            return True

    # 3. Any path segment is a known sensitive directory
    parts_lower = [p.lower() for p in path.parts[:-1]]  # exclude filename
    for segment in parts_lower:
        if segment in _SENSITIVE_DIR_SEGMENTS:
            logger.debug("Secret filter [dir segment %s]: %s", segment, relative_path)
            return True

    return False
