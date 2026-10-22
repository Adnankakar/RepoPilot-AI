from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RepositoryFileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    repository_id: str
    path: str
    blob_hash: str | None
    language: str | None
    size_bytes: int
    commit_sha: str | None
    extension: str
    encoding: str
    discovered_at: datetime
