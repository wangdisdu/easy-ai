from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.error_code import ErrorCode
from app.core.exceptions import ServiceError
from app.core.snowflake import SnowflakeGenerator
from app.db.schema import TbApp, TbAppLog
from app.model.open_model import AppLogResp


class AppLogService:
    def __init__(self, id_generator: SnowflakeGenerator) -> None:
        self._id_generator = id_generator

    def create_log(
        self,
        db: Session,
        *,
        app_id: int | None,
        app_type: str | None,
        provider_id: int | None,
        model_id: int | None,
        model: str | None,
        request_type: str,
        request_payload: Any,
        response_payload: Any,
        success: bool,
        response_status: int | None,
        latency_ms: int | None,
        error_message: str | None,
        langfuse_trace_id: str | None,
        total_tokens: int | None,
        input_tokens: int | None,
        output_tokens: int | None,
        now: int,
        user_id: int | None,
    ) -> TbAppLog:
        entity = TbAppLog(
            id=self._id_generator.next_id(),
            app_id=app_id,
            app_type=app_type,
            provider_id=provider_id,
            model_id=model_id,
            model=model,
            request_type=request_type,
            request_payload=self._to_json(request_payload),
            response_payload=self._to_json(response_payload),
            success=1 if success else 0,
            response_status=response_status,
            latency_ms=latency_ms,
            error_message=error_message,
            langfuse_trace_id=langfuse_trace_id,
            total_tokens=total_tokens,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            create_time=now,
            update_time=now,
            create_user=user_id,
            update_user=user_id,
        )
        db.add(entity)
        db.commit()
        db.refresh(entity)
        return entity

    def list_logs(self, db: Session, limit: int = 100) -> list[AppLogResp]:
        rows: Sequence[TbAppLog] = db.scalars(
            select(TbAppLog).order_by(desc(TbAppLog.create_time)).limit(limit)
        ).all()
        return [self._to_resp(row) for row in rows]

    def list_app_logs(self, db: Session, app_id: int, limit: int = 100) -> list[AppLogResp]:
        app = db.get(TbApp, app_id)
        if not app:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "app not found")
        rows: Sequence[TbAppLog] = db.scalars(
            select(TbAppLog)
            .where(TbAppLog.app_id == app_id)
            .order_by(desc(TbAppLog.create_time))
            .limit(limit)
        ).all()
        return [self._to_resp(row) for row in rows]

    def _to_resp(self, entity: TbAppLog) -> AppLogResp:
        return AppLogResp(
            id=str(entity.id),
            app_id=str(entity.app_id) if entity.app_id is not None else None,
            app_type=entity.app_type,
            provider_id=str(entity.provider_id) if entity.provider_id is not None else None,
            model_id=str(entity.model_id) if entity.model_id is not None else None,
            model=entity.model,
            request_type=entity.request_type,
            success=bool(entity.success),
            response_status=entity.response_status,
            latency_ms=entity.latency_ms,
            error_message=entity.error_message,
            langfuse_trace_id=entity.langfuse_trace_id,
            total_tokens=entity.total_tokens,
            input_tokens=entity.input_tokens,
            output_tokens=entity.output_tokens,
            request_payload=self._parse_json(entity.request_payload),
            response_payload=self._parse_json(entity.response_payload),
            create_time=entity.create_time,
        )

    def _to_json(self, value: Any) -> str | None:
        if value is None:
            return None
        try:
            return json.dumps(value, ensure_ascii=False)
        except TypeError:
            return json.dumps(str(value), ensure_ascii=False)

    def _parse_json(self, value: str | None) -> Any:
        if not value:
            return None
        try:
            return json.loads(value)
        except ValueError:
            return value
