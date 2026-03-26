from pydantic import BaseModel, Field

from app.db.schema import TbUserGroup


class UserGroupCreateReq(BaseModel):
    code: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255)


class UserGroupPageReq(BaseModel):
    page_no: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=10000)
    keyword: str | None = Field(default=None, max_length=255)


class UserGroupUpdateReq(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class UserGroupResp(BaseModel):
    id: str
    code: str
    name: str
    create_time: int
    update_time: int

    @classmethod
    def from_entity(cls, entity: TbUserGroup) -> "UserGroupResp":
        return cls(
            id=str(entity.id),
            code=entity.code,
            name=entity.name,
            create_time=entity.create_time,
            update_time=entity.update_time,
        )


class UserGroupMemberAddReq(BaseModel):
    user_id: str


class UserGroupMemberResp(BaseModel):
    id: str
    user_id: str
    group_id: str
