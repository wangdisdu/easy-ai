from pydantic import BaseModel, Field

from app.db.schema import TbUser

PASSWD_MIN_LEN = 4


class UserCreateReq(BaseModel):
    account: str = Field(min_length=1, max_length=255)
    passwd: str = Field(min_length=PASSWD_MIN_LEN)
    email: str | None = Field(default=None, max_length=255)
    name: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=255)
    department: str | None = Field(default=None, max_length=255)
    role_ids: list[str] = Field(default_factory=list)


class UserPageReq(BaseModel):
    page_no: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=10000)
    keyword: str | None = Field(default=None, max_length=255)


class UserUpdateReq(BaseModel):
    email: str | None = Field(default=None, max_length=255)
    name: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=255)
    department: str | None = Field(default=None, max_length=255)
    role_ids: list[str] | None = None


class UserResetPasswordReq(BaseModel):
    new_passwd: str = Field(min_length=PASSWD_MIN_LEN)


class UserLoginReq(BaseModel):
    account: str = Field(min_length=1, max_length=255)
    passwd: str = Field(min_length=PASSWD_MIN_LEN)


class UserLoginResp(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserResp"


class UserRoleResp(BaseModel):
    id: str
    code: str
    name: str


class UserResp(BaseModel):
    id: str
    account: str
    email: str | None = None
    name: str | None = None
    phone: str | None = None
    department: str | None = None
    roles: list[UserRoleResp] = Field(default_factory=list)
    create_time: int
    update_time: int

    @classmethod
    def from_entity(cls, user: TbUser, roles: list[UserRoleResp] | None = None) -> "UserResp":
        return cls(
            id=str(user.id),
            account=user.account,
            email=user.email,
            name=user.name,
            phone=user.phone,
            department=user.department,
            roles=roles or [],
            create_time=user.create_time,
            update_time=user.update_time,
        )


UserLoginResp.model_rebuild()
