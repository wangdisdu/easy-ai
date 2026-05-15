"""平台级 KV 配置 service。

封装 tb_system_setting 的 get/set/list。仅做读写,不做语义校验——
具体业务(例如 "ai.default.embedding_model_id 必须指向存在的 Embedding 类型 model")
由上层调用方在写入前自行校验。

设计原因:这张表是"平台级"杂项 KV,各个业务都会写,在 service 层做语义校验会
变成大开关 switch 反而难维护;把校验留给最理解该 key 含义的业务模块。
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.request_context import RequestContext
from app.db.schema import TbSystemSetting
from app.model.system_setting_model import SystemSettingResp

logger = logging.getLogger(__name__)


# 当前已知的 AI 基础设施默认指针 key,前端"AI 基础设施"页据此渲染选项
AI_DEFAULT_EMBEDDING_KEY = "ai.default.embedding_model_id"
AI_DEFAULT_RERANK_KEY = "ai.default.rerank_model_id"
AI_DEFAULT_VISION_KEY = "ai.default.vision_model_id"


class SystemSettingService:
    def get(self, db: Session, key: str) -> str | None:
        entity = db.get(TbSystemSetting, key)
        return entity.setting_value if entity else None

    def get_resp(self, db: Session, key: str) -> SystemSettingResp:
        entity = db.get(TbSystemSetting, key)
        if not entity:
            return SystemSettingResp(key=key, value=None)
        return SystemSettingResp(
            key=entity.setting_key,
            value=entity.setting_value,
            update_time=entity.update_time,
        )

    def list_all(self, db: Session) -> list[SystemSettingResp]:
        rows = db.scalars(select(TbSystemSetting)).all()
        return [
            SystemSettingResp(key=r.setting_key, value=r.setting_value, update_time=r.update_time)
            for r in rows
        ]

    def set(
        self, db: Session, key: str, value: str | None, req_ctx: RequestContext
    ) -> SystemSettingResp:
        entity = db.get(TbSystemSetting, key)
        if entity is None:
            entity = TbSystemSetting(
                setting_key=key,
                setting_value=value,
                update_time=req_ctx.request_time_ms,
                update_user=req_ctx.user_id,
            )
            db.add(entity)
        else:
            entity.setting_value = value
            entity.update_time = req_ctx.request_time_ms
            entity.update_user = req_ctx.user_id
        db.commit()
        logger.info(
            "[system-setting] set key=%s value_len=%s user=%s",
            key,
            len(value) if value else 0,
            req_ctx.user_id,
        )
        return SystemSettingResp(
            key=entity.setting_key,
            value=entity.setting_value,
            update_time=entity.update_time,
        )
