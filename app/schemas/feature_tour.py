from pydantic import BaseModel


class SeenToursOut(BaseModel):
    seen_tour_keys: list[str]
