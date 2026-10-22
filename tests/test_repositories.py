import pytest

from app.core.repository_security import (
    RepositoryURLValidationError,
    parse_github_repo_url,
)


def test_valid_github_url():
    owner, repository, canonical_url = parse_github_repo_url(
        "https://github.com/psf/requests"
    )

    assert owner == "psf"
    assert repository == "requests"
    assert canonical_url == "https://github.com/psf/requests"


def test_valid_github_url_with_git_suffix():
    owner, repository, _ = parse_github_repo_url(
        "https://github.com/psf/requests.git"
    )

    assert owner == "psf"
    assert repository == "requests"


@pytest.mark.parametrize(
    "url",
    [
        "",
        "not-a-url",
        "http://github.com/psf/requests",
        "https://github.com.evil.example/psf/requests",
        "https://evil.example/github.com/psf/requests",
        "https://user:password@github.com/psf/requests",
        "https://github.com:8443/psf/requests",
        "https://127.0.0.1/psf/requests",
        "https://github.com/psf/requests?next=https://evil.example",
        "https://github.com/psf/requests#fragment",
        "https://github.com/psf",
        "https://github.com/psf/requests/tree/main",
        "https://github.com/%70sf/requests",
    ],
)
def test_rejects_unsafe_or_invalid_urls(url):
    with pytest.raises(RepositoryURLValidationError):
        parse_github_repo_url(url)