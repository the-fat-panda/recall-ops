from typing import Literal

from pydantic import BaseModel, Field

from backend.schemas.candidate import ScoredAction


class ExperienceCard(BaseModel):
    signature: str
    match_summary: str
    live_evidence: dict = Field(default_factory=dict)
    candidates: list[ScoredAction] = Field(default_factory=list)
    chosen_action: str = ""
    failed_history: list[str] = Field(default_factory=list)
    confidence_band: Literal["HIGH", "MEDIUM", "LOW"]
    explanation: str = ""
    outcome: Literal["RECOMMENDED", "ESCALATED"]
