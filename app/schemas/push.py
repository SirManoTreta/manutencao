from typing import Literal

from pydantic import BaseModel, Field

from .common import WriteModel


class PushRegister(WriteModel):
    fcm_token: str = Field(min_length=1, max_length=4096)
    platform: Literal["android", "ios"] = "android"
    device_name: str | None = Field(default=None, max_length=120)


class PushUnregister(WriteModel):
    fcm_token: str = Field(min_length=1, max_length=4096)


class PushRegistrationStatus(BaseModel):
    registered: bool = True


class PushUnregistrationStatus(BaseModel):
    unregistered: bool = True


class PushStatus(BaseModel):
    enabled: bool
    credentials_configured: bool
    active_devices: int
