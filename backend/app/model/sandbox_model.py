from __future__ import annotations

from pydantic import BaseModel, Field

from app.db.schema import TbSandboxImage


class SandboxImageCreateReq(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    image: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None)
    # 默认资源画像;空=不限制。cpu 形如 "1"/"0.5",memory 形如 "512Mi"/"2Gi"
    cpu: str | None = Field(default=None, max_length=64)
    memory: str | None = Field(default=None, max_length=64)
    is_default: bool = Field(default=False)
    enabled: bool = Field(default=True)


class SandboxImageUpdateReq(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    image: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None)
    cpu: str | None = Field(default=None, max_length=64)
    memory: str | None = Field(default=None, max_length=64)
    is_default: bool | None = Field(default=None)
    enabled: bool | None = Field(default=None)


class SandboxImagePageReq(BaseModel):
    page_no: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=10000)
    keyword: str | None = Field(default=None, max_length=255)


class SandboxViewResp(BaseModel):
    """可视化沙盒(noVNC 桌面)访问信息。ready=False 表示该会话沙盒尚未创建。"""

    ready: bool
    url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)


class SandboxInstanceResp(BaseModel):
    """运行中的沙盒实例(管理页用)。"""

    id: str
    status: str
    image: str | None = None
    created_at: str | None = None
    expires_at: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class SandboxImageResp(BaseModel):
    id: str
    name: str
    image: str
    description: str | None = None
    cpu: str | None = None
    memory: str | None = None
    is_default: bool
    enabled: bool
    create_time: int
    update_time: int

    @classmethod
    def from_entity(cls, entity: TbSandboxImage) -> SandboxImageResp:
        return cls(
            id=str(entity.id),
            name=entity.name,
            image=entity.image,
            description=entity.description,
            cpu=entity.cpu,
            memory=entity.memory,
            is_default=bool(entity.is_default),
            enabled=bool(entity.enabled),
            create_time=entity.create_time,
            update_time=entity.update_time,
        )
