from pydantic import BaseModel


class GifResult(BaseModel):
    id: str
    title: str | None = None
    width: int | None = None
    height: int | None = None
    # Both URLs point at this server's own `/gifs/proxy` route, never Klipy's CDN directly — same
    # "client never contacts an arbitrary third-party host" invariant link previews already follow.
    preview_url: str
    full_url: str


class GifListResponse(BaseModel):
    items: list[GifResult]
