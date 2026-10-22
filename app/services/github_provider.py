from dataclasses import dataclass

import httpx


GITHUB_API_BASE = "https://api.github.com"


class GitHubRepositoryError(Exception):
    """Base error for GitHub repository operations."""


class GitHubRepositoryNotFound(GitHubRepositoryError):
    pass


class GitHubRepositoryEmpty(GitHubRepositoryError):
    pass


class GitHubProviderUnavailable(GitHubRepositoryError):
    pass


@dataclass(frozen=True)
class GitHubRepositoryInfo:
    owner: str
    name: str
    url: str
    default_branch: str
    latest_commit: str
    external_id: str


class GitHubProvider:
    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    def get_repository(self, owner: str, repository: str) -> GitHubRepositoryInfo:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "RepoPilot-AI",
        }

        try:
            with httpx.Client(
                timeout=self.timeout,
                follow_redirects=False,
                headers=headers,
            ) as client:
                response = client.get(
                    f"{GITHUB_API_BASE}/repos/{owner}/{repository}"
                )

                if response.status_code == 404:
                    raise GitHubRepositoryNotFound(
                        "GitHub repository was not found or is not public."
                    )

                if response.status_code == 403:
                    raise GitHubProviderUnavailable(
                        "GitHub API rate limit or access restriction reached."
                    )

                response.raise_for_status()
                data = response.json()

                if data.get("private", True):
                    raise GitHubRepositoryNotFound(
                        "Only public GitHub repositories are supported."
                    )

                if int(data.get("size", 0)) <= 0:
                    raise GitHubRepositoryEmpty(
                        "This GitHub repository is empty."
                    )

                default_branch = data.get("default_branch")
                external_id = data.get("id")

                if not default_branch or external_id is None:
                    raise GitHubRepositoryEmpty(
                        "Repository has no default branch or commit."
                    )

                commit_response = client.get(
                    f"{GITHUB_API_BASE}/repos/{owner}/{repository}"
                    f"/commits/{default_branch}"
                )

                if commit_response.status_code == 404:
                    raise GitHubRepositoryEmpty(
                        "No commit was found on the default branch."
                    )

                if commit_response.status_code == 403:
                    raise GitHubProviderUnavailable(
                        "GitHub API rate limit or access restriction reached."
                    )

                commit_response.raise_for_status()
                commit_data = commit_response.json()
                commit_sha = commit_data.get("sha")

                if not commit_sha:
                    raise GitHubRepositoryEmpty(
                        "Could not find a commit on the default branch."
                    )

                return GitHubRepositoryInfo(
                    owner=data["owner"]["login"],
                    name=data["name"],
                    url=data["html_url"],
                    default_branch=default_branch,
                    latest_commit=commit_sha,
                    external_id=str(external_id),
                )

        except (
            GitHubRepositoryNotFound,
            GitHubRepositoryEmpty,
            GitHubProviderUnavailable,
        ):
            raise
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise GitHubProviderUnavailable(
                "Could not retrieve repository information from GitHub."
            ) from exc