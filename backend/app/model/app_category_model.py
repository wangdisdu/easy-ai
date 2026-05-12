from __future__ import annotations

from pydantic import BaseModel, Field

from app.db.schema import TbAppCategory


class AppCategoryCreateReq(BaseModel):
    code: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None)
    sort_order: int = Field(default=0)


class AppCategoryUpdateReq(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None)
    sort_order: int | None = Field(default=None)


class AppCategoryPageReq(BaseModel):
    page_no: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=10000)
    keyword: str | None = Field(default=None, max_length=255)


class AppCategoryResp(BaseModel):
    id: str
    code: str
    name: str
    description: str | None = None
    sort_order: int
    create_time: int
    update_time: int

    @classmethod
    def from_entity(cls, entity: TbAppCategory) -> AppCategoryResp:
        return cls(
            id=str(entity.id),
            code=entity.code,
            name=entity.name,
            description=entity.description,
            sort_order=entity.sort_order,
            create_time=entity.create_time,
            update_time=entity.update_time,
        )


# 嵌入到 app / skill 响应里的轻量分类引用
class AppCategoryRef(BaseModel):
    id: str
    name: str
