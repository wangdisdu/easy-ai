"""技能市场数据模型。

当前后端实现为占位:settings.skill_market_url 未配置时,所有列表型端点
返回空,详情/安装抛 SKILL_MARKET_NOT_CONFIGURED。

未来真实接入(GitHub registry / 内置 starter pack / 内部 S3)时,
此模型层不需要改动 — 只需在 SkillMarketService 里替换实现即可。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class MarketFileResp(BaseModel):
    """市场详情里的捆绑文件预览(可选,用于详情抽屉展示)。"""

    rel_path: str
    kind: str
    content: str | None = None
    size: int = 0
    binary: bool = False


class MarketSkillResp(BaseModel):
    """市场列表 / 详情共用的技能元数据。"""

    slug: str = Field(min_length=1, max_length=255)
    name: str
    description: str | None = None
    emoji: str | None = None
    version: str | None = None
    author: str | None = None
    homepage: str | None = None
    # 仅详情返回:操作手册 markdown 全文
    instruction: str | None = None
    # 仅详情返回:捆绑文件预览
    files: list[MarketFileResp] = Field(default_factory=list)
    # 仅详情返回:统计 / 平台 / 更新日志(都是可选,留前端展示)
    stars: int | None = None
    downloads: int | None = None
    platforms: list[str] = Field(default_factory=list)
    changelog: str | None = None
    # 详情加载完整内容失败时,前端可显示警告 banner
    content_loaded: bool = True


class MarketSearchResp(BaseModel):
    """搜索响应:items + 是否已配置数据源(供前端决定空态文案)。"""

    items: list[MarketSkillResp] = Field(default_factory=list)
    configured: bool = False
    # 未配置时返回固定提示;前端可直接展示
    message: str | None = None


class MarketTranslateReq(BaseModel):
    text: str = Field(min_length=1, max_length=8000)


class MarketTranslateResp(BaseModel):
    text: str


class MarketInstallReq(BaseModel):
    slug: str = Field(min_length=1, max_length=255)
    visibility: str = Field(default="group", pattern=r"^(group|system)$")
    # 留空则用包内 name
    skill_name: str | None = Field(default=None, max_length=64)
