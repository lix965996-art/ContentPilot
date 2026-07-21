from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RoleData(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str


class UserData(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: str
    email: str | None
    avatar_url: str | None
    status: str
    last_login_at: datetime | None
    roles: list[RoleData]
