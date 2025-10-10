from pydantic import BaseModel, ConfigDict

# 前向引用，避免循环导入
from .permission import PermissionOut


class RoleCreate(BaseModel):
    name: str
    description: str | None = None


class RoleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class RoleOut(BaseModel):
    id: str
    name: str
    description: str | None = None
    permissions: list[PermissionOut] = []

    model_config = ConfigDict(from_attributes=True)
