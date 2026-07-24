from pydantic import BaseModel


class TurnCredentialsResponse(BaseModel):
    urls: list[str]
    username: str
    credential: str
    ttl: int
