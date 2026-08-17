from typing import Literal

from pydantic import BaseModel, Field

from backend.schemas.alert import Alert
from backend.schemas.candidate import IncidentMatch, ScoredAction
from backend.schemas.card import ExperienceCard


class AgentState(BaseModel):
    alert: Alert
    run_id: str
    signature: str = ""
    live_evidence: dict = Field(default_factory=dict)
    matches: list[IncidentMatch] = Field(default_factory=list)
    match_count: int = 0
    candidates: list[ScoredAction] = Field(default_factory=list)
    chosen: ScoredAction | None = None
    is_confident: bool = False
    confidence_band: Literal["HIGH", "MEDIUM", "LOW"] = "LOW"
    explanation: str = ""
    experience_card: ExperienceCard | None = None
    outcome: Literal["RECOMMENDED", "ESCALATED"] = "RECOMMENDED"

    approved: bool = False
    execution_result: dict | None = None
    writeback_done: bool = False
