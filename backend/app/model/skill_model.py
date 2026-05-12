from __future__ import annotations

from pydantic import BaseModel, Field

from app.db.schema import TbSkill, TbSkillVersion
from app.model.app_category_model import AppCategoryRef

# ── Skill Tool (binding) ──


class SkillToolItem(BaseModel):
    tool_id: str = Field(default="0")
    tool_source: str = Field(min_length=1, max_length=255)
    tool_name: str = Field(min_length=1, max_length=255)


# ── Skill ──


_SKILL_NAME_PATTERN = r"^[a-z0-9-]+$"


class SkillCreateReq(BaseModel):
    name: str = Field(min_length=1, max_length=64, pattern=_SKILL_NAME_PATTERN)
    description: str | None = Field(default=None)
    # 关联的应用分类 ID 列表（多对多）
    category_ids: list[str] | None = Field(default=None)
    instruction: str = Field(min_length=1)
    tools: list[SkillToolItem] = Field(default_factory=list)


class SkillUpdateReq(BaseModel):
    name: str | None = Field(default=None, max_length=64, pattern=_SKILL_NAME_PATTERN)
    description: str | None = Field(default=None)
    # None 表示不更新，[] 表示清空
    category_ids: list[str] | None = Field(default=None)
    instruction: str | None = Field(default=None)
    tools: list[SkillToolItem] | None = Field(default=None)


class SkillPageReq(BaseModel):
    page_no: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=10000)
    keyword: str | None = Field(default=None, max_length=255)
    category_id: str | None = Field(default=None)
    skill_status: str | None = Field(default=None, max_length=255)


class SkillPublishReq(BaseModel):
    version: str = Field(min_length=1, max_length=255)
    version_note: str | None = Field(default=None)


class SkillToolResp(BaseModel):
    tool_id: str
    tool_source: str
    tool_name: str


class SkillResp(BaseModel):
    id: str
    name: str
    description: str | None = None
    # 关联的应用分类
    category_ids: list[str] = Field(default_factory=list)
    categories: list[AppCategoryRef] = Field(default_factory=list)
    instruction: str
    skill_status: str
    current_version: str | None = None
    tools: list[SkillToolResp] = []
    create_time: int
    update_time: int

    @classmethod
    def from_entity(
        cls,
        entity: TbSkill,
        tools: list[SkillToolResp] | None = None,
        categories: list[AppCategoryRef] | None = None,
    ) -> SkillResp:
        cats = categories or []
        return cls(
            id=str(entity.id),
            name=entity.name,
            description=entity.description,
            category_ids=[c.id for c in cats],
            categories=cats,
            instruction=entity.instruction,
            skill_status=entity.skill_status,
            current_version=entity.current_version,
            tools=tools or [],
            create_time=entity.create_time,
            update_time=entity.update_time,
        )


class SkillVersionResp(BaseModel):
    id: str
    skill_id: str
    version: str
    version_note: str | None = None
    published_time: int
    create_time: int

    @classmethod
    def from_entity(cls, entity: TbSkillVersion) -> SkillVersionResp:
        return cls(
            id=str(entity.id),
            skill_id=str(entity.skill_id),
            version=entity.version,
            version_note=entity.version_note,
            published_time=entity.published_time,
            create_time=entity.create_time,
        )
