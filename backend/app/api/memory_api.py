"""长期记忆 API：list / upsert / delete / audit / 自助 GDPR purge。

鉴权规则：
- scope=user：scope_id 必须 = 当前登录 user_id（不能读 / 改 / 删别人的记忆）
- scope=app：scope_id 必须是当前 user 创建（owner）的 app
- 自助 GDPR purge：仅清自己的 user-scope 全量；admin 维度的批量擦未提供（需 user_role 之后再加）
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.error_code import ErrorCode
from app.core.exceptions import ServiceError
from app.core.request_context import RequestContext, build_request_context
from app.core.response import Resp
from app.core.snowflake import SnowflakeGenerator
from app.db.session import get_db
from app.model.memory_model import MemoryAuditResp, MemoryResp, MemoryUpsertReq
from app.service.memory_service import MemoryService, can_write_app_memory

router = APIRouter(prefix="/memory", tags=["memory"])

service = MemoryService(SnowflakeGenerator(settings.snowflake_worker_id))


def _enforce_read_scope(scope: str, scope_id_str: str, req_ctx: RequestContext, db: Session) -> int:
    """归一化 scope_id 字符串为 int 并做读权限校验，返回校验后的 int。"""
    try:
        scope_id_int = int(scope_id_str)
    except (TypeError, ValueError):
        raise ServiceError(ErrorCode.BAD_REQUEST, "invalid scope_id") from None
    if scope == "user":
        if req_ctx.user_id is None or scope_id_int != req_ctx.user_id:
            raise ServiceError(ErrorCode.BAD_REQUEST, "cannot access other users' memories")
    elif scope == "app":
        if not can_write_app_memory(db, scope_id_int, req_ctx.user_id):
            raise ServiceError(ErrorCode.BAD_REQUEST, "only app owner can access app memories")
    else:
        raise ServiceError(ErrorCode.BAD_REQUEST, f"invalid scope: {scope}")
    return scope_id_int


@router.get("", response_model=Resp[list[MemoryResp]])
def list_memories(
    scope: str = Query(...),
    scope_id: str = Query(...),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[list[MemoryResp]]:
    scope_id_int = _enforce_read_scope(scope, scope_id, req_ctx, db)
    return Resp(data=service.list_memories(db, scope=scope, scope_id=scope_id_int, limit=limit))


@router.put("", response_model=Resp[MemoryResp])
def upsert_memory(
    req: MemoryUpsertReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[MemoryResp]:
    scope_id_int = _enforce_read_scope(req.scope, req.scope_id, req_ctx, db)
    # 人工写入只允许 user_explicit / admin_set；agent_learned 留给工具自动调用
    source = req.source if req.source != "agent_learned" else "user_explicit"
    return Resp(
        data=service.upsert_memory(
            db,
            scope=req.scope,
            scope_id=scope_id_int,
            memory_key=req.memory_key,
            memory_value=req.memory_value,
            source=source,
            actor_user_id=req_ctx.user_id,
            app_id=scope_id_int if req.scope == "app" else None,
            conversation_id=None,
        )
    )


@router.delete("", response_model=Resp[bool])
def delete_memory(
    scope: str = Query(...),
    scope_id: str = Query(...),
    memory_key: str = Query(...),
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[bool]:
    scope_id_int = _enforce_read_scope(scope, scope_id, req_ctx, db)
    ok = service.delete_memory(
        db,
        scope=scope,
        scope_id=scope_id_int,
        memory_key=memory_key,
        actor_user_id=req_ctx.user_id,
        app_id=scope_id_int if scope == "app" else None,
        conversation_id=None,
    )
    return Resp(data=ok)


@router.get("/audit", response_model=Resp[list[MemoryAuditResp]])
def list_audit(
    scope: str = Query(...),
    scope_id: str = Query(...),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[list[MemoryAuditResp]]:
    scope_id_int = _enforce_read_scope(scope, scope_id, req_ctx, db)
    return Resp(data=service.list_audit(db, scope=scope, scope_id=scope_id_int, limit=limit))


@router.delete("/_self", response_model=Resp[int])
def purge_self(
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[int]:
    """自助 GDPR：清空当前登录用户的全部 user-scope 记忆。"""
    if req_ctx.user_id is None:
        raise ServiceError(ErrorCode.UNAUTHORIZED, "login required")
    n = service.purge_user_memories(db, req_ctx.user_id, actor_user_id=req_ctx.user_id)
    return Resp(data=n)
