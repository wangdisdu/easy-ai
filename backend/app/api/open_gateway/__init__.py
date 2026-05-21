"""对外 API 网关 /open/v1/*。

与管理 API /api/v1/integration 的两个区别:
- 不走全局 ServiceError → HTTP 200 + code 契约,改用标准 HTTP 4xx/5xx
- 不走 require_authenticated_user(JWT),按 Bearer API Key 鉴权

详见 docs/application-integration-design.md §10.2、§13。
"""

from app.api.open_gateway.handlers import register_open_gateway_handlers
from app.api.open_gateway.invoke import router as open_gateway_router

__all__ = ["open_gateway_router", "register_open_gateway_handlers"]
