from __future__ import annotations

import time
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.error_code import ErrorCode
from app.core.exceptions import ServiceError
from app.core.request_context import RequestContext
from app.core.snowflake import SnowflakeGenerator
from app.model.open_model import (
    GatewayHealthResp,
    LiteLLMChatRequest,
    LiteLLMEmbeddingRequest,
    LiteLLMRerankRequest,
    ModelGatewayResponse,
)
from app.service.app_log_service import AppLogService


class ModelGatewayService:
    """LiteLLM 网关访问封装，并统一写入调用日志。"""

    def __init__(
        self,
        timeout: float = 60.0,
        log_service: AppLogService | None = None,
    ) -> None:
        self._timeout = timeout
        self._log_service = log_service or AppLogService(
            SnowflakeGenerator(settings.snowflake_worker_id)
        )

    def health_check(
        self,
        db: Session,
        req_ctx: RequestContext,
    ) -> GatewayHealthResp:
        started_at = time.perf_counter()
        request_payload: dict[str, Any] = {"base_url": self.default_base_url()}
        response_payload: dict[str, Any] | None = None
        response_status: int | None = None
        error_message: str | None = None

        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.get(
                    f"{self.default_base_url()}/models",
                    headers=self._build_headers(),
                )
            response_status = response.status_code
            if response.status_code >= 400:
                raise ServiceError(
                    ErrorCode.INTERNAL_ERROR,
                    f"litellm health check failed: status={response.status_code}",
                )
            payload = response.json()
            if not isinstance(payload, dict):
                raise ServiceError(
                    ErrorCode.INTERNAL_ERROR,
                    "litellm health response payload invalid",
                )
            response_payload = payload
            models = payload.get("data")
            models_count = len(models) if isinstance(models, list) else 0
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            self._log_service.create_log(
                db,
                app_id=None,
                app_type=None,
                provider_id=None,
                model_id=None,
                model=None,
                request_type="health_check",
                request_payload=request_payload,
                response_payload=response_payload,
                success=True,
                response_status=response_status,
                latency_ms=latency_ms,
                error_message=None,
                now=req_ctx.request_time_ms,
                user_id=req_ctx.user_id,
            )
            return GatewayHealthResp(
                status="ok",
                gateway_url=self.default_base_url(),
                latency_ms=latency_ms,
                models_count=models_count,
            )
        except Exception as exc:
            error_message = str(exc)
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            self._log_service.create_log(
                db,
                app_id=None,
                app_type=None,
                provider_id=None,
                model_id=None,
                model=None,
                request_type="health_check",
                request_payload=request_payload,
                response_payload=response_payload,
                success=False,
                response_status=response_status,
                latency_ms=latency_ms,
                error_message=error_message,
                now=req_ctx.request_time_ms,
                user_id=req_ctx.user_id,
            )
            return GatewayHealthResp(
                status="error",
                gateway_url=self.default_base_url(),
                latency_ms=latency_ms,
                error_message=error_message,
            )

    def chat_completion(
        self,
        db: Session,
        req: LiteLLMChatRequest,
        req_ctx: RequestContext,
        *,
        app_id: int | None = None,
        app_type: str | None = None,
        request_type: str = "chat_completion",
    ) -> ModelGatewayResponse:
        payload: dict[str, Any] = {
            "model": req.runtime_config.model,
            "messages": [message.model_dump() for message in req.messages],
        }
        payload.update(req.runtime_config.model_setting)
        payload.update(req.extra_body)
        return self._post_and_log(
            db=db,
            req_ctx=req_ctx,
            path="/chat/completions",
            payload=payload,
            base_url=req.runtime_config.base_url,
            api_key=req.runtime_config.api_key,
            app_id=app_id,
            app_type=app_type,
            provider_id=req.runtime_config.provider_id,
            model_id=req.runtime_config.model_id,
            model=req.runtime_config.model,
            request_type=request_type,
        )

    def embedding(
        self,
        db: Session,
        req: LiteLLMEmbeddingRequest,
        req_ctx: RequestContext,
        *,
        app_id: int | None = None,
        app_type: str | None = None,
        request_type: str = "embedding",
    ) -> ModelGatewayResponse:
        payload: dict[str, Any] = {
            "model": req.runtime_config.model,
            "input": req.input,
        }
        payload.update(req.runtime_config.model_setting)
        payload.update(req.extra_body)
        return self._post_and_log(
            db=db,
            req_ctx=req_ctx,
            path="/embeddings",
            payload=payload,
            base_url=req.runtime_config.base_url,
            api_key=req.runtime_config.api_key,
            app_id=app_id,
            app_type=app_type,
            provider_id=req.runtime_config.provider_id,
            model_id=req.runtime_config.model_id,
            model=req.runtime_config.model,
            request_type=request_type,
        )

    def rerank(
        self,
        db: Session,
        req: LiteLLMRerankRequest,
        req_ctx: RequestContext,
        *,
        app_id: int | None = None,
        app_type: str | None = None,
        request_type: str = "rerank",
    ) -> ModelGatewayResponse:
        payload: dict[str, Any] = {
            "model": req.runtime_config.model,
            "query": req.query,
            "documents": req.documents,
        }
        if req.top_n is not None:
            payload["top_n"] = req.top_n
        payload.update(req.runtime_config.model_setting)
        payload.update(req.extra_body)
        return self._post_and_log(
            db=db,
            req_ctx=req_ctx,
            path="/rerank",
            payload=payload,
            base_url=req.runtime_config.base_url,
            api_key=req.runtime_config.api_key,
            app_id=app_id,
            app_type=app_type,
            provider_id=req.runtime_config.provider_id,
            model_id=req.runtime_config.model_id,
            model=req.runtime_config.model,
            request_type=request_type,
        )

    def default_base_url(self) -> str:
        return settings.litellm_gateway_url.rstrip("/")

    def _post_and_log(
        self,
        *,
        db: Session,
        req_ctx: RequestContext,
        path: str,
        payload: dict[str, Any],
        base_url: str | None,
        api_key: str | None,
        app_id: int | None,
        app_type: str | None,
        provider_id: int | None,
        model_id: int | None,
        model: str | None,
        request_type: str,
    ) -> ModelGatewayResponse:
        started_at = time.perf_counter()
        response_status: int | None = None
        response_payload: dict[str, Any] | None = None
        final_base_url = (base_url or self.default_base_url()).rstrip("/")

        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(
                    f"{final_base_url}{path}",
                    json=payload,
                    headers=self._build_headers(api_key),
                )
            response_status = response.status_code
            if response.status_code >= 400:
                error_detail = (
                    "litellm request failed: "
                    f"status={response.status_code}, "
                    f"body={self._truncate(response.text)}"
                )
                raise ServiceError(
                    ErrorCode.INTERNAL_ERROR,
                    error_detail,
                )
            response_payload = response.json()
            if not isinstance(response_payload, dict):
                raise ServiceError(ErrorCode.INTERNAL_ERROR, "litellm response payload invalid")
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            self._log_service.create_log(
                db,
                app_id=app_id,
                app_type=app_type,
                provider_id=provider_id,
                model_id=model_id,
                model=model,
                request_type=request_type,
                request_payload=payload,
                response_payload=response_payload,
                success=True,
                response_status=response_status,
                latency_ms=latency_ms,
                error_message=None,
                now=req_ctx.request_time_ms,
                user_id=req_ctx.user_id,
            )
            return ModelGatewayResponse(
                data=response_payload,
                raw_response=response_payload,
                response_status=response_status,
                latency_ms=latency_ms,
            )
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            self._log_service.create_log(
                db,
                app_id=app_id,
                app_type=app_type,
                provider_id=provider_id,
                model_id=model_id,
                model=model,
                request_type=request_type,
                request_payload=payload,
                response_payload=response_payload,
                success=False,
                response_status=response_status,
                latency_ms=latency_ms,
                error_message=str(exc),
                now=req_ctx.request_time_ms,
                user_id=req_ctx.user_id,
            )
            if isinstance(exc, ServiceError):
                raise
            raise ServiceError(ErrorCode.INTERNAL_ERROR, f"litellm request failed: {exc}") from exc

    def _build_headers(self, api_key: str | None = None) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        final_api_key = api_key if api_key is not None else settings.litellm_gateway_key
        if final_api_key:
            headers["Authorization"] = f"Bearer {final_api_key}"
        return headers

    def _truncate(self, value: str, limit: int = 400) -> str:
        if len(value) <= limit:
            return value
        return f"{value[:limit]}..."
