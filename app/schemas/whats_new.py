from pydantic import BaseModel


class SeenWhatsNewOut(BaseModel):
    seen_tags: list[str]
