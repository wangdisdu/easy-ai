from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.db.schema import TbMemory, TbMemoryAudit

MemoryScope = Literal["user", "app"]
MemorySource = Literal["user_explicit", "agent_learned", "admin_set"]


class MemoryUpsertReq(BaseModel):
    scope: MemoryScope
    scope_id: str = Field(min_length=1)  # 字符串传输 snowflake id
    memory_key: str = Field(min_length=1, max_length=255)
    memory_value: str = Field(min_length=1)
    source: MemorySource = "user_explicit"


class MemoryListReq(BaseModel):
    scope: MemoryScope
    scope_id: str = Field(min_length=1)
    limit: int = Field(default=100, ge=1, le=1000)


class MemoryResp(BaseModel):
    id: str
    scope: str
    scope_id: str
    owner_user_id: str | None = None
    memory_key: str
    memory_value: str
    source: str
    create_time: int
    update_time: int

    @classmethod
    def from_entity(cls, entity: TbMemory) -> MemoryResp:
        return cls(
            id=str(entity.id),
            scope=entity.scope,
            scope_id=str(entity.scope_id),
            owner_user_id=str(entity.owner_user_id) if entity.owner_user_id else None,
            memory_key=entity.memory_key,
            memory_value=entity.memory_value,
            source=entity.source,
            create_time=entity.create_time,
            update_time=entity.update_time,
        )


class MemoryAuditResp(BaseModel):
    id: str
    event_type: str
    scope: str
    scope_id: str
    memory_key: str
    memory_value_before: str | None = None
    memory_value_after: str | None = None
    source: str
    actor_user_id: str | None = None
    app_id: str | None = None
    conversation_id: str | None = None
    create_time: int

    @classmethod
    def from_entity(cls, entity: TbMemoryAudit) -> MemoryAuditResp:
        return cls(
            id=str(entity.id),
            event_type=entity.event_type,
            scope=entity.scope,
            scope_id=str(entity.scope_id),
            memory_key=entity.memory_key,
            memory_value_before=entity.memory_value_before,
            memory_value_after=entity.memory_value_after,
            source=entity.source,
            actor_user_id=str(entity.actor_user_id) if entity.actor_user_id else None,
            app_id=str(entity.app_id) if entity.app_id else None,
            conversation_id=str(entity.conversation_id) if entity.conversation_id else None,
            create_time=entity.create_time,
        )
