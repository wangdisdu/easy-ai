from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.core.error_code import ErrorCode
from app.core.exceptions import ServiceError
from app.core.request_context import RequestContext
from app.core.snowflake import SnowflakeGenerator
from app.db.schema import TbSandboxImage
from app.model.sandbox_model import (
    SandboxImageCreateReq,
    SandboxImagePageReq,
    SandboxImageResp,
    SandboxImageUpdateReq,
)

logger = logging.getLogger(__name__)


class SandboxImageService:
    def __init__(self, id_generator: SnowflakeGenerator) -> None:
        self._id_generator = id_generator

    # ── CRUD ──

    def create_image(
        self, db: Session, req: SandboxImageCreateReq, req_ctx: RequestContext
    ) -> SandboxImageResp:
        if db.scalar(select(TbSandboxImage).where(TbSandboxImage.name == req.name)):
            raise ServiceError(ErrorCode.DATA_DUPLICATE, "sandbox image name already exists")

        now = req_ctx.request_time_ms
        entity = TbSandboxImage(
            id=self._id_generator.next_id(),
            name=req.name,
            image=req.image,
            description=req.description,
            cpu=req.cpu,
            memory=req.memory,
            is_default=1 if req.is_default else 0,
            enabled=1 if req.enabled else 0,
            create_time=now,
            update_time=now,
            create_user=req_ctx.user_id,
            update_user=req_ctx.user_id,
        )
        db.add(entity)
        db.flush()
        if req.is_default:
            self._clear_other_defaults(db, keep_id=entity.id)
        db.commit()
        db.refresh(entity)
        return SandboxImageResp.from_entity(entity)

    def page_image(
        self, db: Session, req: SandboxImagePageReq
    ) -> tuple[list[SandboxImageResp], int]:
        stmt = select(TbSandboxImage)
        count_stmt = select(func.count(TbSandboxImage.id))
        if req.keyword:
            kw = f"%{req.keyword}%"
            cond = or_(TbSandboxImage.name.like(kw), TbSandboxImage.image.like(kw))
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)

        total = db.scalar(count_stmt) or 0
        offset = (req.page_no - 1) * req.page_size
        rows = db.scalars(
            stmt.order_by(TbSandboxImage.create_time.desc()).offset(offset).limit(req.page_size)
        ).all()
        return [SandboxImageResp.from_entity(r) for r in rows], total

    def list_enabled(self, db: Session) -> list[SandboxImageResp]:
        """供应用配置下拉选择:只列启用的镜像。"""
        rows = db.scalars(
            select(TbSandboxImage)
            .where(TbSandboxImage.enabled == 1)
            .order_by(TbSandboxImage.create_time.desc())
        ).all()
        return [SandboxImageResp.from_entity(r) for r in rows]

    def get_image_by_id(self, db: Session, image_id: int) -> SandboxImageResp:
        entity = db.get(TbSandboxImage, image_id)
        if not entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "sandbox image not found")
        return SandboxImageResp.from_entity(entity)

    def update_image(
        self,
        db: Session,
        image_id: int,
        req: SandboxImageUpdateReq,
        req_ctx: RequestContext,
    ) -> SandboxImageResp:
        entity = db.get(TbSandboxImage, image_id)
        if not entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "sandbox image not found")

        if req.name is not None and req.name != entity.name:
            if db.scalar(
                select(TbSandboxImage.id).where(
                    TbSandboxImage.name == req.name, TbSandboxImage.id != image_id
                )
            ):
                raise ServiceError(ErrorCode.DATA_DUPLICATE, "sandbox image name already exists")
            entity.name = req.name
        if req.image is not None:
            entity.image = req.image
        if req.description is not None:
            entity.description = req.description
        if req.cpu is not None:
            entity.cpu = req.cpu
        if req.memory is not None:
            entity.memory = req.memory
        if req.enabled is not None:
            entity.enabled = 1 if req.enabled else 0
        if req.is_default is not None:
            entity.is_default = 1 if req.is_default else 0
            if req.is_default:
                self._clear_other_defaults(db, keep_id=entity.id)

        entity.update_time = req_ctx.request_time_ms
        entity.update_user = req_ctx.user_id
        db.commit()
        db.refresh(entity)
        return SandboxImageResp.from_entity(entity)

    def delete_image(self, db: Session, image_id: int) -> None:
        entity = db.get(TbSandboxImage, image_id)
        if not entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "sandbox image not found")
        db.delete(entity)
        db.commit()

    # ── 供 Agent 运行时解析镜像 ──

    def resolve_image(self, db: Session, app_config: dict[str, Any]) -> dict[str, str] | None:
        """把 app_config.sandbox.image_id 解析成实际镜像。

        - 指定了 image_id:必须存在且 enabled,否则报错(配置错误应显式失败,
          不静默回退)。
        - 未指定:用 is_default 且 enabled 的那条;没有则返回 None
          (交给 OpenSandbox 部署默认镜像)。

        返回 ``{"image": ..., "cpu": ..., "memory": ...}`` 或 None。
        """
        sandbox_cfg = app_config.get("sandbox") or {}
        image_id = sandbox_cfg.get("image_id")

        if image_id:
            entity = db.get(TbSandboxImage, int(image_id))
            if not entity or not entity.enabled:
                raise ServiceError(
                    ErrorCode.BAD_REQUEST,
                    f"configured sandbox image unavailable: {image_id}",
                )
        else:
            entity = db.scalar(
                select(TbSandboxImage)
                .where(TbSandboxImage.is_default == 1, TbSandboxImage.enabled == 1)
                .order_by(TbSandboxImage.create_time.asc())
            )
            if entity is None:
                return None

        return {
            "image": entity.image,
            "cpu": entity.cpu or "",
            "memory": entity.memory or "",
        }

    # ── 内部 ──

    def _clear_other_defaults(self, db: Session, keep_id: int) -> None:
        """保证全局至多一条 is_default。"""
        db.execute(
            update(TbSandboxImage)
            .where(TbSandboxImage.id != keep_id, TbSandboxImage.is_default == 1)
            .values(is_default=0)
        )
