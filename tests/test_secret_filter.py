"""
Tests for app/services/secret_filter.py

Covers exact filename matches, glob patterns, and sensitive directory
segment detection.  No file I/O — all tests operate on path strings.
"""

import pytest

from app.services.secret_filter import is_secret_file


# ---------------------------------------------------------------------------
# Files that MUST be excluded
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", [
    # Exact dotenv filenames
    ".env",
    ".env.local",
    ".env.production",
    ".env.staging",
    ".env.test",
    # Case-insensitive exact match
    ".ENV",
    ".Env.Production",
    # SSH private keys
    "id_rsa",
    "id_ed25519",
    "id_rsa.pub",
    # Generic credential filenames
    "credentials",
    "credentials.json",
    "service_account.json",
    # Cloud / infrastructure
    "terraform.tfvars",
    ".terraformrc",
    # Password / auth files
    ".htpasswd",
    ".netrc",
    ".pgpass",
    ".npmrc",
    ".pypirc",
    # Keystore / cert exact names
    "keystore.jks",
    "truststore.jks",
    # Generic secrets
    "secrets.yml",
    "secrets.yaml",
    "secrets.json",
    "secret.toml",
])
def test_exact_filenames_are_secret(path):
    assert is_secret_file(path) is True


@pytest.mark.parametrize("path", [
    # Glob: .env.*
    "config/.env.development",
    # Glob: *.pem
    "certs/server.pem",
    "server.PEM",
    # Glob: *.key
    "private.key",
    "tls/server.key",
    # Glob: *.p12 / *.pfx
    "client.p12",
    "client.pfx",
    # Glob: *.crt / *.cer / *.der
    "ca.crt",
    "client.cer",
    "cert.der",
    # Glob: *.ppk
    "putty.ppk",
    # Glob: *secret* / *credential* / *password* / *passwd*
    "my_secret_config.py",
    "app_credentials.json",
    "user_passwords.csv",
    "shadow_passwd.txt",
    # Glob: *apikey* / *api_key* / *api-key*
    "apikey.txt",
    "my_api_key.json",
    "service-api-key.yaml",
    # Glob: *token*
    "access_token.json",
    "github_token.txt",
    # Glob: *.tfvars / *.vault
    "prod.tfvars",
    "ansible.vault",
])
def test_glob_patterns_are_secret(path):
    assert is_secret_file(path) is True


@pytest.mark.parametrize("path", [
    # Sensitive directory segments
    ".ssh/config",
    ".ssh/known_hosts",
    "home/.gnupg/pubring.kbx",
    "deploy/.aws/credentials",
    "infra/.azure/config",
    ".gcloud/application_default_credentials.json",
    ".kube/config",
    "app/secrets/db.json",
    "config/private/settings.py",
    "src/credentials/api.py",
])
def test_sensitive_directory_segments_are_secret(path):
    assert is_secret_file(path) is True


# ---------------------------------------------------------------------------
# Files that MUST NOT be excluded
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", [
    "src/main.py",
    "README.md",
    "app/config.py",          # "config" alone is not sensitive
    "tests/test_auth.py",
    "docs/api.md",
    ".github/workflows/ci.yml",
    "requirements.txt",
    "pyproject.toml",
    "Makefile",
    "src/env_helper.py",      # contains "env" but not as a directory segment
    "public/index.html",
    "assets/style.css",
])
def test_safe_files_are_not_secret(path):
    assert is_secret_file(path) is False
