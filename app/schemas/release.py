from pydantic import BaseModel


class ReleaseOut(BaseModel):
    latest_build: str | None
    download_url: str | None
