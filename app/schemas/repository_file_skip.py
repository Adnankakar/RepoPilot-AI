from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RepositoryFileSkipResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    repository_id: str
    path: str
    reason: str
    skipped_at: datetime
