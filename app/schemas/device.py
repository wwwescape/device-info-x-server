from pydantic import BaseModel, Field


class DeviceRegisterRequest(BaseModel):
    fcm_token: str = Field(min_length=1, max_length=255)
    platform: str = Field(default="android", max_length=32)
    app_version: str | None = Field(default=None, max_length=32)
