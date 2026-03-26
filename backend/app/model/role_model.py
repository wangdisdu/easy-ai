from pydantic import BaseModel, Field

from app.db.schema import TbRole


class RoleCreateReq(BaseModel):
    code: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    permissions: list[str] = Field(default_factory=list)


class RolePageReq(BaseModel):
    page_no: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=10000)
    keyword: str | None = Field(default=None, max_length=255)


class RoleUpdateReq(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    permissions: list[str] = Field(default_factory=list)


class RoleResp(BaseModel):
    id: str
    code: str
    name: str
    permissions: list[str]
    create_time: int
    update_time: int

    @classmethod
    def from_entity(cls, entity: TbRole, permissions: list[str]) -> "RoleResp":
        return cls(
            id=str(entity.id),
            code=entity.code,
            name=entity.name,
            permissions=permissions,
            create_time=entity.create_time,
            update_time=entity.update_time,
        )


class UserRoleAddReq(BaseModel):
    user_id: str
