"""技能市场 service(占位实现)。

当前为 stub:settings.skill_market_url 未配置时一律返回空 / 抛错。
未来接入真实 registry 时只需在此处加 _fetch_remote 即可,API 层不动。
"""

from app.core.config import settings
from app.core.error_code import ErrorCode
from app.core.exceptions import ServiceError
from app.core.request_context import RequestContext
from app.model.skill_market_model import (
    MarketInstallReq,
    MarketSearchResp,
    MarketSkillResp,
    MarketTranslateReq,
    MarketTranslateResp,
)
from app.model.skill_model import SkillResp

NOT_CONFIGURED_MSG = (
    "技能市场数据源未配置(settings.skill_market_url 为空);请联系管理员"
    "在 .env 中设置 SKILL_MARKET_URL 指向一个 registry"
)


class SkillMarketService:
    def _ensure_configured(self) -> None:
        if not settings.skill_market_url:
            raise ServiceError(ErrorCode.SKILL_MARKET_NOT_CONFIGURED, NOT_CONFIGURED_MSG)

    def search(self, q: str | None) -> MarketSearchResp:
        """搜索市场技能。

        未配置时返回 configured=False + 友好 message,而不是抛错 —
        因为搜索是市场首屏的默认操作,前端应当能优雅地展示空态而非错误弹窗。
        """
        _ = q  # 未配置时关键字无意义
        if not settings.skill_market_url:
            return MarketSearchResp(items=[], configured=False, message=NOT_CONFIGURED_MSG)
        # TODO: 真实接入时,在此发起 HTTP 请求并解析返回。
        return MarketSearchResp(items=[], configured=True)

    def inspect(self, slug: str) -> MarketSkillResp:
        """查询单个技能详情(含操作手册 + 捆绑文件)。"""
        self._ensure_configured()
        # TODO: 真实接入时,在此抓 README + 下载 .zip 列文件。
        raise ServiceError(ErrorCode.DATA_NOT_FOUND, f"skill '{slug}' not found in registry")

    def translate(self, req: MarketTranslateReq) -> MarketTranslateResp:
        """翻译技能英文描述为中文。

        当前为占位:直接 echo;真实接入时走 LiteLLM gateway。
        """
        _ = req
        raise ServiceError(
            ErrorCode.SKILL_MARKET_NOT_CONFIGURED,
            "翻译服务未配置;请联系管理员",
        )

    def install(self, req: MarketInstallReq, req_ctx: RequestContext) -> SkillResp:
        """从市场安装技能为本地可编辑副本。"""
        _ = req
        _ = req_ctx
        self._ensure_configured()
        # TODO: 真实接入时:1) 下载技能 zip;2) 走 SkillService.create_skill_from_zip;
        # 3) 应用 visibility 字段(待 visibility 后端支持落地后再启用)。
        raise ServiceError(
            ErrorCode.SKILL_MARKET_NOT_CONFIGURED,
            f"安装流程未实现(slug={req.slug});数据源未配置",
        )
