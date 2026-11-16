from datetime import datetime

from pydantic import BaseModel, ConfigDict


class IndexingJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    repository_id: str
    status: str
    attempt_count: int
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_summary: str | None = None
    failed_stage: str | None = None
    created_at: datetime
    job_id: str | None = None

    def model_post_init(self, __context):
        if self.job_id is None:
            self.job_id = self.id


class TriggerIndexingResponse(BaseModel):
    indexing_job_id: str
    job_id: str | None = None
    message: str = "Indexing job queued."

    def model_post_init(self, __context):
        if self.job_id is None:
            self.job_id = self.indexing_job_id


class RepositoryStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    repository_id: str
    status: str
    latest_job: IndexingJobResponse | None = None
