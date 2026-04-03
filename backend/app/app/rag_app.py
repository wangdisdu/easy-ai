from __future__ import annotations

from sqlalchemy.orm import Session

from app.app.app_runtime import AppRuntime
from app.core.request_context import RequestContext
from app.model.open_model import (
    LiteLLMChatRequest,
    ModelGatewayChatMessage,
    ModelGatewayResponse,
    RagRunRequest,
)
from app.service.model_gateway_service import ModelGatewayService


class RagApp:
    """RAG 运行时骨架，后续补充检索、重排、总结链路。"""

    def __init__(
        self,
        app_runtime: AppRuntime | None = None,
        model_gateway_service: ModelGatewayService | None = None,
    ) -> None:
        self._app_runtime = app_runtime or AppRuntime()
        self._model_gateway_service = model_gateway_service or ModelGatewayService()

    def run(
        self,
        db: Session,
        req: RagRunRequest,
        req_ctx: RequestContext,
        *,
        request_type: str = "api",
    ) -> ModelGatewayResponse:
        runtime_config = self._app_runtime.build_chat_runtime(db=db, app_id=req.app_id)
        gateway_req = LiteLLMChatRequest(
            messages=[ModelGatewayChatMessage(role="user", content=req.query)],
            runtime_config=runtime_config,
        )
        return self._model_gateway_service.chat_completion(
            db=db,
            req=gateway_req,
            req_ctx=req_ctx,
            app_id=req.app_id,
            app_type="rag",
            request_type=request_type,
        )
