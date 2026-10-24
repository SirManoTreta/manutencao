from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class LoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=1024)


class AuthUser(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    is_admin: bool
    is_active: bool


class LoginOutput(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime
    user: AuthUser

    @field_serializer("expires_at")
    def serialize_expiry(self, value: datetime):
        return value.replace(tzinfo=timezone.utc).isoformat()


class DeviceInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    token: str = Field(min_length=1, max_length=4096)
    platform: Literal["android", "ios"] = "android"


class DeviceDelete(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    token: str = Field(min_length=1, max_length=4096)
