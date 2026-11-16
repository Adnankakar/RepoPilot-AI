from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class RepositoryCreate(BaseModel):
    url: HttpUrl


class RepositoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_id: str
    provider: str
    external_id: str
    url: str
    default_branch: str
    indexed_commit: str | None
    status: str
    created_at: datetime


class RepositoryRegistrationResponse(BaseModel):
    repository: RepositoryResponse
    indexing_job_id: str
    job_id: str | None = None
    message: str = Field(default="Repository registered successfully.")

    def model_post_init(self, __context):
        if self.job_id is None:
            self.job_id = self.indexing_job_id