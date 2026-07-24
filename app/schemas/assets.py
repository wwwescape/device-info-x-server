from pydantic import BaseModel


class AssetListResponse(BaseModel):
    # Ids are filename stems, sorted naturally. `nsfw` is only populated when the client asked for
    # mature content (`?mature=true`) — otherwise it's always empty.
    standard: list[str]
    nsfw: list[str]
