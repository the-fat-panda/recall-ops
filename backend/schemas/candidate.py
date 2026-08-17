from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class IncidentMatch(BaseModel):
    id: UUID
    signature: str
    description: str
    environment: str
    created_at: datetime
    similarity: float


class ScoredAction(BaseModel):
    action: str
    success_count: int
    fail_count: int
    confidence: float
    freshness: float
    last_success_at: datetime | None = None
    last_env_version: str | None = None
