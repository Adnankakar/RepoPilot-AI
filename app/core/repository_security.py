from urllib.parse import urlsplit


class RepositoryURLValidationError(ValueError):
    """Raised when a repository URL is not allowed."""


def parse_github_repo_url(repo_url: str) -> tuple[str, str, str]:
    if not isinstance(repo_url, str) or not repo_url.strip():
        raise RepositoryURLValidationError("Repository URL is required.")

    raw_url = repo_url.strip()

    try:
        parsed = urlsplit(raw_url)
        port = parsed.port
    except ValueError as exc:
        raise RepositoryURLValidationError("Invalid repository URL.") from exc

    if parsed.scheme.lower() != "https":
        raise RepositoryURLValidationError(
            "Only HTTPS GitHub repository URLs are allowed."
        )

    if parsed.hostname is None or parsed.hostname.lower() != "github.com":
        raise RepositoryURLValidationError(
            "Only public repositories hosted on github.com are supported."
        )

    if parsed.username or parsed.password:
        raise RepositoryURLValidationError(
            "Credentials are not allowed in repository URLs."
        )

    if port not in (None, 443):
        raise RepositoryURLValidationError("Custom ports are not allowed.")

    if parsed.query or parsed.fragment:
        raise RepositoryURLValidationError(
            "Query strings and fragments are not allowed."
        )

    if "%" in parsed.path or "\\" in parsed.path:
        raise RepositoryURLValidationError("Invalid repository path.")

    parts = parsed.path.strip("/").split("/")

    if len(parts) != 2 or not all(parts):
        raise RepositoryURLValidationError(
            "URL must have the format https://github.com/owner/repository."
        )

    owner, repository = parts

    if repository.endswith(".git"):
        repository = repository[:-4]

    valid_chars = set(
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789-_."
    )

    if (
        not owner
        or not repository
        or owner in {".", ".."}
        or repository in {".", ".."}
        or not set(owner) <= valid_chars
        or not set(repository) <= valid_chars
    ):
        raise RepositoryURLValidationError("Invalid GitHub owner or repository.")

    canonical_url = f"https://github.com/{owner}/{repository}"
    return owner, repository, canonical_url