from pydantic import BaseModel, Field


class Alert(BaseModel):
    service: str
    symptom: str
    meta: dict = Field(default_factory=dict)
