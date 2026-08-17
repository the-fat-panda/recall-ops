from typing import Literal

from pydantic import BaseModel

from backend.schemas.card import ExperienceCard


class Recommendation(BaseModel):
    outcome: Literal["RECOMMENDED", "ESCALATED"]
    chosen_action: str | None = None
    confidence_band: Literal["HIGH", "MEDIUM", "LOW"] | None = None
    card: ExperienceCard | None = None
