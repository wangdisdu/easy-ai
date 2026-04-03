from __future__ import annotations

from pydantic import BaseModel, Field

from app.db.schema import TbSkill, TbSkillVersion

# ── Skill Tool (binding) ──


class SkillToolItem(BaseModel):
    tool_id: str = Field(default="0")
    tool_source: str = Field(min_length=1, max_length=255)
    tool_name: str = Field(min_length=1, max_length=255)


# ── Skill ──


class SkillCreateReq(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None)
    category: str | None = Field(default=None, max_length=255)
    instruction: str = Field(min_length=1)
    tools: list[SkillToolItem] = Field(default_factory=list)


class SkillUpdateReq(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None)
    category: str | None = Field(default=None, max_length=255)
    instruction: str | None = Field(default=None)
    tools: list[SkillToolItem] | None = Field(default=None)


class SkillPageReq(BaseModel):
    page_no: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=10000)
    keyword: str | None = Field(default=None, max_length=255)
    category: str | None = Field(default=None, max_length=255)
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
    category: str | None = None
    instruction: str
    skill_status: str
    current_version: str | None = None
    tools: list[SkillToolResp] = []
    create_time: int
    update_time: int

    @classmethod
    def from_entity(cls, entity: TbSkill, tools: list[SkillToolResp] | None = None) -> SkillResp:
        return cls(
            id=str(entity.id),
            name=entity.name,
            description=entity.description,
            category=entity.category,
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
