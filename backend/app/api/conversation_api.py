from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.request_context import RequestContext, build_request_context
from app.core.response import PagedResp, Resp
from app.core.snowflake import SnowflakeGenerator
from app.core.sse import sse_response
from app.db.session import SessionLocal, get_db
from app.model.conversation_model import (
    ConversationCreateReq,
    ConversationMessageResp,
    ConversationResp,
    ConversationUpdateReq,
    SendMessageReq,
)
from app.service.conversation_service import ConversationService

router = APIRouter(prefix="/conversation", tags=["conversation"])
service = ConversationService(SnowflakeGenerator(settings.snowflake_worker_id))


@router.get("/page", response_model=PagedResp[ConversationResp])
def page_conversations(
    page_no: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> PagedResp[ConversationResp]:
    data, total = service.page_conversations(
        db, user_id=req_ctx.user_id, page_no=page_no, page_size=page_size
    )
    return PagedResp(data=data, total=total)


@router.post("", response_model=Resp[ConversationResp])
def create_conversation(
    req: ConversationCreateReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[ConversationResp]:
    return Resp(data=service.create_conversation(db, req, req_ctx))


@router.get("/{conversation_id}", response_model=Resp[ConversationResp])
def get_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[ConversationResp]:
    return Resp(data=service.get_conversation(db, conversation_id, req_ctx.user_id))


@router.put("/{conversation_id}", response_model=Resp[ConversationResp])
def update_conversation(
    conversation_id: int,
    req: ConversationUpdateReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[ConversationResp]:
    return Resp(data=service.update_conversation(db, conversation_id, req, req_ctx))


@router.delete("/{conversation_id}", response_model=Resp[bool])
async def delete_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[bool]:
    await service.delete_conversation(db, conversation_id, req_ctx.user_id)
    return Resp(data=True)


@router.post("/{conversation_id}/reset", response_model=Resp[bool])
async def reset_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[bool]:
    """清空该会话的运行态（checkpoint），业务消息和反馈保留。"""
    await service.reset_conversation(db, conversation_id, req_ctx.user_id, req_ctx)
    return Resp(data=True)


@router.post("/admin/purge", response_model=Resp[int])
async def purge_expired_checkpoints(
    ttl_days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
    _: RequestContext = Depends(build_request_context),
) -> Resp[int]:
    """运维端点：扫描长时间未更新会话清理其 checkpoint，返回清理数。

    暂用 update_time inactivity 作为触发条件，会话归档状态机落地后切换。
    """
    count = await service.purge_expired_checkpoints(db, ttl_days=ttl_days)
    return Resp(data=count)


@router.get(
    "/{conversation_id}/message",
    response_model=Resp[list[ConversationMessageResp]],
)
def list_messages(
    conversation_id: int,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[list[ConversationMessageResp]]:
    return Resp(data=service.list_messages(db, conversation_id, req_ctx.user_id))


@router.post("/{conversation_id}/message/stream")
async def send_message_stream(
    conversation_id: int,
    req: SendMessageReq,
    req_ctx: RequestContext = Depends(build_request_context),
) -> StreamingResponse:
    db = SessionLocal()
    try:
        generator = service.send_message_stream(db, conversation_id, req.content, req_ctx)
    except Exception:
        db.close()
        raise
    return sse_response(generator)
