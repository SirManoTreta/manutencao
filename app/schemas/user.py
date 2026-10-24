from pydantic import ConfigDict, Field, field_validator

from .common import ReadModel, UTCDateTime, WriteModel


class UserRead(ReadModel):
    id: int
    username: str
    is_admin: bool
    is_active: bool
    created_at: UTCDateTime | None = None


class UserCreate(WriteModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=1024)
    is_admin: bool = False

    @field_validator("username", mode="before")
    @classmethod
    def clean_username(cls, value):
        return value.strip() if isinstance(value, str) else value


class UserUpdate(WriteModel):
    username: str = Field(min_length=1, max_length=80)
    password: str | None = Field(default=None, max_length=1024)
    is_admin: bool = False
    is_active: bool = True
