import uuid

from pydantic import BaseModel


class InsightOut(BaseModel):
    id: uuid.UUID
    text: str


class UnseenInsightsOut(BaseModel):
    insights: list[InsightOut]
